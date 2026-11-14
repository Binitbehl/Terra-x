# TERRA-X: A Spatiotemporal Intelligence Platform for Earth Systems

Made by Binit Behl

**Research question:** can different Earth-observation sources (ground air-quality stations, weather, satellite data, land use and population) be combined to understand and predict environmental change, and how well does that carry over to places and periods the model has not seen?

**Case study:** Delhi, PM2.5, 2022-2025.

This is a student research project. Results are honest and several are negative. It is not a health or policy tool.

## Main results

| Question | Result |
|---|---|
| Can history + weather beat "tomorrow = today" (persistence)? | Slightly, for an unseen period: 1-day MAE 16.6 vs 17.8 ug/m3 (paired difference -1.2, 95% CI -2.5 to -0.0); 3-day gain larger (-3.6, CI -5.7 to -1.7). No gain at unseen stations. |
| Does it work in the smog season it never saw (Nov 2025)? | No. Nothing beat persistence (MAE 40.1). |
| Do daily satellite features (LST, NO2, aerosol index) help? | Not reliably. 7 of 16 comparisons were significant, 4 helpful and 3 harmful. Satellite data varies little between stations (spatial variation ratio 0.16-0.41). |
| Does it survive missing satellite data? | In normal conditions yes (the model barely uses it). In Nov, accuracy degrades steadily as inputs are removed: 44.0 to 56.8 MAE. |
| Can uncertainty be quantified? | Conformalized quantile intervals reach 0.93-0.96 coverage on mild shifts. Scaling the correction by recent PM2.5 level evens out coverage across pollution levels. Nov still under-covers with very wide intervals (about 205-260 ug/m3), not decision-useful. |
| Hotspots? | Weak spatial clustering (Moran's I 0.04-0.12; only post-monsoon significant, p = 0.037). Post-monsoon hot spots are a north / north-west Delhi cluster. Station rankings are moderately persistent across seasons (Spearman 0.42-0.59). |
| Land use and heat? | Summer land-surface temperature correlates with tree cover (r = -0.78) and built-up area (r = +0.29). The urban heat island among stations is small (about +0.7 C). |
| Year-on-year change 2022 vs 2025? | Apr-Sep lower in 2025, October much higher. This reverses sign within the year, so it is a comparison, not a trend. |

All findings, with numbers and caveats, are in `reports/findings.md` (Findings 1-22).

## Limitations (read these first)

- **Station coverage gap:** only 1-2 stations report Nov 2022 to Jan 2025, so multi-year trends are not possible.
- **Only 2022 and 2025** are used for experiments. Year-to-year weather variation is not separated from any trend.
- **One weather point for all of Delhi** (Open-Meteo). Weather cannot explain differences between stations.
- **Next-day weather is treated as known** (an ideal forecast). Real forecast error would make results worse.
- **Satellite data has large gaps** (day LST 52%, night LST 60%, NO2 73% of station-days), and the gaps are informative (cloud and monsoon days).
- **The "unseen place" test (Experiment 2) shares dates between training and test stations**, so its gain over persistence is inflated.
- **Bootstrap intervals are day-level** and ignore week-to-week correlation, so they are somewhat optimistic. November is a single month.
- **Relabelled and co-located stations, and low-cost sensors,** exist in the OpenAQ data. Duplicates were merged, but sensor bias was not corrected.

## Data

| Source | Used for |
|---|---|
| OpenAQ v3 API | Daily PM2.5 at 53 stations (after de-duplication) |
| Open-Meteo archive | Daily weather (temperature, humidity, wind, pressure, precipitation) |
| Google Earth Engine | Static features (land cover, elevation, NDVI, population, LST) and daily MODIS LST, Sentinel-5P NO2 and aerosol index |
| ERA5 (CDS API) | Boundary-layer height, Oct 2025 only |

No raw data is stored in this repository (`data/` is gitignored); the scripts download it.

## Repository layout

```
src/ingest/    data download (OpenAQ, Open-Meteo, ERA5, Earth Engine)
src/process/   cleaning, de-duplication, DuckDB build, SQL runner
src/models/    forecasting experiments, uncertainty, station analysis, hotspots
sql/           DuckDB queries
reports/       findings.md, figures, result tables
app/           Streamlit dashboard
```

## Setup

Python 3.13 on Windows (PowerShell).

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Create a `.env` file in the project root (never commit it):

```
OPENAQ_API_KEY=your_openaq_key
EE_PROJECT=your_google_cloud_project_id
```

Earth Engine needs a one-time `earthengine authenticate`. ERA5 needs a CDS account and `~/.cdsapirc`.

## Run order

```powershell
python src/ingest/openaq_multiyear.py
python src/ingest/openmeteo_download.py
python src/process/dedup_pm25.py
python src/process/build_db.py
python src/ingest/ee_static_features.py
python src/ingest/ee_daily_satellite.py
python src/models/baseline_experiments.py
python src/models/fused_ablation.py
python src/models/missing_data_test.py
python src/models/uncertainty_adaptive.py
python src/models/hotspots_trends.py
streamlit run app/streamlit_app.py
```

`openaq_multiyear.py` and the Earth Engine scripts take a long time (tens of minutes) and resume from cached files if stopped.

## Dashboard

`streamlit run app/streamlit_app.py` opens a local explorer: a station map for any date range, time series, a station-coverage chart that shows the data gap, and the findings log. It reads local data and is not deployed publicly.

## Methods in brief

- **Forecast target:** a station's PM2.5 at t+h (h = 1 or 3 days), predicted as the change from today's value using gradient boosting with absolute-error loss.
- **Generalization tests:** unseen period (2022 to 2025), unseen place (stations held out), unseen place and period, and unseen season (Nov 2025).
- **Uncertainty:** quantile models with conformal correction, optionally scaled by the 7-day mean level.
- **Spatial statistics:** Moran's I and Getis-Ord Gi* with 5-nearest-neighbour weights.

## Data licences and credits

Please check and follow the terms of OpenAQ, Open-Meteo, Copernicus (ERA5, Sentinel-5P), NASA (MODIS) and Google Earth Engine before reusing the data.