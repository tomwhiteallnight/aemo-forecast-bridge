import requests
import re
import zipfile
import io
import csv
import json
import os

GOOGLE_SHEETS_WEBHOOK_URL = os.environ.get("GOOGLE_WEBHOOK_URL")
TARGET_REGION = "QLD1"

def fetch_aemo_forecast():
    print("Connecting to AEMO NEMWEB...")
    # Using a standard browser header is essential for AEMO to accept the connection
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    base_url = "https://nemweb.com.au/Reports/Current/PredispatchIS_Reports/"
    
    try:
        response = requests.get(base_url, headers=headers)
        response.raise_for_status() # This will crash the script if the site blocks you
        html = response.text
        
        # New robust logic: Find ALL zip files on the page, not just those matching one pattern
        zip_files = re.findall(r'href="([^"]+\.zip)"', html, re.IGNORECASE)
        
        if not zip_files:
            print("Could not find any zip files. Here is the start of the HTML page we received:")
            print(html[:500]) # Prints the first 500 chars to help us debug
            return
            
        # Sort and pick the last one (assuming last is most recent)
        latest_zip_filename = sorted(zip_files)[-1]
        
        # Build the full URL
        if latest_zip_filename.startswith("http"):
            zip_url = latest_zip_filename
        else:
            zip_url = base_url + latest_zip_filename
            
        print(f"Downloading: {zip_url}")
        
        zip_response = requests.get(zip_url, headers=headers)
        zip_response.raise_for_status()
        
        # ... (Rest of your parsing logic remains the same)
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
                    if row[0] == 'I' and 'RRP' in row and 'REGIONID' in row:
                        headers = row
                        target_table = row[2]
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
            print("Google Response:", post_response.text)
        else:
            print("No matching data for QLD1 found in the file.")
            
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    fetch_aemo_forecast()
