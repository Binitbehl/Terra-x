import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

pm = pd.read_csv("data/processed/pm25_dedup.csv", parse_dates=["date"])
coords = pm.groupby("location_id")[["lat", "lon"]].first().reset_index()
DATES = pd.date_range("2022-01-01", "2025-11-30")
wide = pm.pivot_table(index="date", columns="location_id", values="pm25",
                      aggfunc="mean").reindex(DATES)
wide.index.name = "date"

wx_cols = ["temp_c", "rh", "wind_speed", "pressure_hpa", "precip_mm"]
wx = pd.read_csv("data/processed/weather_daily_delhi_2022_2025.csv",
                 parse_dates=["date"], index_col="date")[wx_cols]
sat = pd.read_csv("data/processed/satellite_daily.csv", parse_dates=["date"])
SAT_VARS = ["lst_day_c", "lst_night_c", "no2_umol_m2", "aer_ai"]
sat_wide = {v: sat.pivot_table(index="date", columns="location_id", values=v)
                  .reindex(DATES).reindex(columns=wide.columns) for v in SAT_VARS}


def long(frame, name):
    out = frame.copy()
    out.index.name, out.columns.name = "date", "location_id"
    out = out.reset_index().melt(id_vars="date", var_name="location_id", value_name=name)
    out["location_id"] = out["location_id"].astype(int)
    return out.set_index(["date", "location_id"])


H = 1
parts = [long(wide, "pm_today"), long(wide.shift(1), "pm_lag1"),
         long(wide.rolling(7, min_periods=4).mean(), "pm_mean7"),
         long(wide.shift(-H), "target")]
for v in SAT_VARS:
    parts += [long(sat_wide[v], v), long(sat_wide[v].rolling(3, min_periods=1).mean(), v + "_3d")]
d = pd.concat(parts, axis=1).reset_index()
d = d.merge(wx.reset_index(), on="date").merge(
    wx.shift(-H).add_suffix("_next").reset_index(), on="date")
d = d.merge(coords, on="location_id")
d["doy_sin"] = np.sin(2 * np.pi * d["date"].dt.day_of_year / 365.25)
d["doy_cos"] = np.cos(2 * np.pi * d["date"].dt.day_of_year / 365.25)
d["year"], d["month"] = d["date"].dt.year, d["date"].dt.month
d = d.dropna(subset=["target", "pm_today"]).reset_index(drop=True)

SAT_F = [c for v in SAT_VARS for c in (v, v + "_3d")]
BASE = (["pm_today", "pm_lag1", "pm_mean7", "doy_sin", "doy_cos"] + wx_cols
        + [c + "_next" for c in wx_cols])
FULL = BASE + SAT_F


def fit(train, feats):
    m = HistGradientBoostingRegressor(loss="absolute_error", max_iter=300,
                                      learning_rate=0.05, random_state=0)
    m.fit(train[feats], train["target"] - train["pm_today"])
    return m


def mae(y, p):
    return float(np.mean(np.abs(y - p)))


def mask(test, rate, seed):
    t = test.copy()
    rng = np.random.default_rng(seed)
    for v in SAT_VARS:
        drop = rng.random(len(t)) < rate
        t.loc[drop, [v, v + "_3d"]] = np.nan
    return t


s22 = set(d[d.year == 2022]["location_id"])
s25 = set(d[d.year == 2025]["location_id"])
shared, new25 = s22 & s25, s25 - s22
tr_all = d[(d.year == 2022) & (d.month <= 10)]
tr_sh = tr_all[tr_all.location_id.isin(shared)]
t25 = d[d.year == 2025]
EXPS = {
    "1 unseen period": (tr_sh, t25[(t25.month <= 10) & t25.location_id.isin(shared)]),
    "3 place+period": (tr_all, t25[(t25.month <= 10) & t25.location_id.isin(new25)]),
    "4 unseen season": (tr_sh, t25[(t25.month == 11) & t25.location_id.isin(shared)]),
}

rand_rows, cloud_rows = [], []
for name, (tr, te) in EXPS.items():
    m_full, m_base = fit(tr, FULL), fit(tr, BASE)
    y, p0 = te["target"].to_numpy(), te["pm_today"].to_numpy()
    base_pred = m_base.predict(te[BASE]) + p0
    row = {"experiment": name, "n": len(te)}
    for rate in (0, 0.25, 0.5, 0.75, 1.0):
        seeds = [0] if rate in (0, 1.0) else range(5)
        row[f"drop {int(rate * 100)}%"] = round(np.mean(
            [mae(y, m_full.predict(mask(te, rate, s)[FULL]) + p0) for s in seeds]), 1)
    row["hist+wx (no sat)"] = round(mae(y, base_pred), 1)
    row["persistence"] = round(mae(y, p0), 1)
    rand_rows.append(row)

    full_pred = m_full.predict(te[FULL]) + p0
    present = te["lst_day_c"].notna().to_numpy()
    for label, sel in (("day LST present", present), ("day LST missing", ~present)):
        if sel.sum() == 0:
            continue
        cloud_rows.append({"experiment": name, "real data": label, "n": int(sel.sum()),
                           "mean PM2.5": round(float(y[sel].mean()), 1),
                           "hist+wx+sat": round(mae(y[sel], full_pred[sel]), 1),
                           "hist+wx": round(mae(y[sel], base_pred[sel]), 1),
                           "persistence": round(mae(y[sel], p0[sel]), 1)})

print("\n1) Random masking of satellite inputs at test time (MAE ug/m3, 1-day horizon)")
print(pd.DataFrame(rand_rows).to_string(index=False))
print("\n2) Real cloud pattern: test days split by whether day LST exists")
print(pd.DataFrame(cloud_rows).to_string(index=False))