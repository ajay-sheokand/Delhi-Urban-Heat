# Delhi Urban Heat Monitoring Dashboard

Interactive Streamlit dashboard for monitoring urban heat across Delhi's 11 administrative districts using satellite and weather data.

Live app: `https://delhi-urban-heat.streamlit.app/`

## Coverage Area

This project is **Delhi-only**.

- Geographic focus: National Capital Territory of Delhi
- Administrative coverage: 11 Delhi districts
- No NCR-wide analysis is included in the main dashboards

## Overview

The app combines:

- Live air temperature from OpenWeather (district points)
- Historical air temperature from NASA POWER
- Landsat 8 L2 Land Surface Temperature (LST)
- Landsat 8 NDVI (with Sentinel-2 fallback in some paths)
- Land cover overlays (ESA WorldCover primary, MODIS fallback)
- Interactive map + analytical visualizations

## Features

- Interactive Folium map with layer toggles:
  - LST (Landsat 8)
  - NDVI (Landsat 8)
  - Land Cover (ESA 10m or MODIS 500m fallback)
  - District boundaries
  - Live weather markers
- Dynamic legends for LST, NDVI, and Land Cover
- Land-cover legend filtering to show present classes when histogram is available
- Date range controls for satellite analysis
- Scene selection pane (`Scene selection (single scene)` mode) with per-scene metadata:
  - Acquisition date and UTC time
  - Cloud cover (%)
  - Scene ID (`LANDSAT_PRODUCT_ID` / fallback `system:index`)
  - Explicit selected-scene summary shown in UI
- Two map display modes:
  - Median composite (date-range median)
  - Scene mode (single explicitly selected Landsat scene)
- Landsat LST time-series analysis
- Land-cover-wise LST time series (one line per land cover class)
- Spatial district comparison (air temperature vs LST)
- UHI analysis (air-based and surface-based)
- Vegetation-temperature relationship analysis
- Multi-variable NDVI-LST-LULC correlation analysis
- Auto-refresh every 5 minutes
- Mobile-responsive layout

## Data Sources

- Weather (live): OpenWeather API
- Weather (historical): NASA POWER Daily API (`T2M`)
- Satellite LST + NDVI: `LANDSAT/LC08/C02/T1_L2`
- NDVI fallback (some code paths): `COPERNICUS/S2_SR_HARMONIZED`
- Land Cover primary: `ESA/WorldCover/v200`
- Land Cover fallback: `MODIS/061/MCD12Q1`
- Local district boundaries: `delhi_admin.geojson`
- Optional boundary fallback source (if present in workspace):
  - `geoBoundaries-IND-ADM2-all/geoBoundaries-IND-ADM2_simplified.geojson`
  - `geoBoundaries-IND-ADM1-all/geoBoundaries-IND-ADM1_simplified.geojson`

## Scene Selection Logic (Map)

In `Scene selection (single scene)` mode, the app uses a **scene selection pane** instead of selecting only by date.

- Available scenes are read from Landsat metadata (`system:time_start`, `CLOUD_COVER`, scene ID).
- Each selectable option is a unique scene entry with date-time + cloud cover + scene ID.
- The selected scene is applied directly by filtering Landsat collection with:
  - `LANDSAT_PRODUCT_ID` (primary)
  - `system:index` (fallback)
- This removes ambiguity when multiple scenes exist on the same date.

## Statistics and Calculations Used

This section summarizes the exact statistical logic used in `app.py`.

### Satellite Preprocessing

- Landsat cloud/snow/shadow/cirrus masking: `QA_PIXEL` bitmask filtering.
- LST conversion: `ST_B10 * 0.00341802 + 149.0 - 273.15` (deg C).
- NDVI: `(NIR - RED) / (NIR + RED)` using scaled SR bands (`SR_B5`, `SR_B4`).

### Map Layer Statistics

- LST visualization range:
  - Earth Engine reducer: `Reducer.minMax()` over map geometry.
  - Display range uses buffered min/max with bounds clamp (`-5` to `55` deg C).
- Land cover distribution on map:
  - Earth Engine reducer: `Reducer.frequencyHistogram()` on WorldCover class map.
  - Percent coverage = `class_pixels / total_pixels * 100`.

### Time Series (Historical LST)

- Overall LST line:
  - Per-image mean from `Reducer.mean()` over study geometry.
  - Points are plotted by image acquisition date.
- Land-cover-wise LST lines:
  - WorldCover class band is added to each LST image.
  - Grouped reducer: `Reducer.mean().group(groupField=1, groupName='landcover')`.
  - Produces per-date mean LST for each land cover class.

### Spatial District Comparison

- Air temperature:
  - Primary: NASA POWER daily `T2M` mean over selected date range.
  - Fallback: current OpenWeather temperature if POWER data unavailable.
- District LST at points:
  - Earth Engine point sampling on LST image (`sample(point, scale)`).
- Summary metrics:
  - Min, max, mean, and range computed from district air temperatures.

### UHI (Urban Heat Island) Metrics

- Air UHI intensity by district:
  - `district_air_temp - mean_air_temp_across_districts`.
- Surface UHI intensity by district (LST-based):
  - Baseline: mean LST over cropland mask (WorldCover class `40`) when available.
  - Fallback baseline: mean district LST.
  - Metric: `district_LST - baseline_LST`.

### Vegetation vs Temperature Analysis

- NDVI at district points:
  - Sentinel-2 median image (`COPERNICUS/S2_SR_HARMONIZED`) in date range.
  - Point sample around district coordinates.
- Relationship chart:
  - Scatter between sampled NDVI and district air temperature.

### Multi-Variable Correlation (NDVI-LST-LULC)

- Random spatial sampling:
  - Combined LST + NDVI + LandCover image sampled at 100 m.
  - Up to 500 random points (`seed=42`) within study geometry.
- Data quality filters:
  - LST in `(-50, 60)` deg C.
  - NDVI in `[-1, 1]`.
- Correlation metric:
  - Pearson correlation via `pandas.Series.corr()` between NDVI and LST.
- Urban-vs-vegetation temperature delta:
  - Built-up mean LST (class `50`) minus vegetation mean LST (classes `10,20,30`).
- Land-cover area share:
  - Approximated by sample count proportion per class.
- Trend line in NDVI-LST scatter:
  - Linear fit using NumPy `polyfit` (first-order polynomial).

## Technologies Used (from app.py)

- Framework/UI:
  - `streamlit`
  - `streamlit-autorefresh`
- Mapping and legend rendering:
  - `folium`
  - `streamlit-folium`
  - `branca` (`MacroElement`, `Template`)
- Geospatial and satellite access:
  - `earthengine-api` (`ee`)
  - `geopandas`
  - `shapely` (geometry validation helpers)
- Data and analytics:
  - `pandas`
  - `plotly` (`plotly.graph_objects`)
- API/auth and utilities:
  - `requests`
  - `google-auth` (`google.oauth2.service_account`)
  - Python stdlib: `datetime`, `json`, `os`

## Districts Included

- Central
- East
- New Delhi
- North
- North East
- North West
- Shahadra
- South
- South East
- South West
- West

## Architecture

```mermaid
flowchart LR
  U[User Browser] --> S[Streamlit App: app.py]
  S --> OW[OpenWeather API\nLive Weather]
  S --> NP[NASA POWER API\nHistorical Air Temperature]
  S --> GEE[Google Earth Engine]
  GEE --> L8[Landsat 8 L2\nLST + NDVI]
  GEE --> ESA[ESA WorldCover v200]
  GEE --> MODIS[MODIS MCD12Q1\nFallback Land Cover]
  S --> F[Folium + Leaflet Map]
  S --> P[Plotly Analysis Panels]
  F --> U
  P --> U
```

## Setup

### 1. Create and activate a virtual environment

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

### 3. Configure Streamlit secrets

Create `.streamlit/secrets.toml`:

```toml
OPENWEATHER_API_KEY = "your_openweather_api_key"
GEE_SERVICE_ACCOUNT = "your-service-account@project-id.iam.gserviceaccount.com"
GEE_PRIVATE_KEY = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
```

Notes:

- Keep `\n` newlines in `GEE_PRIVATE_KEY`.
- Never commit secrets to version control.

## Run

```bash
streamlit run app.py
```

Default URL: `http://localhost:8501`

## Optional Fast Backend (GitHub Pages)

This project includes a free precompute backend option using GitHub Actions + GitHub Pages.
It publishes `timeseries_scenes.json` so the Time Series section can load quickly without recomputing from Earth Engine on every run.

### Files Added

- `.github/workflows/precompute-backend-data.yml`
- `scripts/precompute_timeseries_backend.py`

### 1. Add GitHub Repository Secrets

In GitHub: `Settings -> Secrets and variables -> Actions`, add:

- `GEE_SERVICE_ACCOUNT`
- `GEE_PRIVATE_KEY`
- `PRECOMPUTE_DAYS` (optional, example `730`)

### 2. Enable GitHub Pages

In GitHub: `Settings -> Pages`:

- Source: `Deploy from a branch`
- Branch: `gh-pages`
- Folder: `/ (root)`

### 3. Run the Workflow

Go to `Actions -> Precompute Backend Data -> Run workflow`.

The workflow also runs every 6 hours by schedule.

### 4. Configure Streamlit to Read Precomputed Data

Add this in `.streamlit/secrets.toml`:

```toml
PRECOMPUTED_DATA_BASE_URL = "https://<your-github-username>.github.io/<your-repo-name>"
```

The app will automatically use `PRECOMPUTED_DATA_BASE_URL/timeseries_scenes.json` when available.

### Notes

- If precomputed data is unavailable, the app falls back to live Earth Engine calculations.
- Land-cover split in time series is still compute-heavy when enabled.

## Project Files

- `app.py`: Main application logic
- `delhi_admin.geojson`: Delhi district boundaries used for mapping/clipping
- `delhi_admin.kml`: Boundary file (not the primary runtime source)
- `requirements.txt`: Python dependencies
- `runtime.txt`: Runtime pin (`python-3.11.8`)
- `gee-streamlit-service-dca01b062e23.json`: Local credential JSON (sensitive)

## Known Limitations

- Folium legend behavior can be sensitive in Streamlit iframe rendering.
- Point-based air temperatures and raster-based LST/NDVI have different scales.
- Correlation module is sample-based and exploratory.
- If boundary helper folders are missing, geometry may fall back to a Delhi rectangle.

## Security

- Do not commit `.streamlit/secrets.toml`.
- Do not commit service-account private keys to public repos.
- Use deployment platform secret managers where possible.

## License

For educational and research use.

## Last Updated

March 12, 2026
