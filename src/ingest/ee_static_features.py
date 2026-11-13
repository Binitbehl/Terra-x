import os
import ee
import pandas as pd
from dotenv import load_dotenv

load_dotenv()
ee.Initialize(project=os.getenv("EE_PROJECT"))

BUFFER_M = 1000          # features are averaged within 1 km of each station
AREA_KM2 = 3.14159 * (BUFFER_M / 1000) ** 2

st = pd.read_csv("data/processed/stations.csv")
points = ee.FeatureCollection([
    ee.Feature(ee.Geometry.Point([float(r.lon), float(r.lat)]),
               {"location_id": int(r.location_id)})
    for r in st.itertuples()
])
regions = points.map(lambda f: f.buffer(BUFFER_M))


def run(name, image, reducer, scale, rename=None):
    try:
        info = image.reduceRegions(collection=regions, reducer=reducer, scale=scale).getInfo()
        df = pd.DataFrame([f["properties"] for f in info["features"]])
        if rename:
            df = df.rename(columns=rename)
        print("ok  ", name)
        return df.set_index("location_id")
    except Exception as e:
        print("FAIL", name, "->", str(e)[:250])
        return None


parts = []

# Land cover fractions (ESA WorldCover 10 m, 2021)
wc = ee.ImageCollection("ESA/WorldCover/v200").first().select("Map")
lc = ee.Image.cat([
    wc.eq(50).rename("built_frac"), wc.eq(10).rename("tree_frac"),
    wc.eq(40).rename("crop_frac"), wc.eq(30).rename("grass_frac"),
    wc.eq(60).rename("bare_frac"), wc.eq(80).rename("water_frac"),
])
parts.append(run("land cover", lc, ee.Reducer.mean(), 30))

# Elevation (SRTM 30 m)
parts.append(run("elevation", ee.Image("USGS/SRTMGL1_003").select("elevation"),
                 ee.Reducer.mean(), 30, {"mean": "elevation_m"}))

# Vegetation (MODIS NDVI, 1 km, mean 2022-2025)
ndvi = (ee.ImageCollection("MODIS/061/MOD13A2").filterDate("2022-01-01", "2025-11-30")
        .select("NDVI").mean().multiply(0.0001))
parts.append(run("ndvi", ndvi, ee.Reducer.mean(), 1000, {"mean": "ndvi_mean"}))

# Population (GHSL 100 m, 2020) -> people per km2
pop = ee.Image("JRC/GHSL/P2023A/GHS_POP/2020").select("population_count")
pdf = run("population", pop, ee.Reducer.sum(), 100, {"sum": "pop_sum"})
if pdf is not None:
    pdf["pop_density_km2"] = pdf["pop_sum"] / AREA_KM2
    parts.append(pdf[["pop_density_km2"]])

# Land surface temperature (MODIS 1 km daytime), summer (May-Jun) and winter (Dec-Jan) means
lst_all = (ee.ImageCollection("MODIS/061/MOD11A1").filterDate("2022-01-01", "2025-11-30")
           .select("LST_Day_1km"))
for label, m1, m2 in (("lst_day_summer_c", 5, 6), ("lst_day_winter_c", 12, 1)):
    if m1 <= m2:
        sel = lst_all.filter(ee.Filter.calendarRange(m1, m2, "month"))
    else:
        sel = lst_all.filter(ee.Filter.Or(ee.Filter.calendarRange(m1, 12, "month"),
                                          ee.Filter.calendarRange(1, m2, "month")))
    img = sel.mean().multiply(0.02).subtract(273.15)
    parts.append(run(label, img, ee.Reducer.mean(), 1000, {"mean": label}))

parts = [p for p in parts if p is not None]
feat = pd.concat(parts, axis=1).reset_index()
out = st.merge(feat, on="location_id", how="left")
out.to_csv("data/processed/station_static_features.csv", index=False)
print(out.describe().T[["count", "min", "mean", "max"]])
print("saved data/processed/station_static_features.csv")