import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

ALPHA = 0.10   # 90% intervals

df = pd.read_csv("data/processed/pm25_dedup.csv", parse_dates=["date"])
coords = df.groupby("location_id")[["lat", "lon"]].first().reset_index()

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
    z = z.merge(coords, on="location_id")
    z["year"] = z["date"].dt.year
    z["month"] = z["date"].dt.month
    return z.dropna(subset=["target", "pm_today"]).reset_index(drop=True)


def fit_q(train, q):
    m = HistGradientBoostingRegressor(loss="quantile", quantile=q, max_iter=300,
                                      learning_rate=0.05, random_state=0)
    return m.fit(train[FEATS], train["target"] - train["pm_today"])


def predict_int(models, d):
    base = d["pm_today"].to_numpy()
    lo = base + models[0.05].predict(d[FEATS])
    mid = base + models[0.5].predict(d[FEATS])
    hi = base + models[0.95].predict(d[FEATS])
    return np.minimum(lo, hi), mid, np.maximum(lo, hi)


rows, points = [], []
for h in (1, 3):
    dh = build_h(h)
    dh["week"] = dh["date"].dt.day_of_year // 7
    tr22 = dh[(dh["year"] == 2022) & (dh["month"] <= 10)]
    train = tr22[tr22["week"] % 4 < 2]          # weeks 0-1 of every 4: training
    cal = tr22[tr22["week"] % 4 == 2]           # calibration weeks
    t25 = dh[dh["year"] == 2025]
    models = {q: fit_q(train, q) for q in (0.05, 0.5, 0.95)}

    # conformalised quantile regression correction (calibrated on 2022 weeks)
    lo_c, _, hi_c = predict_int(models, cal)
    yc = cal["target"].to_numpy()
    scores = np.maximum(lo_c - yc, yc - hi_c)
    k = min(int(np.ceil((len(cal) + 1) * (1 - ALPHA))), len(cal))
    qhat = float(np.sort(scores)[k - 1])

    # persistence baseline: yesterday's value + empirical quantiles of past changes
    e = (train["target"] - train["pm_today"]).to_numpy()
    p_lo, p_hi = np.quantile(e, [ALPHA / 2, 1 - ALPHA / 2])

    sets = {
        "2022 other weeks (no shift)": tr22[tr22["week"] % 4 == 3],
        "2025 Jan-Oct shared stations": t25[(t25["month"] <= 10) & t25["location_id"].isin(shared)],
        "2025 Jan-Oct new stations": t25[(t25["month"] <= 10) & t25["location_id"].isin(new25)],
        "2025 Nov shared stations": t25[(t25["month"] == 11) & t25["location_id"].isin(shared)],
    }
    for name, te in sets.items():
        y = te["target"].to_numpy()
        base = te["pm_today"].to_numpy()
        lo, mid, hi = predict_int(models, te)
        methods = {
            "persistence +/- empirical band": (np.maximum(base + p_lo, 0), base + p_hi),
            "quantile model (raw)": (np.maximum(lo, 0), hi),
            "quantile model + conformal": (np.maximum(lo - qhat, 0), hi + qhat),
        }
        for mname, (l, u) in methods.items():
            rows.append({"horizon": h, "test set": name, "method": mname, "n": len(te),
                         "coverage": round(float(np.mean((y >= l) & (y <= u))), 3),
                         "width": round(float(np.mean(u - l)), 1)})
        points.append({"horizon": h, "test set": name,
                       "MAE persistence": round(float(np.mean(np.abs(y - base))), 1),
                       "MAE median model": round(float(np.mean(np.abs(y - mid))), 1)})

    # coverage by region and period (2025 Jan-Oct, all stations, conformal interval)
    t = t25[t25["month"] <= 10].copy()
    lo, mid, hi = predict_int(models, t)
    l, u = np.maximum(lo - qhat, 0), hi + qhat
    t["covered"] = (t["target"] >= l) & (t["target"] <= u)
    t["width"] = u - l
    t["dist_km"] = 111 * np.sqrt((t["lat"] - 28.6139) ** 2
                                 + ((t["lon"] - 77.2090) * np.cos(np.radians(28.6))) ** 2)
    t["zone"] = pd.cut(t["dist_km"], [0, 10, 20, 1000],
                       labels=["inner <10 km", "middle 10-20 km", "outer >20 km"])
    t["period"] = np.where(t["month"] <= 3, "Jan-Mar", np.where(t["month"] <= 9, "Apr-Sep", "Oct"))
    for col in ("zone", "period"):
        g = t.groupby(col, observed=True).agg(
            stations=("location_id", "nunique"), rows=("covered", "size"),
            coverage=("covered", "mean"), width=("width", "mean")).round(2)
        print(f"\n--- horizon {h} day(s): conformal 90% interval coverage by {col} (2025 Jan-Oct) ---")
        print(g.to_string())

print("\n=== 90% intervals: coverage should be about 0.90 ===")
print(pd.DataFrame(rows).to_string(index=False))
print("\n=== Point forecast MAE (median model vs persistence) ===")
print(pd.DataFrame(points).to_string(index=False))