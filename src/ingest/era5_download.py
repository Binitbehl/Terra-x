import os
import zipfile
import cdsapi

OUT_DIR = "data/raw/era5"
AREA = [29.0, 76.75, 28.25, 77.5]  # North, West, South, East (Delhi + margin)
YEAR = "2025"
MONTHS = ["10", "11"]
VARIABLES = [
    "2m_temperature",
    "2m_dewpoint_temperature",
    "10m_u_component_of_wind",
    "10m_v_component_of_wind",
    "surface_pressure",
    "total_precipitation",
    "boundary_layer_height",
]

os.makedirs(OUT_DIR, exist_ok=True)
client = cdsapi.Client()

for month in MONTHS:
    target = f"{OUT_DIR}/era5_{YEAR}_{month}.download"
    print(f"Requesting {YEAR}-{month} (may queue for a few minutes)...")
    client.retrieve(
        "reanalysis-era5-single-levels",
        {
            "product_type": ["reanalysis"],
            "variable": VARIABLES,
            "year": [YEAR],
            "month": [month],
            "day": [f"{d:02d}" for d in range(1, 32)],
            "time": [f"{h:02d}:00" for h in range(24)],
            "area": AREA,
            "data_format": "netcdf",
            "download_format": "unarchived",
        },
        target,
    )
    # The CDS sometimes returns a zip containing several .nc files
    if zipfile.is_zipfile(target):
        with zipfile.ZipFile(target) as z:
            z.extractall(f"{OUT_DIR}/{YEAR}_{month}")
        os.remove(target)
    else:
        os.rename(target, f"{OUT_DIR}/era5_{YEAR}_{month}.nc")
    print("done", month)