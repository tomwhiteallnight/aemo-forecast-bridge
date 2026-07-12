import requests
import re
import zipfile
import io
import csv
import json
import os
from urllib.parse import urljoin

GOOGLE_SHEETS_WEBHOOK_URL = os.environ.get("GOOGLE_WEBHOOK_URL")
TARGET_REGION = "QLD1"

# Adjust this number to match your retail rate premium (in $/kWh)
# Example: If you pay 30c/kWh flat, set this to 0.25 (as a rough estimate for non-spot costs)
RETAIL_PREMIUM_PER_KWH = 0.25 

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
                            # 1. Convert MWh to kWh (/1000)
                            # 2. Add your Retail Premium to make it look like your bill
                            raw_price = float(row_dict.get('RRP', 0)) / 1000
                            final_price = raw_price + RETAIL_PREMIUM_PREMIUM_PER_KWH
                            
                            forecast_data.append({
                                "datetime": row_dict.get('DATETIME') or row_dict.get('SETTLEMENTDATE'),
                                "region": row_dict.get('REGIONID'),
                                "price": round(final_price, 4)
                            })

        if forecast_data:
            requests.post(GOOGLE_SHEETS_WEBHOOK_URL, json=forecast_data, allow_redirects=True)
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    fetch_aemo_forecast()
