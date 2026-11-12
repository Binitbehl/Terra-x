import duckdb

con = duckdb.connect("data/processed/terra.duckdb")

con.execute("""
CREATE OR REPLACE TABLE station_obs AS
SELECT location_id, name, lat, lon, sensor_id,
       CAST(date AS DATE) AS date, pm25
FROM read_csv_auto('data/raw/openaq_pm25_2022_2025.csv')
WHERE pm25 BETWEEN 0 AND 1000
""")

con.execute("""
CREATE OR REPLACE TABLE stations AS
SELECT location_id, ANY_VALUE(name) AS name,
       ANY_VALUE(lat) AS lat, ANY_VALUE(lon) AS lon
FROM station_obs GROUP BY location_id
""")

con.execute("""
CREATE OR REPLACE TABLE weather_daily AS
SELECT CAST(date AS DATE) AS date, temp_c, temp_max_c, temp_min_c,
       rh, wind_speed, pressure_hpa, precip_mm
FROM read_csv_auto('data/processed/weather_daily_delhi_2022_2025.csv')
""")

for t in ("station_obs", "stations", "weather_daily"):
    n = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    print(t, n, "rows")
con.close()