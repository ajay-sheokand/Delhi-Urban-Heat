# Delhi Urban Heat Monitoring Dashboard

Static, precomputed dashboard for monitoring urban heat in Delhi using satellite and weather data.

Live app: `https://ajay-sheokand.github.io/Delhi-Urban-Heat/`

A legacy Streamlit dashboard (`app.py`) is still in the repo but is no longer the primary/linked app — see [Legacy Streamlit App](#legacy-streamlit-app).

## Scope

- Region: National Capital Territory of Delhi
- District coverage: 11 districts (`delhi_admin.geojson`)
- Ward coverage: 290 wards (`delhi_wards.geojson`), pre-2022 delimitation
- Main use case: map-based heat monitoring, historical analysis, and ward-level heat vulnerability ranking

## What The Static Frontend Shows

**Map (`index.html`)**
- Landsat 8 L2 Land Surface Temperature (LST), median composite over a rolling recent window
- Landsat 8 NDVI (same window)
- Land Cover layer (ESA WorldCover)
- District weather markers and heat alerts (OpenWeather, precomputed every 6h)
- Time series chart for LST (client-side date-range filter), district and ward boundary overlays

**Analytics (`analytics.html`)**
- Urban heat island intensity by district, both air-temperature-based (NASA POWER vs citywide mean) and surface-based (LST vs cropland baseline)
- Air temperature vs LST scatter, NDVI vs LST correlation scatter with trend line and headline Pearson r
- Land-cover composition (area share + mean LST/NDVI by class) from pixel sampling
- LST-by-land-cover-type time series (current window and full ~2-year history)
- Heat vulnerability by ward: top-20 ranked chart/table (see [Ward Vulnerability Score](#ward-vulnerability-score) below)
- Full per-district comparison table

**Roadmap (`roadmap.html`)**
- Real, computed evidence of cloud-cover data gaps in the Landsat record (expected vs actual scene cadence, largest gaps, scenes-per-month chart)
- The case for a SAR-Optical reconstruction approach to fill those gaps (in development — see the file for status)

All pages pull only from the precomputed JSON in `backend-data/` — nothing here triggers a live Earth Engine or third-party API call from the browser.

## Key UI Behavior

- Map layers (LST/NDVI/land cover) and weather/heat alerts are all precomputed server-side and refresh automatically every 6 hours via GitHub Actions — there is no per-visit satellite or weather computation, and no API keys are ever exposed to the browser. The page loads instantly but reflects data as of the last refresh, not the live moment.
- Legends update based on which layers are toggled on.

## Data Sources

| Source | Used for | Resolution / cadence | License / access |
|---|---|---|---|
| [Landsat 8 Collection 2 Level-2](https://developers.google.com/earth-engine/datasets/catalog/LANDSAT_LC08_C02_T1_L2) (`LANDSAT/LC08/C02/T1_L2`) | LST, NDVI | 30m optical / 100m native thermal, 16-day revisit | USGS/NASA, public domain |
| [ESA WorldCover v200](https://developers.google.com/earth-engine/datasets/catalog/ESA_WorldCover_v200) | Land cover classification, cropland UHI baseline | 10m, 2021 epoch, 11 classes | Free, [CC BY 4.0](https://esa-worldcover.org/en/data-access) |
| [WorldPop 100m Population](https://developers.google.com/earth-engine/datasets/catalog/WorldPop_GP_100m_pop) (`WorldPop/GP/100m/pop`) | Ward population / density | ~92.77m native pixel, annual (2000-2020/21) | CC BY 4.0 |
| [NASA POWER Daily API](https://power.larc.nasa.gov/docs/services/api/temporal/daily/) (`T2M`) | District air temperature | ~0.5°×0.625° grid (≈56km × 61km at Delhi's latitude) | Public, no key required |
| [OpenWeather Current Weather API](https://openweathermap.org/current) | Live district weather markers, heat alerts | Point/model nowcast, refreshed every 6h by this pipeline | Requires API key (server-side only, see [Security](#security)) |
| [FAO GAUL Simplified 500m, level 1](https://developers.google.com/earth-engine/datasets/catalog/FAO_GAUL_SIMPLIFIED_500m_2015_level1) | Region-geometry fallback only, if `delhi_admin.geojson` fails EE validation | 500m | Free for non-commercial use |
| `delhi_admin.geojson` | 11 district boundaries | KML-derived, local file | — |
| [`delhi_wards.geojson`](https://github.com/datameet/Municipal_Spatial_Data) | 290 ward boundaries | Local file, sourced from an ArcGIS Online map | [CC BY-SA 2.5 India](http://creativecommons.org/licenses/by-sa/2.5/in/) |

`delhi_wards.geojson` reflects the **pre-2022 delimitation** (the three erstwhile municipal corporations + NDMC + Delhi Cantonment) — no open, downloadable geometry file for the current unified 250-ward structure was found. Disclosed here and on the analytics page rather than presented as current.

## Variables & Calculations

Every derived number on the site traces back to one of the formulas below. Each entry cites the specification it was checked against — this section exists so that a constant like `0.00341802` isn't just "a number in the code," it's a number that can be independently verified.

### Land Surface Temperature (LST)

```
LST_C = ST_B10 * 0.00341802 + 149.0 - 273.15
```

`0.00341802` (scale) and `149.0` (offset) are USGS's official Collection 2 Level-2 conversion factors for the `ST_B10` thermal band, converting the raw digital number to Kelvin; subtracting `273.15` converts to Celsius. Source: [USGS — How do I use a scale factor with Landsat Level-2 science products?](https://www.usgs.gov/faqs/how-do-i-use-a-scale-factor-landsat-level-2-science-products) and the [Landsat 8-9 Collection 2 Level-2 Science Product Guide (LSDS-1619)](https://d9-wret.s3.us-west-2.amazonaws.com/assets/palladium/production/s3fs-public/media/files/LSDS-1619_Landsat-8-9-C2-L2-ScienceProductGuide-v4.pdf). Zonal reducers use `scale=100` (not the resampled 30m grid) because 100m is the thermal band's real resolving power.

### NDVI

```
NDVI = (NIR - Red) / (NIR + Red)
NIR = SR_B5 * 0.0000275 - 0.2
Red = SR_B4 * 0.0000275 - 0.2
```

`0.0000275` / `-0.2` are USGS's official Collection 2 Level-2 scale/offset for surface reflectance bands — same source as above.

### Cloud / Shadow / Snow / Cirrus Masking

Applied to `QA_PIXEL` before any LST/NDVI computation, so contaminated pixels never enter a composite. Correct bit positions, per the official LSDS-1619 bit table (also cross-checked against [Digital Earth Africa's Landsat C2 bit reference](https://docs.digitalearthafrica.org/en/latest/data_specs/Landsat_C2_SR_specs.html)):

| Flag | Bit |
|---|---|
| Cirrus (Landsat 8/9 only) | 2 |
| Cloud | 3 |
| Cloud Shadow | 4 |
| Snow | 5 |

**Correctness note:** this was previously wrong in both `scripts/precompute_timeseries_backend.py` and `app.py` — the four bit shifts were off by one position each (e.g. bit 3 was labeled `cloud_shadow_bit` but bit 3 is actually `Cloud`; bit 7, labeled `cirrus_bit`, is actually `Water`). The mask still excluded four real flags (Cloud, Cloud Shadow, Snow, Water), just not the four it was named for, and it never excluded Cirrus at all. Verified against the official spec above and fixed in both files.

### Land Cover Classes (ESA WorldCover v200)

| Code | Class | Code | Class |
|---|---|---|---|
| 10 | Tree cover | 70 | Snow and ice |
| 20 | Shrubland | 80 | Permanent water bodies |
| 30 | Grassland | 90 | Herbaceous wetland |
| 40 | Cropland | 95 | Mangroves |
| 50 | Built-up | 100 | Moss and lichen |
| 60 | Bare / sparse vegetation | | |

Source: [ESA WorldCover Product User Manual v2.0](https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/docs/WorldCover_PUM_V2.0.pdf).

### District / Ward Zonal Statistics

Per-polygon `Reducer.mean()` over LST/NDVI at `scale=100`. Districts (11) use a Python loop of individual `reduceRegion()` calls; wards (290) use a single batched `reduceRegions()` call per variable — one server round trip covering all 290 polygons instead of 290 sequential ones, which is what keeps ward-resolution stats affordable on a 6-hourly schedule. One EE quirk worth documenting: `reduceRegions()` names its output property after the **band name** for `mean()` (so `LST`, `NDVI`), but after the **reducer name** for `sum()` (so `sum`, not `population`) — confirmed empirically against the live service while building the ward population pipeline.

### Air Temperature

NASA POWER `T2M`, averaged over a rolling window (`ANALYTICS_AIR_TEMP_DAYS`, default 90 days), per district centroid. The native grid is ~0.5° latitude × 0.625° longitude — at Delhi's latitude (28.6°N) that's roughly **56km × 61km per cell**, computed as `0.5° × 111.32 km/°` (latitude) and `0.625° × 111.32 km/° × cos(28.6°)` (longitude). Source: [NASA POWER Daily API docs](https://power.larc.nasa.gov/docs/services/api/temporal/daily/). Delhi's NCT is roughly 40km × 50km — smaller than a single POWER grid cell — which is why this variable stays district-level only and is never computed per-ward (see [Known Limitations](#known-limitations)).

### Live Weather & Heat Alerts

OpenWeather's Current Weather API, refreshed every 6h (not a live per-visit call). The heat alert thresholds used here (`≥40°C` = extreme, `≥35°C` = high) are a **simplified proxy**, not India Meteorological Department's official Heat Wave criteria. IMD's actual definition requires the station's maximum temperature to reach at least 40°C (Plains) *and* either an absolute value of 45°C+ or a departure of 4.5–6.4°C+ from that station's climatological normal, generally assessed against daily maximum temperature rather than an instantaneous reading. Source: [NDMA — Heat Wave](https://ndma.gov.in/Natural-Hazards/Heat-Wave), [IMD Heat Wave FAQ](https://internal.imd.gov.in/section/nhac/dynamic/FAQ_heat_wave.pdf).

### Urban Heat Island Intensity — Air (`uhi_air_c`)

```
uhi_air_c = air_temp_c - citywide_air_temp
```

A simplified variant of the standard UHI-intensity approach: deviation from a reference temperature. This project uses the citywide mean across all 11 district centroids as that reference, rather than a dedicated rural monitoring station — the UHI literature specifically flags reference-site selection as consequential to the resulting value, so treat this as a relative (district-vs-city) comparison, not an absolute urban-vs-rural intensity. Source: Stewart, "[On the definition of urban heat island intensity: the rural reference](https://www.researchgate.net/publication/277217810_On_the_definition_of_urban_heat_island_intensity_the_rural_reference)."

### Urban Heat Island Intensity — Surface (`uhi_surface_c`)

```
uhi_surface_c = mean_lst_c - cropland_baseline_lst_c
```

`cropland_baseline_lst_c` is the mean LST over all WorldCover class-40 (Cropland) pixels citywide — used as the non-urban reference, matching the standard surface-UHI (SUHI) practice of comparing built-up LST against a vegetated/rural reference land cover class rather than a single station.

### NDVI ↔ LST Correlation

Pearson `r` computed over 300 randomly sampled pixels (`seed=42`, reproducible run to run). A negative `r` is the expected sign: vegetation cools the surface via evapotranspiration and shading, a well-established relationship in the UHI and remote-sensing literature — the site's headline correlation number is a direct, if simplified, empirical check of that relationship for Delhi specifically.

### Cloud-Gap / Revisit Evidence (Roadmap page)

The 16-day nominal revisit used to compute expected-vs-actual scene counts is Landsat 8's real orbital repeat cycle (this app queries Landsat 8 alone, not the combined Landsat 8+9 constellation, which would nominally halve that to ~8 days). Source: [USGS Landsat Missions overview](https://www.usgs.gov/landsat-missions).

### Population

WorldPop `GP/100m/pop`, filtered to the most recent available year for India (2020 as of the last deploy that touched this dataset — check `population_year` in `ward_vulnerability.json` for the actual value in any given run). These are **modeled** estimates — WorldPop's bottom-up/top-down methods combine census inputs, satellite imagery, and other covariates to produce a gridded surface — not a direct pixel-level census count.

### Ward Vulnerability Score

```
score = 100 * mean(
    minmax_normalize(mean_lst_c),
    minmax_normalize(mean_ndvi, invert=True),
    minmax_normalize(population_density_km2),
)
```

Each component is min-max normalized to [0, 1] across all 290 wards before averaging (NDVI is inverted first, since *lower* NDVI should score as *more* vulnerable). Combining a heat-exposure layer (LST) with a greenness/cooling-capacity layer (NDVI) and a population-exposure layer (density) follows the general structure used in Heat Vulnerability Index (HVI) research, which typically pairs an exposure layer with a population/sensitivity layer.

**Honesty note:** unlike published HVIs — e.g. the US CDC's Heat & Health Index — this score has **no socioeconomic or health-sensitivity inputs** (age, income, air-conditioning access, pre-existing health conditions). It is an *exposure-only* proxy built entirely from remote-sensing and gridded-population data, not a validated clinical or epidemiological vulnerability index. Read the ranking as "hot, green-poor, and dense," not as a certified risk score. Air temperature is deliberately excluded from this score entirely — see [Air Temperature](#air-temperature) above for why.

## Known Limitations

- **Ward boundaries are pre-2022 delimitation** (290 zones from the three erstwhile municipal corporations + NDMC + Cantonment), not the current unified 250-ward structure — no open geometry file for the current boundaries was found.
- **Air temperature and live weather are district-level only, never ward-level.** NASA POWER's grid cell (~56km × 61km) and OpenWeather's station/model data don't carry real spatial signal below city scale — computing them per-ward would be false precision, not more information.
- **Heat alerts are a simplified proxy for IMD's Heat Wave criteria**, not an official declaration — see [Live Weather & Heat Alerts](#live-weather--heat-alerts).
- **The ward vulnerability score is exposure-only** — no socioeconomic or health data — see [Ward Vulnerability Score](#ward-vulnerability-score).
- **`uhi_air_c` uses a citywide-mean reference, not a dedicated rural station** — see [Urban Heat Island Intensity — Air](#urban-heat-island-intensity--air-uhi_air_c).
- **All map layers and analytics reflect the last successful precompute run** (every 6h), not the live moment when a page is loaded.

## Project Structure

- `web/`: static frontend (primary app)
  - `index.html` / `app.js`: MapLibre map + Chart.js time series + weather + district/ward click-to-inspect
  - `analytics.html` / `analytics.js`: UHI, correlation, land-cover, long-term trend, and ward-vulnerability analytics
  - `roadmap.html` / `roadmap.js`: cloud-gap evidence + SAR-Optical GNN roadmap narrative
  - `style.css`: shared styling for all three pages
- `app.py`: legacy Streamlit dashboard (secondary, not linked as the primary app)
- `delhi_admin.geojson`: Delhi administrative boundaries (11 districts, `District` name property)
- `delhi_admin.kml`: Alternate boundary file
- `delhi_wards.geojson`: Delhi ward boundaries (290 features, `Ward_Name`/`Ward_No` properties — `Ward_No` is the unique key used to match `ward_vulnerability.json` rows)
- `scripts/precompute_timeseries_backend.py`: Precomputes `timeseries_scenes.json` (LST time series), `map_layers.json` (LST/NDVI/land-cover tile URLs), `district_analytics.json` (UHI/correlation/land-cover analytics), `weather.json` (per-district OpenWeather readings + heat alerts), `historical_trends.json` (LST-by-land-cover, monthly, full history — recomputed weekly; force an immediate recompute via the `force_historical_trends` input on a manual `Run workflow`), and `ward_vulnerability.json` (per-ward LST/NDVI/population and vulnerability score, 290 wards, recomputed every 6h)
- `.github/workflows/precompute-backend-data.yml`: Scheduled/manual precompute, then publishes `web/`, `delhi_admin.geojson`, `delhi_wards.geojson`, and `backend-data/` to `gh-pages`
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

`app.py` uses the same Landsat cloud-masking and LST/NDVI formulas documented in [Variables & Calculations](#variables--calculations) above (they were originally ported from this file into the precompute script) — including the same QA_PIXEL bit-position fix.

## Troubleshooting

- `streamit: command not found`:
  - Use `streamlit run app.py` (spelling is `streamlit`).
- Workflow fails with `Invalid GeoJSON geometry`:
  - Current precompute script already includes fallback geometry logic.
- No workflow visible in Actions:
  - Confirm workflow file is on `main` and Actions are enabled in repo settings.
- Static frontend map layers look stale or missing:
  - Earth Engine tile URLs from `getMapId()` are regenerated every 6h by the cron. If a browser tab is left open across a refresh boundary, or the precompute run fails, reload the page — `map_layers.json` keeps the previous run's tiles until the next successful run.
- LST/NDVI values look slightly different from before a given date:
  - The `QA_PIXEL` cloud-masking bit positions were corrected (see [Cloud / Shadow / Snow / Cirrus Masking](#cloud--shadow--snow--cirrus-masking)) — composites after that fix exclude Cirrus-contaminated pixels that previously slipped through, and no longer misidentify which flag they were masking. Expect small, real shifts in LST/NDVI values, not a bug.

## Security

- Keep `.streamlit/secrets.toml` out of git.
- Rotate exposed private keys immediately.
- Prefer GitHub/Streamlit secret managers over plaintext files.
- `GEE_SERVICE_ACCOUNT`, `GEE_PRIVATE_KEY`, and `OPENWEATHER_API_KEY` must all stay server-side only (GitHub Actions secrets) — none of them are ever written into `web/app.js` or any other client-side file. The static frontend only ever fetches the precomputed JSON output (`map_layers.json`, `district_analytics.json`, `timeseries_scenes.json`, `weather.json`, `ward_vulnerability.json`), never a live third-party API directly.

For educational and research use.

## Last Updated

July 23, 2026
