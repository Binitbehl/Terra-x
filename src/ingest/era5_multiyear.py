import os
import sys
import time
import cdsapi

OUT_DIR = "data/raw/era5_multi"
AREA = [29.0, 76.75, 28.25, 77.5]
VARIABLES = [
    "2m_temperature", "2m_dewpoint_temperature",
    "10m_u_component_of_wind", "10m_v_component_of_wind",
    "surface_pressure", "total_precipitation", "boundary_layer_height",
]

year = int(sys.argv[1])
m_from, m_to = int(sys.argv[2]), int(sys.argv[3])

os.makedirs(OUT_DIR, exist_ok=True)
client = cdsapi.Client()

for month in range(m_from, m_to + 1):
    final = f"{OUT_DIR}/era5_{year}_{month:02d}.nc"
    if os.path.exists(final):
        print("skip", year, month)
        continue
    print(f"Requesting {year}-{month:02d} ...")
    try:
        client.retrieve(
            "reanalysis-era5-single-levels",
            {
                "product_type": ["reanalysis"],
                "variable": VARIABLES,
                "year": [str(year)],
                "month": [f"{month:02d}"],
                "day": [f"{d:02d}" for d in range(1, 32)],
                "time": [f"{h:02d}:00" for h in range(24)],
                "area": AREA,
                "data_format": "netcdf",
                "download_format": "unarchived",
            },
            final + ".part",
        )
        os.rename(final + ".part", final)
        print("done", year, month)
    except Exception as e:
        print("FAILED", year, month, "->", e)
        time.sleep(5)