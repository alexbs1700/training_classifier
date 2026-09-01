# training_classifier

Pull your training history from Garmin Connect, tidy it into DataFrames, and
visualise it. The longer-term goal is to classify activities (sport, workout
type, effort) from the per-sample sensor data; right now the repo covers the
data-plumbing and plotting groundwork.

## What's here

| Path | Purpose |
| --- | --- |
| `utils/garmin_aux.py` | Authenticate against Garmin Connect and turn `get_activity_details` output into tidy, canonically-named DataFrames. |
| `utils/plotting_aux.py` | Two matplotlib views: a GitHub-style activity calendar and a single-activity dashboard (route coloured by pace + stacked pace / heart-rate / elevation panels). |
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

## API reference

**`utils.garmin_aux`**

- `init_garmin_api() -> Garmin` — authenticated client (cached tokens or prompt).
- `details_to_df(det, rename=True) -> DataFrame` — one row per sensor sample; columns renamed via the `CANONICAL` map.
- `available_metrics(det) -> DataFrame` — every channel in an activity, with units. Use it when an expected column is missing.
- `clean(df) -> DataFrame` — drop Garmin `999.0` GPS sentinels, interpolate short dropouts, drop rows with no distance.
- `safe_api_call(method, *args) -> (success, result, error_message)` — wraps library exceptions into a tuple.

**`utils.plotting_aux`**

- `plot_activity_calendar(dates, years=None) -> Figure` — one week-grid row per year.
- `plot_activity(df, title="", ...) -> Figure` — needs a `distance` column in metres; heart-rate, elevation and lat/lon panels are drawn only if present.

Both modules run standalone (`python -m utils.plotting_aux`) to render demo figures from synthetic data.
