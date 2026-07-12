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

# --- YOUR TARIFF SETTINGS ---
# Adjust these values based on your bill (in $/kWh)
# E.g., Off-Peak might have lower network charges, Peak has high charges.
PEAK_PREMIUM = 0.45 
OFF_PEAK_PREMIUM = 0.15

def get_retail_premium(dt):
    """
    Apply logic based on Brisbane QLD Tariff windows.
    Modify the '16' (4 PM) and '20' (8 PM) to match your peak window.
    """
    # Peak window: 4 PM (16:00) to 8 PM (20:00)
    if 16 <= dt.hour < 20:
        return PEAK_PREMIUM
    else:
        return OFF_PEAK_PREMIUM

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
                            # Parse AEMO time format (YYYY/MM/DD HH:MM:SS)
                            time_str = row_dict.get('DATETIME') or row_dict.get('SETTLEMENTDATE')
                            dt = datetime.strptime(time_str, '%Y/%m/%d %H:%M:%S')
                            
                            # Wholesale price (converted to $/kWh)
                            wholesale_price = float(row_dict.get('RRP', 0)) / 1000
                            
                            # Add dynamic retail premium
                            final_price = wholesale_price + get_retail_premium(dt)
                            
                            forecast_data.append({
                                "datetime": time_str,
                                "region": row_dict.get('REGIONID'),
                                "price": round(final_price, 4)
                            })

        if forecast_data:
            requests.post(GOOGLE_SHEETS_WEBHOOK_URL, json=forecast_data, allow_redirects=True)
            print("Successfully pushed data with TOU tariff logic.")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    fetch_aemo_forecast()
