# Urban Heat Monitoring Dashboard

Static, precomputed dashboard for monitoring urban heat, now covering two cities — Delhi, India and Münster, Germany — with a one-click switcher between them. Started as a Delhi-only project; see [Multi-City Support](#multi-city-support) for how the second city was added and what does/doesn't carry over between them.

Live app: `https://ajay-sheokand.github.io/Delhi-Urban-Heat/` (add `?city=muenster` for Münster, or use the in-app switcher)

A legacy Streamlit dashboard (`app.py`) is still in the repo but is no longer the primary/linked app, and covers Delhi only — see [Legacy Streamlit App](#legacy-streamlit-app).

## Scope

**Delhi**
- Region: National Capital Territory of Delhi
- District coverage: 11 districts (`delhi_admin.geojson`)
- Ward coverage: 290 wards (`delhi_wards.geojson`), pre-2022 delimitation
- Informal settlement coverage: 685 DUSIB-mapped JJ clusters (`delhi_jj_clusters.geojson`)

**Münster**
- Region: City of Münster, North Rhine-Westphalia, Germany
- District coverage: 9 Stadtbezirke (`muenster_districts.geojson`, dissolved from the ward file)
- Ward coverage: 45 Statistische Bezirke (`muenster_wards.geojson`)
- Elderly-population coverage: Zensus 2022 100m grid, ages 65+ (`muenster_elderly_population.geojson`)

Main use case (both cities): map-based heat monitoring, historical analysis, ward-level heat vulnerability ranking, and a complementary-risk-layer check (informal settlements for Delhi, elderly population for Münster).

## What The Static Frontend Shows

**Map (`index.html`)**
- Landsat 8 L2 Land Surface Temperature (LST), median composite over a rolling recent window
- Landsat 8 NDVI (same window)
- Land Cover layer (ESA WorldCover)
- District weather markers and heat alerts (OpenWeather, precomputed every 6h)
- Time series chart for LST (client-side date-range filter), district, ward, and informal-settlement (JJ cluster) boundary overlays — all click-to-inspect
- Toggleable 3D building extrusion (OpenFreeMap vector tiles, `building` layer, `render_height`/`render_min_height`), tilts the map to 60° pitch on enable — thematically relevant since building density/height relates to heat retention and the urban canyon effect, not just a visual gimmick. Renders from zoom ≥13 (matching the source data's own `minzoom`), so enabling it also zooms in if the map is further out than that. Per-building `colour` is used when OSM has it tagged (falls back to a flat accent color otherwise), plus a vertical shading gradient for a less flat look — this is the practical ceiling on visual/geometric detail for this data: OpenFreeMap's building tiles stop at zoom 14 source resolution (MapLibre overzooms the same geometry beyond that, so nothing is lost by zooming in further, but nothing new appears either) and the schema is LOD1 (block massing only — no roof shapes or building parts), not a limitation of this project's implementation.
- Toggleable **Photorealistic 3D** (beta): Google's Photorealistic 3D Tiles, streamed via Cesium ion (`deck.gl`'s `Tile3DLayer` + `CesiumIonLoader`, interleaved into the MapLibre map through `MapboxOverlay`). Genuinely higher detail than the OpenFreeMap buildings above — real photogrammetric mesh, not block massing — covering the ground, buildings, and trees together, not a thin buildings-only layer, and rendered fully opaque. The native MapLibre LST/NDVI/land-cover raster layers still stay hidden under that mesh (same depth-buffer issue as the boundary layers below), so district/ward/complementary-layer boundaries **and** LST/NDVI/land-cover are redrawn as depth-disabled `deck.gl` layers (`GeoJsonLayer` for boundaries, `TileLayer`+`BitmapLayer` for the raster tiles) on top of the mesh, toggled by the same layer-panel checkboxes, each at `opacity: 0.5` (`PHOTOREALISTIC_OVERLAY_OPACITY` in `app.js`) so the opaque mesh still reads through wherever a data layer is toggled on, rather than being fully hidden by it — see [Known Limitations](#known-limitations) for the depth-buffer workaround this relies on. Uses a free-tier Cesium ion token (non-commercial use, capped at 1,000 root-tile requests/month account-wide — shared across all visitors, not per-visitor) — see [Known Limitations](#known-limitations).

**Analytics (`analytics.html`)**
- Urban heat island intensity by district, both air-temperature-based (NASA POWER vs citywide mean) and surface-based (LST vs cropland baseline)
- Air temperature vs LST scatter, NDVI vs LST correlation scatter with trend line and headline Pearson r
- Land-cover composition (area share + mean LST/NDVI by class) from pixel sampling
- LST-by-land-cover-type time series (current window and full ~2-year history)
- Heat vulnerability by ward: top-20 ranked chart/table (see [Ward Vulnerability Score](#ward-vulnerability-score) below)
- Informal settlements as a complementary risk layer: JJ-cluster counts per ward and a citywide correlation check against the vulnerability score (see [JJ Cluster Overlay & Vulnerability-Score Comparison](#jj-cluster-overlay--vulnerability-score-comparison))
- Full per-district comparison table

**Roadmap (`roadmap.html`)**
- Real, computed evidence of cloud-cover data gaps in the Landsat record (expected vs actual scene cadence, largest gaps, scenes-per-month chart)
- The case for a SAR-Optical reconstruction approach to fill those gaps (in development — see the file for status)

All pages pull only from the precomputed JSON in `backend-data/` — nothing here triggers a live Earth Engine or third-party API call from the browser.

## Key UI Behavior

- Map layers (LST/NDVI/land cover) and weather/heat alerts are all precomputed server-side and refresh automatically every 6 hours via GitHub Actions — there is no per-visit satellite or weather computation, and no API keys are ever exposed to the browser. The page loads instantly but reflects data as of the last refresh, not the live moment.
- Legends update based on which layers are toggled on.

## Multi-City Support

The site started Delhi-only; Münster was added as a second city with a full page reload behind a `?city=` URL parameter (`web/city.js`), not an in-place map teardown/rebuild — simpler and far less bug-prone for a site where all data is precomputed static JSON, so a reload is cheap. The switcher (top-left panel on the map, top nav elsewhere) propagates the current city across all three pages.

**What's shared between cities, unchanged:** every formula in [Variables & Calculations](#variables--calculations) — LST/NDVI conversion, cloud masking, land-cover classes, zonal-statistics methodology, the vulnerability-score formula, the correlation methodology. `scripts/precompute_timeseries_backend.py` runs the exact same `build_*` functions for both cities from one `CITY_CONFIGS` list (`get_city_configs()`) — Delhi's own field names, file paths, and computed values are unchanged from before Münster was added.

**What's genuinely different per city, by necessity:**
- **Boundaries**: Delhi's district/ward files predate this multi-city work (see their own entries below); Münster's come directly from its official open-data portal (see [Data Sources](#data-sources)).
- **The "complementary risk layer"**: Delhi has no equivalent of Germany's Zensus data, and Germany has no equivalent of Delhi's informal settlements — so this layer is Delhi-specific (JJ clusters) or Münster-specific (elderly population 65+) by construction, not a forced shared abstraction. The backend computes both through one generic spatial-join helper (`load_point_features_ward_aggregates()`), parameterized per city; the frontend renders two parallel, independently-worded sections (`data-city-section="delhi"` / `"muenster"` in `analytics.html`), shown/hidden based on the active city, because the two narratives genuinely say different things (see [JJ Cluster Overlay & Vulnerability-Score Comparison](#jj-cluster-overlay--vulnerability-score-comparison) and the Münster elderly-population section on-site).
- **Heat alert methodology**: IMD-style simplified thresholds for Delhi vs DWD-style simplified thresholds for Münster — see [Live Weather & Heat Alerts](#live-weather--heat-alerts).
- **Output paths**: precomputed JSON is namespaced per city (`backend-data/<slug>/*.json`, published to `<slug>/*.json` on `gh-pages`) since both cities produce identically-named files; static boundary files are not namespaced, since they're already uniquely named (`delhi_*` vs `muenster_*`).

## Data Sources

| Source | Used for | Resolution / cadence | License / access |
|---|---|---|---|
| [Landsat 8 Collection 2 Level-2](https://developers.google.com/earth-engine/datasets/catalog/LANDSAT_LC08_C02_T1_L2) (`LANDSAT/LC08/C02/T1_L2`) | LST, NDVI | 30m optical / 100m native thermal, 16-day revisit | USGS/NASA, public domain |
| [ESA WorldCover v200](https://developers.google.com/earth-engine/datasets/catalog/ESA_WorldCover_v200) | Land cover classification, cropland UHI baseline | 10m, 2021 epoch, 11 classes | Free, [CC BY 4.0](https://esa-worldcover.org/en/data-access) |
| [WorldPop 100m Population](https://developers.google.com/earth-engine/datasets/catalog/WorldPop_GP_100m_pop) (`WorldPop/GP/100m/pop`) | Ward population / density | ~92.77m native pixel, annual (2000-2020/21) | CC BY 4.0 |
| [NASA POWER Daily API](https://power.larc.nasa.gov/docs/services/api/temporal/daily/) (`T2M`) | District air temperature | ~0.5°×0.625° grid (≈56km × 61km at Delhi's latitude) | Public, no key required |
| [OpenWeather Current Weather API](https://openweathermap.org/current) | Live district weather markers, heat alerts, wind speed/direction | Point/model nowcast, refreshed every 6h by this pipeline | Requires API key (server-side only, see [Security](#security)) |
| [FAO GAUL Simplified 500m, level 1](https://developers.google.com/earth-engine/datasets/catalog/FAO_GAUL_SIMPLIFIED_500m_2015_level1) | Region-geometry fallback only, if `delhi_admin.geojson` fails EE validation | 500m | Free for non-commercial use |
| `delhi_admin.geojson` | 11 district boundaries | KML-derived, local file | — |
| [`delhi_wards.geojson`](https://github.com/datameet/Municipal_Spatial_Data) | 290 ward boundaries | Local file, sourced from an ArcGIS Online map | [CC BY-SA 2.5 India](http://creativecommons.org/licenses/by-sa/2.5/in/) |
| [`delhi_jj_clusters.geojson`](https://github.com/yashveeeeeeer/india-geodata) | 685 JJ (Jhuggi-Jhopri) informal settlement boundaries | Local file, sourced from DUSIB (Delhi Urban Shelter Improvement Board), via the `india-geodata` GitHub release `urban/boundaries` | [CC0](https://creativecommons.org/publicdomain/zero/1.0/) (public domain) |
| [Stadt Münster Open Data Portal](https://opendata.stadt-muenster.de/) | 45 ward (Statistische Bezirke) boundaries — `muenster_wards.geojson`; 9 districts (`muenster_districts.geojson`) dissolved from these locally by `STADTBEZIR` | Official city GeoJSON, verified 45/45 valid geometries | Open data, city portal |
| [Zensus 2022 (Destatis)](https://www.destatis.de/zensus2022) — 100m population-by-age grid | `muenster_elderly_population.geojson`: ages 65+, clipped to Münster and joined to wards | 100m INSPIRE grid, official 2022 federal census | Official German federal statistics |
| [OpenFreeMap](https://openfreemap.org/) (`https://tiles.openfreemap.org/planet`, OpenMapTiles schema) | Toggleable 3D building extrusion (both cities) | Global OSM-derived vector tiles, `building` layer with `render_height`/`render_min_height`, effective from zoom 14 | Free, unlimited, no API key — data © OpenStreetMap contributors, [ODbL](https://www.openstreetmap.org/copyright) |
| [Google Photorealistic 3D Tiles](https://cesium.com/learn/photorealistic-3d-tiles-learn/), via [Cesium ion](https://cesium.com/platform/cesium-ion/) (asset `2275207`, confirmed against the live ion API) | Toggleable "Photorealistic 3D" beta layer (both cities) | Photogrammetric mesh, global coverage over 2,500+ cities | Free-tier Cesium ion account, **non-commercial use only**, capped at 1,000 root-tile requests/month account-wide — token is client-side by design (Cesium ion tokens are restricted by domain, not kept secret), see [Known Limitations](#known-limitations) |

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

NASA POWER `T2M`, averaged over a rolling window (`ANALYTICS_AIR_TEMP_DAYS`, default 90 days), per district centroid, for both cities. The native grid is ~0.5° latitude × 0.625° longitude — at Delhi's latitude (28.6°N) that's roughly **56km × 61km per cell** (`0.5° × 111.32 km/°` for latitude, `0.625° × 111.32 km/° × cos(28.6°)` for longitude); at Münster's latitude (52.0°N) the same math gives roughly **56km × 43km per cell**, since the longitude term shrinks with `cos(latitude)` closer to the pole. Source: [NASA POWER Daily API docs](https://power.larc.nasa.gov/docs/services/api/temporal/daily/). Both Delhi's NCT (~40km × 50km) and Münster's city area (~15km × 15km) are smaller than a single POWER grid cell — which is why this variable stays district-level only and is never computed per-ward, for either city (see [Known Limitations](#known-limitations)).

### Live Weather & Heat Alerts

OpenWeather's Current Weather API, refreshed every 6h (not a live per-visit call). The same response already used for temperature/humidity also carries wind data, so `weather.json` includes `wind_speed_ms` and `wind_deg` per district for both cities at no extra API cost — `wind_deg` is meteorological convention (the direction the wind is blowing **from**, 0°/360°=N), converted client-side to km/h and a 16-point compass label (`fmtWind()` in `app.js`) for display in each district's weather marker popup. Each city uses a different, city-appropriate alert methodology, both **simplified proxies** rather than a reimplementation of the official model:

- **Delhi (`heat_alert_imd`)**: `≥40°C` = extreme, `≥35°C` = high, based on OpenWeather's `feels_like` value (falls back to raw temperature if unavailable) — same feels_like-over-dry-bulb reasoning as Münster's proxy below, since raw temperature understates perceived heat stress during Delhi's humid pre-monsoon/monsoon heat. Not India Meteorological Department's official Heat Wave criteria — IMD's actual definition requires the station's maximum temperature to reach at least 40°C (Plains) *and* either an absolute value of 45°C+ or a departure of 4.5–6.4°C+ from that station's climatological normal, generally assessed against daily maximum temperature rather than an instantaneous felt-temperature reading. Source: [NDMA — Heat Wave](https://ndma.gov.in/Natural-Hazards/Heat-Wave), [IMD Heat Wave FAQ](https://internal.imd.gov.in/section/nhac/dynamic/FAQ_heat_wave.pdf).
- **Münster (`heat_alert_dwd`)**: `≥38°C` = extreme, `≥32°C` = high, based on OpenWeather's `feels_like` value. Not DWD's official Hitzewarnung system, which uses a humidity/wind/solar-adjusted "felt temperature" from the Klima-Michel model (with a dedicated "Klima-Michel Senior" variant for elderly residents) rather than a single API's feels-like field, and typically requires the elevated felt temperature to persist 2+ consecutive days. The thresholds themselves (32°C strong heat stress / 38°C extreme heat stress) are DWD's real published values. Source: [Uni Bielefeld — Hitzewarnungen (DWD)](https://www.uni-bielefeld.de/themen/hitze/warnstufen/).

### Wind Field (interpolated)

`weather.json`'s `wind_field` object (`build_wind_field()` in the precompute script) turns the ~9-11 real per-district wind readings above into an animated arrow grid on the map (toggle: "🌬️ Wind Field", off by default), for a sense of general flow across the city rather than only at the exact district points. Method, spelled out because it's easy to overstate what a "field" implies:

1. Each district reading (`wind_speed_ms`, `wind_deg`) is converted to a `(u, v)` eastward/northward vector — vector components are what's actually interpolatable; the angle alone isn't (359° and 1° are neighbors, not far apart, so averaging angles directly is wrong).
2. A regular lat/lon grid (default 8×8) is built over the bounding box of the district points, padded 15%.
3. Each grid cell's vector is inverse-distance-weighted (`1/distance²`) from every district's vector, then converted back to a speed/direction.

**Honesty note, same spirit as the [Ward Vulnerability Score](#ward-vulnerability-score)'s:** this is interpolated from a handful of real points, not a measured wind grid — treat it as illustrative of general flow, not as a real reading at any location that isn't one of the source districts. `wind_field.method` is literally the string `"idw_from_district_points"` in the raw JSON, so this is traceable in the data itself, not just in prose here. On the frontend, each arrow points in the direction the wind blows **toward** (opposite of `wind_deg`'s meteorological "from" convention — "where it's going" reads more naturally for a flow visualization) and pulses faster for stronger interpolated wind (`windArrowDuration()` in `app.js`).

**Rendering gotcha, found and fixed after the first deploy of this feature (worth documenting since it's non-obvious and could easily recur):** each arrow is a `maplibregl.Marker`, and MapLibre positions a Marker by writing its own inline `transform: translate(...)` directly onto the element passed as `element:`. A CSS `@keyframes` animation that also animates `transform` on that *same* element fully replaces the property while running — animations don't compose with the underlying inline value, they override it outright — so the very first version of this feature had every arrow's animation wipe out MapLibre's positioning transform the instant it started, collapsing all 64 arrows to the same spot near screen position (0, 0) instead of their real grid coordinates. They existed in the DOM (confirmed via `document.querySelectorAll('.wind-arrow').length`) and had zero console errors, so this was silent — nothing broke loudly, the arrows just weren't where they should be. Fix: two nested elements, not one — an outer "anchor" div that MapLibre positions and never touches with any animation, wrapping an inner `.wind-arrow` div that owns the rotate/pulse animation and has no positioning role of its own.

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

WorldPop `GP/100m/pop`, filtered to the most recent available year for the relevant country (`country` filter: `IND` for Delhi, `DEU` for Münster — see `population_year` in each city's `ward_vulnerability.json` for the actual year in any given run). These are **modeled** estimates — WorldPop's bottom-up/top-down methods combine census inputs, satellite imagery, and other covariates to produce a gridded surface — not a direct pixel-level census count. This is the general ward-level population density input for both cities; Münster's separate elderly-specific 65+ figures come from the Zensus 2022 grid instead (see [JJ Cluster Overlay & Vulnerability-Score Comparison](#jj-cluster-overlay--vulnerability-score-comparison) below, which also covers the Münster elderly-population equivalent).

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

### JJ Cluster Overlay & Vulnerability-Score Comparison

Both cities compute a "complementary risk layer" through the same generic backend helper (`load_point_features_ward_aggregates()`): small point/polygon features with a numeric value field, spatially joined to wards by **feature centroid inside ward polygon**, aggregated to a per-ward count and value sum, then correlated (Pearson `r`, reusing `pearson_correlation()` from [NDVI ↔ LST](#ndvi--lst-correlation)) against `vulnerability_score`. What the layer actually *is* differs by necessity — see [Multi-City Support](#multi-city-support) for why — so each city gets its own output field names and its own on-site narrative.

**Delhi — JJ clusters:** DUSIB's 685 mapped JJ (Jhuggi-Jhopri, i.e. informal settlement) cluster polygons, joined by centroid (not the source data's own `WARD_NO` attribute, which is missing/unusable for ~4% of rows — mostly Cantonment/NDMC clusters — while the geometry itself still resolves cleanly). Output fields: `jj_cluster_count`, `jj_cluster_households` (summed from `APPR_JHUGI`), `jj_household_density_km2`, `validation.jj_cluster_correlation_r`.

**What we actually found for Delhi, checked against the live data rather than assumed:** the correlation is weak, and for raw cluster count it's slightly *negative* (density r ≈ 0.15, count r ≈ -0.16 at the time this was built). Most of the top-ranked wards by vulnerability score — the hot, dense, green-poor Northeast Delhi belt — contain **zero** officially mapped JJ clusters. This isn't a data quality problem: Delhi's unplanned housing spans several distinct legal categories (JJ clusters, unauthorized colonies, urban villages), and DUSIB's list covers only the first of those. A ward can score low on satellite-visible heat/density metrics while still containing residents facing real housing-specific risk (informal construction, no piped water or drainage, insecure tenure) that LST/NDVI/population data structurally cannot see.

**Münster — elderly population (65+):** Zensus 2022's 100m population-by-age grid, clipped to Münster, summed to 65+ per grid cell, joined by cell centroid (trivial for Point geometry — the centroid of a point is itself). Output fields: `elderly_grid_cell_count`, `elderly_population` (the value sum), `elderly_density_km2`, `validation.elderly_correlation_r`. Age is the single largest heat-mortality risk factor in the heat-health literature (it's why DWD's own model has a "Klima-Michel Senior" variant), so this is a genuinely meaningful independent check, not an arbitrary substitute for JJ clusters. One data caveat specific to this source: German federal statistical disclosure control suppresses very small per-cell counts for privacy (shown as `–` in the raw Zensus CSV), treated as 0 here, so true elderly counts in sparsely populated cells are somewhat underestimated.

**In both cases, this overlay is presented as a complementary, independent risk signal, not as validation of the score above** — the on-site sections are explicit about whatever correlation was actually found (weak, for Delhi) and explain why, rather than implying agreement that isn't there.

## Known Limitations

- **Ward boundaries are pre-2022 delimitation** (290 zones from the three erstwhile municipal corporations + NDMC + Cantonment), not the current unified 250-ward structure — no open geometry file for the current boundaries was found.
- **Air temperature and live weather are district-level only, never ward-level.** NASA POWER's grid cell (~56km × 61km) and OpenWeather's station/model data don't carry real spatial signal below city scale — computing them per-ward would be false precision, not more information.
- **Heat alerts are a simplified proxy for IMD's Heat Wave criteria**, not an official declaration — see [Live Weather & Heat Alerts](#live-weather--heat-alerts).
- **The animated wind field is interpolated (inverse-distance weighting) from ~9-11 real district readings, not a measured wind grid** — same "illustrative, not measured" caveat as the ward vulnerability score below, see [Wind Field (interpolated)](#wind-field-interpolated).
- **The ward vulnerability score is exposure-only** — no socioeconomic or health data — see [Ward Vulnerability Score](#ward-vulnerability-score).
- **JJ cluster data covers only officially recognized/mapped clusters** (DUSIB's list), not all informal or precarious housing — and correlates only weakly with the vulnerability score, for real reasons, not a bug — see [JJ Cluster Overlay & Vulnerability-Score Comparison](#jj-cluster-overlay--vulnerability-score-comparison).
- **`uhi_air_c` uses a citywide-mean reference, not a dedicated rural station** — see [Urban Heat Island Intensity — Air](#urban-heat-island-intensity--air-uhi_air_c).
- **Heat alerts for Münster are a simplified proxy for DWD's Hitzewarnung system**, using OpenWeather's `feels_like` against DWD's real thresholds rather than the official Klima-Michel model — see [Live Weather & Heat Alerts](#live-weather--heat-alerts).
- **Münster's elderly-population grid undercounts small-population cells** due to German federal statistical disclosure control suppressing small counts — see [JJ Cluster Overlay & Vulnerability-Score Comparison](#jj-cluster-overlay--vulnerability-score-comparison).
- **All map layers and analytics reflect the last successful precompute run** (every 6h), not the live moment when a page is loaded — true for both cities.
- **3D building extrusion relies on crowdsourced OSM building footprints/heights**, which are far more complete for Münster (well-mapped German city) than for Delhi (OSM building coverage in Indian cities is comparatively sparse and inconsistently tagged with height) — expect visibly patchier building coverage in Delhi. Buildings without a `render_height` value fall back to a flat 5m estimate rather than being omitted, so extrusion height for untagged buildings is a placeholder, not a measurement.
- **Photorealistic 3D is a free-tier Cesium ion feature, not a permanent guarantee.** It's capped at 1,000 root-tile requests/month **account-wide** (shared across every visitor to the site, not per-visitor) — once exhausted for the month, the layer will fail to load until the quota resets, rather than degrading gracefully to a lower-detail view. The free tier is also restricted to non-commercial/individual use per Cesium ion's terms. Unlike the OpenFreeMap buildings layer, this is a full opaque mesh of the entire visible surface, so enabling it replaces the map's heat/vegetation/land-cover visualization rather than layering on top of it — it's an "explore" mode, not an additional data layer. The LST/NDVI/land-cover and boundary layers drawn on top of the mesh (see above) are themselves rendered at half opacity specifically to soften that replacement — they blend with the mesh rather than fully hiding it in turn.
- **District/ward/complementary-layer boundaries, and LST/NDVI/land-cover, render on top of Photorealistic 3D as deck.gl layers (`GeoJsonLayer` for boundaries, `TileLayer`+`BitmapLayer` for the raster tiles) with `{ depthCompare: "always", depthWriteEnabled: false }`**, not the native MapLibre fill/line/raster layers (which stay hidden underneath, invisible). Two things were tried and ruled out first for the boundary case, honestly documented here since both seemed reasonable before testing: (1) draping 2D data onto the mesh's actual geometry via deck.gl's `TerrainExtension` has a confirmed, unresolved upstream bug in interleaved mode for exactly this case ([visgl/deck.gl#7893](https://github.com/visgl/deck.gl/discussions/7893) — a maintainer reproduced it and it doesn't drape); (2) simply reordering the native MapLibre boundary layers to draw after the mesh (`map.moveLayer`) does nothing — verified directly with a bright 6px test line that stayed completely invisible, because once the interleaved 3D layer writes real depth values, MapLibre's own 2D layers get depth-tested against it regardless of paint order. Disabling depth comparison on a deck.gl layer is what actually works, since it bypasses the depth buffer entirely rather than relying on draw order — but `depthCompare: "always"` alone only disables the *test*; deck.gl's default `depthWriteEnabled: true` still applies, meaning these flat overlay layers were still writing their own (mostly meaningless, ground-level) depth values into the shared depth buffer. That caused visible flicker while rotating the camera over Photorealistic 3D, because the mesh's own internal depth test — comparing its real, sub-tile-varying depth against those stale overlay writes — became inconsistent frame to frame as viewing angle and floating-point precision shifted. Adding `depthWriteEnabled: false` alongside `depthCompare: "always"` stops these layers from touching the depth buffer at all, so stacking is governed purely by array draw order, independent of the mesh underneath. The same fix is reused for LST/NDVI/land-cover: each is re-fetched as the same Earth Engine XYZ tile URL already used by the flat map, wrapped in a depth-disabled `TileLayer`, so toggling those layers on now shows the heat/vegetation/land-cover data draped over the photorealistic mesh rather than replacing it outright. One extra gotcha specific to the raster case: `TileLayer`'s default tile-loading path decodes fetched tiles via a loaders.gl `ImageLoader`, but this page only loads `deck.gl` core and `@loaders.gl/3d-tiles` (for the mesh itself) — `@loaders.gl/images` is never on the page, and `deck.gl`'s own UMD bundle doesn't bundle it either (confirmed absent from the built bundle) — so the default path fetches tile bytes but has nothing to decode them into a usable image, and nothing draws. Fixed with a custom `getTileData` that fetches and decodes via the browser's native `createImageBitmap` instead, sidestepping loaders.gl entirely for this one path. The ward boundary line is deliberately drawn thicker here (`lineWidthUnits: "pixels"`, 2.5px fixed) than its flat-map counterpart, for legibility against the busier photorealistic imagery. Weather markers were already visible on top regardless, since they're DOM elements, not WebGL layers.
- **`maxBounds` keeps the map (and therefore all tile requests, including the metered Photorealistic 3D ones) confined to each city's real extent** — computed directly from `delhi_wards.geojson`/`muenster_wards.geojson`'s actual bounds plus padding, not guessed. This stops users from panning globally and burning the shared Cesium ion quota on unrelated places. One real caveat: at 60° pitch (used by both 3D toggles), the camera looks toward the horizon, and a tilted view can still see — and stream tiles for — a modest strip of terrain just past the `maxBounds` edge, since `maxBounds` constrains the 2D pan/center position, not the 3D viewing frustum's far extent. It substantially reduces out-of-area tile requests, not eliminates every last one at a steep pitch.

## Project Structure

- `web/`: static frontend (primary app)
  - `city.js`: shared city config (paths, map view, labels per city) + the `?city=` switcher, included by all three pages
  - `index.html` / `app.js`: MapLibre map + Chart.js time series + weather + district/ward/complementary-layer click-to-inspect
  - `analytics.html` / `analytics.js`: UHI, correlation, land-cover, long-term trend, ward-vulnerability, and complementary-layer analytics
  - `roadmap.html` / `roadmap.js`: cloud-gap evidence + SAR-Optical GNN roadmap narrative
  - `style.css`: shared styling for all pages
- `app.py`: legacy Streamlit dashboard (secondary, not linked as the primary app, Delhi only)
- `delhi_admin.geojson`: Delhi administrative boundaries (11 districts, `District` name property)
- `delhi_admin.kml`: Alternate boundary file
- `delhi_wards.geojson`: Delhi ward boundaries (290 features, `Ward_Name`/`Ward_No` properties — `Ward_No` is the unique key used to match `ward_vulnerability.json` rows)
- `delhi_jj_clusters.geojson`: DUSIB JJ (informal settlement) cluster boundaries (685 features, `slum_name`/`ward_no`/`approx_households`/`land_owning_agency` properties)
- `muenster_districts.geojson`: Münster's 9 districts (Stadtbezirke), dissolved locally from the wards file
- `muenster_wards.geojson`: Münster's 45 wards (Statistische Bezirke), `ward_name`/`ward_no`/`district_name` properties
- `muenster_elderly_population.geojson`: Zensus 2022 100m grid cells (ages 65+) clipped to Münster, `elderly_population`/`total_population` properties
- `scripts/precompute_timeseries_backend.py`: `get_city_configs()` defines both cities; `main()` loops over them, writing each city's `timeseries_scenes.json`, `map_layers.json`, `district_analytics.json`, `weather.json`, `historical_trends.json` (recomputed weekly; force an immediate recompute via the `force_historical_trends` input on a manual `Run workflow`), and `ward_vulnerability.json` (includes the complementary-layer fields) to `backend-data/<city_slug>/`
- `.github/workflows/precompute-backend-data.yml`: Scheduled/manual precompute, then publishes `web/`, both cities' static boundary/complementary geojson files, and `backend-data/<city_slug>/*` (as `<city_slug>/*` on the published site) to `gh-pages`
- `requirements.txt`: Python dependencies
- `runtime.txt`: Python runtime pin

## Static Frontend Setup (GitHub Pages)

The static frontend and its data are published together to the `gh-pages` branch by the same workflow, so setup is a single flow:

1. Add GitHub Actions secrets in your repo:
   - `GEE_SERVICE_ACCOUNT`
   - `GEE_PRIVATE_KEY`
   - `OPENWEATHER_API_KEY` — used server-side only, inside the Actions run, to precompute `weather.json`. It is never written into any client-side file.
   - `CESIUM_ION_TOKEN` — unlike the secrets above, this one **is** written into the published `web/app.js` (a placeholder, `__CESIUM_ION_TOKEN__`, is substituted at publish time) since it powers the client-side Photorealistic 3D map toggle and Cesium ion tokens are designed to be client-visible, restricted by domain rather than kept secret. Kept as a GitHub Actions secret anyway so the raw token isn't sitting in git history / GitHub code search. Get one free at [cesium.com/ion](https://cesium.com/), then restrict it to your GitHub Pages domain in the ion dashboard (Access Tokens -> your token -> URL restriction). Optional — if unset, only the Photorealistic 3D toggle fails (shows an error banner); everything else still works.
   - `PRECOMPUTE_DAYS` (optional, e.g. `730`) — time-series history window
   - `MAP_COMPOSITE_DAYS` and `ANALYTICS_AIR_TEMP_DAYS` are plain env vars with defaults (`45` and `90` respectively) inside `scripts/precompute_timeseries_backend.py` — edit the script if you want different rolling windows; not required secrets.
2. Ensure GitHub Actions is enabled, then run the workflow: `Actions -> Precompute Backend Data -> Run workflow`.
3. In `Settings -> Pages` set:
   - Source: `Deploy from a branch`
   - Branch: `gh-pages`
   - Folder: `/ (root)`
4. Visit `https://<your-github-username>.github.io/<your-repo-name>/` — this now serves `web/index.html` directly, defaulting to Delhi and reading `map_layers.json`, `district_analytics.json`, `weather.json`, `timeseries_scenes.json`, and `ward_vulnerability.json` from `delhi/` on the same site (plus the static `delhi_wards.geojson` / `delhi_jj_clusters.geojson`). Add `?city=muenster` (or use the in-app switcher) for Münster, reading the same filenames from `muenster/` plus `muenster_wards.geojson` / `muenster_elderly_population.geojson`. `analytics.html` and `roadmap.html` are linked from the map's top-left panel and preserve whichever city is currently selected.

The workflow re-runs every 6 hours, regenerating the precomputed JSON files for **both cities** (including fresh Earth Engine tile URLs and fresh weather readings) and republishing everything to `gh-pages`. Each precomputed file has its own try/except in the script, per city — if one fails (e.g. a transient EE or NASA POWER error), the previous version of that file is left in place rather than failing the whole run (the workflow's "Seed backend-data from previous publish" step is what makes that fallback real: it pulls the current live copy of each city's files before the script runs, so a skipped or failed dataset republishes unchanged instead of vanishing).

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
- `CESIUM_ION_TOKEN` is the one deliberate exception: it's a client-side-by-design token (powers the Photorealistic 3D map toggle directly from the browser) that ends up in the published `app.js`. It's still stored as a GitHub Actions secret and injected at publish time rather than committed to source, so it doesn't sit in plaintext git history — but real protection against abuse is the URL restriction on the token itself in the Cesium ion dashboard (restrict it to your GitHub Pages domain), not secrecy, since any visitor's browser can read it from the deployed page regardless.

For educational and research use.

## Last Updated

July 23, 2026 (Münster added as a second city)
