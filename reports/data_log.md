# Data log

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
- Cause unknown (data gap vs ingestion/sensor-ID change).
- Design consequence: period-shift test 2022 -> 2025, restricted to Jan-Oct.

## Finding 6: Generalization baselines for next-day PM2.5 (Delhi)
- Setup: gradient-boosted trees trained on Jan-Oct 2022; features are today's PM2.5, weather (one point for all Delhi), season, lat/lon. Metric: MAE (ug/m3).
- Persistence ("tomorrow = today") is strong: 17.7 vs 34.1 for a seasonal average on unseen period.
- Model (level) vs persistence: unseen period 20.8 vs 17.7; place + period 18.3 vs 16.0; unseen season (Nov 2025) 49.0 vs 39.6. The model loses whenever time is held out.
- Unseen place (station hold-out) is the only win, 21.2 vs 29.2, but it is optimistic: held-out stations share dates and weather with training stations.
- Delta target (predict change from today) helps in every test (19.8, 17.5, 44.0) but still does not beat persistence.
- Limitations: one weather point, perfect next-day weather assumed, one training year, no confidence intervals, no 2023-2024 data.
- Next: absolute-error loss, feature ablation, longer horizons, stations without history.

## Finding 7: Why the model loses to persistence across years
- Stale-value share <= 1% in all years: not a data artefact.
- Persistence MAE 29.2 (2022) vs 17.3 (2025), levels 86.6 vs 61.2: 2022 is higher and noisier.
- Delta target improves over level target in all experiments but does not beat persistence.
- Next: absolute-error loss and feature ablation; one-day horizon may simply favour persistence.