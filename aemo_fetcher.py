import requests
import re
import zipfile
import io
import csv
import json
import os
import traceback
from urllib.parse import urljoin
from datetime import datetime

GOOGLE_SHEETS_WEBHOOK_URL = os.environ.get("GOOGLE_WEBHOOK_URL")
TARGET_REGION = "QLD1"

def get_retail_premium(dt):
    hour = dt.hour
    if 16 <= hour < 21: return 0.50 # Peak
    elif 11 <= hour < 16: return 0.05 # Solar Soak
    else: return 0.20 # Shoulder

def fetch_aemo_data(report_type):
    try:
        if report_type == "forecast":
            base_url = "https://nemweb.com.au/Reports/Current/PredispatchIS_Reports/"
            pattern = "PUBLIC_PREDISPATCHIS"
        else:
            base_url = "https://nemweb.com.au/Reports/Current/DispatchIS_Reports/"
            pattern = "PUBLIC_DISPATCH"

        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(base_url, headers=headers)
        all_files = re.findall(r'href="([^"]+\.zip)"', response.text, re.IGNORECASE)
        target_files = sorted([f for f in all_files if pattern in f.upper()])
        
        if not target_files:
            return []
            
        selected_files = target_files[-2:] # Fetch last 2 to be safe
        data = []
        
        for selected_file in selected_files:
            zip_url = urljoin(base_url, selected_file)
            zip_response = requests.get(zip_url, headers=headers)
            
            with zipfile.ZipFile(io.BytesIO(zip_response.content)) as z:
                for csv_filename in [f for f in z.namelist() if f.lower().endswith('.csv')]:
                    with z.open(csv_filename) as f:
                        lines = f.read().decode('utf-8', errors='ignore').splitlines()
                        reader = csv.reader(lines)
                        
                        csv_headers = []
                        target_table = None
                        
                        for row in reader:
                            if not row: continue
                            # Find Header row
                            if row[0] == 'I' and 'RRP' in row and 'REGIONID' in row:
                                csv_headers = row
                                target_table = row[2]
                            # Find Data row
                            elif row[0] == 'D' and target_table and row[2] == target_table:
                                if len(row) != len(csv_headers): continue
                                row_dict = dict(zip(csv_headers, row))
                                
                                if row_dict.get('REGIONID') == TARGET_REGION:
                                    time_str = row_dict.get('DATETIME') or row_dict.get('SETTLEMENTDATE')
                                    try:
                                        dt = datetime.strptime(time_str, '%Y/%m/%d %H:%M:%S')
                                        price = float(row_dict.get('RRP', 0)) / 1000
                                        final_price = price + get_retail_premium(dt)
                                        data.append({"datetime": time_str, "region": TARGET_REGION, "price": round(final_price, 4)})
                                    except: continue
        return data

    except Exception:
        print(f"CRITICAL ERROR in {report_type}:")
        print(traceback.format_exc())
        return []

if __name__ == "__main__":
    try:
        print("Starting fetch...")
        forecast_data = fetch_aemo_data("forecast")
        actuals_data = fetch_aemo_data("actuals")
        
        payload = {
            "type": "combined", 
            "forecast": forecast_data, 
            "actuals": actuals_data
        }
        
        print(f"Data collected. Sending to webhook. Forecast: {len(forecast_data)}, Actuals: {len(actuals_data)}")
        
        if GOOGLE_SHEETS_WEBHOOK_URL:
            # We explicitly dump to JSON to ensure the format is strictly dictionary-based
            response = requests.post(
                GOOGLE_SHEETS_WEBHOOK_URL, 
                json=payload, 
                headers={'Content-Type': 'application/json'}
            )
            print(f"Response: {response.status_code}")
        else:
            print("No webhook URL configured.")
            
    except Exception:
        print("CRITICAL ERROR in main execution:")
        print(traceback.format_exc())
