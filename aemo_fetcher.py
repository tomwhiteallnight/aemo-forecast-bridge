import requests
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
    
    # Use requests to fetch the page
    response = requests.get(base_url, headers={'User-Agent': 'Mozilla/5.0'})
    html = response.text
    
    zip_files = re.findall(r'href="(PUBLIC_PREDISPATCHIS_[^"]+\.zip)"', html, re.IGNORECASE)
    
    if not zip_files:
        print("Could not find any zip files on NEMWEB.")
        return
        
    latest_zip_filename = sorted(zip_files)[-1]
    zip_url = base_url + latest_zip_filename
    print(f"Downloading: {latest_zip_filename}")
    
    # Download the ZIP content
    zip_response = requests.get(zip_url, headers={'User-Agent': 'Mozilla/5.0'})
    
    forecast_data = []
    
    with zipfile.ZipFile(io.BytesIO(zip_response.content)) as z:
        csv_filename = z.namelist()[0]
        with z.open(csv_filename) as f:
            lines = [line.decode('utf-8') for line in f.readlines()]
            reader = csv.reader(lines)
            
            headers = []
            target_table = None
            
            for row in reader:
                if not row: continue
                # Logic: Find the table headers first
                if row[0] == 'I' and 'RRP' in row and 'REGIONID' in row:
                    headers = row
                    target_table = row[2]
                # Logic: Extract data rows matching that table
                elif row[0] == 'D' and target_table and row[2] == target_table:
                    row_dict = dict(zip(headers, row))
                    if row_dict.get('REGIONID') == TARGET_REGION:
                        time_val = row_dict.get('DATETIME') or row_dict.get('SETTLEMENTDATE')
                        forecast_data.append({
                            "datetime": time_val,
                            "region": row_dict.get('REGIONID'),
                            "price": float(row_dict.get('RRP', 0))
                        })

    if forecast_data:
        print(f"Sending {len(forecast_data)} rows to Google Sheets...")
        
        # 'allow_redirects=True' ensures the post finishes correctly
        response = requests.post(
            GOOGLE_SHEETS_WEBHOOK_URL, 
            json=forecast_data, 
            allow_redirects=True
        )
        print("Google Response Status Code:", response.status_code)
        print("Google Response Text:", response.text)
    else:
        print("No matching regional data found.")

if __name__ == "__main__":
    fetch_aemo_forecast()
