# Delhi Urban Heat Monitoring Dashboard

Static, precomputed dashboard for monitoring urban heat in Delhi using satellite and weather data.

Live app: `https://ajay-sheokand.github.io/Delhi-Urban-Heat/`

A legacy Streamlit dashboard (`app.py`) is still in the repo but is no longer the primary/linked app — see [Legacy Streamlit App](#legacy-streamlit-app).

## Scope

- Region: National Capital Territory of Delhi
- District coverage: 11 districts
- Main use case: map-based heat monitoring + historical analysis

## What The Static Frontend Shows

**Map (`index.html`)**
- Landsat 8 L2 Land Surface Temperature (LST), median composite over a rolling recent window
- Landsat 8 NDVI (same window)
- Land Cover layer (ESA WorldCover)
- District weather markers and heat alerts (OpenWeather, precomputed every 6h)
- Time series chart for LST, district boundaries overlay

**Analytics (`analytics.html`)**
- Urban heat island intensity by district, both air-temperature-based (NASA POWER vs citywide mean) and surface-based (LST vs cropland baseline)
- Air temperature vs LST scatter, NDVI vs LST correlation scatter with trend line and headline Pearson r
- Land-cover composition (area share + mean LST/NDVI by class) from pixel sampling
- LST-by-land-cover-type time series
- Full per-district comparison table

**Roadmap (`roadmap.html`)**
- Real, computed evidence of cloud-cover data gaps in the Landsat record (expected vs actual scene cadence, largest gaps, scenes-per-month chart)
- The case for a SAR-Optical reconstruction approach to fill those gaps (in development — see the file for status)

**Heat Vulnerability by Ward (`analytics.html`)**
- The same LST/NDVI inputs re-run at ward resolution (290 wards, ~26x finer than the 11 districts), plus WorldPop population density, combined into a per-ward vulnerability score
- A ranked top-20 "most vulnerable wards" chart/table, and a clickable ward layer on the map — see [Core Calculations](#core-calculations) for the scoring formula and why air temperature stays district-level

All three pull only from the precomputed JSON in `backend-data/` — nothing here triggers a live Earth Engine or third-party API call from the browser.

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
- Population: `WorldPop/GP/100m/pop` (most recent available year, ~93m resolution) — CC-BY 4.0
- Local Delhi boundary: `delhi_admin.geojson` (11 districts)
- Local ward boundaries: `delhi_wards.geojson` (290 wards) — from [datameet/Municipal_Spatial_Data](https://github.com/datameet/Municipal_Spatial_Data), CC-BY-SA 2.5 India. This reflects the **pre-2022 delimitation** (the three erstwhile municipal corporations + NDMC + Delhi Cantonment) — no open, downloadable geometry file for the current unified 250-ward structure was found. 290 zones at the old delimitation is still a large resolution jump over 11 districts; the vintage is disclosed here and on the analytics page rather than presented as current.

## Core Calculations

- Cloud masking: Landsat `QA_PIXEL` bits (shadow/snow/cloud/cirrus removed)
- LST conversion: `ST_B10 * 0.00341802 + 149.0 - 273.15`
- NDVI: scaled Landsat SR bands (`SR_B5`, `SR_B4`)
- Map LST color range: dynamic `min/max` from `Reducer.minMax()` with small buffer
- Land-cover distribution: `Reducer.frequencyHistogram()`
- Time-series mean LST: per-image `Reducer.mean()` over study geometry
- Optional LULC split in time-series: grouped mean by WorldCover class
- Correlation: Pearson `corr(NDVI, LST)` on sampled pixels
- Ward vulnerability score: average of min-max normalized LST, inverse-normalized NDVI, and normalized population density across all 290 wards (0-100, higher = more vulnerable). Computed via batched `reduceRegions()` zonal stats (a couple of server-side calls covering all wards at once) rather than per-ward round trips. Air temperature (NASA POWER, ~50km grid) and live weather (OpenWeather, station-scale) are deliberately **not** part of this score and stay district-level only — neither source carries real spatial signal at ward resolution across a city Delhi's size, so folding them in would be false precision, not more information.

## Project Structure

- `web/`: static frontend (primary app)
  - `index.html` / `app.js`: MapLibre map + Chart.js time series + weather
  - `analytics.html` / `analytics.js`: UHI, correlation, and land-cover analytics
  - `roadmap.html` / `roadmap.js`: cloud-gap evidence + SAR-Optical GNN roadmap narrative
  - `style.css`: shared styling for all three pages
- `app.py`: legacy Streamlit dashboard (secondary, not linked as the primary app)
- `delhi_admin.geojson`: Delhi administrative boundaries (used by the static frontend, the precompute script's region geometry, and per-district analytics — each of its 11 features carries a `District` name property)
- `delhi_admin.kml`: Alternate boundary file
- `delhi_wards.geojson`: Delhi ward boundaries (290 features, `Ward_Name`/`Ward_No` properties — `Ward_No` is the unique key used to match `ward_vulnerability.json` rows; see [Data Sources](#data-sources) for provenance/license)
- `scripts/precompute_timeseries_backend.py`: Precomputes `timeseries_scenes.json` (LST time series), `map_layers.json` (LST/NDVI/land-cover tile URLs), `district_analytics.json` (UHI/correlation/land-cover analytics), `weather.json` (per-district OpenWeather readings + heat alerts), `historical_trends.json` (LST-by-land-cover, monthly, full history — recomputed weekly, not every 6h, since it's a much heavier query; force an immediate recompute via the `force_historical_trends` input on a manual `Run workflow`), and `ward_vulnerability.json` (per-ward LST/NDVI/population and vulnerability score, 290 wards, recomputed every 6h)
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
   - `MAP_COMPOSITE_DAYS` and `ANALYTICS_AIR_TEMP_DAYS` are plain env vars with defaults (`45` and `90` respectively) inside `scripts/precompute_timeseries_backend.py` — edit the script if you want different rolling windows; not required secrets.
2. Ensure GitHub Actions is enabled, then run the workflow: `Actions -> Precompute Backend Data -> Run workflow`.
3. In `Settings -> Pages` set:
   - Source: `Deploy from a branch`
   - Branch: `gh-pages`
   - Folder: `/ (root)`
4. Visit `https://<your-github-username>.github.io/<your-repo-name>/` — this now serves `web/index.html` directly, reading `map_layers.json`, `district_analytics.json`, `weather.json`, `timeseries_scenes.json`, and `ward_vulnerability.json` from the same site. `analytics.html` and `roadmap.html` are linked from the map's top-left panel.

The workflow re-runs every 6 hours, regenerating the precomputed JSON files (including fresh Earth Engine tile URLs and fresh weather readings) and republishing everything to `gh-pages`. Each precomputed file has its own try/except in the script — if one fails (e.g. a transient EE or NASA POWER error), the previous version of that file is left in place rather than failing the whole run (the workflow's "Seed backend-data from previous publish" step is what makes that fallback real: it pulls the current live copy of each file before the script runs, so a skipped or failed dataset republishes unchanged instead of vanishing).

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
- `GEE_SERVICE_ACCOUNT`, `GEE_PRIVATE_KEY`, and `OPENWEATHER_API_KEY` must all stay server-side only (GitHub Actions secrets) — none of them are ever written into `web/app.js` or any other client-side file. The static frontend only ever fetches the precomputed JSON output (`map_layers.json`, `district_analytics.json`, `timeseries_scenes.json`, `weather.json`), never a live third-party API directly.

For educational and research use.

## Last Updated

July 23, 2026
