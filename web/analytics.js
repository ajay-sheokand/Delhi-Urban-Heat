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

function showErrorBanner(message) {
    const container = document.getElementById("analytics-error-banner");
    const div = document.createElement("div");
    div.className = "error-banner";
    div.textContent = message;
    container.appendChild(div);
}

function applyCityChrome() {
    document.getElementById("page-title").textContent = `Analytics | ${CITY.displayName} Urban Heat Monitor`;
    document.getElementById("site-brand").textContent = `🌡️ ${CITY.displayName} Urban Heat Monitor`;
    document.getElementById("page-heading").textContent = `📊 ${CITY.districtLabel} Analytics`;
    document.getElementById("page-intro").textContent =
        `Urban heat island intensity, vegetation-temperature correlation, and land-cover composition across ${CITY.displayName}'s ${CITY.districtCount} ${CITY.districtLabel.toLowerCase()}${CITY.districtCount === 1 ? "" : "s"}. Computed server-side from a rolling satellite/weather window and refreshed every 6 hours — not a live per-visit computation.`;
    document.getElementById("air-temp-caveat").textContent =
        `NASA POWER's air temperature grid is roughly 50-60km — coarser than ${CITY.displayName}'s ${CITY.districtLabel.toLowerCase()}s, so ${CITY.districtLabel.toLowerCase()}-to-${CITY.districtLabel.toLowerCase()} air-temperature differences below are naturally small. The surface UHI chart (Landsat LST, 100m resolution) is the more spatially meaningful comparison.`;
    document.getElementById("uhi-air-chart-title").textContent = `UHI Intensity by ${CITY.districtLabel} (deviation from citywide mean air temp)`;
    document.getElementById("uhi-surface-chart-title").textContent = `Surface UHI by ${CITY.districtLabel} (LST vs cropland baseline)`;
    document.getElementById("air-lst-scatter-title").textContent = `Air Temp vs LST by ${CITY.districtLabel}`;
    document.getElementById("ward-vulnerability-heading").textContent = `Heat Vulnerability by ${CITY.wardLabel}`;
    document.getElementById("ward-vulnerability-chart-title").textContent = `Top 20 Most Vulnerable ${CITY.wardLabel}s`;
    document.getElementById("ward-table-header-name").textContent = CITY.wardLabel;
    document.getElementById("ward-table-header-complementary").textContent = CITY.complementaryLabel;
    document.getElementById("district-table-heading").textContent = `${CITY.districtLabel} Comparison`;
    document.getElementById("district-table-header-name").textContent = CITY.districtLabel;
    document.getElementById("ward-vulnerability-intro").innerHTML =
        `${CITY.displayName}'s ${CITY.districtCount} ${CITY.districtLabel.toLowerCase()}s are too large to show who is actually most exposed — each covers a large population.
        This section re-runs the LST, NDVI and population inputs at ${CITY.wardLabel.toLowerCase()} resolution (${CITY.wardCount} ${CITY.wardLabel.toLowerCase()}s)
        to rank the areas where high surface heat, low vegetation and high population density overlap.
        <strong>Vulnerability score</strong> = the average of min-max normalized LST, inverse-normalized NDVI, and
        normalized population density per ${CITY.wardLabel.toLowerCase()} (0–100, higher = more vulnerable). Air temperature is intentionally
        <em>not</em> part of this score and stays ${CITY.districtLabel.toLowerCase()}-level only (see the caveat above) — NASA POWER's coarse
        grid and city-scale weather stations don't carry real information at ${CITY.wardLabel.toLowerCase()} scale, so adding them here would
        be false precision, not more signal. See the map's "${CITY.wardLabel} Boundaries" layer to click into any individual ${CITY.wardLabel.toLowerCase()}.`;
    renderCitySwitcher("city-switcher");
    wireCityAwareNavLinks();
    document.querySelectorAll("[data-city-section]").forEach((el) => {
        el.style.display = el.dataset.citySection === CITY.slug ? "" : "none";
    });
}

async function main() {
    applyCityChrome();
    let analytics, mapLayers;
    try {
        const [analyticsRes, mapLayersRes] = await Promise.all([
            fetch(cityDataPath("district_analytics.json"), { cache: "no-store" }),
            fetch(cityDataPath("map_layers.json"), { cache: "no-store" }),
        ]);
        analytics = await analyticsRes.json();
        mapLayers = await mapLayersRes.json();
    } catch (err) {
        console.error("Failed to load analytics data", err);
        document.getElementById("summary-stats").textContent = "";
        showErrorBanner("Analytics data unavailable — try reloading.");
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
    loadLongTermTrends(landCoverColors);
    loadWardVulnerability();
}

async function loadWardVulnerability() {
    let data;
    try {
        const res = await fetch(cityDataPath("ward_vulnerability.json"), { cache: "no-store" });
        data = await res.json();
    } catch (err) {
        console.error("Failed to load ward_vulnerability.json", err);
        showErrorBanner("Ward vulnerability data unavailable — try reloading.");
        return;
    }

    const ranking = data.ranking || [];
    document.getElementById("ward-vulnerability-meta").textContent = ranking.length
        ? `${(data.wards || []).length} wards scored · population year ${data.population_year || "unknown"} · updated ${data.generated_at_utc || "unknown"}`
        : "";

    new Chart(document.getElementById("ward-vulnerability-chart"), {
        type: "bar",
        data: {
            labels: ranking.map((w) => w.ward_name),
            datasets: [
                {
                    label: "Vulnerability score",
                    data: ranking.map((w) => w.vulnerability_score),
                    backgroundColor: "#d62728",
                },
            ],
        },
        options: {
            indexAxis: "y",
            responsive: true,
            plugins: { legend: { display: false } },
            scales: { x: { min: 0, max: 100, title: { display: true, text: "Vulnerability score (0-100)" } } },
        },
    });

    const keys = CITY.complementaryFieldKeys;
    const body = document.querySelector("#ward-vulnerability-table tbody");
    body.innerHTML = ranking
        .map(
            (w) =>
                `<tr><td>${w.ward_name}</td><td>${fmt(w.mean_lst_c)}</td><td>${fmt(w.mean_ndvi, 3)}</td><td>${
                    w.population_density_km2 != null ? Math.round(w.population_density_km2).toLocaleString() : "N/A"
                }</td><td>${fmt(w.vulnerability_score, 1)}</td><td>${w[keys.count] ?? 0}</td></tr>`
        )
        .join("");

    renderComplementarySection(data);
}

function renderComplementarySection(data) {
    const validation = data.validation || {};
    const wards = data.wards || [];
    const keys = CITY.complementaryFieldKeys;

    const correlationElId = CITY.slug === "delhi" ? "jj-correlation-value" : "elderly-correlation-value";
    const metaElId = CITY.slug === "delhi" ? "jj-cluster-meta" : "elderly-meta";
    const chartElId = CITY.slug === "delhi" ? "jj-cluster-scatter-chart" : "elderly-scatter-chart";

    const rEl = document.getElementById(correlationElId);
    if (rEl) {
        const r = validation[keys.correlation];
        rEl.textContent = r !== null && r !== undefined ? `r = ${r.toFixed(2)}` : "unavailable";
    }

    const metaEl = document.getElementById(metaElId);
    if (metaEl) {
        metaEl.textContent = validation[keys.total]
            ? `${validation[keys.total]} ${CITY.complementaryLabel.toLowerCase()} features matched to ${validation[keys.wards]} of ${wards.length} ${CITY.wardLabel.toLowerCase()}s`
            : "";
    }

    const points = wards
        .filter((w) => w.vulnerability_score !== null && w[keys.density] !== null && w[keys.density] !== undefined)
        .map((w) => ({ x: w.vulnerability_score, y: w[keys.density], name: w.ward_name }));

    const canvas = document.getElementById(chartElId);
    if (!canvas) return;
    new Chart(canvas, {
        type: "scatter",
        data: {
            datasets: [
                {
                    label: `${CITY.wardLabel}s`,
                    data: points,
                    backgroundColor: CITY.complementaryFillColor,
                    pointRadius: 4,
                },
            ],
        },
        options: {
            responsive: true,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: (ctx) => `${ctx.raw.name}: score ${ctx.raw.x.toFixed(1)}, density ${Math.round(ctx.raw.y).toLocaleString()}/km²`,
                    },
                },
            },
            scales: {
                x: { title: { display: true, text: "Vulnerability score" } },
                y: { title: { display: true, text: `${CITY.complementaryLabel} density (/km²)` } },
            },
        },
    });
}

async function loadLongTermTrends(landCoverColors) {
    let timeseries = null;
    let historical = null;

    try {
        const res = await fetch(cityDataPath("timeseries_scenes.json"), { cache: "no-store" });
        timeseries = await res.json();
    } catch (err) {
        console.error("Failed to load timeseries_scenes.json", err);
    }

    try {
        const res = await fetch(cityDataPath("historical_trends.json"), { cache: "no-store" });
        historical = await res.json();
    } catch (err) {
        console.error("Failed to load historical_trends.json", err);
    }

    if (!timeseries && !historical) {
        showErrorBanner("Long-term trend data unavailable — try reloading.");
        return;
    }

    if (timeseries) renderLongTermLstChart(timeseries);
    if (historical) renderLongTermLulcChart(historical, landCoverColors);
}

function renderLongTermLstChart(timeseries) {
    const records = (timeseries.records || []).filter((r) => r.mean_lst_c !== null && r.mean_lst_c !== undefined);
    const byMonth = {};
    records.forEach((r) => {
        const month = r.date.slice(0, 7);
        (byMonth[month] = byMonth[month] || []).push(r.mean_lst_c);
    });
    const months = Object.keys(byMonth).sort();
    const means = months.map((m) => byMonth[m].reduce((a, b) => a + b, 0) / byMonth[m].length);

    const trendPoints = means.map((y, i) => ({ x: i, y }));
    const trend = linearRegression(trendPoints);

    const datasets = [
        {
            label: "Monthly mean LST (°C)",
            data: means,
            borderColor: "#ff6b00",
            backgroundColor: "rgba(255,107,0,0.1)",
            pointRadius: 2,
            borderWidth: 2,
            tension: 0.15,
        },
    ];
    if (trend) {
        datasets.push({
            label: "Trend",
            data: months.map((_, i) => trend.slope * i + trend.intercept),
            borderColor: "#111",
            borderWidth: 2,
            borderDash: [6, 4],
            pointRadius: 0,
        });
    }

    new Chart(document.getElementById("long-term-lst-chart"), {
        type: "line",
        data: { labels: months, datasets },
        options: {
            responsive: true,
            scales: {
                x: { ticks: { maxTicksLimit: 10, font: { size: 10 } } },
                y: { title: { display: true, text: "°C" } },
            },
        },
    });
}

function renderLongTermLulcChart(historical, landCoverColors) {
    const rows = historical.monthly_land_cover_lst || [];
    const months = [...new Set(rows.map((r) => r.month))].sort();
    const landCoverNames = [...new Set(rows.map((r) => r.land_cover))];

    const datasets = landCoverNames.map((name) => {
        const byMonth = {};
        rows.filter((r) => r.land_cover === name).forEach((r) => (byMonth[r.month] = r.mean_lst_c));
        return {
            label: name,
            data: months.map((m) => (m in byMonth ? byMonth[m] : null)),
            borderColor: landCoverColors[name] || "#999",
            backgroundColor: landCoverColors[name] || "#999",
            spanGaps: true,
            pointRadius: 2,
            borderWidth: 2,
        };
    });

    new Chart(document.getElementById("long-term-lulc-chart"), {
        type: "line",
        data: { labels: months, datasets },
        options: {
            responsive: true,
            scales: {
                x: { ticks: { maxTicksLimit: 10, font: { size: 10 } } },
                y: { title: { display: true, text: "Mean LST (°C)" } },
            },
        },
    });
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
        statCard(`Hottest ${CITY.districtLabel} (Air UHI)`, hottest.name, `+${fmt(hottest.uhi_air_c)}°C above city mean`, "accent-hot"),
        statCard(`Coolest ${CITY.districtLabel} (Air UHI)`, coolest.name, `${fmt(coolest.uhi_air_c)}°C vs city mean`, "accent-cool"),
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
