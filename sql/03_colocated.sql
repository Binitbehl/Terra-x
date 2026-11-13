-- 8. Station pairs within 0.5 km: same-day PM2.5 comparison
WITH pairs AS (
  SELECT a.location_id AS id_a, b.location_id AS id_b,
         a.name AS name_a, b.name AS name_b,
         sqrt(power((a.lat - b.lat) * 111.0, 2)
            + power((a.lon - b.lon) * 111.0 * cos(radians(28.6)), 2)) AS dist_km
  FROM stations a JOIN stations b ON a.location_id < b.location_id
)
SELECT p.name_a, p.name_b, ROUND(p.dist_km, 2) AS dist_km,
       COUNT(*) AS days,
       ROUND(AVG(x.pm25 - y.pm25), 1) AS mean_diff_a_minus_b,
       ROUND(corr(x.pm25, y.pm25), 2) AS corr
FROM pairs p
JOIN station_obs x ON x.location_id = p.id_a
JOIN station_obs y ON y.location_id = p.id_b AND y.date = x.date
WHERE p.dist_km < 0.5
GROUP BY p.name_a, p.name_b, p.dist_km
HAVING COUNT(*) >= 30
ORDER BY ABS(AVG(x.pm25 - y.pm25)) DESC;

-- 9. Same query, but only pairs with an identical station name before the comma (likely duplicate listings)
SELECT split_part(a.name, ',', 1) AS site, COUNT(DISTINCT a.location_id) AS listings
FROM stations a
GROUP BY site HAVING COUNT(DISTINCT a.location_id) > 1
ORDER BY listings DESC, site;

-- 10. Listings that share a site name: coordinates and active period
SELECT split_part(s.name, ',', 1) AS site, s.location_id, s.name,
       ROUND(s.lat, 4) AS lat, ROUND(s.lon, 4) AS lon,
       MIN(o.date) AS first_day, MAX(o.date) AS last_day, COUNT(*) AS days
FROM stations s JOIN station_obs o ON o.location_id = s.location_id
WHERE split_part(s.name, ',', 1) IN
      (SELECT split_part(name, ',', 1) FROM stations GROUP BY 1 HAVING COUNT(*) > 1)
GROUP BY site, s.location_id, s.name, s.lat, s.lon
ORDER BY site, first_day;

-- 11. Possible relabelled stations: last seen before 2023, first seen from 2025, within 300 m
WITH span AS (
  SELECT location_id, MIN(date) AS first_day, MAX(date) AS last_day
  FROM station_obs GROUP BY location_id
),
cand AS (
  SELECT a.location_id AS old_id, a.name AS old_name, sa.last_day AS old_last,
         b.location_id AS new_id, b.name AS new_name, sb.first_day AS new_first,
         sqrt(power((a.lat - b.lat) * 111.0, 2)
            + power((a.lon - b.lon) * 111.0 * cos(radians(28.6)), 2)) * 1000 AS dist_m
  FROM stations a
  JOIN span sa ON sa.location_id = a.location_id
  JOIN stations b ON b.location_id <> a.location_id
  JOIN span sb ON sb.location_id = b.location_id
  WHERE sa.last_day < DATE '2023-01-01' AND sb.first_day >= DATE '2025-01-01'
)
SELECT old_id, old_name, old_last, new_id, new_name, new_first, ROUND(dist_m) AS dist_m
FROM cand WHERE dist_m < 300 ORDER BY dist_m;