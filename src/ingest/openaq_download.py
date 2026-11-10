import os
import time
import requests
import pandas as pd
from dotenv import load_dotenv

load_dotenv()
HEADERS = {"X-API-Key": os.getenv("OPENAQ_API_KEY")}
BASE = "https://api.openaq.org/v3"

# Settings: min_lon, min_lat, max_lon, max_lat (Delhi region)
BBOX = "76.84,28.40,77.35,28.88"
PM25_ID = 2  # OpenAQ parameter id for PM2.5
DATE_FROM = "2025-10-01T00:00:00Z"
DATE_TO = "2025-11-30T23:59:59Z"
OUTPUT = "data/raw/openaq_pm25_2025_10_11.csv"


def get(url, params=None, retries=3):
    """GET with retries. Returns the results list, or None if it keeps failing."""
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, params=params, timeout=60)
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(2 * (attempt + 1))  # wait longer each retry
                continue
            r.raise_for_status()
            time.sleep(1)  # stay under the rate limit
            return r.json()["results"]
        except requests.exceptions.RequestException as e:
            print(f"  request failed ({e.__class__.__name__}), attempt {attempt + 1}")
            time.sleep(2 * (attempt + 1))
    return None  # give up on this request


if not HEADERS["X-API-Key"]:
    raise SystemExit("API key not found. Check your .env file.")

locations = get(f"{BASE}/locations",
                {"bbox": BBOX, "parameters_id": PM25_ID, "limit": 100})
if locations is None:
    raise SystemExit("Could not fetch locations. Try again in a few minutes.")
print(f"Found {len(locations)} locations")

rows = []
skipped = 0
for i, loc in enumerate(locations, start=1):
    print(f"[{i}/{len(locations)}] {loc['name']}")
    for sensor in loc["sensors"]:
        if sensor["parameter"]["id"] != PM25_ID:
            continue
        days = get(f"{BASE}/sensors/{sensor['id']}/days",
                   {"date_from": DATE_FROM[:10], "date_to": DATE_TO[:10],
                    "datetime_from": DATE_FROM, "datetime_to": DATE_TO,
                    "limit": 1000})
        if days is None:
            print(f"  Skipping sensor {sensor['id']} (server error)")
            skipped += 1
            continue
        for d in days:
            rows.append({
                "location_id": loc["id"],
                "name": loc["name"],
                "lat": loc["coordinates"]["latitude"],
                "lon": loc["coordinates"]["longitude"],
                "sensor_id": sensor["id"],
                "date": d["period"]["datetimeFrom"]["utc"][:10],
                "pm25": d["value"],
            })

df = pd.DataFrame(rows)
print(f"Rows before date filter: {len(df)}")

# Safety net: keep only the requested date range
df["date"] = pd.to_datetime(df["date"])
df = df[(df["date"] >= DATE_FROM[:10]) & (df["date"] <= DATE_TO[:10])]

os.makedirs("data/raw", exist_ok=True)
df.to_csv(OUTPUT, index=False)

print(df.head())
if len(df):
    print(f"Date range: {df['date'].min().date()} to {df['date'].max().date()}")
else:
    print("WARNING: no rows in the requested date range.")
print(f"Saved {len(df)} rows from {df['sensor_id'].nunique()} sensors")
print(f"Skipped {skipped} sensors due to errors")