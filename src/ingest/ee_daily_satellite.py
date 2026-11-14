import glob
import os
import time

import ee
import pandas as pd
from dotenv import load_dotenv

load_dotenv()
ee.Initialize(project=os.getenv("EE_PROJECT"))

OUT_DIR = "data/raw/ee_daily"
os.makedirs(OUT_DIR, exist_ok=True)

st = (pd.read_csv("data/processed/pm25_dedup.csv")
        .groupby("location_id")[["lat", "lon"]].first().reset_index())
points = ee.FeatureCollection([
    ee.Feature(ee.Geometry.Point([float(r.lon), float(r.lat)]).buffer(1000),
               {"location_id": int(r.location_id)})
    for r in st.itertuples()
])

DATASETS = {
    "lst_day_c": dict(coll="MODIS/061/MOD11A1", band="LST_Day_1km", scale=1000,
                      fn=lambda i: i.multiply(0.02).subtract(273.15)),
    "lst_night_c": dict(coll="MODIS/061/MOD11A1", band="LST_Night_1km", scale=1000,
                        fn=lambda i: i.multiply(0.02).subtract(273.15)),
    "no2_umol_m2": dict(coll="COPERNICUS/S5P/OFFL/L3_NO2",
                        band="tropospheric_NO2_column_number_density", scale=5000,
                        fn=lambda i: i.multiply(1e6)),
    "aer_ai": dict(coll="COPERNICUS/S5P/OFFL/L3_AER_AI",
                   band="absorbing_aerosol_index", scale=5000, fn=lambda i: i),
}
# periods used in the forecasting experiments
MONTHS = [(2022, m) for m in range(1, 11)] + [(2025, m) for m in range(1, 12)]


def extract(cfg, start, n_days):
    coll = ee.ImageCollection(cfg["coll"]).select(cfg["band"])

    def day(n):
        d0 = ee.Date(start).advance(ee.Number(n), "day")
        sub = coll.filterDate(d0, d0.advance(1, "day"))
        img = ee.Image(ee.Algorithms.If(
            sub.size().gt(0), cfg["fn"](sub.mean()),
            ee.Image.constant(0).rename(cfg["band"]).selfMask()))   # fully masked = missing
        return img.rename("v").set("date", d0.format("YYYY-MM-dd"))

    daily = ee.ImageCollection(ee.List.sequence(0, n_days - 1).map(day))

    def per_image(img):
        fc = img.reduceRegions(collection=points, reducer=ee.Reducer.mean(),
                               scale=cfg["scale"])
        return fc.map(lambda f: f.set("date", img.get("date")))

    info = ee.FeatureCollection(daily.map(per_image)).flatten().getInfo()
    return pd.DataFrame([f["properties"] for f in info["features"]])


for y, m in MONTHS:
    start = pd.Timestamp(year=y, month=m, day=1)
    n_days = (start + pd.offsets.MonthBegin(1) - start).days
    for name, cfg in DATASETS.items():
        path = f"{OUT_DIR}/{name}_{y}_{m:02d}.csv"
        if os.path.exists(path):
            continue
        for attempt in range(3):
            try:
                d = extract(cfg, start.strftime("%Y-%m-%d"), n_days)
                if "mean" not in d.columns:
                    d["mean"] = float("nan")
                d = d.rename(columns={"mean": name})[["date", "location_id", name]]
                d.to_csv(path, index=False)
                print(f"ok  {name} {y}-{m:02d}: {len(d)} rows, "
                      f"{d[name].notna().mean():.0%} non-missing", flush=True)
                break
            except Exception as e:
                print(f"retry {name} {y}-{m:02d} ({attempt + 1}): {str(e)[:150]}", flush=True)
                time.sleep(10)
        else:
            print(f"FAILED {name} {y}-{m:02d}")

# combine
frames = []
for name in DATASETS:
    files = sorted(glob.glob(f"{OUT_DIR}/{name}_*.csv"))
    if files:
        part = pd.concat([pd.read_csv(f) for f in files])
        frames.append(part.set_index(["date", "location_id"]))
sat = pd.concat(frames, axis=1).reset_index()
sat.to_csv("data/processed/satellite_daily.csv", index=False)
print("\nsaved data/processed/satellite_daily.csv:", sat.shape)
print("share of station-days with a value:")
print(sat[list(DATASETS)].notna().mean().round(2).to_string())