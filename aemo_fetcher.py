import requests
import re
import zipfile
import io
import csv
import os
import sys
from urllib.parse import urljoin

GOOGLE_WEBHOOK_URL = os.environ.get("GOOGLE_WEBHOOK_URL")
TARGET_REGION = "QLD1"

def get_retail_premium(hour):
    if 16 <= hour < 21: return 0.50
    elif 11 <= hour < 16: return 0.05
    else: return 0.20

def scan_csv_for_data(content):
    """Deep scan: find columns dynamically."""
    data = []
    lines = content.splitlines()
    reader = csv.reader(lines)
    
    headers = []
    for row in reader:
        if not row: continue
        # Find headers dynamically
        if row[0] == 'I' and 'REGIONID' in row and 'RRP' in row:
            headers = row
            continue
        # Find data
        if row[0] == 'D' and headers:
            row_dict = dict(zip(headers, row))
            if row_dict.get('REGIONID') == TARGET_REGION:
                try:
                    dt_str = row_dict.get('SETTLEMENTDATE') or row_dict.get('DATETIME')
                    hour = int(dt_str.split(' ')[1].split(':')[0])
                    rrp = float(row_dict.get('RRP', 0)) / 1000
                    data.append({
                        "datetime": dt_str, 
                        "region": "QLD1", 
                        "price": round(rrp + get_retail_premium(hour), 4)
                    })
                except: continue
    return data

def fetch_data(base_url, pattern):
    print(f"DEBUG: Scanning {base_url} for {pattern}")
    try:
        response = requests.get(base_url, headers={'User-Agent': 'Mozilla/5.0'})
        files = re.findall(r'href="([^"]+\.zip)"', response.text, re.IGNORECASE)
        target_files = sorted([f for f in files if pattern in f.upper()])[-3:] # Get last 3
        
        total_found = []
        for file in target_files:
            print(f"DEBUG: Processing {file}")
            r = requests.get(urljoin(base_url, file))
            with zipfile.ZipFile(io.BytesIO(r.content)) as z:
                for name in [n for n in z.namelist() if n.endswith('.csv')]:
                    with z.open(name) as f:
                        file_data = scan_csv_for_data(f.read().decode('utf-8', errors='ignore'))
                        print(f"DEBUG: Found {len(file_data)} rows in {name}")
                        total_found.extend(file_data)
        return total_found
    except Exception as e:
        print(f"DEBUG: Error: {e}")
        return []

if __name__ == "__main__":
    forecast = fetch_data("https://nemweb.com.au/Reports/Current/PredispatchIS_Reports/", "PUBLIC_PREDISPATCHIS")
    actuals = fetch_data("https://nemweb.com.au/Reports/Current/DispatchIS_Reports/", "PUBLIC_DISPATCH")
    
    print(f"DEBUG: Final Count - Forecast: {len(forecast)}, Actuals: {len(actuals)}")
    
    if GOOGLE_WEBHOOK_URL:
        requests.post(GOOGLE_WEBHOOK_URL, json={"forecast": forecast, "actuals": actuals})

