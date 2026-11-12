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