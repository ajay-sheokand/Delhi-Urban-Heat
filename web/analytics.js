function linearRegression(points) {
    const n = points.length;
    if (n < 2) return null;
    const sumX = points.reduce((s, p) => s + p.x, 0);
    const sumY = points.reduce((s, p) => s + p.y, 0);
    const sumXY = points.reduce((s, p) => s + p.x * p.y, 0);
    const sumXX = points.reduce((s, p) => s + p.x * p.x, 0);
    const denom = n * sumXX - sumX * sumX;
    if (denom === 0) return null;
    const slope = (n * sumXY - sumX * sumY) / denom;
    const intercept = (sumY - slope * sumX) / n;
    return { slope, intercept };
}

function fmt(value, digits = 1) {
    return value === null || value === undefined || Number.isNaN(value) ? "N/A" : value.toFixed(digits);
}

function statCard(label, value, sub, accentClass) {
    return `<div class="stat-card ${accentClass || ""}"><div class="stat-label">${label}</div><div class="stat-value">${value}</div>${
        sub ? `<div class="stat-sub">${sub}</div>` : ""
    }</div>`;
}

async function main() {
    let analytics, mapLayers;
    try {
        const [analyticsRes, mapLayersRes] = await Promise.all([
            fetch("district_analytics.json", { cache: "no-store" }),
            fetch("map_layers.json", { cache: "no-store" }),
        ]);
        analytics = await analyticsRes.json();
        mapLayers = await mapLayersRes.json();
    } catch (err) {
        console.error("Failed to load analytics data", err);
        document.getElementById("summary-stats").textContent = "Analytics data unavailable.";
        return;
    }

    document.getElementById("data-updated").textContent = `Data last updated: ${analytics.generated_at_utc || "unknown"}`;

    const landCoverColors = {};
    (mapLayers?.layers?.land_cover?.classes || []).forEach((c) => {
        landCoverColors[c.label] = c.color;
    });

    renderSummary(analytics);
    renderUhiCharts(analytics);
    renderScatterCharts(analytics);
    renderLandCoverCharts(analytics, landCoverColors);
    renderTables(analytics);
}

function renderSummary(analytics) {
    const districts = (analytics.districts || []).filter((d) => d.uhi_air_c !== null && d.uhi_air_c !== undefined);
    const el = document.getElementById("summary-stats");

    if (!districts.length) {
        el.textContent = "No district data available.";
        return;
    }

    const hottest = districts.reduce((a, b) => (b.uhi_air_c > a.uhi_air_c ? b : a));
    const coolest = districts.reduce((a, b) => (b.uhi_air_c < a.uhi_air_c ? b : a));
    const corr = analytics.correlation;

    el.innerHTML = [
        statCard("Hottest District (Air UHI)", hottest.name, `+${fmt(hottest.uhi_air_c)}°C above city mean`, "accent-hot"),
        statCard("Coolest District (Air UHI)", coolest.name, `${fmt(coolest.uhi_air_c)}°C vs city mean`, "accent-cool"),
        statCard("Citywide Mean Air Temp", `${fmt(analytics.citywide_air_temp_c)}°C`, "NASA POWER, rolling window"),
        statCard("Cropland Baseline LST", `${fmt(analytics.cropland_baseline_lst_c)}°C`, "ESA WorldCover class 40"),
        statCard(
            "NDVI ↔ LST Correlation",
            corr && corr.ndvi_lst_r !== null ? corr.ndvi_lst_r.toFixed(3) : "N/A",
            "Negative = vegetation cools"
        ),
        statCard(
            "Urban vs Vegetation Heat Effect",
            corr && corr.uhi_effect_c !== null && corr.uhi_effect_c !== undefined ? `+${fmt(corr.uhi_effect_c)}°C` : "N/A",
            "Built-up minus green-cover LST"
        ),
    ].join("");
}

function renderUhiCharts(analytics) {
    const districts = analytics.districts || [];

    new Chart(document.getElementById("uhi-air-chart"), {
        type: "bar",
        data: {
            labels: districts.map((d) => d.name),
            datasets: [
                {
                    label: "Air UHI (°C)",
                    data: districts.map((d) => d.uhi_air_c),
                    backgroundColor: districts.map((d) => (d.uhi_air_c >= 0 ? "#d62728" : "#1f77b4")),
                },
            ],
        },
        options: {
            responsive: true,
            plugins: { legend: { display: false } },
            scales: { y: { title: { display: true, text: "°C deviation" } } },
        },
    });

    new Chart(document.getElementById("uhi-surface-chart"), {
        type: "bar",
        data: {
            labels: districts.map((d) => d.name),
            datasets: [
                {
                    label: "Surface UHI (°C)",
                    data: districts.map((d) => d.uhi_surface_c),
                    backgroundColor: districts.map((d) => (d.uhi_surface_c >= 0 ? "#ff8800" : "#2ca02c")),
                },
            ],
        },
        options: {
            responsive: true,
            plugins: { legend: { display: false } },
            scales: { y: { title: { display: true, text: "°C vs cropland" } } },
        },
    });
}

function renderScatterCharts(analytics) {
    const districts = (analytics.districts || []).filter(
        (d) => d.air_temp_c !== null && d.mean_lst_c !== null && d.air_temp_c !== undefined && d.mean_lst_c !== undefined
    );

    new Chart(document.getElementById("air-lst-scatter"), {
        type: "scatter",
        data: {
            datasets: [
                {
                    label: "Districts",
                    data: districts.map((d) => ({ x: d.air_temp_c, y: d.mean_lst_c, name: d.name })),
                    backgroundColor: "#ff6b00",
                    pointRadius: 6,
                },
            ],
        },
        options: {
            responsive: true,
            plugins: {
                legend: { display: false },
                tooltip: { callbacks: { label: (ctx) => `${ctx.raw.name}: ${ctx.raw.x.toFixed(1)}°C air / ${ctx.raw.y.toFixed(1)}°C LST` } },
            },
            scales: {
                x: { title: { display: true, text: "Air Temperature (°C)" } },
                y: { title: { display: true, text: "Land Surface Temperature (°C)" } },
            },
        },
    });

    const corr = analytics.correlation;
    const samples = corr?.sample_points || [];
    const scatterPoints = samples.map((p) => ({ x: p.ndvi, y: p.lst }));
    const trend = linearRegression(scatterPoints);
    const xs = scatterPoints.map((p) => p.x);
    const xMin = xs.length ? Math.min(...xs) : -0.3;
    const xMax = xs.length ? Math.max(...xs) : 1;

    const datasets = [
        {
            type: "scatter",
            label: "Sampled pixels",
            data: scatterPoints,
            backgroundColor: "rgba(31,119,180,0.5)",
            pointRadius: 3,
        },
    ];
    if (trend) {
        datasets.push({
            type: "line",
            label: "Trend",
            data: [
                { x: xMin, y: trend.slope * xMin + trend.intercept },
                { x: xMax, y: trend.slope * xMax + trend.intercept },
            ],
            borderColor: "#111",
            borderWidth: 2,
            borderDash: [6, 4],
            pointRadius: 0,
        });
    }

    new Chart(document.getElementById("ndvi-lst-scatter"), {
        type: "scatter",
        data: { datasets },
        options: {
            responsive: true,
            scales: {
                x: { title: { display: true, text: "NDVI" } },
                y: { title: { display: true, text: "LST (°C)" } },
            },
        },
    });
}

function renderLandCoverCharts(analytics, landCoverColors) {
    const stats = analytics.correlation?.land_cover_stats || [];

    new Chart(document.getElementById("landcover-share-chart"), {
        type: "bar",
        data: {
            labels: stats.map((s) => s.land_cover),
            datasets: [
                {
                    label: "Area Share (%)",
                    data: stats.map((s) => s.area_pct),
                    backgroundColor: stats.map((s) => landCoverColors[s.land_cover] || "#999"),
                },
            ],
        },
        options: {
            indexAxis: "y",
            responsive: true,
            plugins: { legend: { display: false } },
            scales: { x: { title: { display: true, text: "% of sampled pixels" } } },
        },
    });

    const lulcSeries = analytics.lulc_time_series || [];
    const dates = [...new Set(lulcSeries.map((r) => r.date))].sort();
    const landCoverNames = [...new Set(lulcSeries.map((r) => r.land_cover))];

    const datasets = landCoverNames.map((name) => {
        const byDate = {};
        lulcSeries.filter((r) => r.land_cover === name).forEach((r) => (byDate[r.date] = r.mean_lst_c));
        return {
            label: name,
            data: dates.map((d) => (d in byDate ? byDate[d] : null)),
            borderColor: landCoverColors[name] || "#999",
            backgroundColor: landCoverColors[name] || "#999",
            spanGaps: true,
            pointRadius: 3,
            borderWidth: 2,
        };
    });

    new Chart(document.getElementById("lulc-time-chart"), {
        type: "line",
        data: { labels: dates, datasets },
        options: {
            responsive: true,
            scales: { y: { title: { display: true, text: "Mean LST (°C)" } } },
        },
    });
}

function renderTables(analytics) {
    const lcBody = document.querySelector("#landcover-table tbody");
    lcBody.innerHTML = (analytics.correlation?.land_cover_stats || [])
        .map(
            (s) =>
                `<tr><td>${s.land_cover}</td><td>${s.area_pct.toFixed(1)}%</td><td>${fmt(s.mean_lst_c)}</td><td>${fmt(
                    s.mean_ndvi,
                    3
                )}</td><td>${s.count}</td></tr>`
        )
        .join("");

    const distBody = document.querySelector("#district-table tbody");
    distBody.innerHTML = (analytics.districts || [])
        .map(
            (d) =>
                `<tr><td>${d.name}</td><td>${fmt(d.mean_lst_c)}</td><td>${fmt(d.mean_ndvi, 3)}</td><td>${fmt(
                    d.air_temp_c
                )}</td><td>${fmt(d.uhi_air_c)}</td><td>${fmt(d.uhi_surface_c)}</td></tr>`
        )
        .join("");
}

main();
