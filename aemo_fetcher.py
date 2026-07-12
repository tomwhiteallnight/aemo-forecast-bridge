import requests
import re
import zipfile
import io
import csv
import json
import os
from urllib.parse import urljoin

GOOGLE_SHEETS_WEBHOOK_URL = os.environ.get("GOOGLE_WEBHOOK_URL")
TARGET_REGION = "QLD1"

def fetch_aemo_forecast():
    print("Connecting to AEMO NEMWEB...")
    # The base URL of the directory
    base_url = "https://nemweb.com.au/Reports/Current/PredispatchIS_Reports/"
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    try:
        response = requests.get(base_url, headers=headers)
        response.raise_for_status()
        html = response.text
        
        # Regex to find all zip files
        zip_files = re.findall(r'href="([^"]+\.zip)"', html, re.IGNORECASE)
        
        if not zip_files:
            print("Could not find any zip files.")
            return
            
        # Sort files and grab the last one
        latest_zip_filename = sorted(zip_files)[-1]
        
        # FIX: Use urljoin to perfectly join the base and the relative path
        zip_url = urljoin(base_url, latest_zip_filename)
            
        print(f"Downloading: {zip_url}")
        
        zip_response = requests.get(zip_url, headers=headers)
        zip_response.raise_for_status()
        
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
                    # Identifying headers and target table
                    if row[0] == 'I' and 'RRP' in row and 'REGIONID' in row:
                        headers = row
                        target_table = row[2]
                    # Parsing data rows
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
            post_response = requests.post(GOOGLE_SHEETS_WEBHOOK_URL, json=forecast_data, allow_redirects=True)
            print("Google Response Code:", post_response.status_code)
            print("Google Response Text:", post_response.text)
        else:
            print("No matching data for QLD1 found.")
            
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    fetch_aemo_forecast()
