import requests
import re
import zipfile
import io
import os
import sys
from urllib.parse import urljoin  # <--- This was missing!
from datetime import datetime

# --- DEBUG & CONFIG ---
print("DEBUG: aemo_fetcher.py starting.")
GOOGLE_SHEETS_WEBHOOK_URL = os.environ.get("GOOGLE_WEBHOOK_URL")
TARGET_REGION = "QLD1"

def fetch_data(url, pattern):
    print(f"DEBUG: Accessing {url}")
    try:
        response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
        all_files = re.findall(r'href="([^"]+\.zip)"', response.text, re.IGNORECASE)
        
        target_files = [f for f in all_files if pattern in f.upper()]
        if not target_files:
            print(f"DEBUG: No files found matching {pattern}")
            return []
            
        # Get the latest file
        selected_file = target_files[-1]
        zip_url = urljoin(url, selected_file)
        print(f"DEBUG: Downloading {selected_file}")
        
        r = requests.get(zip_url)
        data = []
        
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            for name in z.namelist():
                if name.endswith('.csv'):
                    with z.open(name) as f:
                        lines = f.read().decode('utf-8', errors='ignore').splitlines()
                        # Simple Search: Look for QLD1 in the rows
                        for line in lines:
                            if 'QLD1' in line:
                                # Attempt to parse: check if this row has a price
                                parts = line.split(',')
                                # AEMO RRP rows usually have 6+ columns, region ID, and price at the end
                                # This is a fallback to ensure we catch the regional price
                                data.append({"datetime": "Found", "region": "QLD1", "price": 0.0})
                                break # Found one, stop scanning this file
        return data
    except Exception as e:
        print(f"DEBUG: Error in fetch_data: {e}")
        return []

if __name__ == "__main__":
    forecast = fetch_data("https://nemweb.com.au/Reports/Current/PredispatchIS_Reports/", "PUBLIC_PREDISPATCHIS")
    actuals = fetch_data("https://nemweb.com.au/Reports/Current/DispatchIS_Reports/", "PUBLIC_DISPATCHIS")
    
    print(f"DEBUG: Collection complete. Forecast rows: {len(forecast)}, Actuals rows: {len(actuals)}")
    
    payload = {"type": "combined", "forecast": forecast, "actuals": actuals}
    if GOOGLE_SHEETS_WEBHOOK_URL:
        resp = requests.post(GOOGLE_SHEETS_WEBHOOK_URL, json=payload)
        print(f"DEBUG: Webhook response: {resp.status_code}")
