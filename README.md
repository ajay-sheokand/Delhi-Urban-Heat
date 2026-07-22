# Delhi Urban Heat Monitoring Dashboard

Static, precomputed dashboard for monitoring urban heat in Delhi using satellite and weather data.

Live app: `https://<your-github-username>.github.io/<your-repo-name>/`

A legacy Streamlit dashboard (`app.py`) is still in the repo but is no longer the primary/linked app — see [Legacy Streamlit App](#legacy-streamlit-app).

## Scope

- Region: National Capital Territory of Delhi
- District coverage: 11 districts
- Main use case: map-based heat monitoring + historical analysis

## What The Static Frontend Shows (v1)

- Landsat 8 L2 Land Surface Temperature (LST), median composite over a rolling recent window
- Landsat 8 NDVI (same window)
- Land Cover layer (ESA WorldCover)
- District weather markers and heat alerts (OpenWeather, precomputed every 6h)
- Time series analysis for LST
- District boundaries overlay

The following sections of the older Streamlit app are **not yet ported** to the static frontend and remain available only in the legacy app: spatial/UHI analysis (air temperature vs LST by district), NDVI-LST-LULC correlation analysis, historical NASA POWER air temperature, and detailed per-district comparison tables. These are planned as a fast-follow.

## Key UI Behavior

- Map layers (LST/NDVI/land cover) and weather/heat alerts are all precomputed server-side and refresh automatically every 6 hours via GitHub Actions — there is no per-visit satellite or weather computation, and no API keys are ever exposed to the browser. The page loads instantly but reflects data as of the last refresh, not the live moment.
- Legends update based on which layers are toggled on.

## Data Sources

- Live weather: OpenWeather API
- Historical weather: NASA POWER Daily API (`T2M`)
- LST + NDVI: `LANDSAT/LC08/C02/T1_L2`
- NDVI fallback: `COPERNICUS/S2_SR_HARMONIZED`
- Land cover primary: `ESA/WorldCover/v200`
- Land cover fallback: `MODIS/061/MCD12Q1`
- Local Delhi boundary: `delhi_admin.geojson`

## Core Calculations

- Cloud masking: Landsat `QA_PIXEL` bits (shadow/snow/cloud/cirrus removed)
- LST conversion: `ST_B10 * 0.00341802 + 149.0 - 273.15`
- NDVI: scaled Landsat SR bands (`SR_B5`, `SR_B4`)
- Map LST color range: dynamic `min/max` from `Reducer.minMax()` with small buffer
- Land-cover distribution: `Reducer.frequencyHistogram()`
- Time-series mean LST: per-image `Reducer.mean()` over study geometry
- Optional LULC split in time-series: grouped mean by WorldCover class
- Correlation: Pearson `corr(NDVI, LST)` on sampled pixels

## Project Structure

- `web/`: static frontend (primary app) — `index.html`, `app.js` (MapLibre map + Chart.js time series + weather), `style.css`
- `app.py`: legacy Streamlit dashboard (secondary, not linked as the primary app)
- `delhi_admin.geojson`: Delhi administrative boundaries (used by both the static frontend and the precompute script)
- `delhi_admin.kml`: Alternate boundary file
- `scripts/precompute_timeseries_backend.py`: Precomputes `timeseries_scenes.json` (LST time series), `map_layers.json` (LST/NDVI/land-cover tile URLs), and `weather.json` (per-district OpenWeather readings + heat alerts)
- `.github/workflows/precompute-backend-data.yml`: Scheduled/manual precompute, then publishes `web/`, `delhi_admin.geojson`, and `backend-data/` to `gh-pages`
- `requirements.txt`: Python dependencies
- `runtime.txt`: Python runtime pin

## Static Frontend Setup (GitHub Pages)

The static frontend and its data are published together to the `gh-pages` branch by the same workflow, so setup is a single flow:

1. Add GitHub Actions secrets in your repo:
   - `GEE_SERVICE_ACCOUNT`
   - `GEE_PRIVATE_KEY`
   - `OPENWEATHER_API_KEY` — used server-side only, inside the Actions run, to precompute `weather.json`. It is never written into any client-side file.
   - `PRECOMPUTE_DAYS` (optional, e.g. `730`) — time-series history window
   - `MAP_COMPOSITE_DAYS` is set via an env var in the script (default `45`) — change it in `scripts/precompute_timeseries_backend.py` if you want a different rolling window for the map layers, not a required secret.
2. Ensure GitHub Actions is enabled, then run the workflow: `Actions -> Precompute Backend Data -> Run workflow`.
3. In `Settings -> Pages` set:
   - Source: `Deploy from a branch`
   - Branch: `gh-pages`
   - Folder: `/ (root)`
4. Visit `https://<your-github-username>.github.io/<your-repo-name>/` — this now serves `web/index.html` directly, reading `map_layers.json`, `weather.json`, and `timeseries_scenes.json` from the same site.

The workflow re-runs every 6 hours, regenerating all three JSON files (including fresh Earth Engine tile URLs and fresh weather readings) and republishing everything to `gh-pages`. If `OPENWEATHER_API_KEY` is missing or a weather fetch fails, the script leaves the previous `weather.json` in place rather than failing the whole run.

## Legacy Streamlit App

### 1. Create virtual environment

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

macOS/Linux:

```bash
python -m venv .venv
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Add Streamlit secrets

Create `.streamlit/secrets.toml`:

```toml
OPENWEATHER_API_KEY = "your_openweather_api_key"
GEE_SERVICE_ACCOUNT = "your-service-account@project-id.iam.gserviceaccount.com"
GEE_PRIVATE_KEY = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
PRECOMPUTED_DATA_BASE_URL = "https://<your-github-username>.github.io/<your-repo-name>"
```

Notes:

- Keep `\n` in `GEE_PRIVATE_KEY`.
- Do not commit secrets.

### 4. Run app

```bash
streamlit run app.py
```

Default URL: `http://localhost:8501`

The Streamlit app can also read the same precomputed `timeseries_scenes.json` for faster time-series loading: set `PRECOMPUTED_DATA_BASE_URL` in `.streamlit/secrets.toml` to your GitHub Pages URL and restart. If unavailable, it falls back to live Earth Engine computation.

## Troubleshooting

- `streamit: command not found`:
  - Use `streamlit run app.py` (spelling is `streamlit`).
- Workflow fails with `Invalid GeoJSON geometry`:
  - Current precompute script already includes fallback geometry logic.
- No workflow visible in Actions:
  - Confirm workflow file is on `main` and Actions are enabled in repo settings.
- Static frontend map layers look stale or missing:
  - Earth Engine tile URLs from `getMapId()` are regenerated every 6h by the cron. If a browser tab is left open across a refresh boundary, or the precompute run fails, reload the page — `map_layers.json` keeps the previous run's tiles until the next successful run.

## Security

- Keep `.streamlit/secrets.toml` out of git.
- Rotate exposed private keys immediately.
- Prefer GitHub/Streamlit secret managers over plaintext files.
- `GEE_SERVICE_ACCOUNT`, `GEE_PRIVATE_KEY`, and `OPENWEATHER_API_KEY` must all stay server-side only (GitHub Actions secrets) — none of them are ever written into `web/app.js` or any other client-side file. The static frontend only ever fetches the precomputed JSON output (`map_layers.json`, `timeseries_scenes.json`, `weather.json`), never a live third-party API directly.

For educational and research use.

## Last Updated

July 22, 2026
