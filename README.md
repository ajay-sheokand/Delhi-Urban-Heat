# Delhi Urban Heat Monitoring Dashboard

Interactive Streamlit dashboard for monitoring urban heat in Delhi using satellite and weather data.

Live app: `https://delhi-urban-heat.streamlit.app/`

## Scope

- Region: National Capital Territory of Delhi
- District coverage: 11 districts
- Main use case: map-based heat monitoring + historical analysis

## What The App Shows

- Landsat 8 L2 Land Surface Temperature (LST)
- Landsat 8 NDVI (Sentinel-2 fallback in one analysis block)
- Land Cover layer (ESA WorldCover primary, MODIS fallback)
- Live district weather markers (OpenWeather)
- Historical district air temperature (NASA POWER)
- Time series analysis for LST
- Spatial/UHI analysis and NDVI-LST-LULC correlation analysis

## Key UI Behavior

- Satellite section supports date range selection.
- Map has two modes:
  - `Median composite (range)`
  - `Scene selection (single scene)`
- In scene mode, users pick one scene directly from a select box (date-time, cloud %, scene id in label).
- Scene tables in the satellite/date-range section are intentionally hidden.
- Dynamic legends are attached to map layers and update based on layer visibility.
- Auto-refresh runs every 5 minutes.

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

- `app.py`: Streamlit dashboard
- `delhi_admin.geojson`: Delhi administrative boundaries
- `delhi_admin.kml`: Alternate boundary file
- `scripts/precompute_timeseries_backend.py`: Precompute time-series JSON for fast mode
- `.github/workflows/precompute-backend-data.yml`: Scheduled/manual precompute and publish
- `requirements.txt`: Python dependencies
- `runtime.txt`: Python runtime pin

## Local Setup

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

## Optional Fast Backend (GitHub Pages)

This mode precomputes `timeseries_scenes.json` and serves it from GitHub Pages so time-series loading is faster.

### Steps

1. Add GitHub Actions secrets in your repo:
   - `GEE_SERVICE_ACCOUNT`
   - `GEE_PRIVATE_KEY`
   - `PRECOMPUTE_DAYS` (optional, e.g. `730`)
2. Ensure GitHub Actions is enabled.
3. Run workflow: `Actions -> Precompute Backend Data -> Run workflow`.
4. In `Settings -> Pages` set:
   - Source: `Deploy from a branch`
   - Branch: `gh-pages`
   - Folder: `/ (root)`
5. Verify output URL:
   - `https://<your-github-username>.github.io/<your-repo-name>/timeseries_scenes.json`
6. Set `PRECOMPUTED_DATA_BASE_URL` in `.streamlit/secrets.toml` and restart app.

Behavior:

- If precomputed JSON is available, app uses it for time-series inventory/means.
- If unavailable, app falls back to live Earth Engine computation.

## Troubleshooting

- `streamit: command not found`:
  - Use `streamlit run app.py` (spelling is `streamlit`).
- Workflow fails with `Invalid GeoJSON geometry`:
  - Current precompute script already includes fallback geometry logic.
- No workflow visible in Actions:
  - Confirm workflow file is on `main` and Actions are enabled in repo settings.

## Security

- Keep `.streamlit/secrets.toml` out of git.
- Rotate exposed private keys immediately.
- Prefer GitHub/Streamlit secret managers over plaintext files.

For educational and research use.

## Last Updated

March 12, 2026
