import os
import requests
import pandas as pd

# Central Delhi point; change dates here if needed
LAT, LON = 28.61, 77.21
START, END = "2025-10-01", "2025-11-29"
OUTPUT = "data/processed/weather_daily_delhi.csv"

params = {
    "latitude": LAT,
    "longitude": LON,
    "start_date": START,
    "end_date": END,
    "hourly": ",".join([
        "temperature_2m",
        "relative_humidity_2m",
        "surface_pressure",
        "precipitation",
        "wind_speed_10m",
    ]),
    "wind_speed_unit": "ms",
    "timezone": "UTC",  # matches the UTC dates in the OpenAQ data
}

r = requests.get("https://archive-api.open-meteo.com/v1/archive",
                 params=params, timeout=60)
r.raise_for_status()
h = pd.DataFrame(r.json()["hourly"])
h["time"] = pd.to_datetime(h["time"])
h = h.set_index("time")

daily = pd.DataFrame({
    "temp_c": h["temperature_2m"].resample("D").mean(),
    "temp_max_c": h["temperature_2m"].resample("D").max(),
    "temp_min_c": h["temperature_2m"].resample("D").min(),
    "rh": h["relative_humidity_2m"].resample("D").mean(),
    "wind_speed": h["wind_speed_10m"].resample("D").mean(),
    "pressure_hpa": h["surface_pressure"].resample("D").mean(),
    "precip_mm": h["precipitation"].resample("D").sum(),
})
daily.index.name = "date"

os.makedirs("data/processed", exist_ok=True)
daily.to_csv(OUTPUT)
print(daily.head())
print(daily.describe().T[["min", "mean", "max"]])
print(f"Saved {len(daily)} days to {OUTPUT}")