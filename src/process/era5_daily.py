import glob
import os
import numpy as np
import pandas as pd
import xarray as xr

files = sorted(glob.glob("data/raw/era5/**/*.nc", recursive=True))
print("Found files:", files)
if not files:
    raise SystemExit("No .nc files found in data/raw/era5/. Download them first "
                     "and run src/process/unpack_era5.py.")

datasets = []
for f in files:
    ds = xr.open_dataset(f)
    if "valid_time" in ds.coords:
        ds = ds.rename({"valid_time": "time"})
    for extra in ("expver", "number"):
        if extra in ds.dims:
            ds = ds.mean(extra)
        elif extra in ds.coords:
            ds = ds.drop_vars(extra)
    datasets.append(ds)

ds = xr.merge(datasets, compat="override")

spatial_dims = [d for d in ("latitude", "longitude") if d in ds.dims]
hourly = ds.mean(dim=spatial_dims).to_dataframe()
hourly = hourly.drop(columns=[c for c in hourly.columns if c in ("number", "expver")],
                     errors="ignore")
hourly = hourly.sort_index()
print("Columns found:", list(hourly.columns))

t_c = hourly["t2m"] - 273.15
td_c = hourly["d2m"] - 273.15
hourly["temp_c"] = t_c
hourly["rh"] = 100 * np.exp(17.625 * td_c / (243.04 + td_c)) / np.exp(17.625 * t_c / (243.04 + t_c))
hourly["wind_speed"] = np.sqrt(hourly["u10"] ** 2 + hourly["v10"] ** 2)
hourly["pressure_hpa"] = hourly["sp"] / 100
hourly["precip_mm"] = hourly["tp"] * 1000
hourly["blh_m"] = hourly["blh"]

daily = hourly[["temp_c", "rh", "wind_speed", "pressure_hpa", "blh_m"]].resample("D").mean()
daily["temp_max_c"] = hourly["temp_c"].resample("D").max()
daily["temp_min_c"] = hourly["temp_c"].resample("D").min()
daily["precip_mm"] = hourly["precip_mm"].resample("D").sum()
daily["blh_max_m"] = hourly["blh_m"].resample("D").max()
daily.index.name = "date"

os.makedirs("data/processed", exist_ok=True)
daily.to_csv("data/processed/era5_daily_delhi.csv")
print(daily.head())
print(daily.describe().T[["min", "mean", "max"]])
print(f"Saved {len(daily)} days to data/processed/era5_daily_delhi.csv")