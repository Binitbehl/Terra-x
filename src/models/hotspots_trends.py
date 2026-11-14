import numpy as np
import pandas as pd
from scipy.stats import spearmanr, wilcoxon

pm = pd.read_csv("data/processed/pm25_dedup.csv", parse_dates=["date"])
pm["year"], pm["month"] = pm["date"].dt.year, pm["date"].dt.month
coords = pm.groupby("location_id")[["lat", "lon"]].first()
names = pm.groupby("location_id")["name"].first() if "name" in pm.columns else None
rng = np.random.default_rng(0)


def haversine(lat, lon):
    la, lo = np.radians(lat), np.radians(lon)
    dlat, dlon = la[:, None] - la[None, :], lo[:, None] - lo[None, :]
    a = np.sin(dlat / 2) ** 2 + np.cos(la)[:, None] * np.cos(la)[None, :] * np.sin(dlon / 2) ** 2
    return 6371 * 2 * np.arcsin(np.sqrt(a))


def knn_weights(c, k=5):
    D = haversine(c["lat"].to_numpy(), c["lon"].to_numpy())
    np.fill_diagonal(D, np.inf)
    W = np.zeros_like(D)
    for i, row in enumerate(np.argsort(D, axis=1)[:, :k]):
        W[i, row] = 1
    return W


def morans_i(x, W, n_perm=999):
    Wr = W / W.sum(1, keepdims=True)

    def stat(v):
        z = v - v.mean()
        return (z @ Wr @ z) / (z @ z)

    obs = stat(x)
    perm = np.array([stat(rng.permutation(x)) for _ in range(n_perm)])
    return obs, (1 + (perm >= obs).sum()) / (n_perm + 1)


def gi_star(x, W):
    n = len(x)
    Ws = W + np.eye(n)
    wi = Ws.sum(1)
    xb, s = x.mean(), np.sqrt((x ** 2).mean() - x.mean() ** 2)
    return (Ws @ x - xb * wi) / (s * np.sqrt((n * (Ws ** 2).sum(1) - wi ** 2) / (n - 1)))


SEASONS = {"winter (Jan-Feb)": [1, 2], "pre-monsoon (Mar-May)": [3, 4, 5],
           "monsoon (Jun-Sep)": [6, 7, 8, 9], "post-monsoon (Oct-Nov)": [10, 11]}

print("=== 1) Spatial clustering of station-mean PM2.5, 2025 (k=5 nearest neighbours) ===")
season_means = {}
for sname, months in SEASONS.items():
    sub = pm[(pm.year == 2025) & pm.month.isin(months)]
    g = sub.groupby("location_id")["pm25"].agg(["mean", "count"])
    g = g[g["count"] >= 15]
    c = coords.loc[g.index]
    W = knn_weights(c)
    x = g["mean"].to_numpy()
    I, p = morans_i(x, W)
    z = gi_star(x, W)
    season_means[sname] = g["mean"]
    print(f"\n{sname}: {len(g)} stations, mean {x.mean():.1f}, range {x.min():.0f}-{x.max():.0f}, "
          f"Moran's I = {I:.2f} (p = {p:.3f})")
    out = pd.DataFrame({"location_id": g.index, "mean_pm25": x.round(1), "gi_z": z.round(2)})
    if names is not None:
        out.insert(1, "name", names.loc[g.index].to_numpy())
    hot = out[out.gi_z > 1.96].sort_values("gi_z", ascending=False)
    cold = out[out.gi_z < -1.96].sort_values("gi_z")
    print(f"  significant hot spots (z > 1.96): {len(hot)}; cold spots (z < -1.96): {len(cold)}")
    if len(hot):
        print(hot.head(5).to_string(index=False))

print("\n=== 2) Do station rankings persist across seasons? (Spearman, 2025) ===")
sm = pd.DataFrame(season_means)
print("stations per season:", sm.notna().sum().to_dict())
print("(pairwise: only stations present in both seasons; winter dropped, too few stations)")
sm = sm.drop(columns=["winter (Jan-Feb)"])
print(sm.corr(method="spearman").round(2).to_string())
print("stations in each pair:")
print(sm.notna().astype(int).T.dot(sm.notna().astype(int)).to_string())

print("\n=== 3) Year-on-year comparison, shared stations (>= 15 days in the month both years) ===")
rows = []
for m in range(1, 11):
    a = pm[(pm.year == 2022) & (pm.month == m)].groupby("location_id")["pm25"].agg(["mean", "count"])
    b = pm[(pm.year == 2025) & (pm.month == m)].groupby("location_id")["pm25"].agg(["mean", "count"])
    j = a.join(b, suffixes=("22", "25"), how="inner")
    j = j[(j["count22"] >= 15) & (j["count25"] >= 15)]
    if len(j) < 6:
        continue
    diff = (j["mean25"] - j["mean22"]).to_numpy()
    boots = [np.median(rng.choice(diff, len(diff))) for _ in range(1000)]
    lo, hi = np.percentile(boots, [2.5, 97.5])
    rows.append({"month": m, "stations": len(j), "mean_2022": round(j["mean22"].mean(), 1),
                 "mean_2025": round(j["mean25"].mean(), 1),
                 "median_change": round(float(np.median(diff)), 1),
                 "ci_low": round(lo, 1), "ci_high": round(hi, 1),
                 "lower_in_2025": int((diff < 0).sum()),
                 "wilcoxon_p": round(float(wilcoxon(diff).pvalue), 4)})
print(pd.DataFrame(rows).to_string(index=False))