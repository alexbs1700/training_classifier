-- Consumption-ready projection of the raw Garmin landing table `activities_raw`
-- (168 columns of mixed API cruft) down to the fields worth querying.
--
--   from utils.db import run_query
--   run_query("build_activities")
--
-- It's a VIEW: it always reflects the current contents of `activities_raw`, so
-- there is nothing to rebuild after a fresh sync. Run this once to (re)define it.

-- `activities` was a physical table earlier in this repo's history; drop it so
-- CREATE OR REPLACE VIEW can claim the name.
DROP TABLE IF EXISTS activities;

CREATE OR REPLACE TABLE activities AS
SELECT
    -- identity
    activity_id,
    activity_name                        AS name,
    owner_id,
    owner_display_name,
    activity_type_type_key               AS sport,
    activity_type_parent_type_id         AS sport_group,
    CAST(start_time_local AS TIMESTAMP)  AS start_local,
    CAST(start_time_local AS DATE)       AS day,
    location_name,
    has_polyline,
    is_p_r                               AS is_pr,
    -- volume
    distance                             AS distance_m,
    duration                             AS duration_s,
    moving_duration                      AS moving_s,
    elapsed_duration                     AS elapsed_s,
    elevation_gain                       AS elev_gain_m,
    elevation_loss                       AS elev_loss_m,
    lap_count,
    -- speed
    average_speed                        AS avg_speed_ms,
    max_speed                            AS max_speed_ms,
    -- cardio
    average_h_r                          AS avg_hr,
    max_h_r                              AS max_hr,
    hr_time_in_zone_1, hr_time_in_zone_2, hr_time_in_zone_3,
    hr_time_in_zone_4, hr_time_in_zone_5,
    avg_respiration_rate, max_respiration_rate, min_respiration_rate,
    -- power (cycling)
    avg_power, max_power, norm_power, max20_min_power,
    training_stress_score                AS tss,
    intensity_factor                     AS "if",
    power_time_in_zone_1, power_time_in_zone_2, power_time_in_zone_3,
    power_time_in_zone_4, power_time_in_zone_5, power_time_in_zone_6,
    power_time_in_zone_7,
    -- power-duration curve: best mean power over each window, seconds
    max_avg_power_1, max_avg_power_2, max_avg_power_5, max_avg_power_10,
    max_avg_power_20, max_avg_power_30, max_avg_power_60, max_avg_power_120,
    max_avg_power_300, max_avg_power_600, max_avg_power_1200,
    max_avg_power_1800, max_avg_power_3600, max_avg_power_7200,
    max_avg_power_18000,
    -- fastest splits: best time over each distance, metres
    fastest_split_100, fastest_split_400, fastest_split_750,
    fastest_split_1000, fastest_split_1609, fastest_split_5000,
    fastest_split_10000, fastest_split_21098, fastest_split_40000,
    -- cadence, sport-conditional
    average_biking_cadence_in_rev_per_minute      AS avg_cadence_bike,
    average_running_cadence_in_steps_per_minute   AS avg_cadence_run,
    average_swim_cadence_in_strokes_per_minute    AS avg_cadence_swim,
    max_swim_cadence_in_strokes_per_minute        AS max_cadence_swim,
    max_biking_cadence_in_rev_per_minute          AS max_cadence_bike,
    max_running_cadence_in_steps_per_minute       AS max_cadence_run,
    steps, avg_stride_length,
    -- swim
    average_swolf, pool_length, unit_of_pool_length_unit_key AS pool_unit,
    active_lengths, avg_stroke_distance, avg_strokes, max_stroke_cadence,
    strokes,                              -- pedal revs on a bike, strokes in water
    -- strength
    total_sets, active_sets, total_reps,
    -- load / adaptation
    aerobic_training_effect              AS aerobic_te,
    anaerobic_training_effect            AS anaerobic_te,
    training_effect_label,
    activity_training_load               AS training_load,
    moderate_intensity_minutes, vigorous_intensity_minutes,
    v_o2_max_value                       AS vo2max,
    lactate_threshold_bpm, max_ftp,
    -- context
    calories, bmr_calories,
    min_temperature, max_temperature,
    min_elevation, max_elevation, avg_elevation,
    start_latitude, start_longitude, end_latitude, end_longitude,
    device_id, manufacturer, is_manual_activity AS manual
FROM activities_raw;
