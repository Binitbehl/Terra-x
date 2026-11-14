import os

import pandas as pd
import pydeck as pdk
import streamlit as st

st.set_page_config(page_title="TERRA-X Delhi", layout="wide")


@st.cache_data
def load():
    pm = pd.read_csv("data/processed/pm25_dedup.csv", parse_dates=["date"])
    if "name" not in pm.columns:
        pm["name"] = pm["location_id"].astype(str)
    return pm


pm = load()
dmin, dmax = pm["date"].min().date(), pm["date"].max().date()

st.title("TERRA-X: Delhi PM2.5 explorer")
st.caption("Daily PM2.5 from OpenAQ ground stations. Research prototype, not for health decisions.")

with st.sidebar:
    st.header("Filters")
    start, end = st.date_input("Date range", value=(pd.Timestamp("2025-10-01").date(), dmax),
                               min_value=dmin, max_value=dmax)
    min_days = st.slider("Minimum days per station", 1, 60, 15)
    vmax = st.slider("Colour scale max (ug/m3)", 50, 300, 200, step=10)

sub = pm[(pm["date"] >= pd.Timestamp(start)) & (pm["date"] <= pd.Timestamp(end))]
tab_map, tab_ts, tab_cov, tab_find = st.tabs(["Map", "Time series", "Coverage", "Findings"])

# ---------- map ----------
with tab_map:
    g = (sub.groupby("location_id")
            .agg(name=("name", "first"), lat=("lat", "first"), lon=("lon", "first"),
                 mean_pm25=("pm25", "mean"), days=("pm25", "count"))
            .reset_index())
    g = g[g["days"] >= min_days]
    if g.empty:
        st.warning("No station has that many days in this period. Widen the date range or lower the minimum.")
    else:
        t = (g["mean_pm25"] / vmax).clip(0, 1)
        g["color"] = [[int(255 + (128 - 255) * x), int(237 + (0 - 237) * x), int(160 + (38 - 160) * x), 220]
                      for x in t]
        g["mean_txt"] = g["mean_pm25"].round(1).astype(str)
        layer = pdk.Layer("ScatterplotLayer", data=g, get_position="[lon, lat]",
                          get_fill_color="color", get_radius=900, pickable=True,
                          stroked=True, get_line_color=[60, 60, 60], line_width_min_pixels=1)
        view = pdk.ViewState(latitude=float(g["lat"].mean()), longitude=float(g["lon"].mean()), zoom=9.3)
        st.pydeck_chart(pdk.Deck(layers=[layer], initial_view_state=view,
                                 tooltip={"text": "{name}\nMean PM2.5: {mean_txt} ug/m3\nDays: {days}"}))
        c1, c2, c3 = st.columns(3)
        c1.metric("Stations shown", len(g))
        c2.metric("Mean of station means", f"{g['mean_pm25'].mean():.1f}")
        c3.metric("Range", f"{g['mean_pm25'].min():.0f} to {g['mean_pm25'].max():.0f}")
        st.dataframe(g.sort_values("mean_pm25", ascending=False)
                       [["name", "mean_pm25", "days"]].round(1), use_container_width=True)
        st.caption("Station means use different numbers of days; agencies and sensor types differ.")

# ---------- time series ----------
with tab_ts:
    wide = sub.pivot_table(index="date", columns="name", values="pm25", aggfunc="mean")
    chosen = st.multiselect("Stations to add", sorted(wide.columns), default=[])
    smooth = st.checkbox("7-day rolling mean", value=True)
    out = pd.DataFrame({"citywide median": wide.median(axis=1)})
    for c in chosen:
        out[c] = wide[c]
    if smooth:
        out = out.rolling(7, min_periods=3).mean()
    st.line_chart(out)
    st.caption("Citywide median uses whichever stations reported that day, so its meaning changes "
               "when station numbers change (see Coverage).")

# ---------- coverage ----------
with tab_cov:
    cov = pm.groupby("date")["location_id"].nunique().rename("stations reporting")
    st.area_chart(cov)
    st.warning("Between Nov 2022 and Jan 2025 only 1-2 stations report, so multi-year comparisons "
               "and any citywide trend in that window are not reliable.")

# ---------- findings ----------
with tab_find:
    if os.path.exists("reports/findings.md"):
        st.markdown(open("reports/findings.md", encoding="utf-8").read())
    path = "reports/tables/fused_ablation_compare.csv"
    if os.path.exists(path):
        st.subheader("Satellite ablation: paired differences (negative = first model better)")
        st.dataframe(pd.read_csv(path), use_container_width=True)