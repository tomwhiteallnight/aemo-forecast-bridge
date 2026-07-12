import requests
import re
import zipfile
import io
import csv
import os
import sys

# --- VERIFY SCRIPT START ---
print("DEBUG: aemo_fetcher.py has started executing.")

GOOGLE_SHEETS_WEBHOOK_URL = os.environ.get("GOOGLE_WEBHOOK_URL")
if not GOOGLE_SHEETS_WEBHOOK_URL:
    print("CRITICAL: GOOGLE_WEBHOOK_URL environment variable is missing!")
    sys.exit(1)

TARGET_REGION = "QLD1"

def fetch_data(url, pattern):
    print(f"DEBUG: Accessing {url}")
    response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
    all_files = re.findall(r'href="([^"]+\.zip)"', response.text, re.IGNORECASE)
    print(f"DEBUG: Found {len(all_files)} files total.")
    
    target_files = [f for f in all_files if pattern in f.upper()]
    print(f"DEBUG: Found {len(target_files)} files matching pattern '{pattern}'")
    
    if not target_files:
        return []
        
    # Get the last 1 file
    selected_file = target_files[-1]
    print(f"DEBUG: Downloading {selected_file}")
    
    zip_url = urljoin(url, selected_file)
    r = requests.get(zip_url)
    
    data = []
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        for name in z.namelist():
            if name.endswith('.csv'):
                print(f"DEBUG: Reading {name}")
                with z.open(name) as f:
                    # Just reading the first 50 lines to find QLD1
                    content = f.read().decode('utf-8', errors='ignore')
                    if 'QLD1' in content:
                        print(f"DEBUG: SUCCESS - QLD1 found in {name}")
                        data.append({"datetime": "Found", "region": "QLD1", "price": 0.0})
    return data

if __name__ == "__main__":
    print("DEBUG: Starting AEMO Fetch...")
    forecast = fetch_data("https://nemweb.com.au/Reports/Current/PredispatchIS_Reports/", "PUBLIC_PREDISPATCHIS")
    actuals = fetch_data("https://nemweb.com.au/Reports/Current/DispatchIS_Reports/", "PUBLIC_DISPATCHIS")
    
    print(f"DEBUG: Collection complete. Forecast: {len(forecast)}, Actuals: {len(actuals)}")
    
    payload = {"type": "combined", "forecast": forecast, "actuals": actuals}
    resp = requests.post(GOOGLE_SHEETS_WEBHOOK_URL, json=payload)
    print(f"DEBUG: Webhook response: {resp.status_code}")
