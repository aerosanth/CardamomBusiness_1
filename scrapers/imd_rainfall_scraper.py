import requests
import struct
import datetime
import sqlite3
import os
import urllib3

import sys
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.append(_PROJECT_ROOT)

from modules.logger import get_app_logger
scraper_logger = get_app_logger("imd_rainfall_scraper")

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

URL = "https://www.imdpune.gov.in/cmpg/Griddata/rainfall.php"
DB_FILE = "cardamom_data.db"
START_YEAR = 1901
END_YEAR = 2025

LOCATIONS = {
    'Kottakudi': {'lat': 10.0789, 'lon': 77.2627},
    'Pooparai': {'lat': 9.98057, 'lon': 77.20328},
    'Bangalore': {'lat': 12.9716, 'lon': 77.5946}
}

def get_indices(lat, lon):
    y_float = (lat - 6.5) / 0.25
    x_float = (lon - 66.5) / 0.25
    lat_idx_nearest = round(y_float)
    lon_idx_nearest = round(x_float)
    
    y0 = int(y_float)
    y1 = min(y0 + 1, 128)
    x0 = int(x_float)
    x1 = min(x0 + 1, 134)
    
    dy = y_float - y0
    dx = x_float - x0
    return {
        'nearest': (lat_idx_nearest, lon_idx_nearest),
        'bilinear': (y0, y1, x0, x1, dy, dx)
    }

for loc in LOCATIONS:
    LOCATIONS[loc]['indices'] = get_indices(LOCATIONS[loc]['lat'], LOCATIONS[loc]['lon'])

def download_file(year):
    filename = f"ind{year}_rfp25.grd"
    if os.path.exists(filename):
        return filename
        
    scraper_logger.info(f"Downloading data for {year} from {URL}...")
    try:
        session = requests.Session()
        session.verify = False
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': URL,
            'Origin': 'https://www.imdpune.gov.in'
        }
        
        payload = {'rain': str(year), 'Submit': 'Download'}
        download_resp = session.post(URL, data=payload, headers=headers, stream=True)
        download_resp.raise_for_status()
        
        with open(filename, 'wb') as f:
            for chunk in download_resp.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        return filename
    except Exception as e:
        scraper_logger.error(f"Failed to download for {year}: {e}")
        return None

def get_val(data, lat_idx, lon_idx):
    idx = lat_idx * 135 + lon_idx
    val_bytes = data[idx * 4 : idx * 4 + 4]
    if len(val_bytes) < 4:
        return 0.0
    val = struct.unpack('<f', val_bytes)[0]
    return 0.0 if val < -900 else val

def extract_and_store(year, filename, conn):
    bytes_per_day = 135 * 129 * 4
    start_date = datetime.date(year, 1, 1)
    
    is_leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
    days_in_year = 366 if is_leap else 365
    
    records = []
    
    with open(filename, 'rb') as f:
        for day in range(days_in_year):
            data = f.read(bytes_per_day)
            if not data or len(data) < bytes_per_day:
                break
                
            current_date = start_date + datetime.timedelta(days=day)
            date_str = current_date.strftime('%Y-%m-%d')
            
            for loc, info in LOCATIONS.items():
                nearest_idx = info['indices']['nearest']
                nearest_val = get_val(data, nearest_idx[0], nearest_idx[1])
                
                y0, y1, x0, x1, dy, dx = info['indices']['bilinear']
                q11 = get_val(data, y0, x0)
                q21 = get_val(data, y0, x1)
                q12 = get_val(data, y1, x0)
                q22 = get_val(data, y1, x1)
                
                bilinear_val = (
                    q11 * (1 - dx) * (1 - dy) +
                    q21 * dx * (1 - dy) +
                    q12 * (1 - dx) * dy +
                    q22 * dx * dy
                )
                
                records.append((loc, date_str, nearest_val, bilinear_val))
                
    cursor = conn.cursor()
    cursor.executemany('''
        INSERT OR IGNORE INTO rainfall_data (location, date, rainfall_nearest_mm, rainfall_bilinear_mm)
        VALUES (?, ?, ?, ?)
    ''', records)
    conn.commit()

def setup_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS rainfall_data (
            location TEXT,
            date TEXT,
            rainfall_nearest_mm REAL,
            rainfall_bilinear_mm REAL,
            PRIMARY KEY (location, date)
        )
    ''')
    conn.commit()
    return conn

if __name__ == "__main__":
    scraper_logger.info("Starting IMD Rainfall data extraction for 1901-2025...")
    conn = setup_db()
    
    for year in range(START_YEAR, END_YEAR + 1):
        filename = download_file(year)
        if filename:
            extract_and_store(year, filename, conn)
            scraper_logger.info(f"Processed and stored data for {year}.")
            
            # Note: We are keeping the .grd files as they download. 
            # If storage is an issue, you can uncomment the line below to delete after processing:
            # os.remove(filename)
            
    conn.close()
    scraper_logger.info(f"All years processed! Data saved to SQLite Database: {DB_FILE}")
