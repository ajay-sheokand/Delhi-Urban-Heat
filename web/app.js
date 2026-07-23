const map = new maplibregl.Map({
    container: "map",
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
        },
        layers: [{ id: "carto-base", type: "raster", source: "carto" }],
    },
    center: [77.1025, 28.6139],
    zoom: 10,
});

map.addControl(new maplibregl.NavigationControl(), "bottom-right");

function showErrorBanner(message) {
    const container = document.getElementById("index-error-banner");
    const div = document.createElement("div");
    div.className = "error-banner";
    div.textContent = message;
    container.appendChild(div);
}

map.on("load", async () => {
    setupTabs();
    document.getElementById("data-updated").textContent = "Loading map data…";
    document.getElementById("heat-alerts-list").textContent = "Loading weather…";
    await Promise.all([loadMapLayers(), loadDistrictBoundaries(), loadTimeSeries()]);
    loadWeather();
});

async function loadMapLayers() {
    let data;
    try {
        const res = await fetch("map_layers.json", { cache: "no-store" });
        data = await res.json();
    } catch (err) {
        console.error("Failed to load map_layers.json", err);
        document.getElementById("data-updated").textContent = "";
        showErrorBanner("Map layers unavailable — try reloading.");
        return;
    }

    document.getElementById("data-updated").textContent =
        `Map data last updated: ${data.generated_at_utc || "unknown"}`;

    const { lst, ndvi, land_cover } = data.layers;

    addRasterLayer("lst", lst.tile_url, lst.opacity, true);
    addRasterLayer("ndvi", ndvi.tile_url, ndvi.opacity, false);
    addRasterLayer("landcover", land_cover.tile_url, land_cover.opacity, false);

    renderLstLegend(lst.min, lst.max, lst.palette);
    renderLandCoverLegend(land_cover.classes, land_cover.histogram);

    wireToggle("toggle-lst", "lst-layer", "legend-lst");
    wireToggle("toggle-ndvi", "ndvi-layer", "legend-ndvi");
    wireToggle("toggle-landcover", "landcover-layer", "legend-landcover");
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
        layoutLegends();
    });
    if (legend) legend.style.display = checkbox.checked ? "block" : "none";
}

function layoutLegends() {
    const order = ["legend-lst", "legend-ndvi", "legend-landcover"];
    let bottom = 240; // clears the bottom panel
    order.forEach((id) => {
        const el = document.getElementById(id);
        if (!el || el.style.display === "none") return;
        el.style.bottom = `${bottom}px`;
        bottom += el.offsetHeight + 10;
    });
}

function renderLstLegend(min, max, palette) {
    const gradient = document.getElementById("legend-lst-gradient");
    gradient.style.background = `linear-gradient(to right, ${palette.join(",")})`;
    document.getElementById("legend-lst-scale").innerHTML =
        `<span>${min.toFixed(1)}°C</span><span>${max.toFixed(1)}°C</span>`;

    const ndviGradient = document.getElementById("legend-ndvi-gradient");
    ndviGradient.style.background =
        "linear-gradient(to right, #8B0000,#DC143C,#FF4500,#FFD700,#FFFF00,#7FFF00,#00FF00,#006400)";

    layoutLegends();
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

    layoutLegends();
}

function titleCase(str) {
    return (str || "")
        .toLowerCase()
        .replace(/\b\w/g, (c) => c.toUpperCase());
}

async function loadDistrictBoundaries() {
    let geojson;
    try {
        const res = await fetch("delhi_admin.geojson", { cache: "no-store" });
        geojson = await res.json();
    } catch (err) {
        console.error("Failed to load delhi_admin.geojson", err);
        showErrorBanner("District boundaries unavailable — try reloading.");
        return;
    }

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
    });

    map.on("mouseenter", "district-fill", () => (map.getCanvas().style.cursor = "pointer"));
    map.on("mouseleave", "district-fill", () => (map.getCanvas().style.cursor = ""));

    let districtStats = [];
    try {
        const res = await fetch("district_analytics.json", { cache: "no-store" });
        const data = await res.json();
        districtStats = data.districts || [];
    } catch (err) {
        console.error("Failed to load district_analytics.json", err);
    }

    map.on("click", "district-fill", (e) => {
        const props = e.features[0].properties;
        const rawName = props.District || props.Name || "Unknown";
        const name = titleCase(rawName);
        const stats = districtStats.find((d) => d.name === name);

        const html = stats
            ? `<strong>${name}</strong><br/>
               LST: ${fmtC(stats.mean_lst_c)} · NDVI: ${fmtNum(stats.mean_ndvi, 3)}<br/>
               Air Temp: ${fmtC(stats.air_temp_c)}<br/>
               Air UHI: ${fmtC(stats.uhi_air_c, true)} · Surface UHI: ${fmtC(stats.uhi_surface_c, true)}`
            : `<strong>${name}</strong><br/>District analytics unavailable.`;

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
        const res = await fetch("timeseries_scenes.json", { cache: "no-store" });
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

async function loadWeather() {
    const alertsList = document.getElementById("heat-alerts-list");

    let data;
    try {
        const res = await fetch("weather.json", { cache: "no-store" });
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
        const popupHtml = `<strong>${d.name}</strong><br/>${d.temp_c.toFixed(1)}°C (feels ${d.feels_like_c.toFixed(
            1
        )}°C)<br/>Humidity: ${d.humidity}%<br/>${d.heat_alert_label}`;

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

    const sorted = [...districts].sort((a, b) => b.temp_c - a.temp_c);
    alertsList.innerHTML = sorted
        .map(
            (d) =>
                `<div class="alert-row"><span>${d.name}</span><span class="alert-${d.heat_alert_level}">${d.temp_c.toFixed(1)}°C — ${d.heat_alert_label}</span></div>`
        )
        .join("");
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
