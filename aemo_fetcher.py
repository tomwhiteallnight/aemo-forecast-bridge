import requests
import re
import zipfile
import io
import csv
import os
import sys
from urllib.parse import urljoin

# --- CONFIG ---
GOOGLE_WEBHOOK_URL = os.environ.get("GOOGLE_WEBHOOK_URL")
TARGET_REGION = "QLD1"

def get_retail_premium(hour):
    if 16 <= hour < 21: return 0.50
    elif 11 <= hour < 16: return 0.05
    else: return 0.20

def fetch_table(url, pattern, target_table):
    print(f"DEBUG: Checking {url} for {target_table}")
    try:
        response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
        files = re.findall(r'href="([^"]+\.zip)"', response.text, re.IGNORECASE)
        target = sorted([f for f in files if pattern in f.upper()])[-1]
        
        print(f"DEBUG: Opening {target}")
        r = requests.get(urljoin(url, target))
        data = []
        
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            for name in [n for n in z.namelist() if n.endswith('.csv')]:
                with z.open(name) as f:
                    lines = f.read().decode('utf-8', errors='ignore').splitlines()
                    reader = csv.reader(lines)
                    headers = []
                    for row in reader:
                        if not row: continue
                        # Find Header
                        if row[0] == 'I' and target_table in row:
                            headers = row
                        # Parse Data
                        elif row[0] == 'D' and headers and row[2] == target_table:
                            row_dict = dict(zip(headers, row))
                            if row_dict.get('REGIONID') == TARGET_REGION:
                                dt_str = row_dict.get('SETTLEMENTDATE') or row_dict.get('DATETIME')
                                hour = int(dt_str.split(' ')[1].split(':')[0])
                                rrp = float(row_dict.get('RRP', 0)) / 1000
                                data.append({"datetime": dt_str, "region": "QLD1", "price": round(rrp + get_retail_premium(hour), 4)})
        return data
    except Exception as e:
        print(f"DEBUG: Error fetching {target_table}: {e}")
        return []

if __name__ == "__main__":
    # Fetch both using the correct table identifiers
    forecast = fetch_table("https://nemweb.com.au/Reports/Current/PredispatchIS_Reports/", "PUBLIC_PREDISPATCHIS", "PREDISPATCHPRICE")
    actuals = fetch_table("https://nemweb.com.au/Reports/Current/DispatchIS_Reports/", "PUBLIC_DISPATCHIS", "DISPATCHPRICE")
    
    payload = {"forecast": forecast, "actuals": actuals}
    
    if GOOGLE_WEBHOOK_URL:
        resp = requests.post(GOOGLE_WEBHOOK_URL, json=payload)
        print(f"DEBUG: Sent {len(forecast)} forecast and {len(actuals)} actuals. Response: {resp.status_code}")
    else:
        print("DEBUG: Webhook URL missing.")
