"""Fetch new observations for one NWS station and append them to data/<STATION>.csv.

The NWS API only keeps about 7 days of observations, so this script builds the
long-term archive. It is safe to run any number of times: rows are de-duplicated
by timestamp.

Values are stored in the SI units the API returns (degC, km/h, Pa, mm, m).
Unit conversion happens in plot.py.
"""
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

STATION = os.environ.get("STATION_ID", "BRC")
# NWS asks for a User-Agent that identifies you; set CONTACT in the workflow.
CONTACT = os.environ.get("CONTACT", "station-charts (github actions)")
API = "https://api.weather.gov"
DATA_FILE = Path(__file__).resolve().parent.parent / "data" / f"{STATION}.csv"

# NWS property name -> CSV column name
FIELDS = {
    "temperature": "temp_c",
    "dewpoint": "dewpoint_c",
    "relativeHumidity": "rh_pct",
    "windDirection": "wind_dir_deg",
    "windSpeed": "wind_kmh",
    "windGust": "gust_kmh",
    "barometricPressure": "pressure_pa",
    "seaLevelPressure": "slp_pa",
    "visibility": "visibility_m",
    "precipitationLastHour": "precip_1h_mm",
    "precipitationLast3Hours": "precip_3h_mm",
    "precipitationLast6Hours": "precip_6h_mm",
    "windChill": "windchill_c",
    "heatIndex": "heatindex_c",
}


def get_json(url, params=None):
    r = requests.get(
        url,
        params=params,
        headers={"User-Agent": CONTACT, "Accept": "application/geo+json"},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def fetch_since(start):
    """Return a list of row dicts for observations after `start`, following pagination."""
    url = f"{API}/stations/{STATION}/observations"
    params = {"start": start.strftime("%Y-%m-%dT%H:%M:%SZ"), "limit": 500}
    rows, pages = [], 0
    while url and pages < 20:
        data = get_json(url, params)
        feats = data.get("features", [])
        if not feats:
            break
        for f in feats:
            p = f["properties"]
            row = {"timestamp": p["timestamp"]}
            for key, col in FIELDS.items():
                v = p.get(key)
                row[col] = v.get("value") if isinstance(v, dict) else None
            row["text"] = p.get("textDescription")
            rows.append(row)
        # The next page link already carries its own query string.
        url, params = data.get("pagination", {}).get("next"), None
        pages += 1
    return rows


def main():
    if DATA_FILE.exists():
        old = pd.read_csv(DATA_FILE, parse_dates=["timestamp"])
        last = old["timestamp"].max()
        # Go back a few hours so late or corrected obs are picked up.
        start = last.to_pydatetime() - timedelta(hours=6)
    else:
        old = pd.DataFrame()
        start = datetime.now(timezone.utc) - timedelta(days=7)

    try:
        rows = fetch_since(start)
    except requests.HTTPError as e:
        print(f"NWS API error for station {STATION}: {e}", file=sys.stderr)
        sys.exit(1)

    new = pd.DataFrame(rows)
    if new.empty:
        print("No new observations.")
        return
    new["timestamp"] = pd.to_datetime(new["timestamp"], utc=True)

    df = pd.concat([old, new], ignore_index=True)
    df = (
        df.drop_duplicates(subset="timestamp", keep="last")
        .sort_values("timestamp")
        .reset_index(drop=True)
    )
    DATA_FILE.parent.mkdir(exist_ok=True)
    df.to_csv(DATA_FILE, index=False, date_format="%Y-%m-%dT%H:%M:%SZ")
    print(f"{STATION}: {len(new)} fetched, {len(df)} total rows, latest {df['timestamp'].max()}")


if __name__ == "__main__":
    main()
