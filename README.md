# BRC – Brighton Crest weather charts

Hourly archive and interactive charts for NWS station **BRC** (Brighton Crest snow study plot).

- A GitHub Actions job runs every hour. It pulls new observations from `api.weather.gov`, adds them to `data/BRC.csv`, and rebuilds `docs/index.html`.
- GitHub Pages serves the `docs/` folder as a website.

The NWS API only keeps about 7 days of observations. This repo builds the long-term record from the day you turn it on.

## Setup

1. Create a new **public** repo on GitHub (Pages is free for public repos) and push these files to `main`.
2. In `.github/workflows/update.yml`, put your email in `CONTACT`.
3. **Settings → Actions → General → Workflow permissions** → choose *Read and write permissions*.
4. **Actions** tab → *Update BRC charts* → **Run workflow** for the first run.
5. **Settings → Pages** → Source: *Deploy from a branch*, branch `main`, folder `/docs`.
6. The charts will be at `https://<your-username>.github.io/<repo-name>/`.

## Run locally

```bash
pip install -r requirements.txt
python scripts/fetch.py
python scripts/plot.py
open docs/index.html
```

## Another station

Change `STATION_ID`, `STATION_NAME`, and `LOCAL_TZ` in the workflow (or set them as environment variables locally).

## Notes

- The CSV stores the SI units the API returns (°C, km/h, Pa, mm). `plot.py` converts to °F, mph, mb, and inches.
- A panel only shows up if the station reports that variable.
- GitHub turns off scheduled workflows after 60 days of no repo activity. The hourly commits keep this repo active.
