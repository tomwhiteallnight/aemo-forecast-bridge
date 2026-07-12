import requests
import re
import zipfile
import io
import os
from urllib.parse import urljoin

GOOGLE_SHEETS_WEBHOOK_URL = os.environ.get("GOOGLE_WEBHOOK_URL")

def get_data(url, pattern):
    response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
    files = re.findall(r'href="([^"]+\.zip)"', response.text, re.IGNORECASE)
    target = sorted([f for f in files if pattern in f.upper()])[-1]
    
    data = []
    r = requests.get(urljoin(url, target))
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        for name in [n for n in z.namelist() if n.endswith('.csv')]:
            with z.open(name) as f:
                lines = f.read().decode('utf-8', errors='ignore').splitlines()
                # AEMO CSVs are complex, let's just find the QLD1 price row
                for line in lines:
                    if 'QLD1' in line and 'D,' in line:
                        parts = line.split(',')
                        # Assuming RRP is 10th column in DISPATCHPRICE, adjust if needed
                        try:
                            # A simple extraction
                            data.append({"datetime": parts[4], "region": "QLD1", "price": float(parts[-2])/1000})
                        except: continue
    return data[:50] # Limit to 50 rows to avoid crashing the webhook

if __name__ == "__main__":
    payload = {
        "forecast": get_data("https://nemweb.com.au/Reports/Current/PredispatchIS_Reports/", "PUBLIC_PREDISPATCHIS"),
        "actuals": get_data("https://nemweb.com.au/Reports/Current/DispatchIS_Reports/", "PUBLIC_DISPATCHIS")
    }
    requests.post(GOOGLE_SHEETS_WEBHOOK_URL, json=payload)
