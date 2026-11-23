"""Fetch snow observations for one station from the Synoptic Weather API and
append them to data/<STATION>_snow.csv.

Needs a Synoptic token in the SYNOPTIC_TOKEN environment variable (stored as a
GitHub repo secret). Without a token the script skips quietly, so the NWS
charts keep working.

Values are requested in English units, so the CSV is in inches.
"""
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

STATION = os.environ.get("STATION_ID", "BRC")
TOKEN = os.environ.get("SYNOPTIC_TOKEN", "").strip()
# How far back to go on the very first run. Synoptic keeps long history, but
# your account tier may limit how far back you can request.
BACKFILL_DAYS = int(os.environ.get("SNOW_BACKFILL_DAYS", "30"))
API = "https://api.synopticdata.com/v2/stations/timeseries"
DATA_FILE = Path(__file__).resolve().parent.parent / "data" / f"{STATION}_snow.csv"

# Synoptic variable -> CSV column
VARS = {
    "snow_depth": "snow_depth_in",
    "snow_interval": "snow_interval_in",
    "snow_water_equiv": "swe_in",
}


def pick_set(obs, var):
    """Synoptic names series like snow_depth_set_1 (measured) or *_set_1d (derived).
    Prefer the measured set and fall back to whatever exists."""
    keys = sorted(k for k in obs if k.startswith(f"{var}_set_"))
    measured = [k for k in keys if not k.endswith("d")]
    return (measured or keys or [None])[0]


def main():
    if not TOKEN:
        print("SYNOPTIC_TOKEN not set; skipping snow data.")
        return

    if DATA_FILE.exists():
        old = pd.read_csv(DATA_FILE, parse_dates=["timestamp"])
        start = old["timestamp"].max().to_pydatetime() - timedelta(hours=6)
    else:
        old = pd.DataFrame()
        start = datetime.now(timezone.utc) - timedelta(days=BACKFILL_DAYS)
    end = datetime.now(timezone.utc)

    params = {
        "stid": STATION,
        "start": start.strftime("%Y%m%d%H%M"),
        "end": end.strftime("%Y%m%d%H%M"),
        "vars": ",".join(VARS),
        "units": "english",
        "obtimezone": "utc",
        "token": TOKEN,
    }
    r = requests.get(API, params=params, timeout=60)
    r.raise_for_status()
    data = r.json()

    summary = data.get("SUMMARY", {})
    if summary.get("RESPONSE_CODE") != 1:
        # Print Synoptic's own message (bad token, unknown station, no data, ...).
        print(f"Synoptic error: {summary.get('RESPONSE_MESSAGE')}", file=sys.stderr)
        sys.exit(1)

    stations = data.get("STATION", [])
    if not stations:
        print("Synoptic returned no station data.")
        return
    st = stations[0]
    obs = st.get("OBSERVATIONS", {})
    new = pd.DataFrame({"timestamp": pd.to_datetime(obs.get("date_time", []), utc=True)})
    found = []
    for var, col in VARS.items():
        key = pick_set(obs, var)
        if key:
            new[col] = pd.to_numeric(pd.Series(obs[key]), errors="coerce")
            found.append(var)
        else:
            new[col] = pd.NA
    print(f"Synoptic {st.get('STID')} ({st.get('NAME')}): variables found: {', '.join(found) or 'none'}")

    if new.empty:
        print("No new snow observations.")
        return

    df = pd.concat([old, new], ignore_index=True)
    df = (
        df.drop_duplicates(subset="timestamp", keep="last")
        .sort_values("timestamp")
        .reset_index(drop=True)
    )
    DATA_FILE.parent.mkdir(exist_ok=True)
    df.to_csv(DATA_FILE, index=False, date_format="%Y-%m-%dT%H:%M:%SZ")
    print(f"{STATION} snow: {len(new)} fetched, {len(df)} total rows, latest {df['timestamp'].max()}")


if __name__ == "__main__":
    main()
