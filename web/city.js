// Shared city configuration + switcher, included before app.js/analytics.js/roadmap.js
// on every page. Selecting a city is a full page reload with ?city=<slug> in the URL —
// simpler and far less bug-prone than tearing down/rebuilding MapLibre layers in place,
// and reloads are cheap here since everything is precomputed static JSON.

const CITIES = {
    delhi: {
        slug: "delhi",
        displayName: "Delhi",
        flag: "🇮🇳",
        mapView: { center: [77.1025, 28.6139], zoom: 10 },
        districtBoundaryFile: "delhi_admin.geojson",
        districtNameProp: "District",
        districtNameTitleCase: true,
        districtLabel: "District",
        districtCount: 11,
        wardBoundaryFile: "delhi_wards.geojson",
        wardNameProp: "Ward_Name",
        wardNoProp: "Ward_No",
        wardLabel: "Ward",
        wardCount: 290,
        complementaryLayerFile: "delhi_jj_clusters.geojson",
        complementaryLabel: "Informal Settlements",
        complementaryCount: 685,
        complementaryToggleIcon: "🏘️",
        complementaryFillColor: "#8b4513",
        complementaryLineColor: "#5a2d0c",
        // Must match scripts/precompute_timeseries_backend.py's get_city_configs()
        // "delhi" entry's "complementary" field-name map exactly.
        complementaryFieldKeys: {
            count: "jj_cluster_count",
            density: "jj_household_density_km2",
            correlation: "jj_cluster_correlation_r",
            wards: "wards_with_jj_clusters",
            total: "total_jj_clusters_matched",
        },
        panelDescription:
            "Satellite-derived land surface temperature, vegetation and land cover across Delhi's 11 districts. Map layers refresh automatically every 6 hours.",
        heatAlertMethodology: "IMD-style (simplified proxy)",
    },
    muenster: {
        slug: "muenster",
        displayName: "Münster",
        flag: "🇩🇪",
        mapView: { center: [7.6261, 51.9607], zoom: 12 },
        districtBoundaryFile: "muenster_districts.geojson",
        districtNameProp: "district_name",
        districtNameTitleCase: false,
        districtLabel: "Stadtbezirk",
        districtCount: 9,
        wardBoundaryFile: "muenster_wards.geojson",
        wardNameProp: "ward_name",
        wardNoProp: "ward_no",
        wardLabel: "Statistischer Bezirk",
        wardCount: 45,
        complementaryLayerFile: "muenster_elderly_population.geojson",
        complementaryLabel: "Elderly Population (65+)",
        complementaryCount: null,
        complementaryToggleIcon: "👴",
        complementaryFillColor: "#4a6fa5",
        complementaryLineColor: "#2c4a75",
        // Must match scripts/precompute_timeseries_backend.py's get_city_configs()
        // "muenster" entry's "complementary" field-name map exactly.
        complementaryFieldKeys: {
            count: "elderly_grid_cell_count",
            density: "elderly_density_km2",
            correlation: "elderly_correlation_r",
            wards: "wards_with_elderly_data",
            total: "total_elderly_grid_cells_matched",
        },
        panelDescription:
            "Satellite-derived land surface temperature, vegetation and land cover across Münster's 9 Stadtbezirke. Map layers refresh automatically every 6 hours.",
        heatAlertMethodology: "DWD-style (simplified proxy)",
    },
};

function getCurrentCitySlug() {
    const params = new URLSearchParams(window.location.search);
    const slug = params.get("city");
    return CITIES[slug] ? slug : "delhi";
}

const CITY_SLUG = getCurrentCitySlug();
const CITY = CITIES[CITY_SLUG];

// Precomputed per-run JSON (map_layers.json etc.) is namespaced under a
// city subfolder, since both cities produce identically-named files.
// The static boundary/complementary geojson files are not namespaced -
// they're already uniquely named per city (delhi_wards.geojson vs
// muenster_wards.geojson) and only published once, not every run.
function cityDataPath(filename) {
    return `${CITY_SLUG}/${filename}`;
}

function cityPageUrl(page, slug) {
    return `${page}?city=${slug}`;
}

function renderCitySwitcher(containerId) {
    const container = document.getElementById(containerId);
    if (!container) return;
    const page = window.location.pathname.split("/").pop() || "index.html";
    container.innerHTML = Object.values(CITIES)
        .map((c) => {
            const activeClass = c.slug === CITY_SLUG ? " active" : "";
            return `<a href="${cityPageUrl(page, c.slug)}" class="city-switch-btn${activeClass}">${c.flag} ${c.displayName}</a>`;
        })
        .join("");
}

// Propagates the current city through the top nav links (Map / Analytics / Roadmap)
// so switching pages doesn't silently reset back to Delhi.
function wireCityAwareNavLinks() {
    document.querySelectorAll("a[data-nav-page]").forEach((a) => {
        a.href = cityPageUrl(a.dataset.navPage, CITY_SLUG);
    });
}
