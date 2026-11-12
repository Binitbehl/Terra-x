-- 1. Stations with data per year
SELECT year(date) AS yr, COUNT(DISTINCT location_id) AS stations, COUNT(*) AS rows
FROM station_obs GROUP BY yr ORDER BY yr;

-- 2. Monthly citywide mean PM2.5 and number of stations
SELECT date_trunc('month', date) AS month,
       ROUND(AVG(pm25), 1) AS mean_pm25,
       COUNT(DISTINCT location_id) AS stations
FROM station_obs GROUP BY month ORDER BY month;

-- 3. Ten most polluted stations, Oct-Nov 2025 (at least 45 days of data)
SELECT name, ROUND(AVG(pm25), 1) AS mean_pm25, COUNT(*) AS days
FROM station_obs
WHERE date BETWEEN '2025-10-01' AND '2025-11-29'
GROUP BY location_id, name
HAVING COUNT(*) >= 45
ORDER BY mean_pm25 DESC LIMIT 10;

-- 4. 7-day rolling mean and yesterday's value per station (window functions)
SELECT name, date, pm25,
       ROUND(AVG(pm25) OVER (PARTITION BY location_id ORDER BY date
             ROWS BETWEEN 6 PRECEDING AND CURRENT ROW), 1) AS rolling7,
       LAG(pm25) OVER (PARTITION BY location_id ORDER BY date) AS yesterday
FROM station_obs
WHERE location_id = (SELECT location_id FROM stations WHERE name LIKE 'Anand Vihar%' LIMIT 1)
  AND date >= '2025-10-01'
ORDER BY date LIMIT 15;

-- 5. Join PM2.5 with weather: correlation by year
SELECT year(p.date) AS yr,
       ROUND(corr(p.pm25_med, w.wind_speed), 2) AS corr_wind,
       ROUND(corr(p.pm25_med, w.temp_c), 2) AS corr_temp
FROM (SELECT date, MEDIAN(pm25) AS pm25_med FROM station_obs GROUP BY date) p
JOIN weather_daily w USING (date)
GROUP BY yr ORDER BY yr;

-- 6. Same stations only: monthly mean PM2.5, 2022 vs 2025
WITH shared AS (
  SELECT location_id FROM station_obs WHERE year(date) = 2022
  INTERSECT
  SELECT location_id FROM station_obs WHERE year(date) = 2025
)
SELECT month(date) AS m,
       ROUND(AVG(CASE WHEN year(date) = 2022 THEN pm25 END), 1) AS y2022,
       ROUND(AVG(CASE WHEN year(date) = 2025 THEN pm25 END), 1) AS y2025
FROM station_obs
WHERE location_id IN (SELECT location_id FROM shared) AND year(date) IN (2022, 2025)
GROUP BY m ORDER BY m;

-- 7. Seasonally adjusted correlation (each variable minus its calendar-month mean), well-covered days only
WITH d AS (
  SELECT p.date, p.pm, w.wind_speed, w.temp_c, month(p.date) AS m
  FROM (SELECT date, MEDIAN(pm25) AS pm FROM station_obs
        GROUP BY date HAVING COUNT(DISTINCT location_id) >= 30) p
  JOIN weather_daily w USING (date)
),
a AS (
  SELECT *,
         pm - AVG(pm) OVER (PARTITION BY m) AS pm_anom,
         wind_speed - AVG(wind_speed) OVER (PARTITION BY m) AS wind_anom,
         temp_c - AVG(temp_c) OVER (PARTITION BY m) AS temp_anom
  FROM d
)
SELECT year(date) AS yr, COUNT(*) AS days,
       ROUND(corr(pm_anom, wind_anom), 2) AS corr_wind_anom,
       ROUND(corr(pm_anom, temp_anom), 2) AS corr_temp_anom
FROM a GROUP BY yr ORDER BY yr;