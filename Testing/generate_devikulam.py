import struct
import datetime
import os
import csv

FILENAME = "ind2025_rfp25.grd"
OUT_CSV = "uploaded_docs/devikulam_rainfall_2025.csv"

def extract_rainfall():
    if not os.path.exists(FILENAME):
        print(f"{FILENAME} not found.")
        return
    
    LAT_TARGET = 10.06
    LON_TARGET = 77.12
    
    y_float = (LAT_TARGET - 6.5) / 0.25
    x_float = (LON_TARGET - 66.5) / 0.25
    
    LAT_IDX_NEAREST = round(y_float)
    LON_IDX_NEAREST = round(x_float)
    
    y0 = int(y_float)
    y1 = min(y0 + 1, 128)
    x0 = int(x_float)
    x1 = min(x0 + 1, 134)
    
    dy = y_float - y0
    dx = x_float - x0
    
    def get_val(data, lat_idx, lon_idx):
        idx = lat_idx * 135 + lon_idx
        val_bytes = data[idx * 4 : idx * 4 + 4]
        val = struct.unpack('<f', val_bytes)[0]
        return 0.0 if val < -900 else val

    start_date = datetime.date(2025, 1, 1)
    
    bytes_per_day = 135 * 129 * 4
    
    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    with open(FILENAME, 'rb') as f, open(OUT_CSV, 'w', newline='') as out_f:
        writer = csv.writer(out_f)
        writer.writerow(['Date', 'Rainfall_Nearest_mm', 'Rainfall_Bilinear_mm'])
        
        for day in range(365):
            data = f.read(bytes_per_day)
            if not data or len(data) < bytes_per_day:
                break
            
            nearest_val = get_val(data, LAT_IDX_NEAREST, LON_IDX_NEAREST)
            
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
            
            current_date = start_date + datetime.timedelta(days=day)
            writer.writerow([current_date.strftime('%Y-%m-%d'), nearest_val, bilinear_val])
    print("Devikulam CSV created successfully.")

if __name__ == '__main__':
    extract_rainfall()
