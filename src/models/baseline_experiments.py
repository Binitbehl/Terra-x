import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.model_selection import GroupKFold

# ---------- load ----------
df = pd.read_csv("data/raw/openaq_pm25_2022_2025.csv", parse_dates=["date"])
df = df[(df["pm25"] >= 0) & (df["pm25"] <= 1000)]
coords = df.groupby("location_id")[["lat", "lon"]].first().reset_index()

wide = df.pivot_table(index="date", columns="location_id", values="pm25", aggfunc="mean")
wide = wide.reindex(pd.date_range("2022-01-01", "2025-11-30"))
wide.index.name = "date"

wx_cols = ["temp_c", "rh", "wind_speed", "pressure_hpa", "precip_mm"]
wx = pd.read_csv("data/processed/weather_daily_delhi_2022_2025.csv",
                 parse_dates=["date"], index_col="date")[wx_cols]
wx_next = wx.shift(-1).add_suffix("_next")   # next-day weather (assumes a forecast)


def long(frame, name):
    out = frame.reset_index().melt(id_vars="date", var_name="location_id", value_name=name)
    return out.set_index(["date", "location_id"])


# ---------- features: predict TOMORROW's PM2.5 for each station ----------
d = pd.concat([
    long(wide, "pm_today"),
    long(wide.shift(1), "pm_lag1"),
    long(wide.rolling(7, min_periods=4).mean(), "pm_mean7"),
    long(wide.shift(-1), "target"),
], axis=1).reset_index()
d = d.merge(wx.reset_index(), on="date").merge(wx_next.reset_index(), on="date")
d = d.merge(coords, on="location_id")
d["doy_sin"] = np.sin(2 * np.pi * d["date"].dt.day_of_year / 365.25)
d["doy_cos"] = np.cos(2 * np.pi * d["date"].dt.day_of_year / 365.25)
d["year"] = d["date"].dt.year
d["month"] = d["date"].dt.month
d = d.dropna(subset=["target", "pm_today"]).reset_index(drop=True)

FEATURES = (["pm_today", "pm_lag1", "pm_mean7"] + wx_cols
            + [c + "_next" for c in wx_cols] + ["doy_sin", "doy_cos", "lat", "lon"])


def predict_all(train, test):
    kw = dict(max_iter=300, learning_rate=0.05, random_state=0)
    m_level = HistGradientBoostingRegressor(**kw).fit(train[FEATURES], train["target"])
    m_delta = HistGradientBoostingRegressor(**kw).fit(
        train[FEATURES], train["target"] - train["pm_today"])
    overall = train["target"].mean()
    month_mean = train.groupby("month")["target"].mean()
    return {
        "mean_only": np.full(len(test), overall),
        "month_mean": test["month"].map(month_mean).fillna(overall).to_numpy(),
        "persistence": test["pm_today"].to_numpy(),
        "model_level": m_level.predict(test[FEATURES]),
        "model_delta": test["pm_today"].to_numpy() + m_delta.predict(test[FEATURES]),
    }


def score(name, test, preds):
    row = {"experiment": name, "n_test": len(test)}
    y = test["target"].to_numpy()
    for k, p in preds.items():
        row[k] = round(float(np.mean(np.abs(y - p))), 1)
    return row


# ---------- splits ----------
s22 = set(d[d.year == 2022]["location_id"])
s25 = set(d[d.year == 2025]["location_id"])
shared, new25 = s22 & s25, s25 - s22
print(f"stations 2022: {len(s22)}, 2025: {len(s25)}, shared: {len(shared)}, new in 2025: {len(new25)}")

train_all = d[(d.year == 2022) & (d.month <= 10)]
train_sh = train_all[train_all.location_id.isin(shared)]
t25 = d[d.year == 2025]
rows = []

# 1. unseen period
te = t25[(t25.month <= 10) & t25.location_id.isin(shared)]
rows.append(score("1 unseen period", te, predict_all(train_sh, te)))

# 2. unseen place (5-fold, held-out stations; optimistic: shared dates)
tests, preds = [], {}
for tr_i, te_i in GroupKFold(5).split(train_all, groups=train_all["location_id"]):
    te2 = train_all.iloc[te_i]
    p = predict_all(train_all.iloc[tr_i], te2)
    tests.append(te2)
    for k, v in p.items():
        preds.setdefault(k, []).append(v)
rows.append(score("2 unseen place", pd.concat(tests),
                  {k: np.concatenate(v) for k, v in preds.items()}))

# 3. unseen place AND period
te = t25[(t25.month <= 10) & t25.location_id.isin(new25)]
rows.append(score("3 place + period", te, predict_all(train_all, te)))

# 4. unseen season (Nov 2025, shared stations)
te = t25[(t25.month == 11) & t25.location_id.isin(shared)]
rows.append(score("4 unseen season", te, predict_all(train_sh, te)))

print("\nMean absolute error (ug/m3), predicting next-day PM2.5. Lower is better.")
print(pd.DataFrame(rows).to_string(index=False))

# ---------- diagnostics ----------
x = d[d["month"] <= 10].copy()
x["persist_err"] = (x["target"] - x["pm_today"]).abs()
print("\nLevel and persistence error by year (Jan-Oct):")
print(x.groupby("year").agg(mean_pm=("target", "mean"),
                            median_pm=("target", "median"),
                            persist_mae=("persist_err", "mean")).round(1))

s = df.sort_values(["location_id", "date"]).copy()
s["same"] = s.groupby("location_id")["pm25"].diff().eq(0)
print("\nShare of days repeating the previous value exactly:")
print(s.groupby(s["date"].dt.year)["same"].mean().round(3))

# ---------- autocorrelation by year ----------
print("\nCorrelation of today's PM2.5 with tomorrow's, by year (Jan-Oct):")
for yr, g in x.groupby("year"):
    print(yr, round(g["pm_today"].corr(g["target"]), 3))

# ---------- ablation: absolute-error loss, delta target ----------
def mae(y, p):
    return round(float(np.mean(np.abs(np.asarray(y) - np.asarray(p)))), 1)

def fit_delta(train, test, feats):
    m = HistGradientBoostingRegressor(loss="absolute_error", max_iter=300,
                                      learning_rate=0.05, random_state=0)
    m.fit(train[feats], train["target"] - train["pm_today"])
    return test["pm_today"].to_numpy() + m.predict(test[feats])

exps = {
    "1 period": (train_sh, t25[(t25.month <= 10) & t25.location_id.isin(shared)]),
    "3 place+period": (train_all, t25[(t25.month <= 10) & t25.location_id.isin(new25)]),
    "4 season": (train_sh, t25[(t25.month == 11) & t25.location_id.isin(shared)]),
}
HIST = ["pm_today", "pm_lag1", "pm_mean7"]
SEAS = ["doy_sin", "doy_cos"]
WX = wx_cols
WXN = [c + "_next" for c in wx_cols]
sets = {
    "history": HIST,
    "history+season": HIST + SEAS,
    "history+weather": HIST + WX,
    "history+weather+forecast": HIST + WX + WXN,
    "all (+lat/lon)": HIST + SEAS + WX + WXN + ["lat", "lon"],
}
out = {"persistence": {k: mae(te["target"], te["pm_today"]) for k, (tr, te) in exps.items()}}
for name, feats in sets.items():
    out[name] = {k: mae(te["target"], fit_delta(tr, te, feats)) for k, (tr, te) in exps.items()}
print("\nAblation (MAE, ug/m3; delta target, absolute-error loss):")
print(pd.DataFrame(out).T.to_string())