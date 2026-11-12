import os
import time
import requests
import pandas as pd
from dotenv import load_dotenv

load_dotenv()
HEADERS = {"X-API-Key": os.getenv("OPENAQ_API_KEY")}
BASE = "https://api.openaq.org/v3"
BBOX = "76.84,28.40,77.35,28.88"
PM25_ID = 2
CHUNKS = [("2022-01-01", "2022-12-31"), ("2023-01-01", "2023-12-31"),
          ("2024-01-01", "2024-12-31"), ("2025-01-01", "2025-11-30")]
OUTPUT = "data/raw/openaq_pm25_2022_2025.csv"


def get(url, params=None, retries=3):
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, params=params, timeout=60)
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(2 * (attempt + 1))
                continue
            r.raise_for_status()
            time.sleep(1)
            return r.json()["results"]
        except requests.exceptions.RequestException as e:
            print(f"  request failed ({e.__class__.__name__}), attempt {attempt + 1}")
            time.sleep(2 * (attempt + 1))
    return None


if not HEADERS["X-API-Key"]:
    raise SystemExit("API key not found. Check your .env file.")

locations = get(f"{BASE}/locations", {"bbox": BBOX, "parameters_id": PM25_ID, "limit": 100})
if locations is None:
    raise SystemExit("Could not fetch locations.")
print(f"Found {len(locations)} locations")

rows, skipped = [], 0
for i, loc in enumerate(locations, start=1):
    print(f"[{i}/{len(locations)}] {loc['name']}")
    for sensor in loc["sensors"]:
        if sensor["parameter"]["id"] != PM25_ID:
            continue
        for d_from, d_to in CHUNKS:
            days = get(f"{BASE}/sensors/{sensor['id']}/days",
                       {"date_from": d_from, "date_to": d_to,
                        "datetime_from": f"{d_from}T00:00:00Z",
                        "datetime_to": f"{d_to}T23:59:59Z", "limit": 1000})
            if days is None:
                skipped += 1
                continue
            for d in days:
                rows.append({
                    "location_id": loc["id"], "name": loc["name"],
                    "lat": loc["coordinates"]["latitude"],
                    "lon": loc["coordinates"]["longitude"],
                    "sensor_id": sensor["id"],
                    "date": d["period"]["datetimeFrom"]["utc"][:10],
                    "pm25": d["value"],
                })

df = pd.DataFrame(rows)
df["date"] = pd.to_datetime(df["date"])
df = df[(df["date"] >= "2022-01-01") & (df["date"] <= "2025-11-30")]
df = df.drop_duplicates(["sensor_id", "date"])
os.makedirs("data/raw", exist_ok=True)
df.to_csv(OUTPUT, index=False)
print(f"Saved {len(df)} rows from {df['sensor_id'].nunique()} sensors")
print(df.groupby(df["date"].dt.year)["sensor_id"].nunique())
print(f"Failed requests: {skipped}")