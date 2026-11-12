import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

# ---------- load ----------
df = pd.read_csv("data/raw/openaq_pm25_2022_2025.csv", parse_dates=["date"])
df = df[(df["pm25"] >= 0) & (df["pm25"] <= 1000)]

wide = df.pivot_table(index="date", columns="location_id", values="pm25", aggfunc="mean")
wide = wide.reindex(pd.date_range("2022-01-01", "2025-11-30"))
wide.index.name = "date"

wx_cols = ["temp_c", "rh", "wind_speed", "pressure_hpa", "precip_mm"]
wx = pd.read_csv("data/processed/weather_daily_delhi_2022_2025.csv",
                 parse_dates=["date"], index_col="date")[wx_cols]

s22 = set(df[df["date"].dt.year == 2022]["location_id"])
s25 = set(df[df["date"].dt.year == 2025]["location_id"])
shared, new25 = s22 & s25, s25 - s22

HIST = ["pm_today", "pm_lag1", "pm_mean7"]
FC = [c + "_fc" for c in wx_cols]
FEATS = HIST + wx_cols + FC


def long(frame, name):
    out = frame.reset_index().melt(id_vars="date", var_name="location_id", value_name=name)
    return out.set_index(["date", "location_id"])


def build_h(h):
    z = pd.concat([
        long(wide, "pm_today"),
        long(wide.shift(1), "pm_lag1"),
        long(wide.rolling(7, min_periods=4).mean(), "pm_mean7"),
        long(wide.shift(-h), "target"),
    ], axis=1).reset_index()
    z = z.merge(wx.reset_index(), on="date")
    z = z.merge(wx.shift(-h).add_suffix("_fc").reset_index(), on="date")
    z["year"] = z["date"].dt.year
    z["month"] = z["date"].dt.month
    return z.dropna(subset=["target", "pm_today"]).reset_index(drop=True)


def fit_delta(train, test, feats):
    m = HistGradientBoostingRegressor(loss="absolute_error", max_iter=300,
                                      learning_rate=0.05, random_state=0)
    m.fit(train[feats], train["target"] - train["pm_today"])
    return test["pm_today"].to_numpy() + m.predict(test[feats])


def mae(y, p):
    return round(float(np.mean(np.abs(np.asarray(y) - np.asarray(p)))), 1)


def day_bootstrap(test, pred, n=1000, seed=0):
    y = test["target"].to_numpy()
    diff = np.abs(y - pred) - np.abs(y - test["pm_today"].to_numpy())  # < 0: model better
    daily = pd.Series(diff).groupby(test["date"].to_numpy()).mean().to_numpy()
    rng = np.random.default_rng(seed)
    boots = [rng.choice(daily, len(daily)).mean() for _ in range(n)]
    lo, hi = np.percentile(boots, [2.5, 97.5])
    return round(float(daily.mean()), 2), round(float(lo), 2), round(float(hi), 2)


# ---------- run ----------
rows = []
for h in (1, 2, 3):
    print(f"horizon {h} day(s) ...", flush=True)
    dh = build_h(h)
    tr_all = dh[(dh.year == 2022) & (dh.month <= 10)]
    tr_sh = tr_all[tr_all.location_id.isin(shared)]
    t = dh[dh.year == 2025]
    for name, (tr, te) in {
        "1 period": (tr_sh, t[(t.month <= 10) & t.location_id.isin(shared)]),
        "3 place+period": (tr_all, t[(t.month <= 10) & t.location_id.isin(new25)]),
    }.items():
        p = fit_delta(tr, te, FEATS)
        d_mean, lo, hi = day_bootstrap(te, p)
        rows.append({"horizon_days": h, "experiment": name, "n_test": len(te),
                     "persistence": mae(te["target"], te["pm_today"]),
                     "model": mae(te["target"], p),
                     "model_minus_persist": d_mean, "ci95_low": lo, "ci95_high": hi})

print("\nHorizons; model_minus_persist < 0 means the model beats persistence.")
print("ci95 = 95% bootstrap interval resampling days.")
print(pd.DataFrame(rows).to_string(index=False))