import duckdb
import numpy as np
import pandas as pd

feat = pd.read_csv("data/processed/station_static_features.csv")
con = duckdb.connect("data/processed/terra.duckdb", read_only=True)

def station_mean(start, end, min_days):
    return con.execute(f"""
        SELECT location_id, AVG(pm25) AS pm25_mean FROM station_obs
        WHERE date BETWEEN '{start}' AND '{end}'
        GROUP BY location_id HAVING COUNT(*) >= {min_days}""").df()

land = [c for c in ["built_frac", "tree_frac", "crop_frac", "ndvi_mean",
                    "pop_density_km2", "elevation_m"] if c in feat.columns]

# ---- 1. Urban heat island: LST vs land use ----
print("=== Spearman correlation of station LST with land use (n =", len(feat), "stations) ===")
for lst in ("lst_day_summer_c", "lst_day_winter_c"):
    print(lst)
    print(feat[land + [lst]].corr(method="spearman")[lst].drop(lst).round(2).to_string())

if "built_frac" in feat:
    lo, hi = feat["built_frac"].quantile([1 / 3, 2 / 3])
    low, high = feat[feat.built_frac <= lo], feat[feat.built_frac >= hi]
    print(f"\nMean LST, most built-up third (n={len(high)}) minus least built-up third (n={len(low)}):")
    for lst in ("lst_day_summer_c", "lst_day_winter_c"):
        print(f"  {lst}: {high[lst].mean() - low[lst].mean():+.2f} C")


# ---- 2. Standardised regression ----
def ols(df, y, xs):
    z = df[xs + [y]].dropna()
    X = (z[xs] - z[xs].mean()) / z[xs].std()
    Y = (z[y] - z[y].mean()) / z[y].std()
    A = np.column_stack([np.ones(len(X)), X.to_numpy()])
    beta, *_ = np.linalg.lstsq(A, Y.to_numpy(), rcond=None)
    r2 = 1 - ((Y - A @ beta) ** 2).sum() / ((Y - Y.mean()) ** 2).sum()
    print(f"\nOLS {y} ~ {', '.join(xs)}  (n={len(z)}, R2={r2:.2f})")
    for name, b in zip(xs, beta[1:]):
        print(f"  {name:18s} {b:+.2f}")

xs = [c for c in ["built_frac", "ndvi_mean", "pop_density_km2", "elevation_m"] if c in feat.columns]
ols(feat, "lst_day_summer_c", xs)

# ---- 3. Station mean PM2.5 vs land use ----
for label, start, end, nmin in (("Oct-Nov 2025", "2025-10-01", "2025-11-29", 45),
                                ("Feb-Sep 2025", "2025-02-01", "2025-09-30", 180)):
    d = feat.merge(station_mean(start, end, nmin), on="location_id")
    print(f"\n=== Station mean PM2.5, {label} (n = {len(d)} stations): Spearman with static features ===")
    cols = land + ["lst_day_summer_c", "lst_day_winter_c"]
    print(d[cols + ["pm25_mean"]].corr(method="spearman")["pm25_mean"].drop("pm25_mean").round(2).to_string())