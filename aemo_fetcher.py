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

def get_retail_premium(dt):
    hour = dt.hour
    if 16 <= hour < 21: return 0.50 # Peak
    elif 11 <= hour < 16: return 0.05 # Solar Soak
    else: return 0.20 # Shoulder

def fetch_aemo_data(report_type):
    # Forecast uses PredispatchIS, Actuals uses DispatchIS
    if report_type == "forecast":
        base_url = "https://nemweb.com.au/Reports/Current/PredispatchIS_Reports/"
        pattern = "PUBLIC_PREDISPATCHIS"
    else:
        # Broadening search for actuals
        base_url = "https://nemweb.com.au/Reports/Current/DispatchIS_Reports/"
        pattern = "PUBLIC_DISPATCH" # Broadened from PUBLIC_DISPATCHPRICE to capture variations

    headers = {'User-Agent': 'Mozilla/5.0'}
    
    response = requests.get(base_url, headers=headers)
    all_files = re.findall(r'href="([^"]+\.zip)"', response.text, re.IGNORECASE)
    
    # Filter for relevant files
    target_files = sorted([f for f in all_files if pattern in f.upper()])
    
    if not target_files:
        print(f"CRITICAL: No files found for {report_type} using pattern '{pattern}'")
        print(f"DEBUG: Here are the first 10 files available in {base_url}:")
        print(all_files[:10]) 
        return []
            
    # Get the last 5 files to be safe
    selected_files = target_files[-5:]
    data = []
    
    for selected_file in selected_files:
        zip_url = urljoin(base_url, selected_file)
        try:
            zip_response = requests.get(zip_url, headers=headers)
            with zipfile.ZipFile(io.BytesIO(zip_response.content)) as z:
                csv_files = [f for f in z.namelist() if f.lower().endswith('.csv')]
                for csv_filename in csv_files:
                    with z.open(csv_filename) as f:
                        lines = f.read().decode('utf-8', errors='ignore').splitlines()
                        reader = csv.reader(lines)
                        headers, target_table = [], None
                        for row in reader:
                            if not row: continue
                            if row[0] == 'I' and 'RRP' in row and 'REGIONID' in row:
                                headers, target_table = row, row[2]
                            elif row[0] == 'D' and target_table and row[2] == target_table:
                                row_dict = dict(zip(headers, row))
                                if row_dict.get('REGIONID') == TARGET_REGION:
                                    time_str = row_dict.get('DATETIME') or row_dict.get('SETTLEMENTDATE')
                                    try:
                                        dt = datetime.strptime(time_str, '%Y/%m/%d %H:%M:%S')
                                        price = float(row_dict.get('RRP', 0)) / 1000
                                        final_price = price + get_retail_premium(dt)
                                        data.append({"datetime": time_str, "region": TARGET_REGION, "price": round(final_price, 4)})
                                    except: continue
        except Exception as e:
            print(f"Error processing {selected_file}: {e}")
            
    return data

if __name__ == "__main__":
    forecast = fetch_aemo_data("forecast")
    actuals = fetch_aemo_data("actuals")
    
    payload = {"type": "combined", "forecast": forecast, "actuals": actuals}
    requests.post(GOOGLE_SHEETS_WEBHOOK_URL, json=payload, allow_redirects=True)
    print(f"Push complete. Forecast rows: {len(forecast)}, Actuals rows: {len(actuals)}")
