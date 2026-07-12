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
    if report_type == "forecast":
        base_url = "https://nemweb.com.au/Reports/Current/PredispatchIS_Reports/"
        pattern = "PUBLIC_PREDISPATCHIS"
        target_table_name = "PREDISPATCHPRICE" # We want the price table
    else:
        base_url = "https://nemweb.com.au/Reports/Current/DispatchIS_Reports/"
        pattern = "PUBLIC_DISPATCHIS"
        target_table_name = "DISPATCHPRICE" # We want the price table

    headers = {'User-Agent': 'Mozilla/5.0'}
    
    try:
        response = requests.get(base_url, headers=headers)
        all_files = re.findall(r'href="([^"]+\.zip)"', response.text, re.IGNORECASE)
        target_files = sorted([f for f in all_files if pattern in f.upper()])
        
        if not target_files: return []
            
        # Get the last 5 files to get enough history
        selected_files = target_files[-5:]
        data = []
        
        for selected_file in selected_files:
            zip_url = urljoin(base_url, selected_file)
            zip_response = requests.get(zip_url, headers=headers)
            
            with zipfile.ZipFile(io.BytesIO(zip_response.content)) as z:
                for csv_filename in [f for f in z.namelist() if f.lower().endswith('.csv')]:
                    with z.open(csv_filename) as f:
                        lines = f.read().decode('utf-8', errors='ignore').splitlines()
                        reader = csv.reader(lines)
                        
                        headers = []
                        for row in reader:
                            if not row: continue
                            # Look for the specific table name we want
                            if row[0] == 'I' and target_table_name in row:
                                headers = row
                            # Parse data rows
                            elif row[0] == 'D' and headers and row[2] == target_table_name:
                                row_dict = dict(zip(headers, row))
                                if row_dict.get('REGIONID') == TARGET_REGION:
                                    time_str = row_dict.get('SETTLEMENTDATE') or row_dict.get('DATETIME')
                                    try:
                                        dt = datetime.strptime(time_str, '%Y/%m/%d %H:%M:%S')
                                        rrp = float(row_dict.get('RRP', 0)) / 1000
                                        final_price = rrp + get_retail_premium(dt)
                                        data.append({"datetime": time_str, "region": TARGET_REGION, "price": round(final_price, 4)})
                                    except: continue
        return data
    except Exception as e:
        print(f"Error fetching {report_type}: {e}")
        return []

if __name__ == "__main__":
    forecast_data = fetch_aemo_data("forecast")
    actuals_data = fetch_aemo_data("actuals")
    
    payload = {"type": "combined", "forecast": forecast_data, "actuals": actuals_data}
    
    if forecast_data or actuals_data:
        requests.post(GOOGLE_SHEETS_WEBHOOK_URL, json=payload, allow_redirects=True)
        print(f"Push complete. Forecast: {len(forecast_data)}, Actuals: {len(actuals_data)}")
