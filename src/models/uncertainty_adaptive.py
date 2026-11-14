import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

ALPHA = 0.10     # 90% intervals
FLOOR = 20.0     # minimum scale (ug/m3) so clean days do not get tiny intervals

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
    hi = base + models[0.95].predict(d[FEATS])
    return np.minimum(lo, hi), np.maximum(lo, hi)


def level(d):
    """Recent pollution level used to scale the correction."""
    return np.maximum(d["pm_mean7"].fillna(d["pm_today"]).to_numpy(), FLOOR)


def conformal_q(scores):
    n = len(scores)
    k = min(int(np.ceil((n + 1) * (1 - ALPHA))), n)
    return float(np.sort(scores)[k - 1])


def interval_score(y, l, u):
    pen = (2 / ALPHA) * (np.maximum(l - y, 0) + np.maximum(y - u, 0))
    return float(np.mean((u - l) + pen))


rows = []
for h in (1, 3):
    dh = build_h(h)
    dh["week"] = dh["date"].dt.day_of_year // 7
    tr22 = dh[(dh["year"] == 2022) & (dh["month"] <= 10)]
    train = tr22[tr22["week"] % 4 < 2]
    cal = tr22[tr22["week"] % 4 == 2]
    t25 = dh[dh["year"] == 2025]
    models = {q: fit_q(train, q) for q in (0.05, 0.5, 0.95)}

    lo_c, hi_c = predict_int(models, cal)
    yc = cal["target"].to_numpy()
    raw_scores = np.maximum(lo_c - yc, yc - hi_c)
    q_fixed = conformal_q(raw_scores)
    q_scaled = conformal_q(raw_scores / level(cal))
    print(f"\nhorizon {h}: fixed correction {q_fixed:.1f} ug/m3; "
          f"scaled correction {q_scaled:.2f} x recent level")

    def make(d):
        lo, hi = predict_int(models, d)
        s = level(d)
        return {"fixed": (np.maximum(lo - q_fixed, 0), hi + q_fixed),
                "scaled": (np.maximum(lo - q_scaled * s, 0), hi + q_scaled * s)}

    sets = {
        "2022 other weeks (no shift)": tr22[tr22["week"] % 4 == 3],
        "2025 Jan-Oct shared stations": t25[(t25["month"] <= 10) & t25["location_id"].isin(shared)],
        "2025 Jan-Oct new stations": t25[(t25["month"] <= 10) & t25["location_id"].isin(new25)],
        "2025 Nov shared stations": t25[(t25["month"] == 11) & t25["location_id"].isin(shared)],
    }
    for name, te in sets.items():
        y = te["target"].to_numpy()
        for mname, (l, u) in make(te).items():
            rows.append({"horizon": h, "test set": name, "method": mname, "n": len(te),
                         "coverage": round(float(np.mean((y >= l) & (y <= u))), 3),
                         "width": round(float(np.mean(u - l)), 1),
                         "interval_score": round(interval_score(y, l, u), 1)})

    # coverage by period and by recent pollution level (all 2025 stations, Jan-Nov)
    t = t25.copy()
    ints = make(t)
    y = t["target"].to_numpy()
    for m_, (l, u) in ints.items():
        t[f"cov_{m_}"] = (y >= l) & (y <= u)
        t[f"w_{m_}"] = u - l
    t["period"] = np.select([t["month"] <= 3, t["month"] <= 9, t["month"] == 10],
                            ["1 Jan-Mar", "2 Apr-Sep", "3 Oct"], "4 Nov")
    t["level_bin"] = pd.cut(level(t), [0, 50, 100, 200, 10000],
                            labels=["a <50", "b 50-100", "c 100-200", "d >200"])
    for col in ("period", "level_bin"):
        g = t.groupby(col, observed=True).agg(
            rows=("cov_fixed", "size"),
            cov_fixed=("cov_fixed", "mean"), width_fixed=("w_fixed", "mean"),
            cov_scaled=("cov_scaled", "mean"), width_scaled=("w_scaled", "mean")).round(2)
        print(f"\n--- horizon {h} day(s): coverage by {col} (2025, all stations) ---")
        print(g.to_string())

print("\n=== 90% intervals: fixed vs scaled conformal (coverage target 0.90; lower interval score is better) ===")
print(pd.DataFrame(rows).to_string(index=False))