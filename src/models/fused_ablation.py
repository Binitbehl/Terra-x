import os

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.model_selection import GroupKFold

# ---------- load ----------
pm = pd.read_csv("data/processed/pm25_dedup.csv", parse_dates=["date"])
coords = pm.groupby("location_id")[["lat", "lon"]].first().reset_index()
wide = pm.pivot_table(index="date", columns="location_id", values="pm25", aggfunc="mean")
DATES = pd.date_range("2022-01-01", "2025-11-30")
wide = wide.reindex(DATES)
wide.index.name = "date"

wx_cols = ["temp_c", "rh", "wind_speed", "pressure_hpa", "precip_mm"]
wx = pd.read_csv("data/processed/weather_daily_delhi_2022_2025.csv",
                 parse_dates=["date"], index_col="date")[wx_cols]

# static station features (land cover, elevation, NDVI, population, LST climatology)
stat = pd.read_csv("data/processed/station_static_features.csv")
if "location_id" not in stat.columns:
    raise SystemExit(f"No location_id column in static file. Columns: {list(stat.columns)}")
STAT_COLS = [c for c in stat.select_dtypes("number").columns
             if c not in ("location_id", "lat", "lon")]
stat = stat[["location_id"] + STAT_COLS].drop_duplicates("location_id")

# daily satellite
sat = pd.read_csv("data/processed/satellite_daily.csv", parse_dates=["date"])
SAT_VARS = ["lst_day_c", "lst_night_c", "no2_umol_m2", "aer_ai"]
sat_wide = {v: sat.pivot_table(index="date", columns="location_id", values=v)
                  .reindex(DATES) for v in SAT_VARS}
for v in SAT_VARS:
    sat_wide[v] = sat_wide[v].reindex(columns=wide.columns)


def long(frame, name):
    out = frame.copy()
    out.index.name = "date"
    out.columns.name = "location_id"
    out = out.reset_index().melt(id_vars="date", var_name="location_id", value_name=name)
    out["location_id"] = out["location_id"].astype(int)
    return out.set_index(["date", "location_id"])


# ---------- sanity check: how much do satellite variables vary between stations? ----------
print("Spatial variation check (std across stations within a day, divided by overall std).")
print("Near 0 = stations share the same value; 1 = as variable between stations as over time.")
for v in SAT_VARS:
    w = sat_wide[v]
    within = w.std(axis=1).mean()
    total = np.nanstd(w.to_numpy())
    print(f"  {v:12s} {within / total:.2f}")
print()

SAT_F = []
for v in SAT_VARS:
    SAT_F += [v, v + "_3d"]
WXN = [c + "_next" for c in wx_cols]
HIST = ["pm_today", "pm_lag1", "pm_mean7"]
WX = wx_cols + WXN + ["doy_sin", "doy_cos"]

SETS = {
    "hist+wx": HIST + WX,
    "hist+sat": HIST + SAT_F,
    "hist+wx+sat": HIST + WX + SAT_F,
    "hist+wx+static": HIST + WX + STAT_COLS,
    "hist+wx+static+sat": HIST + WX + STAT_COLS + SAT_F,
}
COMPARE = [  # (with, without, label)
    ("hist+wx+sat", "hist+wx", "satellite added to hist+wx"),
    ("hist+wx+static+sat", "hist+wx+static", "satellite added to hist+wx+static"),
    ("hist+wx", "persistence", "hist+wx vs persistence"),
    ("hist+wx+static+sat", "persistence", "full model vs persistence"),
]


def build(H):
    parts = [long(wide, "pm_today"), long(wide.shift(1), "pm_lag1"),
             long(wide.rolling(7, min_periods=4).mean(), "pm_mean7"),
             long(wide.shift(-H), "target")]
    for v in SAT_VARS:
        parts.append(long(sat_wide[v], v))
        parts.append(long(sat_wide[v].rolling(3, min_periods=1).mean(), v + "_3d"))
    d = pd.concat(parts, axis=1).reset_index()
    d = d.merge(wx.reset_index(), on="date").merge(
        wx.shift(-H).add_suffix("_next").reset_index(), on="date")
    d = d.merge(coords, on="location_id").merge(stat, on="location_id", how="left")
    d["doy_sin"] = np.sin(2 * np.pi * d["date"].dt.dayofyear / 365.25)
    d["doy_cos"] = np.cos(2 * np.pi * d["date"].dt.dayofyear / 365.25)
    d["year"], d["month"] = d["date"].dt.year, d["date"].dt.month
    return d.dropna(subset=["target", "pm_today"]).reset_index(drop=True)


def fit_predict(train, test, feats):
    m = HistGradientBoostingRegressor(loss="absolute_error", max_iter=300,
                                      learning_rate=0.05, random_state=0)
    m.fit(train[feats], train["target"] - train["pm_today"])
    return m.predict(test[feats]) + test["pm_today"].to_numpy()


def boot(test, a, b, y, n=1000, seed=0):
    """Mean of |y-a| - |y-b| with day-level bootstrap CI. Negative = a is better."""
    diff = np.abs(y - a) - np.abs(y - b)
    g = pd.DataFrame({"date": test["date"].to_numpy(), "d": diff}).groupby("date")["d"].agg(["sum", "count"])
    s, c = g["sum"].to_numpy(), g["count"].to_numpy()
    idx = np.random.default_rng(seed).integers(0, len(g), (n, len(g)))
    est = s[idx].sum(1) / c[idx].sum(1)
    return diff.mean(), *np.percentile(est, [2.5, 97.5])


mae_rows, cmp_rows = [], []
for H in (1, 3):
    d = build(H)
    s22 = set(d[d.year == 2022]["location_id"])
    s25 = set(d[d.year == 2025]["location_id"])
    shared, new25 = s22 & s25, s25 - s22
    tr_all = d[(d.year == 2022) & (d.month <= 10)]
    tr_sh = tr_all[tr_all.location_id.isin(shared)]
    t25 = d[d.year == 2025]

    exps = {
        "1 unseen period": [(tr_sh, t25[(t25.month <= 10) & t25.location_id.isin(shared)])],
        "3 place+period": [(tr_all, t25[(t25.month <= 10) & t25.location_id.isin(new25)])],
        "4 unseen season": [(tr_sh, t25[(t25.month == 11) & t25.location_id.isin(shared)])],
        "2 unseen place": [(tr_all.iloc[a], tr_all.iloc[b]) for a, b in
                           GroupKFold(5).split(tr_all, groups=tr_all["location_id"])],
    }
    for ename, splits in exps.items():
        test = pd.concat([te for _, te in splits])
        y = test["target"].to_numpy()
        preds = {"persistence": test["pm_today"].to_numpy()}
        for sname, feats in SETS.items():
            preds[sname] = np.concatenate([fit_predict(tr, te, feats) for tr, te in splits])
        row = {"horizon": H, "experiment": ename, "n": len(test),
               "lst_day%": round(100 * test["lst_day_c"].notna().mean()),
               "no2%": round(100 * test["no2_umol_m2"].notna().mean())}
        row.update({k: round(float(np.mean(np.abs(y - p))), 1) for k, p in preds.items()})
        mae_rows.append(row)
        for a, b, label in COMPARE:
            m, lo, hi = boot(test, preds[a], preds[b], y)
            cmp_rows.append({"horizon": H, "experiment": ename, "comparison": label,
                             "mean_diff": round(m, 2), "ci_low": round(lo, 2), "ci_high": round(hi, 2)})
        print(f"done H={H} {ename}", flush=True)

mae = pd.DataFrame(mae_rows)
cmp_ = pd.DataFrame(cmp_rows)
os.makedirs("reports/tables", exist_ok=True)
mae.to_csv("reports/tables/fused_ablation_mae.csv", index=False)
cmp_.to_csv("reports/tables/fused_ablation_compare.csv", index=False)
print("\nMAE (ug/m3), lower is better:")
print(mae.to_string(index=False))
print("\nPaired difference in absolute error (negative = first model better), 95% day-level CI:")
print(cmp_.to_string(index=False))