# training_classifier

Pull your training history from Garmin Connect, tidy it into DataFrames, and
visualise it. The longer-term goal is to classify activities (sport, workout
type, effort) from the per-sample sensor data; right now the repo covers the
data-plumbing and plotting groundwork.

## What's here

| Path | Purpose |
| --- | --- |
| `utils/garmin_aux.py` | Authenticate against Garmin Connect, turn `get_activity_details` output into tidy DataFrames, and cache per-activity detail streams to Parquet (`sync_details`). |
| `utils/plotting_aux.py` | Two matplotlib views: a GitHub-style activity calendar and a single-activity dashboard (route coloured by pace + stacked pace / heart-rate / elevation panels). |
| `utils/data_manipulation_aux.py` | DataFrame helpers, e.g. `normalize_ordered` (flatten nested JSON records while keeping original key order). |
| `utils/db.py` | Query the DuckDB store and the Parquet files with DuckDB (`run_query`, `sql`). |
| `querys/*.sql` | Saved queries, one per file. Tracked in git; their outputs are not. |
| `data/activities.db` | DuckDB store: `activities_raw` table + `activities` view. Git-ignored. |
| `data/details_raw/<id>.parquet` | One per-sample detail stream per activity. Git-ignored. |
| `experiments.ipynb` | Scratch notebook: fetch all activities, plot the calendar, drill into one activity. |
| `main.py` | Placeholder entry point. |

## Setup

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
```

## Usage

### Authentication

`init_garmin_api()` tries cached OAuth tokens first (`~/.garminconnect/` by
default), then falls back to an interactive email / password / MFA prompt. After
the first successful login, token refresh means later runs need no interaction.

Optional environment variables:

| Variable | Meaning |
| --- | --- |
| `GARMIN_EMAIL` | Garmin Connect email (skips the prompt) |
| `GARMIN_PASSWORD` | Garmin Connect password (skips the prompt) |
| `GARMINTOKENS` | Token-cache directory (default `~/.garminconnect`) |

Credentials and token files are git-ignored.

### Example

```python
from datetime import datetime

from utils.garmin_aux import init_garmin_api, details_to_df, clean
from utils.plotting_aux import plot_activity_calendar, plot_activity

api = init_garmin_api()

# Every logged activity (the API returns at most 1000 per call)
total = api.count_activities()
activities = []
for start in range(0, total, 1000):
    batch = api.get_activities(start, 1000)
    if not batch:
        break
    activities.extend(batch)

# Calendar of active days
dates = [datetime.fromisoformat(a["startTimeLocal"]).date() for a in activities]
plot_activity_calendar(dates)

# Dashboard for the most recent activity
details = api.get_activity_details(activities[0]["activityId"])
df = clean(details_to_df(details))
plot_activity(df, title="Latest activity")
```

Run the notebook with:

```bash
uv run jupyter lab experiments.ipynb
```

### The DuckDB store

The notebook normalises the raw Garmin activity summaries into
`data/activities.db`:

| Object | What it is |
| --- | --- |
| `activities_raw` | Landing **table** — every column the Garmin API returned (168 of them), names snake-cased. Never edited by hand. |
| `activities` | Consumption-ready **view** over `activities_raw`: ~110 columns worth querying, typed timestamps, canonical names, SI units. Defined by `querys/build_activities.sql`. As a view it always reflects the current landing table — no rebuild after a sync. |

### Querying

Keep queries as `.sql` files under `querys/` and run them by name. The store is
attached as the catalog `data`, so a query references `data.activities` (or just
`activities`):

```python
from utils.db import run_query

run_query("build_activities")           # (re)define the `activities` view
run_query("weekly_volume")              # runs querys/weekly_volume.sql
run_query("activity", activity_id=123)  # binds $activity_id in the SQL
```

`run_query` returns the **last** statement's result, so a script that ends in
`CREATE VIEW …` / `CREATE TABLE …` returns an empty frame — that's expected; the
point is the object it leaves behind.

Relative file paths resolve from the repo root, so queries can also read data
files directly:

```sql
-- querys/weekly_volume.sql
SELECT date_trunc('week', start_local)::date AS week,
       count(*)                              AS activities,
       round(sum(distance_m) / 1000.0, 1)    AS km
FROM data.activities
GROUP BY 1
ORDER BY 1;
```

Or from the DuckDB CLI:

```bash
duckdb data/activities.db ".read querys/build_activities.sql"
```

> The notebook kernel holds a write lock on `data/activities.db` while its DuckDB
> connection is open. Run the notebook's `con.close()` cell (or restart the
> kernel) before calling `run_query`, or you'll hit `Conflicting lock is held`.

### Per-activity detail streams

`get_activity_details` returns a per-sample stream (GPS, HR, power, cadence, …).
`sync_details` caches one Parquet file per activity under `data/details_raw/`,
skipping activities already fetched:

```python
from utils.garmin_aux import sync_details

ids = [a["activityId"] for a in activities]
sync_details(api, ids)            # data/details_raw/<id>.parquet, tqdm progress bar
```

Query them with DuckDB — no table or view to maintain. `sql()` runs an ad-hoc
string; pass `attach=False` for Parquet-only queries (they never touch the
store's lock):

```python
from utils.db import sql

# one activity
sql("SELECT * FROM 'data/details_raw/24174865995.parquet' WHERE heart_rate > 160", attach=False)

# aggregate across all of them (union_by_name handles missing channels)
sql("""
    SELECT activity_id, max(power) AS peak_w
    FROM read_parquet('data/details_raw/*.parquet', union_by_name := true)
    GROUP BY activity_id
""", attach=False)

# filter by activity attributes — join the `activities` view (needs attach)
sql("""
    SELECT s.*
    FROM read_parquet('data/details_raw/*.parquet', union_by_name := true) s
    JOIN activities a USING (activity_id)
    WHERE a.sport = 'running' AND a.day >= DATE '2026-01-01'
""")
```

For a known subset, pass the file list instead of globbing 2 000 files:

```python
files = [f"data/details_raw/{i}.parquet" for i in ids]
sql("SELECT * FROM read_parquet(?)", [files], attach=False)
```

## API reference

**`utils.garmin_aux`**

- `init_garmin_api() -> Garmin` — authenticated client (cached tokens or prompt).
- `details_to_df(det, rename=True) -> DataFrame` — one row per sensor sample; columns renamed via the `CANONICAL` map. Raises `ValueError` if the activity has no recorded stream.
- `available_metrics(det) -> DataFrame` — every channel in an activity, with units. Use it when an expected column is missing.
- `clean(df) -> DataFrame` — drop Garmin `999.0` GPS sentinels, interpolate short dropouts, drop rows with no distance.
- `sync_details(api, activity_ids, dest="data/details_raw", *, overwrite=False, pause=0.2, progress=True) -> list[int]` — cache each activity's detail stream as `<dest>/<id>.parquet` (tqdm bar); skips files already present. Raise `pause` if a bulk backfill trips Garmin's `429`.
- `safe_api_call(method, *args) -> (success, result, error_message)` — wraps library exceptions into a tuple.

**`utils.plotting_aux`**

- `plot_activity_calendar(dates, years=None) -> Figure` — one week-grid row per year.
- `plot_activity(df, title="", ...) -> Figure` — needs a `distance` column in metres; heart-rate, elevation and lat/lon panels are drawn only if present.

Both modules run standalone (`python -m utils.plotting_aux`) to render demo figures from synthetic data.

**`utils.db`**

- `run_query(name, *, attach=True, read_only=False, **params) -> DataFrame` — execute `querys/<name>.sql`, returning the last statement's result; keyword args bind to `$name` query parameters.
- `sql(query, params=None, *, attach=True, read_only=False) -> DataFrame` — run an ad-hoc query string.
- `connect(db=..., *, attach=True, read_only=False) -> DuckDBPyConnection` — in-memory connection with file paths rooted at the repo; with `attach` the store is opened as the `data` catalog, with `attach=False` no database is touched.
