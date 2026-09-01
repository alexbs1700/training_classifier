"""Activity visualisations.

Two entry points:

* ``plot_activity_calendar`` — GitHub-style calendar, one row of weeks per year.
* ``plot_activity`` — single-activity dashboard: route + pace + heart rate +
  elevation.
"""

from datetime import date, timedelta

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.collections import LineCollection
from matplotlib.colors import ListedColormap, Normalize
from matplotlib.patches import Patch
from matplotlib.ticker import FuncFormatter

ACCENT = "#111111"
MUTED = "#9a9a9a"


# --------------------------------------------------------------------------- #
# Activity calendar                                                           #
# --------------------------------------------------------------------------- #

def _grid_for_year(year, active_days):
    """Return a 7 x n_weeks array: 1 = active, 0 = idle, nan = outside the year."""
    jan1 = date(year, 1, 1)
    dec31 = date(year, 12, 31)
    offset = jan1.weekday()                      # Monday = 0
    n_days = (dec31 - jan1).days + 1
    n_weeks = (n_days + offset + 6) // 7

    grid = np.full((7, n_weeks), np.nan)
    for i in range(n_days):
        day = jan1 + timedelta(days=i)
        col, row = divmod(i + offset, 7)
        grid[row, col] = 1.0 if day in active_days else 0.0
    return grid


def _month_starts(year, offset):
    """Column position and label for the first day of each month."""
    positions, labels = [], []
    for month in range(1, 13):
        day_index = (date(year, month, 1) - date(year, 1, 1)).days
        positions.append((day_index + offset) // 7)
        labels.append(date(year, month, 1).strftime("%b"))
    return positions, labels


def plot_activity_calendar(dates, years=None, figsize_per_year=1.55, cell_gap=1.4):
    """
    dates : iterable of datetime.date (or anything with .date()) that had an activity
    years : explicit list of years to draw; defaults to the full observed span
    """
    active = {d.date() if hasattr(d, "date") else d for d in dates}
    if years is None:
        years = range(min(active).year, max(active).year + 1)
    years = list(years)

    cmap = ListedColormap(["#ffffff", "#111111"])

    fig, axes = plt.subplots(
        len(years), 1,
        figsize=(13, figsize_per_year * len(years)),
        constrained_layout=True,
    )
    axes = np.atleast_1d(axes)

    for ax, year in zip(axes, years):
        grid = _grid_for_year(year, active)
        masked = np.ma.masked_invalid(grid)

        ax.pcolormesh(
            masked, cmap=cmap, vmin=0, vmax=1,
            edgecolors="#d8d8d8", linewidth=cell_gap,
        )
        ax.set_aspect("equal")
        ax.invert_yaxis()

        offset = date(year, 1, 1).weekday()
        positions, labels = _month_starts(year, offset)
        ax.set_xticks([p + 0.5 for p in positions])
        ax.set_xticklabels(labels, fontsize=8, color="#666666")
        ax.set_yticks([0.5, 3.5, 6.5])
        ax.set_yticklabels(["Mon", "Thu", "Sun"], fontsize=8, color="#666666")
        ax.tick_params(length=0)
        for side in ax.spines.values():
            side.set_visible(False)

        n_active = int(np.nansum(grid))
        n_days = int(np.sum(~np.isnan(grid)))
        ax.set_title(
            f"{year}    {n_active} / {n_days} days  ({n_active / n_days:.0%})",
            loc="left", fontsize=11, fontweight="bold", pad=6,
        )

    axes[-1].legend(
        handles=[
            Patch(facecolor="#111111", edgecolor="#d8d8d8", label="activity logged"),
            Patch(facecolor="#ffffff", edgecolor="#d8d8d8", label="nothing logged"),
        ],
        loc="upper left", bbox_to_anchor=(0, -0.35),
        frameon=False, ncols=2, fontsize=9,
    )
    return fig


# --------------------------------------------------------------------------- #
# Single-activity dashboard                                                   #
# --------------------------------------------------------------------------- #

def _mmss(minutes, _=None):
    """Format decimal minutes as m:ss for pace axes."""
    if not np.isfinite(minutes):
        return ""
    m, s = divmod(int(round(minutes * 60)), 60)
    return f"{m}:{s:02d}"


def smooth(x, window=15):
    """Centred rolling mean that tolerates NaNs."""
    x = np.asarray(x, dtype=float)
    kernel = np.ones(window) / window
    filled = np.nan_to_num(x, nan=0.0)
    valid = (~np.isnan(x)).astype(float)
    num = np.convolve(filled, kernel, mode="same")
    den = np.convolve(valid, kernel, mode="same")
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(den > 0, num / den, np.nan)


def pace_from_speed(speed_ms, min_speed=0.5, window=15):
    """min/km from m/s, smoothed, with stops masked out."""
    speed = smooth(speed_ms, window)
    with np.errstate(divide="ignore", invalid="ignore"):
        pace = 1000.0 / (speed * 60.0)
    return np.where(speed > min_speed, pace, np.nan)


def _style(ax, label):
    ax.set_ylabel(label, fontsize=9, color="#555555")
    ax.tick_params(labelsize=8, colors="#777777", length=0)
    ax.grid(axis="y", color="#eeeeee", linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "bottom", "left"):
        ax.spines[side].set_visible(False)


def plot_activity(df, title="", speed_col="speed", hr_col="heart_rate",
                  alt_col="altitude", lat_col="latitude", lon_col="longitude"):
    """
    df needs a `distance` column in metres plus whichever of the optional
    channels exist. Missing channels are skipped, not faked.
    """
    if "distance" not in df:
        raise KeyError(
            "plot_activity needs a `distance` column (metres). Got columns: "
            f"{list(df.columns)}. If this came from Garmin's get_activity_details, "
            "run it through utils.garmin_aux.activity_details_to_df first."
        )
    dist_km = df["distance"].to_numpy() / 1000.0
    pace = pace_from_speed(df[speed_col].to_numpy())

    panels = [("Pace (min/km)", pace, "pace")]
    if hr_col in df:
        panels.append(("Heart rate (bpm)", smooth(df[hr_col].to_numpy()), "line"))
    if alt_col in df:
        panels.append(("Elevation (m)", smooth(df[alt_col].to_numpy()), "fill"))

    fig = plt.figure(figsize=(13, 3.1 * len(panels)), constrained_layout=True)
    gs = fig.add_gridspec(len(panels), 3, width_ratios=[1.15, 1, 1])

    # --- route, coloured by pace -------------------------------------------
    ax_map = fig.add_subplot(gs[:, 0])
    if lat_col in df and lon_col in df:
        lat, lon = df[lat_col].to_numpy(), df[lon_col].to_numpy()
        pts = np.column_stack([lon, lat]).reshape(-1, 1, 2)
        segs = np.concatenate([pts[:-1], pts[1:]], axis=1)
        finite = pace[np.isfinite(pace)]
        lo, hi = np.percentile(finite, [5, 95]) if finite.size else (0.0, 1.0)
        lc = LineCollection(
            list(segs), cmap="viridis_r", linewidth=2.4,
            norm=Normalize(lo, hi),
        )
        lc.set_array(pace[:-1])
        ax_map.add_collection(lc)
        ax_map.autoscale_view()
        ax_map.scatter(lon[0], lat[0], s=45, c="white", ec=ACCENT, zorder=3, lw=1.5)
        ax_map.scatter(lon[-1], lat[-1], s=45, c=ACCENT, zorder=3)
        # 1 deg lon shrinks by cos(lat); without this the route is stretched
        ax_map.set_aspect(1.0 / np.cos(np.deg2rad(np.nanmean(lat))))
        cb = fig.colorbar(lc, ax=ax_map, fraction=0.04, pad=0.02)
        cb.ax.yaxis.set_major_formatter(FuncFormatter(_mmss))
        cb.ax.tick_params(labelsize=8, colors="#777777", length=0)
        cb.set_label("pace", fontsize=9, color="#555555")
        cb.outline.set_visible(False)
    ax_map.set_xticks([])
    ax_map.set_yticks([])
    for side in ax_map.spines.values():
        side.set_visible(False)

    # --- stacked channels ---------------------------------------------------
    axes = []
    for i, (label, series, kind) in enumerate(panels):
        ax = fig.add_subplot(gs[i, 1:], sharex=axes[0] if axes else None)
        axes.append(ax)
        if kind == "fill":
            ax.fill_between(dist_km, series, np.nanmin(series),
                            color=MUTED, alpha=0.45, lw=0)
        else:
            ax.plot(dist_km, series, color=ACCENT, lw=1.3)
        if kind == "pace":
            ax.invert_yaxis()          # faster is up, as every runner expects
            ax.yaxis.set_major_formatter(FuncFormatter(_mmss))
            # one stop would otherwise stretch the axis to 30:00 and flatten
            # everything else into a straight line
            lo, hi = np.nanpercentile(series, [1, 99])
            ax.set_ylim(hi + 0.3, lo - 0.3)
        _style(ax, label)
        if i < len(panels) - 1:
            ax.tick_params(labelbottom=False)

    axes[-1].set_xlabel("Distance (km)", fontsize=9, color="#555555")
    if title:
        fig.suptitle(title, fontsize=13, fontweight="bold", ha="left", x=0.01)
    return fig


if __name__ == "__main__":
    # synthetic history: consistent triathlon years, then a mid-2026 stop
    rng = np.random.default_rng(7)
    fake = []
    for year in range(2022, 2027):
        day = date(year, 1, 1)
        while day.year == year:
            if year == 2026 and day > date(2026, 6, 10):
                p = 0.12                      # post-quit: occasional ride
            elif day.weekday() >= 5:
                p = 0.85
            else:
                p = 0.55
            if rng.random() < p and day <= date(2026, 9, 1):
                fake.append(day)
            day += timedelta(days=1)

    fig = plot_activity_calendar(fake, years=range(2022, 2027))
    fig.savefig("/home/claude/calendar_demo.png", dpi=160, bbox_inches="tight",
                facecolor="white")

    # synthetic single ride
    import pandas as pd

    rng = np.random.default_rng(3)
    n = 3600
    t = np.arange(n)
    speed = 4.2 + 0.9 * np.sin(t / 420) + rng.normal(0, 0.28, n)
    speed[1500:1560] = 0.05                                  # a stop at a light
    speed = np.clip(speed, 0, None)
    dist = np.cumsum(speed)
    theta = t / n * 2 * np.pi
    lat = 43.545 + 0.02 * np.sin(theta) + 0.004 * np.sin(5 * theta)
    lon = -5.662 + 0.03 * np.cos(theta) + 0.005 * np.cos(3 * theta)
    ride = pd.DataFrame({
        "distance": dist,
        "speed": speed,
        "heart_rate": np.clip(138 + 16 * np.sin(t / 500) + rng.normal(0, 3, n), 90, 195),
        "altitude": 180 + 60 * np.sin(t / 900) + rng.normal(0, 1.2, n),
        "latitude": lat,
        "longitude": lon,
    })

    fig = plot_activity(ride, title="Morning ride  ·  Gijón")
    fig.savefig("/home/claude/activity_demo.png", dpi=160,
                bbox_inches="tight", facecolor="white")
    print("saved")
