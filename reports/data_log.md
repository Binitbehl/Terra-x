# Data log

## Data sources and processing
- OpenAQ v3 API, daily PM2.5 per sensor, Delhi box 76.84,28.40,77.35,28.88. Oct-Nov 2025 test download, then 2022-2025 in yearly chunks (21,545 raw rows after cleaning, 58 station IDs).
- Cleaning: negative values and values > 1000 ug/m3 removed.
- De-duplication (Finding 14): station IDs relabelled between 2022 and 2025 merged via src/process/station_merge.csv; output data/processed/pm25_dedup.csv (21,269 rows, 53 stations). All models and the DuckDB database use this file.
- Weather: Open-Meteo historical archive, one point (28.61, 77.21), hourly to daily, UTC, 2022-01-01 to 2025-11-29. ERA5 (Oct 2025 only; multi-year requests queued) used for boundary layer height in Findings 2-4.
- Station features: Google Earth Engine, 1 km buffer around each station (ESA WorldCover, MODIS NDVI and daytime LST, GHSL population, SRTM elevation). Extracted for 58 IDs before de-duplication.
- Database: DuckDB (data/processed/terra.duckdb) with station_obs, stations, weather_daily.

## OpenAQ PM2.5, Delhi region, 2025-10-01 to 2025-11-29
- Source: OpenAQ v3 API, daily aggregates per sensor
- Bounding box: 76.84,28.40,77.35,28.88
- Raw: 3030 rows, 53 sensors
- Removed: negative values and values > 1000 ug/m3 (sensor errors)
- Coverage: most stations have 60/60 days; some have gaps (min 3 days)
- Note: box includes Gurugram, Faridabad, Noida, Ghaziabad stations

## Finding 1 (Oct-Nov 2025, Delhi, 60 days)
- Raw correlations of PM2.5 with temperature, humidity, pressure are strong (|r| 0.5-0.65)
  but mostly reflect a shared seasonal trend.
- After differencing/detrending, all |r| < 0.3.
- Baselines: mean MAE 66.5, persistence MAE 31.1 ug/m3.
- Limitation: 60 days, one season, one weather point; no boundary layer height yet.

## Finding 2 (Oct 2025, Delhi, 31 days)
- Wind speed: consistently negative with PM2.5 (raw -0.52, detrended -0.30).
- BLH max: positive (+0.43 raw, +0.42 detrended), opposite to dilution physics.
  Not explained by seasonal drift. Hypotheses: emission-event confounding
  (Diwali, stubble burning), ERA5 BLH accuracy in heavy smog. Untested.
- Limitation: ~25 independent points, 9 variables tested -> chance correlations likely.

## Finding 3 (Oct 2025, Delhi)
- Wind speed is the only variable consistently negative across raw, detrended
  and Spearman analyses (-0.30 to -0.53).
- BLH max positive in all tests (+0.41 to +0.43), likely confounded by rain/cloud
  (shallow BLH and clean air on wet days). Dry-day check pending.
- temp_min_c changes sign between raw (-0.33) and detrended (+0.58): unreliable.
- 31 days is too short to separate meteorology from seasonal and event effects.

## Finding 4 (Oct 2025, Delhi, 26 dry days)
- Wind speed is the strongest and most robust negative correlate (-0.58).
- BLH max falls from +0.43 (all days) to +0.25 (dry days): rain/cloud confounding
  explained most of the unexpected positive sign. Residual not significant.
- Conclusion: in this month, wind is the only reliable meteorological signal.

## Finding 5: OpenAQ station coverage (Delhi box)
- Jan-Oct 2022: 39-44 stations. Nov 2022-2024: 1-2 stations. 2025: 51-53.
- Citywide median is not comparable across years; track n_sensors.
- Cause: old station IDs end Oct 2022 and new IDs start 2025-02-18 (Finding 14), suggesting a feed/ID change at the source rather than station outages (hypothesis, not verified).
- Design consequence: period-shift test 2022 -> 2025, restricted to Jan-Oct.

## Finding 6: Generalization baselines for next-day PM2.5 (Delhi; updated after de-duplication)
- Setup: gradient-boosted trees trained on Jan-Oct 2022; features are today's PM2.5, weather (one point for all Delhi), season, lat/lon. Metric: MAE (ug/m3).
- Persistence ("tomorrow = today") is strong: 17.8 vs 34.1 for a seasonal average on unseen period.
- Model (level) vs persistence: unseen period 20.2 vs 17.8; place + period (9 stations) 17.4 vs 14.1; unseen season (Nov 2025) 47.1 vs 40.1. The model loses whenever time is held out.
- Unseen place (station hold-out) is the only win, 21.0 vs 29.2, but it is optimistic: held-out stations share dates and weather with training stations.
- Delta target (predict change from today) helps in every test (19.6, 16.5, 46.3) but still does not beat persistence.
- Before de-duplication (superseded): place + period used 14 stations, 18.3 vs 16.0.
- Limitations: one weather point, perfect next-day weather assumed, one training year, no confidence intervals, no 2023-2024 data.
- Next: absolute-error loss, feature ablation, longer horizons, stations without history.

## Finding 7: What helps beat persistence (ablation, absolute-error loss, delta target; updated after de-duplication)
- Autocorrelation of PM2.5 (today vs tomorrow): 0.68 in 2022, 0.80 in 2025. Yesterday is less informative in 2022, so a 2022-trained model underuses it.
- Absolute-error loss (matches MAE) beats squared error: 19.6 -> 16.8 (unseen period), 16.5 -> 14.5 (place + period).
- Only next-day weather helps: MAE 16.9 vs persistence 17.8 (unseen period); same-day weather adds only ~0.3 (17.5 -> 17.2).
- Place + period (9 stations): no model beats persistence (best 14.2 vs 14.1). Correction: the earlier gain (15.4 vs 16.0) was an artefact of relabelled stations (Finding 14).
- Unseen season (Nov 2025): history or season features alone are far worse than persistence (76.1, 75.5 vs 40.1); next-day weather repairs most of it (42.8) but still does not beat persistence. Hypothesis: mean reversion learned in 2022 fails in sustained November episodes.
- Lat/lon does not help on unseen stations (14.5 vs 14.2) or unseen period (16.8 vs 16.9).
- Caveats: gains are ~5%, one split, no confidence intervals; next-day weather assumes a perfect forecast.

## Finding 8: Gain over persistence by forecast horizon (95% bootstrap CI, days resampled; updated after de-duplication)
- Persistence MAE (unseen period): 17.8 (1 day), 22.5 (2 days), 24.6 (3 days).
- Model (history + weather + target-day weather, delta target, absolute-error loss) vs persistence, day-averaged difference:
  - 1 day: -1.79 [-3.20, -0.39] (unseen period); +0.03 [-1.49, +1.38] (place + period, 9 stations)
  - 2 days: -1.25 [-3.28, +0.60]; +0.66 [-1.41, +2.51]
  - 3 days: -3.24 [-5.67, -0.93]; -0.08 [-2.69, +2.24]
- Reliable gains: 1-day and 3-day unseen period (3-day: 24.6 -> 22.5 MAE). 2-day not significant.
- Place + period: no gain at any horizon. Earlier gains (14 stations) were an artefact of relabelled stations (Finding 14).
- Gain does not grow monotonically (2-day not significant).
- Caveats: target-day weather is actual weather (upper bound); bootstrap ignores
  day-to-day correlation so intervals are likely narrow; six comparisons, no correction;
  MAE columns are station-day averages while intervals are day-averaged.

## Finding 9: Seasonality, year comparison and robust weather signal (OpenAQ, Open-Meteo, DuckDB)
- Repeatable seasonal cycle each year: winter peak (150-250 ug/m3), monsoon low (30-40).
- Raw correlations with weather (temp -0.55 to -0.72, wind -0.27 to -0.44) are dominated by seasonality.
- After removing calendar-month means (days with 30+ stations): wind stays negative (-0.28 in 2022, -0.18 in 2025); temperature falls to ~0 (+0.08, +0.13).
- Wind is the only robust weather correlate, but explains only ~3-8% of daily variance. Day-to-day correlation means true uncertainty is wider than naive p-values.
- Same 39 stations, 2022 vs 2025: Feb-Sep lower in 2025 by 8-36%; Oct +71% (63 -> 108). One year per side, so not a trend. Jan, Nov and Dec comparisons are invalid (1-2 stations in one year). Computed before de-duplication (43 stations are now shared); not rerun.
- Highest Oct-Nov 2025 means: north/northwest Delhi (Bawana, Wazirpur, Jahangirpuri, Rohini, Mundka, Ashok Vihar) and Anand Vihar, Loni, 190-220 ug/m3.
- GK1 (Oberoi Terrace, 46 days, no agency label) ranks first at 235.8; may be a low-cost sensor, unverified.
- Rank differences among the top ten are small vs day-to-day variability.

## Finding 10: Station features, urban heat and pollution (58 station IDs, Earth Engine)
- Features per station (1 km buffer): ESA WorldCover fractions, MODIS NDVI and daytime LST, GHSL population, SRTM elevation.
- Summer LST: tree cover -0.78 (Spearman), crop +0.50, NDVI -0.50, built-up +0.29, pop density +0.01. Most built-up third only +0.68 C warmer than least built-up third (winter +0.59 C).
- Vegetation, not built-up area, is the main control on daytime LST. Weak UHI likely due to no rural reference, 1 km pixels shared by stations, clear-sky daytime-only MODIS. Night LST not yet tested.
- Regression of LST on land use (R2 0.31) unstable: collinear predictors, standardised coefficient >1 for NDVI.
- Station mean PM2.5 correlates most consistently with population density (+0.42 Oct-Nov, +0.39 Feb-Sep); built-up +0.23/+0.33, NDVI -0.24/-0.32.
- Caveats: n=43-51 stations, spatial autocorrelation, 16 correlations tested without correction; computed before de-duplication (the four relabelled stations were counted under old IDs but feature values are identical).

## Finding 11: Can static features predict station mean PM2.5 at unseen stations? (Ridge, cross-validated; updated after de-duplication)
- Oct-Nov 2025 (n=50, std of station means 39.9 ug/m3): leave-one-station-out MAE 29.9 vs mean baseline 32.7 (+9%); held-out regions 36.9 vs 35.0 (-5%).
- Feb-Sep 2025 (n=42, std 9.8): leave-one-out 7.3 vs 7.5 (+4%); held-out regions 7.7 vs 8.1 (+5%); within noise given the small spread.
- Conclusion: built-up fraction, vegetation, land surface temperature, population density and elevation (1 km) give no detectable improvement over the average of other stations in Oct-Nov when whole regions are held out.
- Correlations of ~0.3-0.4 (Finding 10) are too weak to predict at n~50.
- Before de-duplication: n=51/43; +9%/-5% and +2%/-2%.
- Limitations: one year of station means; small n; correlated predictors; sensor/calibration differences; spatial autocorrelation; one buffer size (1 km).

## Finding 12: Location vs land-use features for station mean PM2.5 (ridge / 4-nearest stations; updated after de-duplication)
- Oct-Nov 2025 (n=50): leave-one-out gains over the mean baseline: static features +9%, location only +7%, features + location +18%. Held-out regions: -5%, +9%, +9%.
- Feb-Sep 2025 (n=42, small spread): unstable, -1% to +8% across models and tests; no conclusion. (Before de-duplication, location only looked better at +6%/+6%, partly because the Pusa twin predicted itself.)
- In Oct-Nov, location predicts better than land-use features and generalises across held-out regions (modest +9%), pointing to a broad regional gradient.
- Land-use features help only when neighbours are available (+18% leave-one-out), not when regions are held out.
- ~80% of the Oct-Nov station-to-station spread is unexplained.
- Caveats: n~50, no CIs, single k-means region split, one year, 1 km buffer, sensor differences between stations.

## Finding 13: Where station predictions are uncertain (neighbour-based leave-one-out, Oct-Nov 2025; updated after de-duplication)
- Median absolute error of predicting a station from its 4 nearest stations: 21.6 ug/m3 (n=49, GK1 excluded, Pusa twin merged); a few stations miss by 50-90.
- Largest errors are at the edge of the region (Faridabad Sector 30 -93.5, Teri Gram -72.1, NISE Gwal Pahari +60.6), where neighbours are far away and Delhi stations are used to extrapolate.
- Four of six strongest negative residuals are CPCB-labelled stations (DTU -83.5, IHBAS -83.3, NSIT -55.8, Shadipur -47.8). Possible network/instrument/siting effect; confounded with location.
- Residual by agency (n=49, GK1 excluded): CPCB -41.6 (n=6), DPCC +16.5 (n=24), HSPCB -39.0 (n=5, edge extrapolation), IMD +9.9 (n=7), UPPCB +14.1 (n=3), IITM -17.5 (n=2).
- CPCB-vs-DPCC gap (~58 ug/m3) is large but confounded with location and based on 6 stations.
- Co-located IMD and DPCC monitors at Pusa agree closely (276 days, mean difference -1.9 ug/m3, r=0.97), so the CPCB gap is more likely siting/location than instrument bias (hypothesis; no co-located CPCB pair available).
- GK1 (Oberoi Terrace) is +66.9 above its neighbours (235.8 vs 168.9); 46 days, no agency label, may be a low-cost sensor (unverified).
- Duplicate/relabelled station IDs were found and merged (Finding 14); conclusions here were unchanged.
- Implication: spatial uncertainty is larger at the periphery and where stations are sparse; measurement differences between networks may contribute.

## Finding 14: Robustness to merging relabelled stations (PM2.5 de-duplication)
- Four stations were relabelled between 2022 and 2025 (new OpenAQ IDs, same site): Anand Vihar (90 m apart), ITO, Punjabi Bagh, R K Puram (0 m). Pusa IMD and DPCC are co-located (r=0.97) and were merged for station-level tests.
- All old IDs end Oct 2022 and all new IDs start 2025-02-18: consistent with a feed/ID change rather than station outages (hypothesis, not verified).
- Stations after merging: 44 (2022), 52 (2025), 43 shared (was 39), 9 new in 2025 (was 14), 1 only in 2022 (was 5). Four of the 14 earlier "unseen" stations had been seen in training under old IDs.
- Unseen-period results hold: gain over persistence -1.79 [-3.20, -0.39] at 1 day, -3.24 [-5.67, -0.93] at 3 days (day-averaged MAE difference, ug/m3).
- Place + period results do not hold: on the 9 truly unseen stations, model minus persistence is +0.03 [-1.49, 1.38] (1 day), +0.66 [-1.41, 2.51] (2 days), -0.08 [-2.69, 2.24] (3 days). Best ablation model 14.2 vs persistence 14.1.
- Station-level Oct-Nov results unchanged (n=50): location only +9% and features only -5% with regions held out; features + location +18% leave-one-out.
- Station-level Feb-Sep results unstable (-1% to +8% across tests, station spread 9.8 ug/m3): no conclusion drawn.
- Agency residuals unchanged: CPCB -41.6 (n=6), DPCC +16.5 (n=24), HSPCB -39.0 (n=5), IMD +9.9 (n=7).
- Lesson: duplicate station IDs inflated apparent generalisation to unseen places; de-duplicate before any station hold-out.

## Open items
- Prediction intervals for daily forecasts and coverage by region (edge vs central stations).
- Rerun Finding 9 same-station comparison and Finding 10 correlations on de-duplicated stations (43 shared).
- Check whether the 2022 -> 2025 ID change is documented by OpenAQ.
- Verify GK1 sensor type; rerun station tests with and without it.
- Night-time LST and a regional grid for a proper urban heat island map.
- ERA5 multi-year boundary layer height (requests queued) to test BLH in the forecasting model.