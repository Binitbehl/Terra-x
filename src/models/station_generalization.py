import duckdb
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.dummy import DummyRegressor
from sklearn.linear_model import RidgeCV
from sklearn.model_selection import GroupKFold, LeaveOneOut, cross_val_predict
from sklearn.neighbors import KNeighborsRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

feat = pd.read_csv("data/processed/station_static_features.csv")
con = duckdb.connect("data/processed/terra.duckdb", read_only=True)

FEATS = ["built_frac", "tree_frac", "ndvi_mean", "pop_density_km2",
         "elevation_m", "lst_day_summer_c", "lst_day_winter_c"]
ridge = make_pipeline(StandardScaler(), RidgeCV(alphas=np.logspace(-1, 3, 20)))
base = DummyRegressor(strategy="mean")
knn = KNeighborsRegressor(n_neighbors=4, weights="distance")

for label, start, end, nmin in (("Oct-Nov 2025", "2025-10-01", "2025-11-29", 45),
                                ("Feb-Sep 2025", "2025-02-01", "2025-09-30", 180)):
    pm = con.execute(f"""SELECT location_id, AVG(pm25) AS y FROM station_obs
        WHERE date BETWEEN '{start}' AND '{end}'
        GROUP BY location_id HAVING COUNT(*) >= {nmin}""").df()
    d = feat.merge(pm, on="location_id").dropna(subset=FEATS + ["y"]).reset_index(drop=True)
    X, y = d[FEATS].to_numpy(), d["y"]
    coords = np.column_stack([d["lon"] * np.cos(np.radians(28.6)), d["lat"]])
    blocks = KMeans(5, n_init=10, random_state=0).fit_predict(d[["lat", "lon"]])
    candidates = {
        "static features (ridge)": (ridge, X),
        "location only (4 nearest)": (knn, coords),
        "features + location": (ridge, np.column_stack([X, coords])),
    }
    print(f"\n=== {label}: station mean PM2.5 (n={len(d)}, std {y.std():.1f}) ===")
    for cvname, cv, groups in (("leave-one-station-out", LeaveOneOut(), None),
                               ("held-out regions (5)", GroupKFold(5), blocks)):
        b = cross_val_predict(base, X, y, cv=cv, groups=groups)
        mae_b = np.mean(np.abs(y - b))
        print(f"-- {cvname}: mean-baseline MAE {mae_b:.1f}")
        for cname, (m, Z) in candidates.items():
            p = cross_val_predict(m, Z, y, cv=cv, groups=groups)
            mae = np.mean(np.abs(y - p))
            print(f"   {cname:28s} MAE {mae:5.1f}  ({100 * (1 - mae / mae_b):+.0f}%)")