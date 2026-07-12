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
    else:
        base_url = "https://nemweb.com.au/Reports/Current/DispatchIS_Reports/"
        pattern = "PUBLIC_DISPATCH" # Catch-all

    headers = {'User-Agent': 'Mozilla/5.0'}
    
    try:
        response = requests.get(base_url, headers=headers)
        all_files = re.findall(r'href="([^"]+\.zip)"', response.text, re.IGNORECASE)
        target_files = sorted([f for f in all_files if pattern in f.upper()])
        
        if not target_files: return []
            
        # Check last 3 files
        selected_files = target_files[-3:]
        data = []
        
        for selected_file in selected_files:
            zip_url = urljoin(base_url, selected_file)
            zip_response = requests.get(zip_url, headers=headers)
            
            with zipfile.ZipFile(io.BytesIO(zip_response.content)) as z:
                for csv_filename in [f for f in z.namelist() if f.lower().endswith('.csv')]:
                    with z.open(csv_filename) as f:
                        lines = f.read().decode('utf-8', errors='ignore').splitlines()
                        # --- DIAGNOSTIC PRINT ---
                        print(f"DEBUG: File {csv_filename} snippet (first 5 rows):")
                        for i, line in enumerate(lines[:5]):
                            print(f"  Line {i}: {line}")
                        # -------------------------
                        
                        reader = csv.reader(lines)
                        for row in reader:
                            if not row: continue
                            # Logic: If row is a data row and contains QLD1, append it
                            # We are searching for 'QLD1' anywhere in the row if specific column logic fails
                            if 'QLD1' in row:
                                data.append({"datetime": "DEBUG", "region": "QLD1", "price": 0.0})
        
        return data
    except Exception as e:
        print(f"Error: {e}")
        return []

if __name__ == "__main__":
    forecast_data = fetch_aemo_data("forecast")
    actuals_data = fetch_aemo_data("actuals")
    
    # Send whatever we found to the webhook
    payload = {"type": "combined", "forecast": forecast_data, "actuals": actuals_data}
    requests.post(GOOGLE_SHEETS_WEBHOOK_URL, json=payload, allow_redirects=True)
    print(f"Push complete. Actuals row count found in search: {len(actuals_data)}")
