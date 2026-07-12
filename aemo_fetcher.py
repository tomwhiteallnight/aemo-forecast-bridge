import requests
import re
import zipfile
import io
import csv
import json
import os
from urllib.parse import urljoin
from datetime import datetime

GOOGLE_SHEETS_WEBHOOK_URL = os.environ.get("GOOGLE_WEBHOOK_URL")
TARGET_REGION = "QLD1"

# --- TARIFF 6900 SETTINGS ---
# Adjust these "Premium" values to represent the cost your retailer adds 
# to the wholesale price for each specific time window.
PEAK_PREMIUM = 0.50      # 4pm - 9pm
OFF_PEAK_PREMIUM = 0.05  # 11am - 4pm (Solar soak)
SHOULDER_PREMIUM = 0.20  # 9pm - 11am

def get_retail_premium(dt):
    """
    Logic for Energex Tariff 6900 (Solar Sponge).
    """
    hour = dt.hour
    
    # Peak: 4pm - 9pm (16:00 - 21:00)
    if 16 <= hour < 21:
        return PEAK_PREMIUM
    
    # Off-Peak (Solar Soak): 11am - 4pm (11:00 - 16:00)
    elif 11 <= hour < 16:
        return OFF_PEAK_PREMIUM
    
    # Shoulder: All other times (21:00 - 11:00)
    else:
        return SHOULDER_PREMIUM

def fetch_aemo_forecast():
    base_url = "https://nemweb.com.au/Reports/Current/PredispatchIS_Reports/"
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    try:
        response = requests.get(base_url, headers=headers)
        response.raise_for_status()
        html = response.text
        
        zip_files = re.findall(r'href="([^"]+\.zip)"', html, re.IGNORECASE)
        if not zip_files: return
        
        latest_zip_filename = sorted(zip_files)[-1]
        zip_url = urljoin(base_url, latest_zip_filename)
        zip_response = requests.get(zip_url, headers=headers)
        
        forecast_data = []
        with zipfile.ZipFile(io.BytesIO(zip_response.content)) as z:
            csv_filename = z.namelist()[0]
            with z.open(csv_filename) as f:
                reader = csv.reader(line.decode('utf-8') for line in f.readlines())
                headers = []
                target_table = None
                
                for row in reader:
                    if not row: continue
                    if row[0] == 'I' and 'RRP' in row and 'REGIONID' in row:
                        headers = row
                        target_table = row[2]
                    elif row[0] == 'D' and target_table and row[2] == target_table:
                        row_dict = dict(zip(headers, row))
                        if row_dict.get('REGIONID') == TARGET_REGION:
                            time_str = row_dict.get('DATETIME') or row_dict.get('SETTLEMENTDATE')
                            dt = datetime.strptime(time_str, '%Y/%m/%d %H:%M:%S')
                            
                            # Wholesale price (converted to $/kWh)
                            wholesale_price = float(row_dict.get('RRP', 0)) / 1000
                            
                            # Apply Tariff 6900 logic
                            final_price = wholesale_price + get_retail_premium(dt)
                            
                            forecast_data.append({
                                "datetime": time_str,
                                "region": row_dict.get('REGIONID'),
                                "price": round(final_price, 4)
                            })

        if forecast_data:
            requests.post(GOOGLE_SHEETS_WEBHOOK_URL, json=forecast_data, allow_redirects=True)
            print("Successfully updated with Tariff 6900 logic.")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    fetch_aemo_forecast()
