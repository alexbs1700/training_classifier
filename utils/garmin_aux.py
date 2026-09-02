"""Garmin Connect helpers: authentication and activity data extraction.

Three public entry points:

* ``init_garmin_api``    — authenticate and return a ready ``Garmin`` client.
* ``details_to_df``     — flatten ``get_activity_details`` output into a tidy
                          DataFrame with canonical column names.
* ``available_metrics`` — inspect which channels a given activity returned.
* ``clean``             — drop Garmin sentinel rows and fill short GPS gaps.
* ``safe_api_call``     — thin wrapper that converts library exceptions into
                          (success, result, error_message) tuples.

Environment variables (all optional):
    GARMIN_EMAIL      your Garmin Connect email
    GARMIN_PASSWORD   your Garmin Connect password
    GARMINTOKENS      token-cache directory (default: ~/.garminconnect)
"""

import contextlib
import logging
import os
import sys
import time
from collections.abc import Iterable
from datetime import date
from getpass import getpass
from pathlib import Path

import numpy as np
import pandas as pd
from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectNotFoundError,
    GarminConnectTooManyRequestsError,
)

logging.getLogger("garminconnect").setLevel(logging.CRITICAL)
log = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Auth / connection helpers                                                    #
# --------------------------------------------------------------------------- #


def _status_code_from_error(exc: Exception) -> int | None:
    """Best-effort HTTP status extraction from a library exception."""
    response = getattr(exc, "response", None)
    if response is not None:
        status = getattr(response, "status_code", None)
        if isinstance(status, int):
            return status

    error_str = str(exc)
    for code in ("400", "401", "403", "404", "429", "500"):
        if code in error_str:
            return int(code)
    return None


def safe_api_call(api_method, *args, **kwargs):
    """Call an API method and return ``(success, result, error_message)``."""
    try:
        return True, api_method(*args, **kwargs), None

    except GarminConnectNotFoundError as e:
        return False, None, f"Not found (404) — endpoint may have moved: {e}"
    except GarminConnectAuthenticationError as e:
        return False, None, f"Authentication error: {e}"
    except GarminConnectTooManyRequestsError as e:
        return False, None, f"Rate limit exceeded: {e}"
    except GarminConnectConnectionError as e:
        status = _status_code_from_error(e)
        messages = {
            400: "Not available (400) — feature may not be enabled for your account",
            401: "Authentication required (401) — please re-authenticate",
            403: "Access denied (403) — account may not have permission",
            404: "Not found (404) — endpoint may have moved",
            429: "Rate limit (429) — please wait before retrying",
            500: "Server error (500) — Garmin servers are having issues",
        }
        msg = messages.get(status) if status is not None else None
        return False, None, msg or f"Connection error: {e}"
    except Exception as e:
        return False, None, f"Unexpected error: {e}"


def init_garmin_api() -> Garmin:
    """Return an authenticated ``Garmin`` client.

    Tries cached tokens first (``~/.garminconnect/`` by default); falls back
    to an interactive credential prompt with MFA support.  OAuth refresh tokens
    mean subsequent runs require no user interaction.
    """
    tokenstore = str(Path(os.getenv("GARMINTOKENS", "~/.garminconnect")).expanduser())

    try:
        garmin = Garmin()
        garmin.login(tokenstore)
        return garmin

    except GarminConnectTooManyRequestsError as err:
        logging.error(f"Rate limit: {err}")
        sys.exit(1)

    except (GarminConnectAuthenticationError, GarminConnectConnectionError):
        logging.error("No valid tokens found — please log in.")

    while True:
        try:
            email = os.getenv("GARMIN_EMAIL") or input("Email: ").strip()
            password = os.getenv("GARMIN_PASSWORD") or getpass("Password: ")
            garmin = Garmin(
                email=email,
                password=password,
                prompt_mfa=lambda: input("MFA code: ").strip(),
            )
            password = None  # don't hold plaintext longer than needed
            garmin.login(tokenstore)
            return garmin

        except GarminConnectTooManyRequestsError as err:
            logging.error(f"Rate limit: {err}")
            sys.exit(1)

        except GarminConnectAuthenticationError:
            logging.error("Wrong credentials — please try again.")

        except GarminConnectConnectionError as err:
            raise RuntimeError(f"Garmin connection error: {err}") from err

        except KeyboardInterrupt as err:
            raise RuntimeError("Garmin login cancelled by user") from err


# --------------------------------------------------------------------------- #
# Activity data helpers                                                        #
# --------------------------------------------------------------------------- #

# Maps Garmin's internal metric keys to the names plot_activity() expects.
# Channels not listed here are kept under their original Garmin key.
CANONICAL = {
    "directLatitude": "latitude",
    "directLongitude": "longitude",
    "directSpeed": "speed",  # m/s
    "directHeartRate": "heart_rate",  # bpm
    "directPower": "power",  # watts
    "directBikeCadence": "cadence",  # rpm
    "directRunCadence": "cadence",  # steps/min
    "directElevation": "altitude",  # metres
    "sumDistance": "distance",  # metres
    "sumDuration": "elapsed",  # seconds
    "directTimestamp": "timestamp",
}


def details_to_df(det: dict, rename: bool = True) -> pd.DataFrame:
    """Flatten ``Garmin.get_activity_details`` output into a tidy DataFrame.

    Each row is one GPS/sensor sample.  Column names are mapped through
    ``CANONICAL``; call ``available_metrics(det)`` if an expected channel is
    missing.
    """
    index_of = {m["key"]: m["metricsIndex"] for m in det["metricDescriptors"]}
    rows = [r["metrics"] for r in det["activityDetailMetrics"]]
    df = pd.DataFrame(rows).rename(columns={idx: key for key, idx in index_of.items()})

    if rename:
        df = df.rename(columns={k: v for k, v in CANONICAL.items() if k in df})
        df = df.loc[:, ~df.columns.duplicated()]

    return df


def available_metrics(det: dict) -> pd.DataFrame:
    """Return a DataFrame of every channel in this activity, with its unit."""
    return pd.DataFrame(
        [
            {"key": m["key"], "unit": (m.get("unit") or {}).get("key")}
            for m in det["metricDescriptors"]
        ]
    ).sort_values("key", ignore_index=True)


def clean(df: pd.DataFrame) -> pd.DataFrame:
    """Drop Garmin sentinel rows and forward-fill short GPS dropouts (≤10 samples)."""
    df = df.copy()
    for col in ("latitude", "longitude"):
        if col in df:
            # Garmin occasionally emits 999.0 / -999.0 as a "no fix" sentinel.
            df.loc[df[col].abs() > 180, col] = np.nan
            df[col] = df[col].interpolate(limit=10)
    if "distance" in df:
        df = df[df["distance"].notna()].reset_index(drop=True)
    return df


DETAILS_DIR = Path("data/details_raw")


def sync_details(
    api: Garmin,
    activity_ids: Iterable[int],
    dest: Path | str = DETAILS_DIR,
    *,
    overwrite: bool = False,
    pause: float = 1.0,
) -> list[int]:
    """Cache each activity's per-sample detail stream as one Parquet file.

    Writes ``<dest>/<activity_id>.parquet`` (``details_to_df`` output plus an
    ``activity_id`` column, all channels kept).  Ids already on disk are skipped
    unless ``overwrite``; ``pause`` seconds are slept between API calls to stay
    under Garmin's rate limit.  Returns the ids actually fetched.
    """
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)

    fetched: list[int] = []
    for activity_id in activity_ids:
        path = dest / f"{activity_id}.parquet"
        if path.exists() and not overwrite:
            continue

        ok, det, err = safe_api_call(api.get_activity_details, activity_id)
        if not ok or not det:
            log.warning("skipping %s: %s", activity_id, err or "no data")
            continue

        df = details_to_df(det)
        df.insert(0, "activity_id", activity_id)
        df.to_parquet(path, compression="zstd")
        fetched.append(activity_id)
        log.info("cached %s (%d samples)", activity_id, len(df))

        if pause:
            time.sleep(pause)

    return fetched


# --------------------------------------------------------------------------- #
# Quick smoke-test / demo                                                      #
# --------------------------------------------------------------------------- #


def main():
    try:
        api = init_garmin_api()
    except RuntimeError as err:
        print(err)
        return

    today = date.today().isoformat()

    success, summary, err = safe_api_call(api.get_user_summary, today)
    if success and summary:
        print(f"Steps today : {summary.get('totalSteps', 0)}")
        print(f"Calories    : {summary.get('totalKilocalories', 0):.0f} kcal")
        print(f"Distance    : {summary.get('totalDistanceMeters', 0) / 1000:.2f} km")
    elif err:
        print(f"Could not fetch summary: {err}")

    success, hr, err = safe_api_call(api.get_heart_rates, today)
    if success and hr:
        print(f"Resting HR  : {hr.get('restingHeartRate', 'n/a')} bpm")
    elif err:
        print(f"Could not fetch heart rate: {err}")


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        main()
