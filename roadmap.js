const NOMINAL_REVISIT_DAYS = 16;

function statCard(label, value, sub) {
    return `<div class="stat-card"><div class="stat-label">${label}</div><div class="stat-value">${value}</div>${
        sub ? `<div class="stat-sub">${sub}</div>` : ""
    }</div>`;
}

function daysBetween(a, b) {
    return Math.round((b - a) / (1000 * 60 * 60 * 24));
}

function showErrorBanner(message) {
    const container = document.getElementById("roadmap-error-banner");
    const div = document.createElement("div");
    div.className = "error-banner";
    div.textContent = message;
    container.appendChild(div);
}

function applyCityChrome() {
    document.getElementById("page-title").textContent = `Roadmap | ${CITY.displayName} Urban Heat Monitor`;
    document.getElementById("site-brand").textContent = `🌡️ ${CITY.displayName} Urban Heat Monitor`;
    document.getElementById("page-intro").textContent =
        `Every optical satellite used on this site — Landsat 8, Sentinel-2 — is blind through cloud cover. The numbers below are computed directly from this project's own Landsat record, not a hypothetical: they show how often that actually happens over ${CITY.displayName}.`;
    document.getElementById("problem-text").textContent =
        `Landsat 8 revisits ${CITY.displayName} roughly every 16 days, but usable land-surface-temperature scenes require the sky to actually be clear — cloud cover silently removes a share of that already-sparse schedule (see the real gap data above). Any product built purely on optical imagery inherits these blind spots by construction, exactly like the map layers earlier on this site.`;
    renderCitySwitcher("city-switcher");
    wireCityAwareNavLinks();
}

async function main() {
    applyCityChrome();
    let data;
    try {
        const res = await fetch(cityDataPath("timeseries_scenes.json"), { cache: "no-store" });
        data = await res.json();
    } catch (err) {
        console.error("Failed to load timeseries_scenes.json", err);
        document.getElementById("gap-stats").textContent = "";
        showErrorBanner("Data unavailable — try reloading.");
        return;
    }

    const dates = [...new Set((data.records || []).map((r) => r.date))].sort();
    if (dates.length < 2) {
        document.getElementById("gap-stats").textContent = "Not enough data yet to compute gap statistics.";
        return;
    }

    const dateObjs = dates.map((d) => new Date(d + "T00:00:00Z"));
    const coverageStart = new Date(data.coverage_start + "T00:00:00Z");
    const coverageEnd = new Date(data.coverage_end + "T00:00:00Z");
    const coverageDays = daysBetween(coverageStart, coverageEnd);
    const expectedScenes = Math.max(1, Math.floor(coverageDays / NOMINAL_REVISIT_DAYS) + 1);
    const coveragePct = Math.min(100, (dates.length / expectedScenes) * 100);

    const gaps = [];
    for (let i = 1; i < dateObjs.length; i++) {
        const gapDays = daysBetween(dateObjs[i - 1], dateObjs[i]);
        if (gapDays > NOMINAL_REVISIT_DAYS + 4) {
            gaps.push({ start: dates[i - 1], end: dates[i], days: gapDays });
        }
    }
    gaps.sort((a, b) => b.days - a.days);

    const avgGap = dateObjs.length > 1
        ? dateObjs.slice(1).reduce((sum, d, i) => sum + daysBetween(dateObjs[i], d), 0) / (dateObjs.length - 1)
        : 0;
    const longestGap = gaps.length ? gaps[0].days : 0;

    document.getElementById("gap-stats").innerHTML = [
        statCard("Usable Scenes in Record", dates.length, `${data.coverage_start} → ${data.coverage_end}`),
        statCard("Expected at 16-Day Revisit", expectedScenes, "If every pass were cloud-free"),
        statCard("Effective Coverage", `${coveragePct.toFixed(0)}%`, "Usable scenes / expected scenes"),
        statCard("Average Gap Between Scenes", `${avgGap.toFixed(1)} days`, `vs ${NOMINAL_REVISIT_DAYS}-day nominal revisit`),
        statCard("Longest Real Gap", `${longestGap} days`, gaps.length ? `${gaps[0].start} → ${gaps[0].end}` : "No large gaps found"),
        statCard("Gaps Over Nominal Revisit", gaps.length, "Instances of missed cloud-free passes"),
    ].join("");

    renderMonthlyChart(dates);
    renderGapsTable(gaps);
}

function renderMonthlyChart(dates) {
    const counts = {};
    dates.forEach((d) => {
        const month = d.slice(0, 7);
        counts[month] = (counts[month] || 0) + 1;
    });
    const months = Object.keys(counts).sort();

    new Chart(document.getElementById("scenes-per-month-chart"), {
        type: "bar",
        data: {
            labels: months,
            datasets: [
                {
                    label: "Usable scenes",
                    data: months.map((m) => counts[m]),
                    backgroundColor: "#1f77b4",
                },
            ],
        },
        options: {
            responsive: true,
            plugins: { legend: { display: false } },
            scales: {
                x: { ticks: { maxTicksLimit: 12 } },
                y: { title: { display: true, text: "Scene count" }, ticks: { stepSize: 1 } },
            },
        },
    });
}

function renderGapsTable(gaps) {
    const body = document.querySelector("#gaps-table tbody");
    if (!gaps.length) {
        body.innerHTML = `<tr><td colspan="3">No gaps longer than the nominal ${NOMINAL_REVISIT_DAYS}-day revisit were found in this window.</td></tr>`;
        return;
    }
    body.innerHTML = gaps
        .slice(0, 10)
        .map((g) => `<tr><td>${g.start}</td><td>${g.end}</td><td>${g.days} days</td></tr>`)
        .join("");
}

main();
