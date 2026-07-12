import requests
import re
import zipfile
import io
import os
import sys
from urllib.parse import urljoin

GOOGLE_WEBHOOK_URL = os.environ.get("GOOGLE_WEBHOOK_URL")
TARGET_REGION = "QLD1"

def get_retail_premium(hour):
    if 16 <= hour < 21: return 0.50
    elif 11 <= hour < 16: return 0.05
    else: return 0.20

def process_file_content(content):
    """Scan CSV content for REGIONID and RRP columns dynamically."""
    data = []
    lines = content.splitlines()
    reader = csv.reader(lines)
    
    headers = []
    for row in reader:
        if not row: continue
        # Capture header row (starts with 'I')
        if row[0] == 'I':
            if 'REGIONID' in row and 'RRP' in row:
                headers = row
        # Capture data row (starts with 'D')
        elif row[0] == 'D' and headers:
            try:
                row_dict = dict(zip(headers, row))
                if row_dict.get('REGIONID') == TARGET_REGION:
                    # Parse timestamp (handles both SettlementDate and DateTime)
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
    try:
        response = requests.get(base_url, headers={'User-Agent': 'Mozilla/5.0'})
        files = re.findall(r'href="([^"]+\.zip)"', response.text, re.IGNORECASE)
        target_files = sorted([f for f in files if pattern in f.upper()])[-2:]
        
        all_data = []
        for file in target_files:
            r = requests.get(urljoin(base_url, file))
            with zipfile.ZipFile(io.BytesIO(r.content)) as z:
                for name in [n for n in z.namelist() if n.endswith('.csv')]:
                    with z.open(name) as f:
                        all_data.extend(process_file_content(f.read().decode('utf-8', errors='ignore')))
        return all_data
    except Exception as e:
        print(f"DEBUG: Error fetching {pattern}: {e}")
        return []

if __name__ == "__main__":
    import csv
    forecast = fetch_data("https://nemweb.com.au/Reports/Current/PredispatchIS_Reports/", "PUBLIC_PREDISPATCHIS")
    actuals = fetch_data("https://nemweb.com.au/Reports/Current/DispatchIS_Reports/", "PUBLIC_DISPATCHIS")
    
    payload = {"forecast": forecast, "actuals": actuals}
    if GOOGLE_WEBHOOK_URL:
        requests.post(GOOGLE_WEBHOOK_URL, json=payload)
    print(f"DEBUG: Found {len(forecast)} forecast and {len(actuals)} actuals.")
