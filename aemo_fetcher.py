import requests
import re
import zipfile
import io
import csv
import os
from urllib.parse import urljoin

GOOGLE_WEBHOOK_URL = os.environ.get("GOOGLE_WEBHOOK_URL")
TARGET_REGION = "QLD1"

def get_retail_premium(hour):
    if 16 <= hour < 21: return 0.50
    elif 11 <= hour < 16: return 0.05
    else: return 0.20

def scan_csv_for_price(content):
    """Scan CSV content for the Regional RRP."""
    data = []
    lines = content.splitlines()
    reader = csv.reader(lines)
    
    headers = []
    for row in reader:
        if not row: continue
        # Capture header row: Looking for RRP and RegionID
        if row[0] == 'I':
            if 'RRP' in row and 'REGIONID' in row:
                headers = row
                continue
        # Capture data row: Look for QLD1
        elif row[0] == 'D' and headers:
            row_dict = dict(zip(headers, row))
            if row_dict.get('REGIONID') == TARGET_REGION:
                try:
                    dt_str = row_dict.get('SETTLEMENTDATE') or row_dict.get('DATETIME')
                    hour = int(dt_str.split(' ')[1].split(':')[0])
                    # Ensure we have a valid price
                    rrp = float(row_dict.get('RRP', 0)) / 1000
                    data.append({
                        "datetime": dt_str, 
                        "region": "QLD1", 
                        "price": round(rrp + get_retail_premium(hour), 4)
                    })
                except Exception: continue
    return data

def fetch_data(base_url, pattern):
    print(f"DEBUG: Scanning {base_url} for {pattern}")
    try:
        response = requests.get(base_url, headers={'User-Agent': 'Mozilla/5.0'})
        files = re.findall(r'href="([^"]+\.zip)"', response.text, re.IGNORECASE)
        # Sort by latest
        target_files = sorted([f for f in files if pattern in f.upper()])[-3:]
        
        all_data = []
        for file in target_files:
            r = requests.get(urljoin(base_url, file))
            with zipfile.ZipFile(io.BytesIO(r.content)) as z:
                for name in [n for n in z.namelist() if n.endswith('.csv')]:
                    with z.open(name) as f:
                        all_data.extend(scan_csv_for_price(f.read().decode('utf-8', errors='ignore')))
        return all_data
    except Exception as e:
        print(f"DEBUG: Error: {e}")
        return []

if __name__ == "__main__":
    # Updated: Pointing to the correct "Dispatch_Reports" folder
    forecast = fetch_data("https://nemweb.com.au/Reports/Current/Predispatch_Reports/", "PUBLIC_PREDISPATCHPRICE")
    actuals = fetch_data("https://nemweb.com.au/Reports/Current/Dispatch_Reports/", "PUBLIC_DISPATCHPRICE")
    
    print(f"DEBUG: Found {len(forecast)} forecast and {len(actuals)} actuals.")
    
    if GOOGLE_WEBHOOK_URL:
        requests.post(GOOGLE_WEBHOOK_URL, json={"forecast": forecast, "actuals": actuals})
