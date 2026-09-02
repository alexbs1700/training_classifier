-- Weekly training volume: activity count, hours and distance per ISO week.
--
--   from utils.db import run_query
--   run_query("weekly_volume")

SELECT
    date_trunc('week', start_local)::date AS week,
    count(*)                              AS activities,
    round(sum(duration_s) / 3600.0, 1)    AS hours,
    round(sum(distance_m) / 1000.0, 1)    AS km
FROM activities
GROUP BY 1
ORDER BY 1;
