// Cesium ion access token (free-tier, non-commercial). Public/client-side by design —
// Cesium ion tokens are meant to be restricted by domain in the ion dashboard, not kept secret —
// but it's still injected at publish time from a GitHub Actions secret rather than committed in
// source, so it isn't sitting in plaintext in git history / GitHub code search.
const CESIUM_ION_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJqdGkiOiJkZmU1ODk5OC01ODVjLTQ1NWUtOWFjMy1iMDcxNzBjMjc1ODciLCJpZCI6NDIxMjI0LCJzdWIiOiJhamF5LXNoZW9rYW5kIiwiaXNzIjoiaHR0cHM6Ly9hcGkuY2VzaXVtLmNvbSIsImF1ZCI6ImRlbGhpX3VyYmFuX2hlYXQiLCJpYXQiOjE3ODQ4MjM4MjF9.X00X5mHCuYALTdikkDbMhF8EfKhONHKVnhoGc5Jloe4";
// Cesium ion's fixed, account-shared asset ID for Google Photorealistic 3D Tiles
// (confirmed against the live ion API, not assumed).
const GOOGLE_PHOTOREALISTIC_3D_TILES_ASSET_ID = 2275207;

const map = new maplibregl.Map({
    container: "map",
    attributionControl: false,
    style: {
        version: 8,
        sources: {
            carto: {
                type: "raster",
                tiles: [
                    "https://a.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
                    "https://b.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
                    "https://c.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
                    "https://d.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
                ],
                tileSize: 256,
                attribution: "© OpenStreetMap contributors © CARTO",
            },
            openmaptiles: {
                type: "vector",
                url: "https://tiles.openfreemap.org/planet",
                attribution: "OpenFreeMap © OpenMapTiles Data from OpenStreetMap",
            },
        },
        layers: [
            { id: "carto-base", type: "raster", source: "carto" },
            {
                id: "building-3d",
                type: "fill-extrusion",
                source: "openmaptiles",
                "source-layer": "building",
                minzoom: 13,
                layout: { visibility: "none" },
                paint: {
                    "fill-extrusion-base": ["coalesce", ["get", "render_min_height"], 0],
                    "fill-extrusion-height": ["coalesce", ["get", "render_height"], 5],
                    "fill-extrusion-color": ["coalesce", ["get", "colour"], "hsl(28, 60%, 60%)"],
                    "fill-extrusion-vertical-gradient": true,
                    "fill-extrusion-opacity": 0.95,
                },
            },
        ],
    },
    center: CITY.mapView.center,
    zoom: CITY.mapView.zoom,
    maxBounds: CITY.mapView.maxBounds,
});

map.addControl(new maplibregl.NavigationControl(), "bottom-right");
map.addControl(
    new maplibregl.AttributionControl({
        customAttribution: ["3D Tiles: Google, via Cesium ion"],
    })
);

function showErrorBanner(message) {
    const container = document.getElementById("index-error-banner");
    const div = document.createElement("div");
    div.className = "error-banner";
    div.textContent = message;
    container.appendChild(div);
}

function applyCityChrome() {
    document.getElementById("page-title").textContent = `${CITY.displayName} Urban Heat Monitor`;
    document.getElementById("wordmark-city").textContent = CITY.displayName;
    document.getElementById("panel-description").textContent = CITY.panelDescription;
    document.getElementById("toggle-districts-label").textContent = `${CITY.districtLabel} Boundaries`;
    document.getElementById("toggle-wards-label").textContent = `${CITY.wardLabel} Boundaries (${CITY.wardCount}, click to inspect)`;
    const complementaryCountLabel = CITY.complementaryCount ? `${CITY.complementaryCount}, ` : "";
    document.getElementById("toggle-complementary-label").textContent =
        `${CITY.complementaryToggleIcon} ${CITY.complementaryLabel} (${complementaryCountLabel}click to inspect)`;
    renderCitySwitcher("city-switcher");
    wireCityAwareNavLinks();
    applyStatRow();
}

// Same CITY config fields the layer-toggle labels above already use - just surfaced as
// scannable stat chips at the top of the sidebar (structurally similar to a GIS-dashboard
// stat row, but our own numbers: administrative geography, not building/road counts).
function applyStatRow() {
    document.getElementById("stat-districts").textContent = CITY.districtCount;
    document.getElementById("stat-districts-unit").textContent = `${CITY.districtLabel}s`;
    document.getElementById("stat-wards").textContent = CITY.wardCount;
    document.getElementById("stat-wards-unit").textContent = `${CITY.wardLabel}s`;
    document.getElementById("stat-complementary").textContent = CITY.complementaryCount ?? "—";
    document.getElementById("stat-complementary-unit").textContent = CITY.complementaryLabel;
}

map.on("load", async () => {
    applyCityChrome();
    setupTabs();
    setupSidebarToggle();
    wireBuildingsToggle();
    wirePhotorealisticToggle();
    document.getElementById("data-updated").textContent = "Loading map data…";
    document.getElementById("heat-alerts-list").textContent = "Loading weather…";
    await Promise.all([loadMapLayers(), loadDistrictBoundaries(), loadWardBoundaries(), loadComplementaryLayer(), loadTimeSeries()]);
    loadWeather();
});

async function loadMapLayers() {
    let data;
    try {
        const res = await fetch(cityDataPath("map_layers.json"), { cache: "no-store" });
        data = await res.json();
    } catch (err) {
        console.error("Failed to load map_layers.json", err);
        document.getElementById("data-updated").textContent = "";
        showErrorBanner("Map layers unavailable — try reloading.");
        return;
    }

    document.getElementById("data-updated").textContent =
        `Map data last updated: ${data.generated_at_utc || "unknown"}`;

    const { lst, ndvi, land_cover, no2, co, ch4, flood_risk } = data.layers;

    addRasterLayer("lst", lst.tile_url, lst.opacity, true);
    addRasterLayer("ndvi", ndvi.tile_url, ndvi.opacity, false);
    addRasterLayer("landcover", land_cover.tile_url, land_cover.opacity, false);

    rasterLayerCache = {
        lst: { tileUrl: lst.tile_url, opacity: lst.opacity },
        ndvi: { tileUrl: ndvi.tile_url, opacity: ndvi.opacity },
        landcover: { tileUrl: land_cover.tile_url, opacity: land_cover.opacity },
    };

    renderLstLegend(lst.min, lst.max, lst.palette);
    renderLandCoverLegend(land_cover.classes, land_cover.histogram);

    wireToggle("toggle-lst", "lst-layer", "legend-lst");
    wireToggle("toggle-ndvi", "ndvi-layer", "legend-ndvi");
    wireToggle("toggle-landcover", "landcover-layer", "legend-landcover");

    wireOpacitySlider("opacity-lst", "lst-layer", lst.opacity);
    wireOpacitySlider("opacity-ndvi", "ndvi-layer", ndvi.opacity);
    wireOpacitySlider("opacity-landcover", "landcover-layer", land_cover.opacity);

    // Sentinel-5P column densities are tiny numbers in raw mol/m² (NO2/CO) - scaled to
    // µmol/m²/mmol/m² here purely for legend readability, same underlying data either way.
    // Any of these three can be absent from the JSON entirely: the backend omits a pollutant
    // rather than publish a blank layer when a city has zero valid retrievals for it even
    // after its retry composite (e.g. CH4 over Delhi during monsoon - TROPOMI's SWIR-based
    // CH4 retrieval needs clear-sky scenes). Missing here just means "no data this run", not
    // a bug - disable the toggle and say so instead of adding a layer/source that can't load.
    wirePollutantLayer("no2", no2, "toggle-no2", "legend-no2", (v) => `${(v * 1e6).toFixed(0)} µmol/m²`);
    wirePollutantLayer("co", co, "toggle-co", "legend-co", (v) => `${(v * 1e3).toFixed(1)} mmol/m²`);
    wirePollutantLayer("ch4", ch4, "toggle-ch4", "legend-ch4", (v) => `${v.toFixed(0)} ppb`);

    wireFloodRiskLayer(flood_risk);
    loadBuildingStats();
}

// SRTM-elevation relative-risk proxy (see build_flood_risk_layer() in the precompute
// script) - same "layer can be legitimately absent, disable rather than fake it"
// handling as wirePollutantLayer, plus the classes/honesty_note it carries so the
// legend states plainly that this is not an official flood-hazard map.
function wireFloodRiskLayer(layerData) {
    const checkbox = document.getElementById("toggle-flood-risk");
    if (!layerData) {
        if (checkbox) {
            checkbox.checked = false;
            checkbox.disabled = true;
            checkbox.title = "Flood risk layer unavailable for this run.";
        }
        const legend = document.getElementById("legend-flood-risk");
        if (legend) legend.style.display = "none";
        return;
    }
    addRasterLayer("flood-risk", layerData.tile_url, layerData.opacity, false);
    rasterLayerCache["flood-risk"] = { tileUrl: layerData.tile_url, opacity: layerData.opacity };

    document.getElementById("legend-flood-risk-items").innerHTML = layerData.classes
        .map(
            (c) =>
                `<div class="legend-item"><span class="legend-swatch" style="background:${c.color};"></span><span>${c.label}</span></div>`
        )
        .join("");
    document.getElementById("legend-flood-risk-note").textContent = layerData.honesty_note || "";

    wireToggle("toggle-flood-risk", "flood-risk-layer", "legend-flood-risk");
}

// Real building count from Google Open Buildings v3 (see build_building_stats_dataset())
// - Delhi-only, since that dataset has zero coverage over Europe. building_stats.json only
// exists for cities with has_building_data set, and even there it's only (re)computed on
// should_run_weekly_job()'s cadence (a ~2.5-minute FeatureCollection.size() over the whole
// city, not worth re-running every 6 hours for a static satellite-derived dataset) - a 404
// here just means "not applicable to this city" or "not computed yet", not an error.
async function loadBuildingStats() {
    let data;
    try {
        const res = await fetch(cityDataPath("building_stats.json"), { cache: "no-store" });
        if (!res.ok) return;
        data = await res.json();
    } catch (err) {
        return;
    }

    document.getElementById("stat-buildings-chip").style.display = "";
    const statEl = document.getElementById("stat-buildings");
    statEl.textContent = formatCompactCount(data.building_count);
    statEl.title = `${data.building_count.toLocaleString()} buildings detected`;

    const row = document.getElementById("row-buildings");
    row.style.display = "";
    document.getElementById("toggle-buildings-label").textContent =
        `Building Footprints (${formatCompactCount(data.building_count)} detected)`;

    addRasterLayer("buildings", data.footprint_tile_url, 0.55, false);
    rasterLayerCache["buildings"] = { tileUrl: data.footprint_tile_url, opacity: 0.55 };

    document.getElementById("legend-buildings-note").textContent =
        `${data.building_count.toLocaleString()} buildings across ${data.area_km2.toFixed(0)} km² ` +
        `(~${Math.round(data.density_per_km2).toLocaleString()}/km²). ${data.honesty_note}`;

    wireToggle("toggle-buildings", "buildings-layer", "legend-buildings");

    // Every other map_layers.json-backed layer (LST/NDVI/land cover/pollutants/flood-risk)
    // gets its rasterLayerCache entry synchronously inside loadMapLayers(), before anything
    // can have triggered the Photorealistic 3D overlay yet. building_stats.json is fetched
    // separately and later (its own network round-trip, Delhi-only), so if a user switches
    // Photorealistic 3D on before this resolves, buildRasterOverlayLayers() already ran once
    // and skipped "buildings" (no cache entry yet) - and nothing else was going to call
    // syncBoundaryOverlayLayers() again just because this fetch finished afterward. Explicitly
    // re-syncing here closes that gap: harmless no-op if 3D isn't active (syncBoundaryOverlayLayers
    // checks photorealisticActive itself), but fixes the real case where it is.
    syncBoundaryOverlayLayers();
}

function formatCompactCount(n) {
    if (n >= 1e6) return `${(n / 1e6).toFixed(1)}M`;
    if (n >= 1e3) return `${(n / 1e3).toFixed(0)}K`;
    return String(n);
}

function wirePollutantLayer(key, layerData, checkboxId, legendId, formatValue) {
    const checkbox = document.getElementById(checkboxId);
    if (!layerData) {
        if (checkbox) {
            checkbox.checked = false;
            checkbox.disabled = true;
            checkbox.title = "No valid satellite data for this pollutant in the current composite window (common for CH4 during Delhi's monsoon) - check back later.";
        }
        const legend = document.getElementById(legendId);
        if (legend) legend.style.display = "none";
        return;
    }
    if (checkbox) {
        checkbox.disabled = false;
        checkbox.title = "";
    }
    addRasterLayer(key, layerData.tile_url, layerData.opacity, false);
    rasterLayerCache[key] = { tileUrl: layerData.tile_url, opacity: layerData.opacity };
    renderGradientLegend(key, layerData.min, layerData.max, layerData.palette, formatValue);
    wireToggle(checkboxId, `${key}-layer`, legendId);
}

function addRasterLayer(key, tileUrl, opacity, visible) {
    map.addSource(`${key}-source`, {
        type: "raster",
        tiles: [tileUrl],
        tileSize: 256,
    });
    map.addLayer({
        id: `${key}-layer`,
        type: "raster",
        source: `${key}-source`,
        paint: { "raster-opacity": opacity },
        layout: { visibility: visible ? "visible" : "none" },
    });
}

function wireToggle(checkboxId, layerId, legendId) {
    const checkbox = document.getElementById(checkboxId);
    const legend = document.getElementById(legendId);
    checkbox.addEventListener("change", () => {
        map.setLayoutProperty(layerId, "visibility", checkbox.checked ? "visible" : "none");
        if (legend) legend.style.display = checkbox.checked ? "block" : "none";
        syncBoundaryOverlayLayers();
    });
    if (legend) legend.style.display = checkbox.checked ? "block" : "none";
}

// Initializes the slider to the actual backend-computed default opacity for that layer
// (map_layers.json), not an arbitrary fixed value, so it doesn't visually mismatch the
// layer's real starting appearance the first time a visitor sees it.
function wireOpacitySlider(sliderId, layerId, initialOpacity) {
    const slider = document.getElementById(sliderId);
    const valueLabel = document.getElementById(`${sliderId}-value`);
    if (!slider) return;
    const initialPercent = Math.round(initialOpacity * 100);
    slider.value = initialPercent;
    if (valueLabel) valueLabel.textContent = `${initialPercent}%`;
    slider.addEventListener("input", () => {
        const percent = Number(slider.value);
        map.setPaintProperty(layerId, "raster-opacity", percent / 100);
        if (valueLabel) valueLabel.textContent = `${percent}%`;
    });
}

function wireBuildingsToggle() {
    const checkbox = document.getElementById("toggle-3d-buildings");
    checkbox.addEventListener("change", () => {
        map.setLayoutProperty("building-3d", "visibility", checkbox.checked ? "visible" : "none");
        if (checkbox.checked) {
            map.easeTo({ pitch: 60, zoom: Math.max(map.getZoom(), 15), duration: 1000 });
        } else {
            map.easeTo({ pitch: 0, duration: 1000 });
        }
    });
}

let photorealisticOverlay = null;
let photorealisticActive = false;
let currentPhotorealisticLayer = null;
let districtGeojsonCache = null;
let wardGeojsonCache = null;
let complementaryGeojsonCache = null;
let rasterLayerCache = {};

function hexToRgb(hex, alpha) {
    const n = parseInt(hex.replace("#", ""), 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255, alpha];
}

// Draping 2D data onto the photorealistic mesh's real geometry (deck.gl's TerrainExtension)
// is a confirmed, unresolved upstream bug in interleaved mode (visgl/deck.gl#7893). A simpler
// fix — just reordering the flat MapLibre boundary layers to draw after the mesh — does NOT
// work either: once the interleaved 3D layer writes real depth values, MapLibre's own 2D
// layers get depth-tested against it regardless of paint order, so they stay fully hidden
// (verified directly, not assumed). What does work: render the boundaries as deck.gl
// GeoJsonLayers in the same interleaved overlay with { depthCompare: "always" } (deck.gl
// 9.1+ renamed the old depthTest:false parameter to align with WebGPU), which bypasses
// depth comparison entirely instead of relying on draw order.
// Drawn at half opacity (on top of each layer's own per-color alpha) so the photorealistic
// mesh underneath - kept fully opaque itself - still reads through the data, rather than
// the data fully hiding it wherever it's toggled on.
const PHOTOREALISTIC_OVERLAY_OPACITY = 0.5;

function buildBoundaryOverlayLayers() {
    const layers = [];
    if (districtGeojsonCache) {
        layers.push(
            new deck.GeoJsonLayer({
                id: "photoreal-district-lines",
                data: districtGeojsonCache,
                filled: false,
                stroked: true,
                getLineColor: hexToRgb("#2c3e50", 230),
                lineWidthMinPixels: 1.5,
                opacity: PHOTOREALISTIC_OVERLAY_OPACITY,
                visible: document.getElementById("toggle-districts").checked,
                parameters: { depthCompare: "always", depthWriteEnabled: false },
            })
        );
    }
    if (wardGeojsonCache) {
        layers.push(
            new deck.GeoJsonLayer({
                id: "photoreal-ward-lines",
                data: wardGeojsonCache,
                filled: false,
                stroked: true,
                getLineColor: hexToRgb("#6a3fb5", 220),
                // Fixed pixel width (not the meters-based default) so it reads clearly
                // thick against the photorealistic mesh at any zoom/pitch, rather than
                // just skimming the old 1px floor.
                lineWidthUnits: "pixels",
                getLineWidth: 2.5,
                lineWidthMinPixels: 2.5,
                opacity: PHOTOREALISTIC_OVERLAY_OPACITY,
                visible: document.getElementById("toggle-wards").checked,
                parameters: { depthCompare: "always", depthWriteEnabled: false },
            })
        );
    }
    if (complementaryGeojsonCache) {
        const isPoints = complementaryGeojsonCache.features[0]?.geometry?.type === "Point";
        layers.push(
            new deck.GeoJsonLayer({
                id: "photoreal-complementary",
                data: complementaryGeojsonCache,
                filled: true,
                stroked: !isPoints,
                pointType: "circle",
                getFillColor: hexToRgb(CITY.complementaryFillColor, isPoints ? 180 : 115),
                getLineColor: hexToRgb(CITY.complementaryLineColor, 200),
                getPointRadius: 4,
                pointRadiusUnits: "pixels",
                lineWidthMinPixels: 1,
                opacity: PHOTOREALISTIC_OVERLAY_OPACITY,
                visible: document.getElementById("toggle-jj-clusters").checked,
                parameters: { depthCompare: "always", depthWriteEnabled: false },
            })
        );
    }
    return layers;
}

// LST/NDVI/land-cover are the same Earth Engine XYZ tile URLs used by the flat MapLibre
// raster layers (addRasterLayer) - reused here as deck.gl TileLayers, each wrapping
// BitmapLayer sublayers, with depthCompare: "always" so they draw over the opaque
// photorealistic mesh instead of being hidden under it like the native MapLibre layers are.
// TileLayer's default tile-data path decodes fetched tiles via a loaders.gl ImageLoader,
// which this page never loads (only deck.gl core + @loaders.gl/3d-tiles are on the page,
// and deck.gl's own UMD bundle doesn't bundle @loaders.gl/images) - with no loader to decode
// the fetched PNG bytes, BitmapLayer.image never gets a real image and nothing draws.
// getTileData below bypasses that entirely with the browser's native createImageBitmap.
async function fetchTileImage({ url, signal }) {
    const res = await fetch(url, { signal });
    if (!res.ok) throw new Error(`Tile fetch failed: ${res.status}`);
    const blob = await res.blob();
    return await createImageBitmap(blob);
}

function buildRasterOverlayLayers() {
    const specs = [
        { key: "lst", checkboxId: "toggle-lst" },
        { key: "ndvi", checkboxId: "toggle-ndvi" },
        { key: "landcover", checkboxId: "toggle-landcover" },
        { key: "no2", checkboxId: "toggle-no2" },
        { key: "co", checkboxId: "toggle-co" },
        { key: "ch4", checkboxId: "toggle-ch4" },
        { key: "flood-risk", checkboxId: "toggle-flood-risk" },
        { key: "buildings", checkboxId: "toggle-buildings" },
    ];
    const layers = [];
    specs.forEach(({ key, checkboxId }) => {
        const cached = rasterLayerCache[key];
        const checkbox = document.getElementById(checkboxId);
        if (!cached || !checkbox) return;
        layers.push(
            new deck.TileLayer({
                id: `photoreal-${key}-tiles`,
                data: cached.tileUrl,
                minZoom: 0,
                maxZoom: 19,
                tileSize: 256,
                // Half opacity here specifically (over the mesh), not cached.opacity - that's
                // the flat-map value and unrelated to how this should look over Photorealistic 3D.
                opacity: PHOTOREALISTIC_OVERLAY_OPACITY,
                visible: checkbox.checked,
                parameters: { depthCompare: "always", depthWriteEnabled: false },
                getTileData: fetchTileImage,
                renderSubLayers: (props) => {
                    const { bbox } = props.tile;
                    return new deck.BitmapLayer(props, {
                        data: null,
                        image: props.data,
                        bounds: [bbox.west, bbox.south, bbox.east, bbox.north],
                        parameters: { depthCompare: "always", depthWriteEnabled: false },
                    });
                },
            })
        );
    });
    return layers;
}

function syncBoundaryOverlayLayers() {
    if (!photorealisticActive || !photorealisticOverlay) return;
    const layers = currentPhotorealisticLayer
        ? [currentPhotorealisticLayer, ...buildRasterOverlayLayers(), ...buildBoundaryOverlayLayers()]
        : [];
    photorealisticOverlay.setProps({ layers });
}

// CesiumIonLoader has a known bug (community-reported) where it only handles Cesium-hosted
// assets, not "external" ones like Google Photorealistic 3D Tiles (Cesium ion proxies these
// from Google rather than hosting them). Workaround: resolve the real tile.googleapis.com URL
// ourselves via the ion endpoint API, then hand that directly to Tile3DLayer with the plain
// Tiles3DLoader — no ion-specific loader needed once we already have a real URL.
async function buildPhotorealisticLayer() {
    const res = await fetch(
        `https://api.cesium.com/v1/assets/${GOOGLE_PHOTOREALISTIC_3D_TILES_ASSET_ID}/endpoint?access_token=${CESIUM_ION_TOKEN}`
    );
    if (!res.ok) throw new Error(`Cesium ion endpoint request failed: ${res.status}`);
    const endpoint = await res.json();
    return new deck.Tile3DLayer({
        id: "google-photorealistic-3d-tiles",
        data: endpoint.options.url,
        loaders: [loaders.Tiles3DLoader],
    });
}

function wirePhotorealisticToggle() {
    const checkbox = document.getElementById("toggle-photorealistic-3d");
    if (!checkbox) return;
    checkbox.addEventListener("change", async () => {
        if (checkbox.checked) {
            if (!photorealisticOverlay) {
                photorealisticOverlay = new deck.MapboxOverlay({ interleaved: true, layers: [] });
                map.addControl(photorealisticOverlay);
            }
            try {
                currentPhotorealisticLayer = await buildPhotorealisticLayer();
                photorealisticActive = true;
                syncBoundaryOverlayLayers();
                map.easeTo({ pitch: 60, zoom: Math.max(map.getZoom(), 16), duration: 1000 });
            } catch (err) {
                console.error("Failed to load photorealistic 3D tiles", err);
                showErrorBanner("Photorealistic 3D tiles failed to load — Cesium ion's free-tier quota may be exhausted for this month, or the ion token isn't configured.");
                photorealisticActive = false;
                currentPhotorealisticLayer = null;
                checkbox.checked = false;
            }
        } else {
            photorealisticActive = false;
            currentPhotorealisticLayer = null;
            if (photorealisticOverlay) photorealisticOverlay.setProps({ layers: [] });
            map.easeTo({ pitch: 0, duration: 1000 });
        }
    });
}

// Legends live as normal in-flow rows in the sidebar now (not floating boxes stacked by
// absolute position), so they lay themselves out via ordinary CSS flow - no JS positioning
// math needed here any more.

function renderLstLegend(min, max, palette) {
    const gradient = document.getElementById("legend-lst-gradient");
    gradient.style.background = `linear-gradient(to right, ${palette.join(",")})`;
    document.getElementById("legend-lst-scale").innerHTML =
        `<span>${min.toFixed(1)}°C</span><span>${max.toFixed(1)}°C</span>`;

    const ndviGradient = document.getElementById("legend-ndvi-gradient");
    ndviGradient.style.background =
        "linear-gradient(to right, #8B0000,#DC143C,#FF4500,#FFD700,#FFFF00,#7FFF00,#00FF00,#006400)";
}

// Shared by the three Sentinel-5P pollutant legends (no2/co/ch4) - same gradient+scale
// shape as renderLstLegend's LST half, just parameterized instead of copy-pasted 3x.
function renderGradientLegend(idPrefix, min, max, palette, formatValue) {
    const gradient = document.getElementById(`legend-${idPrefix}-gradient`);
    if (!gradient) return;
    gradient.style.background = `linear-gradient(to right, ${palette.join(",")})`;
    const scale = document.getElementById(`legend-${idPrefix}-scale`);
    if (scale) scale.innerHTML = `<span>${formatValue(min)}</span><span>${formatValue(max)}</span>`;
}

function renderLandCoverLegend(classes, histogram) {
    const presentIds = new Set(Object.keys(histogram || {}));
    const visibleClasses = presentIds.size
        ? classes.filter((c) => presentIds.has(String(c.id)))
        : classes;

    document.getElementById("legend-landcover-items").innerHTML = visibleClasses
        .map(
            (c) =>
                `<div class="legend-item"><span class="legend-swatch" style="background:${c.color};"></span><span>${c.label}</span></div>`
        )
        .join("");
}

function titleCase(str) {
    return (str || "")
        .toLowerCase()
        .replace(/\b\w/g, (c) => c.toUpperCase());
}

async function loadDistrictBoundaries() {
    let geojson;
    try {
        const res = await fetch(CITY.districtBoundaryFile, { cache: "no-store" });
        geojson = await res.json();
    } catch (err) {
        console.error(`Failed to load ${CITY.districtBoundaryFile}`, err);
        showErrorBanner(`${CITY.districtLabel} boundaries unavailable — try reloading.`);
        return;
    }
    districtGeojsonCache = geojson;

    map.addSource("districts", { type: "geojson", data: geojson });
    map.addLayer({
        id: "district-fill",
        type: "fill",
        source: "districts",
        paint: { "fill-color": "#000000", "fill-opacity": 0 },
    });
    map.addLayer({
        id: "district-lines",
        type: "line",
        source: "districts",
        paint: { "line-color": "#2c3e50", "line-width": 1.5, "line-opacity": 0.8 },
    });

    document.getElementById("toggle-districts").addEventListener("change", (e) => {
        const visibility = e.target.checked ? "visible" : "none";
        map.setLayoutProperty("district-lines", "visibility", visibility);
        map.setLayoutProperty("district-fill", "visibility", visibility);
        syncBoundaryOverlayLayers();
    });

    map.on("mouseenter", "district-fill", () => (map.getCanvas().style.cursor = "pointer"));
    map.on("mouseleave", "district-fill", () => (map.getCanvas().style.cursor = ""));

    // See the matching comment in loadBuildingStats() for the full explanation: this is its
    // own independent fetch (started alongside, not inside, loadMapLayers() - see the
    // Promise.all() in the bootstrap below), so if a user enables Photorealistic 3D before it
    // resolves, buildBoundaryOverlayLayers() runs once with districtGeojsonCache still null
    // and permanently omits district lines from the mesh until some other toggle happens to
    // fire a resync. Low-probability in practice (this fetch is small/fast), but the failure
    // mode is silent and easy to mistake for a real bug in the overlay code itself rather than
    // a load-order race, so it's worth closing here too, not just for buildings.
    syncBoundaryOverlayLayers();

    let districtStats = [];
    try {
        const res = await fetch(cityDataPath("district_analytics.json"), { cache: "no-store" });
        const data = await res.json();
        districtStats = data.districts || [];
    } catch (err) {
        console.error("Failed to load district_analytics.json", err);
    }

    map.on("click", "district-fill", (e) => {
        const props = e.features[0].properties;
        const rawName = props[CITY.districtNameProp] || "Unknown";
        const name = CITY.districtNameTitleCase ? titleCase(rawName) : rawName;
        const stats = districtStats.find((d) => d.name === name);

        const html = stats
            ? `<strong>${name}</strong><br/>
               LST: ${fmtC(stats.mean_lst_c)} · NDVI: ${fmtNum(stats.mean_ndvi, 3)}<br/>
               Air Temp: ${fmtC(stats.air_temp_c)}<br/>
               Air UHI: ${fmtC(stats.uhi_air_c, true)} · Surface UHI: ${fmtC(stats.uhi_surface_c, true)}`
            : `<strong>${name}</strong><br/>${CITY.districtLabel} analytics unavailable.`;

        new maplibregl.Popup({ offset: 8 }).setLngLat(e.lngLat).setHTML(html).addTo(map);
    });
}

async function loadWardBoundaries() {
    let geojson;
    try {
        const res = await fetch(CITY.wardBoundaryFile, { cache: "no-store" });
        geojson = await res.json();
    } catch (err) {
        console.error(`Failed to load ${CITY.wardBoundaryFile}`, err);
        showErrorBanner(`${CITY.wardLabel} boundaries unavailable — try reloading.`);
        return;
    }
    wardGeojsonCache = geojson;

    map.addSource("wards", { type: "geojson", data: geojson });
    map.addLayer({
        id: "ward-fill",
        type: "fill",
        source: "wards",
        paint: { "fill-color": "#000000", "fill-opacity": 0 },
        layout: { visibility: "none" },
    });
    map.addLayer({
        id: "ward-lines",
        type: "line",
        source: "wards",
        paint: { "line-color": "#6a3fb5", "line-width": 0.75, "line-opacity": 0.6 },
        layout: { visibility: "none" },
    });

    document.getElementById("toggle-wards").addEventListener("change", (e) => {
        const visibility = e.target.checked ? "visible" : "none";
        map.setLayoutProperty("ward-lines", "visibility", visibility);
        map.setLayoutProperty("ward-fill", "visibility", visibility);
        syncBoundaryOverlayLayers();
    });

    map.on("mouseenter", "ward-fill", () => (map.getCanvas().style.cursor = "pointer"));
    map.on("mouseleave", "ward-fill", () => (map.getCanvas().style.cursor = ""));

    // Same load-order race as loadDistrictBoundaries()/loadBuildingStats() - see those
    // comments. wardGeojsonCache is only usable by buildBoundaryOverlayLayers() from this
    // point on, so resync here too in case Photorealistic 3D was switched on first.
    syncBoundaryOverlayLayers();

    let wardStats = [];
    try {
        const res = await fetch(cityDataPath("ward_vulnerability.json"), { cache: "no-store" });
        const data = await res.json();
        wardStats = data.wards || [];
    } catch (err) {
        console.error("Failed to load ward_vulnerability.json", err);
    }

    map.on("click", "ward-fill", (e) => {
        const props = e.features[0].properties;
        const wardNo = props[CITY.wardNoProp];
        const name = props[CITY.wardNameProp] || "Unknown";
        const stats = wardStats.find((w) => w.ward_no === wardNo);

        const html = stats
            ? `<strong>${name}</strong><br/>
               LST: ${fmtC(stats.mean_lst_c)} · NDVI: ${fmtNum(stats.mean_ndvi, 3)}<br/>
               Population density: ${
                   stats.population_density_km2 != null ? Math.round(stats.population_density_km2).toLocaleString() : "N/A"
               }/km²<br/>
               Vulnerability score: ${fmtNum(stats.vulnerability_score, 1)} / 100<br/>
               <span class="muted">Air temperature is ${CITY.districtLabel.toLowerCase()}-level only — see the boundary below.</span>`
            : `<strong>${name}</strong><br/>${CITY.wardLabel} analytics unavailable.`;

        new maplibregl.Popup({ offset: 8 }).setLngLat(e.lngLat).setHTML(html).addTo(map);
    });
}

function complementaryFeaturePopupHtml(props) {
    if (CITY.slug === "delhi") {
        const households = props.approx_households;
        return `<strong>${props.slum_name}</strong><br/>
            Ward: ${props.ward_name}<br/>
            Approx. households: ${households != null ? Number(households).toLocaleString() : "N/A"}<br/>
            Land-owning agency: ${props.land_owning_agency || "N/A"}<br/>
            <span class="muted">Source: DUSIB (Delhi Urban Shelter Improvement Board)</span>`;
    }
    // muenster: Zensus grid cells are anonymous 100m cells, not named places.
    const elderly = props.elderly_population;
    const total = props.total_population;
    return `<strong>Zensus grid cell</strong><br/>
        Population 65+: ${elderly != null ? Number(elderly).toLocaleString() : "N/A"}<br/>
        Total population: ${total != null ? Number(total).toLocaleString() : "N/A"}<br/>
        <span class="muted">Source: Zensus 2022 (Destatis), 100m grid</span>`;
}

async function loadComplementaryLayer() {
    let geojson;
    try {
        const res = await fetch(CITY.complementaryLayerFile, { cache: "no-store" });
        geojson = await res.json();
    } catch (err) {
        console.error(`Failed to load ${CITY.complementaryLayerFile}`, err);
        showErrorBanner(`${CITY.complementaryLabel} data unavailable — try reloading.`);
        return;
    }
    complementaryGeojsonCache = geojson;

    // MapLibre fill/line layers only render (and hit-test) Polygon geometry;
    // Münster's elderly-population layer is Points, so it needs a circle
    // layer instead - and since fill layers can't hit-test Points either,
    // "complementary-fill" IS the clickable layer either way, just typed
    // differently depending on the current city's geometry.
    const isPoints = geojson.features[0]?.geometry?.type === "Point";
    map.addSource("complementary-layer", { type: "geojson", data: geojson });

    if (isPoints) {
        map.addLayer({
            id: "complementary-fill",
            type: "circle",
            source: "complementary-layer",
            paint: { "circle-color": CITY.complementaryFillColor, "circle-radius": 4, "circle-opacity": 0.7 },
            layout: { visibility: "none" },
        });
    } else {
        map.addLayer({
            id: "complementary-fill",
            type: "fill",
            source: "complementary-layer",
            paint: { "fill-color": CITY.complementaryFillColor, "fill-opacity": 0.45 },
            layout: { visibility: "none" },
        });
        map.addLayer({
            id: "complementary-lines",
            type: "line",
            source: "complementary-layer",
            paint: { "line-color": CITY.complementaryLineColor, "line-width": 1, "line-opacity": 0.8 },
            layout: { visibility: "none" },
        });
    }

    document.getElementById("toggle-jj-clusters").addEventListener("change", (e) => {
        const visibility = e.target.checked ? "visible" : "none";
        map.setLayoutProperty("complementary-fill", "visibility", visibility);
        if (map.getLayer("complementary-lines")) {
            map.setLayoutProperty("complementary-lines", "visibility", visibility);
        }
        syncBoundaryOverlayLayers();
    });

    map.on("mouseenter", "complementary-fill", () => (map.getCanvas().style.cursor = "pointer"));
    map.on("mouseleave", "complementary-fill", () => (map.getCanvas().style.cursor = ""));

    // Same load-order race as loadDistrictBoundaries()/loadBuildingStats() - see those
    // comments. complementaryGeojsonCache is only usable by buildBoundaryOverlayLayers()
    // from this point on, so resync here too in case Photorealistic 3D was switched on first.
    syncBoundaryOverlayLayers();

    map.on("click", "complementary-fill", (e) => {
        const html = complementaryFeaturePopupHtml(e.features[0].properties);
        new maplibregl.Popup({ offset: 8 }).setLngLat(e.lngLat).setHTML(html).addTo(map);
    });
}

function fmtC(value, showSign = false) {
    if (value === null || value === undefined || Number.isNaN(value)) return "N/A";
    const sign = showSign && value > 0 ? "+" : "";
    return `${sign}${value.toFixed(1)}°C`;
}

function fmtNum(value, digits) {
    return value === null || value === undefined || Number.isNaN(value) ? "N/A" : value.toFixed(digits);
}

let lstChart = null;
let allTimeSeriesRecords = [];

async function loadTimeSeries() {
    let data;
    try {
        const res = await fetch(cityDataPath("timeseries_scenes.json"), { cache: "no-store" });
        data = await res.json();
    } catch (err) {
        console.error("Failed to load timeseries_scenes.json", err);
        showErrorBanner("Time series data unavailable — try reloading.");
        return;
    }

    allTimeSeriesRecords = (data.records || []).filter((r) => r.mean_lst_c !== null && r.mean_lst_c !== undefined);

    const startInput = document.getElementById("ts-start-date");
    const endInput = document.getElementById("ts-end-date");
    startInput.min = endInput.min = data.coverage_start || "";
    startInput.max = endInput.max = data.coverage_end || "";
    startInput.value = data.coverage_start || "";
    endInput.value = data.coverage_end || "";

    const ctx = document.getElementById("lst-chart").getContext("2d");
    lstChart = new Chart(ctx, {
        type: "line",
        data: {
            labels: [],
            datasets: [
                {
                    label: "Mean LST (°C)",
                    data: [],
                    borderColor: "#ff6b00",
                    backgroundColor: "rgba(255,107,0,0.1)",
                    pointRadius: 0,
                    borderWidth: 1.5,
                    tension: 0.15,
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: { ticks: { maxTicksLimit: 8, font: { size: 10 } } },
                y: { title: { display: true, text: "°C" } },
            },
            plugins: { legend: { display: false } },
        },
    });

    applyTimeSeriesDateFilter();

    startInput.addEventListener("change", applyTimeSeriesDateFilter);
    endInput.addEventListener("change", applyTimeSeriesDateFilter);
}

function applyTimeSeriesDateFilter() {
    if (!lstChart) return;
    const start = document.getElementById("ts-start-date").value;
    const end = document.getElementById("ts-end-date").value;

    const filtered = allTimeSeriesRecords.filter((r) => (!start || r.date >= start) && (!end || r.date <= end));

    lstChart.data.labels = filtered.map((r) => r.date);
    lstChart.data.datasets[0].data = filtered.map((r) => r.mean_lst_c);
    lstChart.update();
}

const COMPASS_DIRECTIONS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"];

function windCompass(deg) {
    if (deg === null || deg === undefined || Number.isNaN(deg)) return null;
    return COMPASS_DIRECTIONS[Math.round(deg / 22.5) % 16];
}

// wind_deg is meteorological convention - the direction the wind blows FROM, per OpenWeather's docs.
function fmtWind(speedMs, deg) {
    if (speedMs === null || speedMs === undefined || Number.isNaN(speedMs)) return "N/A";
    const kmh = (speedMs * 3.6).toFixed(1);
    const compass = windCompass(deg);
    return compass ? `${kmh} km/h ${compass}` : `${kmh} km/h`;
}

async function loadWeather() {
    const alertsList = document.getElementById("heat-alerts-list");

    let data;
    try {
        const res = await fetch(cityDataPath("weather.json"), { cache: "no-store" });
        data = await res.json();
    } catch (err) {
        console.error("Failed to load weather.json", err);
        alertsList.textContent = "Weather data unavailable.";
        return;
    }

    document.getElementById("weather-updated").textContent =
        `Weather last synced: ${data.generated_at_utc || "unknown"}`;

    const districts = data.districts || [];
    if (!districts.length) {
        alertsList.textContent = "Weather data unavailable.";
        return;
    }

    const showMarkers = document.getElementById("toggle-weather").checked;
    const markers = districts.map((d) => {
        // OpenWeather Air Pollution API (SILAM model, ground-level ug/m3) - a separate fetch
        // from the temp/humidity/wind above, so it's independently optional per district.
        const aqiLine =
            d.aqi_label != null
                ? `<br/>AQI: ${d.aqi_label}${d.pm2_5 != null ? ` (PM2.5: ${d.pm2_5.toFixed(1)} µg/m³)` : ""}`
                : "";
        const popupHtml = `<strong>${d.name}</strong><br/>${d.temp_c.toFixed(1)}°C (feels ${d.feels_like_c.toFixed(
            1
        )}°C)<br/>Humidity: ${d.humidity}%<br/>Wind: ${fmtWind(d.wind_speed_ms, d.wind_deg)}<br/>${d.heat_alert_label}${aqiLine}`;

        const el = document.createElement("div");
        el.className = "weather-marker";
        el.style.backgroundColor = alertColor(d.heat_alert_level);

        const marker = new maplibregl.Marker({ element: el })
            .setLngLat([d.lon, d.lat])
            .setPopup(new maplibregl.Popup({ offset: 14 }).setHTML(popupHtml));

        if (showMarkers) marker.addTo(map);
        return marker;
    });

    document.getElementById("toggle-weather").addEventListener("change", (e) => {
        markers.forEach((m) => (e.target.checked ? m.addTo(map) : m.remove()));
    });

    wireWindFieldLayer(data.wind_field);

    const sorted = [...districts].sort((a, b) => b.temp_c - a.temp_c);
    alertsList.innerHTML = sorted
        .map(
            (d) =>
                `<div class="alert-row"><span>${d.name}</span><span class="alert-${d.heat_alert_level}">${d.temp_c.toFixed(1)}°C — ${d.heat_alert_label}</span></div>`
        )
        .join("");
}

// Animated wind-field particle flow (canvas), in the style of windy.com/earth.nullschool:
// many small particles are advected through the interpolated (u, v) vector field built
// server-side from the ~9-11 real district readings (build_wind_field() in the precompute
// script), each leaving a fading trail. This reuses the exact same interpolated grid the
// earlier discrete-arrow version used - only the rendering technique changed, not the
// underlying data or its "illustrative, not measured" honesty caveat (see the README's Wind
// Field section). A single rotating/pulsing arrow per grid cell read as flicker, not flow;
// a particle trace genuinely shows motion because it draws where each particle *has been*,
// not just its current instantaneous state.

// Rebuilds the flat 64-cell list into a lookup-able grid of (u, v) vectors, in the exact
// row-major order build_wind_field() emits them (i = latitude step outer loop, j = longitude
// step inner loop) - safe to rely on since this file and the precompute script are written
// and maintained together, not an independent consumer of a public API.
function buildVectorGrid(windField) {
    const cells = windField?.cells || [];
    const gridSize = windField?.grid_size || 0;
    if (gridSize < 2 || cells.length !== gridSize * gridSize) return null;

    const latMin = cells[0].lat;
    const latMax = cells[(gridSize - 1) * gridSize].lat;
    const lonMin = cells[0].lon;
    const lonMax = cells[gridSize - 1].lon;

    const u = new Float32Array(cells.length);
    const v = new Float32Array(cells.length);
    const speed = new Float32Array(cells.length);
    cells.forEach((c, idx) => {
        const towardRad = ((c.wind_deg + 180) % 360) * (Math.PI / 180);
        u[idx] = c.wind_speed_ms * Math.sin(towardRad);
        v[idx] = c.wind_speed_ms * Math.cos(towardRad);
        speed[idx] = c.wind_speed_ms;
    });

    return { gridSize, latMin, latMax, lonMin, lonMax, u, v, speed };
}

// Bilinear interpolation between the 4 grid nodes surrounding (lon, lat) - the same
// technique the grid itself was built with server-side (inverse-distance weighting), just
// one interpolation step closer to the particle's exact position instead of only the 64
// discrete node points. Returns null outside the grid's extent (particle should respawn).
function sampleVectorGrid(grid, lon, lat) {
    const { gridSize, latMin, latMax, lonMin, lonMax, u, v, speed } = grid;
    const fi = ((lat - latMin) / (latMax - latMin)) * (gridSize - 1);
    const fj = ((lon - lonMin) / (lonMax - lonMin)) * (gridSize - 1);
    if (!Number.isFinite(fi) || !Number.isFinite(fj) || fi < 0 || fi > gridSize - 1 || fj < 0 || fj > gridSize - 1) {
        return null;
    }
    const i0 = Math.floor(fi);
    const j0 = Math.floor(fj);
    const i1 = Math.min(i0 + 1, gridSize - 1);
    const j1 = Math.min(j0 + 1, gridSize - 1);
    const ti = fi - i0;
    const tj = fj - j0;
    const idx = (i, j) => i * gridSize + j;
    const lerp = (a, b, t) => a + (b - a) * t;
    const bilerp = (arr) => lerp(lerp(arr[idx(i0, j0)], arr[idx(i0, j1)], tj), lerp(arr[idx(i1, j0)], arr[idx(i1, j1)], tj), ti);
    return { u: bilerp(u), v: bilerp(v), speed: bilerp(speed) };
}

// Stylized (not a measurement-grade scale) - dark teal at calm, through cyan, into magenta
// at the top of Delhi's realistic wind range (~0-8 m/s), matching the windy.com-style
// reference this feature was asked to look like.
function windSpeedColor(speedMs) {
    const stops = [
        [8, 145, 130],
        [56, 189, 205],
        [168, 85, 220],
        [225, 60, 170],
    ];
    const t = Math.max(0, Math.min(1, speedMs / 8)) * (stops.length - 1);
    const i0 = Math.min(Math.floor(t), stops.length - 2);
    const localT = t - i0;
    const [r0, g0, b0] = stops[i0];
    const [r1, g1, b1] = stops[i0 + 1];
    const r = Math.round(r0 + (r1 - r0) * localT);
    const g = Math.round(g0 + (g1 - g0) * localT);
    const b = Math.round(b0 + (b1 - b0) * localT);
    return `rgb(${r},${g},${b})`;
}

const METERS_PER_DEG_LAT = 111320;
// The grid now spans each city's real full extent (city["bbox_fallback"] server-side), not
// just the area bounded by the district reading points - roughly double the previous
// coverage for Delhi, so the particle count is scaled up to match trail density.
const WIND_PARTICLE_COUNT = 700;
// Real wind speeds (a few m/s) are imperceptible as real-world-scale motion over a ~50km
// city view - this scales displayed motion for legibility, but it should still read as a
// real breeze, not a gale. At Delhi's default zoom (10) and a typical current reading
// (~4 m/s), 850 works out to roughly 25 screen px/s - crossing a 1400px-wide view in
// ~55s, a calm drift rather than a sprint. (The previous value, 12000, worked out to
// ~360 px/s at the same conditions - the whole visible city in under 4 seconds, which is
// what actually prompted this change.) Necessarily zoom-dependent like any map-space
// animation: the same real wind covers more screen pixels/sec zoomed in, fewer zoomed out.
const WIND_PARTICLE_SPEED_SCALE = 850;
const WIND_PARTICLE_MAX_AGE = 240;

let windFieldAnimation = null;

function startWindFieldAnimation(windField) {
    const grid = buildVectorGrid(windField);
    if (!grid) return;

    const mapEl = document.getElementById("map");
    const canvas = document.createElement("canvas");
    canvas.id = "wind-field-canvas";
    mapEl.appendChild(canvas);
    const ctx = canvas.getContext("2d");

    function randomParticle() {
        return {
            lon: grid.lonMin + Math.random() * (grid.lonMax - grid.lonMin),
            lat: grid.latMin + Math.random() * (grid.latMax - grid.latMin),
            age: Math.floor(Math.random() * WIND_PARTICLE_MAX_AGE),
        };
    }
    let particles = Array.from({ length: WIND_PARTICLE_COUNT }, randomParticle);

    function resizeCanvas() {
        const dpr = window.devicePixelRatio || 1;
        canvas.width = mapEl.clientWidth * dpr;
        canvas.height = mapEl.clientHeight * dpr;
        canvas.style.width = `${mapEl.clientWidth}px`;
        canvas.style.height = `${mapEl.clientHeight}px`;
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }
    resizeCanvas();
    window.addEventListener("resize", resizeCanvas);

    // Trails are drawn in screen space, so they'd smear incorrectly while the view itself
    // is moving - simplest fix is to drop the trail history at the start of any pan/zoom and
    // let it rebuild once the view settles, rather than trying to keep it correctly
    // transformed mid-gesture.
    function clearTrail() {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
    }
    map.on("movestart", clearTrail);
    map.on("zoomstart", clearTrail);

    let lastTime = performance.now();
    let rafId = null;

    function frame(now) {
        const dt = Math.min((now - lastTime) / 1000, 0.1);
        lastTime = now;

        const w = canvas.clientWidth;
        const h = canvas.clientHeight;
        // Fades existing trail pixels toward transparent (multiplies their alpha) rather
        // than clearing outright, which is what actually produces the trailing-streak look
        // instead of single disconnected dashes. Trail *length* on screen is distance
        // covered before this decays to invisible, i.e. speed x persistence together -
        // slowing WIND_PARTICLE_SPEED_SCALE down without raising this would leave trails
        // looking like short stubby dots rather than flowing lines, so persistence went up
        // to compensate and keep roughly the same visible trail length as before.
        ctx.globalCompositeOperation = "destination-in";
        ctx.fillStyle = "rgba(0,0,0,0.985)";
        ctx.fillRect(0, 0, w, h);
        ctx.globalCompositeOperation = "source-over";
        ctx.lineWidth = 1.4;
        ctx.lineCap = "round";

        particles.forEach((p) => {
            const sample = sampleVectorGrid(grid, p.lon, p.lat);
            if (!sample || p.age > WIND_PARTICLE_MAX_AGE) {
                Object.assign(p, randomParticle(), { age: 0 });
                return;
            }
            const prevScreen = map.project([p.lon, p.lat]);
            const metersPerDegLon = METERS_PER_DEG_LAT * Math.cos((p.lat * Math.PI) / 180);
            p.lon += (sample.u * dt * WIND_PARTICLE_SPEED_SCALE) / metersPerDegLon;
            p.lat += (sample.v * dt * WIND_PARTICLE_SPEED_SCALE) / METERS_PER_DEG_LAT;
            p.age += 1;
            const newScreen = map.project([p.lon, p.lat]);

            ctx.strokeStyle = windSpeedColor(sample.speed);
            ctx.beginPath();
            ctx.moveTo(prevScreen.x, prevScreen.y);
            ctx.lineTo(newScreen.x, newScreen.y);
            ctx.stroke();
        });
    }

    function loop(now) {
        frame(now);
        rafId = requestAnimationFrame(loop);
    }
    rafId = requestAnimationFrame(loop);

    windFieldAnimation = {
        stop() {
            cancelAnimationFrame(rafId);
            window.removeEventListener("resize", resizeCanvas);
            map.off("movestart", clearTrail);
            map.off("zoomstart", clearTrail);
            canvas.remove();
            windFieldAnimation = null;
        },
    };
}

function wireWindFieldLayer(windField) {
    const checkbox = document.getElementById("toggle-wind-field");
    if (!checkbox) return;
    if (checkbox.checked) startWindFieldAnimation(windField);
    checkbox.addEventListener("change", (e) => {
        if (e.target.checked) {
            startWindFieldAnimation(windField);
        } else if (windFieldAnimation) {
            windFieldAnimation.stop();
        }
    });
}

function alertColor(level) {
    if (level === "extreme") return "#b30000";
    if (level === "high") return "#cc7000";
    return "#2e7d32";
}

function setupTabs() {
    document.querySelectorAll(".tab-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
            document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
            btn.classList.add("active");
            document.querySelectorAll(".tab-content").forEach((c) => (c.style.display = "none"));
            document.getElementById(`tab-${btn.dataset.tab}`).style.display = "block";
            if (lstChart) lstChart.resize();
        });
    });
}

// Sidebar is a persistent docked panel on desktop; below the CSS breakpoint (see
// .sidebar-toggle-btn / body.sidebar-open in style.css) it slides in as an overlay instead,
// since there isn't room for both a full-height sidebar and the map on a phone-width screen.
function setupSidebarToggle() {
    const btn = document.getElementById("sidebar-toggle-btn");
    if (!btn) return;
    btn.addEventListener("click", () => {
        document.body.classList.toggle("sidebar-open");
    });
}
