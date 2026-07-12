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

# Tariff 6900 Logic
def get_retail_premium(dt):
    hour = dt.hour
    if 16 <= hour < 21: return 0.50 # Peak
    elif 11 <= hour < 16: return 0.05 # Solar Soak
    else: return 0.20 # Shoulder

def fetch_aemo_data(report_type):
    # Determine URL based on report type
    base_url = "https://nemweb.com.au/Reports/Current/PredispatchIS_Reports/" if report_type == "forecast" else "https://nemweb.com.au/Reports/Current/DispatchIS_Reports/"
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    response = requests.get(base_url, headers=headers)
    zip_files = re.findall(r'href="([^"]+\.zip)"', response.text, re.IGNORECASE)
    if not zip_files: return None
    
    latest_zip = sorted(zip_files)[-1]
    zip_url = urljoin(base_url, latest_zip)
    zip_response = requests.get(zip_url, headers=headers)
    
    data = []
    with zipfile.ZipFile(io.BytesIO(zip_response.content)) as z:
        with z.open(z.namelist()[0]) as f:
            reader = csv.reader(line.decode('utf-8') for line in f.readlines())
            headers, target_table = [], None
            for row in reader:
                if not row: continue
                if row[0] == 'I' and 'RRP' in row and 'REGIONID' in row:
                    headers, target_table = row, row[2]
                elif row[0] == 'D' and target_table and row[2] == target_table:
                    row_dict = dict(zip(headers, row))
                    if row_dict.get('REGIONID') == TARGET_REGION:
                        time_str = row_dict.get('DATETIME') or row_dict.get('SETTLEMENTDATE')
                        dt = datetime.strptime(time_str, '%Y/%m/%d %H:%M:%S')
                        price = float(row_dict.get('RRP', 0)) / 1000
                        # Add premium logic
                        final_price = price + get_retail_premium(dt)
                        data.append({"datetime": time_str, "region": TARGET_REGION, "price": round(final_price, 4)})
    return data

if __name__ == "__main__":
    forecast = fetch_aemo_data("forecast")
    actuals = fetch_aemo_data("actuals")
    
    # Send both as a single JSON package with types
    payload = {"type": "combined", "forecast": forecast, "actuals": actuals}
    requests.post(GOOGLE_SHEETS_WEBHOOK_URL, json=payload, allow_redirects=True)
