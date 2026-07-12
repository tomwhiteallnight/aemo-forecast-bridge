import urllib.request
import re
import zipfile
import io
import csv
import json
import os

# Grabs your secure URL from GitHub Secrets
GOOGLE_SHEETS_WEBHOOK_URL = os.environ.get("GOOGLE_WEBHOOK_URL")
TARGET_REGION = "QLD1"

def fetch_aemo_forecast():
    print("Connecting to AEMO NEMWEB...")
    base_url = "https://nemweb.com.au/Reports/Current/PredispatchIS_Reports/"
    
    req = urllib.request.Request(base_url, headers={'User-Agent': 'Mozilla/5.0'})
    html = urllib.request.urlopen(req).read().decode('utf-8')
    
    zip_files = re.findall(r'href="(PUBLIC_PREDISPATCHIS_[^"]+\.zip)"', html, re.IGNORECASE)
    
    if not zip_files:
        print("Could not find any zip files on NEMWEB.")
        return
        
    latest_zip_filename = sorted(zip_files)[-1]
    zip_url = base_url + latest_zip_filename
    print(f"Downloading latest forecast: {latest_zip_filename}")
    
    zip_req = urllib.request.Request(zip_url, headers={'User-Agent': 'Mozilla/5.0'})
    zip_data = urllib.request.urlopen(zip_req).read()
    
    forecast_data = []
    
    with zipfile.ZipFile(io.BytesIO(zip_data)) as z:
        csv_filename = z.namelist()[0]
        with z.open(csv_filename) as f:
            lines = [line.decode('utf-8') for line in f.readlines()]
            reader = csv.reader(lines)
            
            headers = []
            for row in reader:
                if not row:
                    continue
                row_type = row[0]
                
                if row_type == 'I' and row[2] == 'PRICE':
                    headers = row
                elif row_type == 'D' and row[2] == 'PRICE':
                    row_dict = dict(zip(headers, row))
                    if row_dict.get('REGIONID') == TARGET_REGION:
                        forecast_data.append({
                            "datetime": row_dict.get('DATETIME'),
                            "region": row_dict.get('REGIONID'),
                            "price": float(row_dict.get('RRP', 0))
                        })

    if forecast_data:
        print(f"Extracted {len(forecast_data)} intervals for {TARGET_REGION}. Sending to Google Sheets...")
        payload = json.dumps(forecast_data).encode('utf-8')
        post_req = urllib.request.Request(
            GOOGLE_SHEETS_WEBHOOK_URL, 
            data=payload, 
            headers={'Content-Type': 'application/json'}
        )
        response = urllib.request.urlopen(post_req)
        print("Response:", response.read().decode('utf-8'))
    else:
        print("No matching regional data found.")

if __name__ == "__main__":
    fetch_aemo_forecast()
