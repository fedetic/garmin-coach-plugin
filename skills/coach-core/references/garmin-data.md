# Garmin data: where each signal comes from

Tool names are from the `garmin` MCP server (Taxuspt/garmin_mcp, unofficial
Garmin Connect API). Not every watch records everything: a field that's
missing or null is reported as missing, never estimated.

## Daily readiness inputs -> `record_metrics` canonical names

| Canonical metric | Garmin call(s) | Notes |
|---|---|---|
| `hrv_overnight_ms` | `get_hrv_data(date)` (last-night average); `get_hrv_trend` for history | Garmin's own status (BALANCED/UNBALANCED/LOW) is based on its weekly average vs its baseline. Record the nightly value and quote the status separately |
| `rhr_bpm` | `get_rhr_day(date)` or `get_heart_rates(date)` | |
| `sleep_hours`, `sleep_score` | `get_sleep_data(date)`; `get_sleep_summary_range` for history | `date` = the morning you woke up |
| `body_battery_morning` | `get_body_battery(date, date)` | use the value at wake / the daily high |
| `stress_avg` | `get_stress_summary` / `get_all_day_stress` | |
| `training_readiness` | `get_morning_training_readiness` / `get_training_readiness` | Only on newer watches |
| `vo2max` | `get_vo2max_trend`, `get_training_status` | running and/or cycling VO2max, which are separate values |
| `acute_load` | `get_training_status`, `get_training_load_balance` | |
| `steps` | `get_daily_steps` / `get_stats_range` | |
| `weight_kg` | `get_weigh_ins` / `get_daily_weigh_ins` | goes to body_metrics |

**Backfill on first setup:** pull 60+ days (use range calls where they exist)
so baselines are meaningful from day one. `readiness_report` flags a
baseline with fewer than 14 days as LOW confidence.

## Endurance and performance

| Signal | Call |
|---|---|
| VO2max trend | `get_vo2max_trend` |
| Race predictions (5k/10k/HM/M) | `get_race_predictions` |
| Lactate threshold HR/pace | `get_lactate_threshold` |
| Training status, load focus (anaerobic / high aerobic / low aerobic) | `get_training_status`, `get_training_load_balance`, `get_training_load_trend` |
| Endurance score, hill score | `get_endurance_score`, `get_hill_score` |
| Running tolerance (injury-risk load proxy) | `get_running_tolerance`, `get_running_tolerance_trend` |
| HR zones | `get_heart_rate_zones` (`set_heart_rate_zones` to update after an LT test) |
| Cycling FTP, power curve | `get_cycling_ftp`, `get_power_duration_curve` |
| Per-activity time in zones | `get_activity_hr_in_timezones`, `get_activity_power_in_timezones` |
| Training effect (aerobic/anaerobic) | `get_training_effect` |
| Personal records | `get_personal_record` |

## Activities and strength sets

- `get_activities_by_date(start, end)` lists activities (id, name, type,
  duration, HR). Don't pass `activity_type="strength_training"`: it's a
  sub-type and the API rejects it with a 400. Filter on `type` client-side.
- `get_activity(id)` gives details, including `workout_rpe` and `feel` when
  the athlete set them.
- `get_activity_exercise_sets(id)` gives a set list. Weight is in **grams**,
  `setType` is ACTIVE or REST, and `exercises[0]` is Garmin's best guess.
  `category: UNKNOWN` means the watch couldn't classify the set and the
  athlete didn't correct it. The output is verbose, so pass the sets to
  `import_activity` (raw or compact) rather than restating them.
- `set_activity_exercise_sets` can correct a misclassified set if the athlete asks.

## Nutrition

`get_nutrition_daily_food_log`, `get_nutrition_summary_between_dates`,
`get_nutrition_daily_settings` only return data if the athlete logs food in
Garmin Connect. If nothing comes back, ask about intake in the check-in.

## Writing

Workouts and calendar: see the `coach-garmin-sync` skill. Body data:
`add_weigh_in`, `add_hydration_data`. Don't call write tools the athlete
didn't ask for, beyond pushing planned workouts.

## Connection problems

- Auth tokens live in `~/.garminconnect/` and are valid for about 6 months.
  Re-auth: `uvx --python 3.12 --from git+https://github.com/Taxuspt/garmin_mcp garmin-mcp-auth`.
- HTTP 401 on install from GitHub over HTTPS can be an anonymous rate limit.
  Switching to the `git+ssh://` URL works if the user has a GitHub SSH key.
- "Result too large": paginate (`page`, `page_size`) or narrow the date range.
