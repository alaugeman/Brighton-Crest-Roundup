"""Build an interactive chart page (docs/index.html) from data/<STATION>.csv."""
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

STATION = os.environ.get("STATION_ID", "BRC")
STATION_NAME = os.environ.get("STATION_NAME", "Brighton Crest")
TZ = os.environ.get("LOCAL_TZ", "America/Denver")
ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = ROOT / "data" / f"{STATION}.csv"
SNOW_FILE = ROOT / "data" / f"{STATION}_snow.csv"
OUT_FILE = ROOT / "docs" / "index.html"

C2F = lambda c: c * 9 / 5 + 32
KMH2MPH = 0.621371
PA2MB = 0.01
MM2IN = 1 / 25.4


def load():
    df = pd.read_csv(DATA_FILE, parse_dates=["timestamp"])
    df["time"] = df["timestamp"].dt.tz_convert(TZ)
    df["temp_f"] = C2F(df["temp_c"])
    df["dewpoint_f"] = C2F(df["dewpoint_c"])
    df["windchill_f"] = C2F(df["windchill_c"])
    df["wind_mph"] = df["wind_kmh"] * KMH2MPH
    df["gust_mph"] = df["gust_kmh"] * KMH2MPH
    df["pressure_mb"] = df["pressure_pa"] * PA2MB
    df["precip_1h_in"] = df["precip_1h_mm"] * MM2IN
    return df


def load_snow():
    """Synoptic snow data (inches), if the snow fetch has run."""
    if not SNOW_FILE.exists():
        return None
    s = pd.read_csv(SNOW_FILE, parse_dates=["timestamp"])
    s["time"] = s["timestamp"].dt.tz_convert(TZ)
    return s


def has(df, col):
    return col in df and df[col].notna().any()


def build(df, snow=None):
    s = snow if snow is not None else pd.DataFrame()
    panels = [
        ("Temperature (°F)", [(df, "temp_f"), (df, "dewpoint_f"), (df, "windchill_f")]),
        ("Snow depth (in)", [(s, "snow_depth_in")]),
        ("Interval new snow (in)", [(s, "snow_interval_in")]),
        ("Snow water equivalent (in)", [(s, "swe_in")]),
        ("Relative humidity (%)", [(df, "rh_pct")]),
        ("Wind (mph)", [(df, "wind_mph"), (df, "gust_mph")]),
        ("Wind direction (°)", [(df, "wind_dir_deg")]),
        ("Station pressure (mb)", [(df, "pressure_mb")]),
        ("Precip, last hour (in)", [(df, "precip_1h_in")]),
    ]
    # Only draw panels that have data. Many stations don't report everything.
    panels = [(t, [(f, c) for f, c in cols if has(f, c)]) for t, cols in panels]
    panels = [(t, cols) for t, cols in panels if cols]

    fig = make_subplots(
        rows=len(panels), cols=1, shared_xaxes=True, vertical_spacing=0.035,
        subplot_titles=[t for t, _ in panels],
    )
    style = {
        "temp_f": dict(name="Temp", color="#d6492f"),
        "dewpoint_f": dict(name="Dewpoint", color="#2e8b57"),
        "windchill_f": dict(name="Wind chill", color="#5b8bd6", dash="dot"),
        "rh_pct": dict(name="RH", color="#2e8b57"),
        "wind_mph": dict(name="Speed", color="#3366cc"),
        "gust_mph": dict(name="Gust", color="#f28e2b", mode="markers"),
        "wind_dir_deg": dict(name="Direction", color="#555555", mode="markers"),
        "pressure_mb": dict(name="Pressure", color="#7b4fa0"),
        "precip_1h_in": dict(name="Precip 1h", color="#1f77b4", bar=True),
        "snow_depth_in": dict(name="Snow depth", color="#1b4f9c", width=2.2),
        "snow_interval_in": dict(name="Interval snow", color="#6fa8dc", bar=True),
        "swe_in": dict(name="SWE", color="#0f8b8d"),
    }
    for i, (_, cols) in enumerate(panels, start=1):
        for f, c in cols:
            s = style[c]
            if s.get("bar"):
                tr = go.Bar(x=f["time"], y=f[c], name=s["name"], marker_color=s["color"])
            else:
                mode = s.get("mode", "lines")
                tr = go.Scatter(
                    x=f["time"], y=f[c], name=s["name"], mode=mode,
                    connectgaps=False,
                    line=dict(color=s["color"], width=s.get("width", 1.6), dash=s.get("dash")),
                    marker=dict(color=s["color"], size=4),
                )
            fig.add_trace(tr, row=i, col=1)
        if [c for _, c in cols] == ["wind_dir_deg"]:
            fig.update_yaxes(range=[0, 360], tickvals=[0, 90, 180, 270, 360],
                             ticktext=["N", "E", "S", "W", "N"], row=i, col=1)

    # Open on the last 7 days and offer quick range buttons.
    end = df["time"].max()
    fig.update_xaxes(range=[end - pd.Timedelta(days=7), end], showgrid=True)
    fig.update_xaxes(
        rangeselector=dict(buttons=[
            dict(count=1, label="24h", step="day", stepmode="backward"),
            dict(count=3, label="3d", step="day", stepmode="backward"),
            dict(count=7, label="7d", step="day", stepmode="backward"),
            dict(count=1, label="1mo", step="month", stepmode="backward"),
            dict(step="all", label="All"),
        ]),
        row=1, col=1,
    )
    fig.update_layout(
        height=230 * len(panels) + 80,
        template="plotly_white",
        hovermode="x unified",
        legend=dict(orientation="h", y=1.02, x=1, xanchor="right", yanchor="bottom"),
        margin=dict(l=60, r=20, t=60, b=40),
    )
    return fig


def latest_summary(df, snow=None):
    r = df.iloc[-1]
    def fmt(v, unit, nd=0):
        return "—" if pd.isna(v) else f"{v:.{nd}f}{unit}"
    text = (
        f"Latest ({r['time']:%a %b %-d, %-I:%M %p %Z}): "
        f"{fmt(r['temp_f'], '°F')} · dewpoint {fmt(r['dewpoint_f'], '°F')} · "
        f"RH {fmt(r['rh_pct'], '%')} · wind {fmt(r['wind_dir_deg'], '°')} "
        f"at {fmt(r['wind_mph'], ' mph')} gust {fmt(r['gust_mph'], ' mph')}"
    )
    if snow is not None and has(snow, "snow_depth_in"):
        sd = snow.dropna(subset=["snow_depth_in"])
        last = sd.iloc[-1]
        text += f" · snow depth {last['snow_depth_in']:.1f} in"
        day_ago = sd[sd["time"] <= last["time"] - pd.Timedelta(hours=24)]
        if not day_ago.empty:
            text += f" ({last['snow_depth_in'] - day_ago.iloc[-1]['snow_depth_in']:+.1f} in / 24h)"
    return text


def main():
    df = load()
    snow = load_snow()
    fig = build(df, snow)
    chart = fig.to_html(full_html=False, include_plotlyjs="cdn", config={"displaylogo": False})
    updated = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M UTC")
    html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{STATION} – {STATION_NAME}</title>
<style>
 body{{font-family:system-ui,-apple-system,Segoe UI,sans-serif;margin:0 auto;max-width:1200px;padding:16px;color:#222}}
 h1{{margin:0 0 4px;font-size:1.5rem}} .sub{{color:#666;margin:0 0 8px}}
 .now{{background:#f4f6f8;border-radius:6px;padding:8px 12px;margin:8px 0 4px}}
 footer{{color:#888;font-size:.85rem;margin-top:12px}}
</style></head><body>
<h1>{STATION_NAME} ({STATION})</h1>
<p class="sub">NWS observations{' + Synoptic snow data' if snow is not None else ''} · times in {TZ} · {len(df):,} obs since {df['time'].min():%Y-%m-%d}</p>
<div class="now">{latest_summary(df, snow)}</div>
{chart}
<footer>Data: api.weather.gov{' · Synoptic Data' if snow is not None else ''} · page rebuilt {updated} · <a href="{STATION}.csv">download CSV</a>{f' · <a href="{SNOW_FILE.name}">snow CSV</a>' if snow is not None else ''}</footer>
</body></html>"""
    OUT_FILE.parent.mkdir(exist_ok=True)
    OUT_FILE.write_text(html, encoding="utf-8")
    # Pages only serves docs/, so publish a copy of the archive alongside the page.
    (OUT_FILE.parent / f"{STATION}.csv").write_bytes(DATA_FILE.read_bytes())
    if SNOW_FILE.exists():
        (OUT_FILE.parent / SNOW_FILE.name).write_bytes(SNOW_FILE.read_bytes())
    print(f"Wrote {OUT_FILE}")


if __name__ == "__main__":
    main()
