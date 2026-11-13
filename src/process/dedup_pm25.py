import pandas as pd

df = pd.read_csv("data/raw/openaq_pm25_2022_2025.csv", parse_dates=["date"])
df = df[(df["pm25"] >= 0) & (df["pm25"] <= 1000)]          # clean before averaging
merge = pd.read_csv("src/process/station_merge.csv")
mapping = dict(zip(merge["old_id"], merge["new_id"]))

meta = df.drop_duplicates("location_id").set_index("location_id")[["name", "lat", "lon"]]
df["location_id"] = df["location_id"].replace(mapping)
df[["name", "lat", "lon"]] = meta.loc[df["location_id"]].to_numpy()  # canonical name/coords

out = (df.groupby(["location_id", "date"], as_index=False)
         .agg(name=("name", "first"), lat=("lat", "first"), lon=("lon", "first"),
              sensor_id=("sensor_id", "first"), pm25=("pm25", "mean")))
out.to_csv("data/processed/pm25_dedup.csv", index=False)
print("rows:", len(out), " stations:", out["location_id"].nunique())
y22 = set(out[out["date"].dt.year == 2022]["location_id"])
y25 = set(out[out["date"].dt.year == 2025]["location_id"])
print("2022:", len(y22), "2025:", len(y25), "shared:", len(y22 & y25),
      "new in 2025:", len(y25 - y22), "2022 only:", len(y22 - y25))