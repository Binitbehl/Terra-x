import os
import duckdb
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from sklearn.model_selection import LeaveOneOut, cross_val_predict
from sklearn.neighbors import KNeighborsRegressor

feat = pd.read_csv("data/processed/station_static_features.csv")
con = duckdb.connect("data/processed/terra.duckdb", read_only=True)
pm = con.execute("""SELECT location_id, AVG(pm25) AS pm25_mean FROM station_obs
    WHERE date BETWEEN '2025-10-01' AND '2025-11-29'
    GROUP BY location_id HAVING COUNT(*) >= 45""").df()
d = feat[["location_id", "name", "lat", "lon"]].merge(pm, on="location_id").reset_index(drop=True)

coords = np.column_stack([d["lon"] * np.cos(np.radians(28.6)), d["lat"]])
d["pred_loo"] = cross_val_predict(KNeighborsRegressor(4, weights="distance"),
                                  coords, d["pm25_mean"], cv=LeaveOneOut())
d["resid"] = d["pm25_mean"] - d["pred_loo"]   # > 0: more polluted than neighbours suggest

fig, ax = plt.subplots(1, 2, figsize=(14, 6.5))
s0 = ax[0].scatter(d["lon"], d["lat"], c=d["pm25_mean"], cmap="YlOrRd", s=90, edgecolor="k")
fig.colorbar(s0, ax=ax[0], label="Mean PM2.5, Oct-Nov 2025 (ug/m3)")
ax[0].set_title("Station mean PM2.5")

lim = float(np.abs(d["resid"]).max())
s1 = ax[1].scatter(d["lon"], d["lat"], c=d["resid"], cmap="RdBu_r", vmin=-lim, vmax=lim,
                   s=90, edgecolor="k")
fig.colorbar(s1, ax=ax[1], label="Observed minus neighbour prediction (ug/m3)")
ax[1].set_title("Where neighbours mispredict a station")
for _, r in d.reindex(d["resid"].abs().sort_values(ascending=False).index).head(6).iterrows():
    ax[1].annotate(r["name"].split(",")[0], (r["lon"], r["lat"]), fontsize=8,
                   xytext=(4, 4), textcoords="offset points")
for a in ax:
    a.set_xlabel("Longitude")
    a.set_ylabel("Latitude")
    a.set_aspect(1 / np.cos(np.radians(28.6)))

os.makedirs("reports/figures", exist_ok=True)
plt.tight_layout()
plt.savefig("reports/figures/station_hotspots.png", dpi=150)
print("saved reports/figures/station_hotspots.png")

print("\nStations least predictable from their neighbours:")
print(d.reindex(d["resid"].abs().sort_values(ascending=False).index)
        .head(10)[["name", "pm25_mean", "pred_loo", "resid"]].round(1).to_string(index=False))
print("\nMedian absolute residual:", round(float(d["resid"].abs().median()), 1), "ug/m3")