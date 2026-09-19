function statCard(label, value, sub) {
    return `<div class="stat-card"><div class="stat-label">${label}</div><div class="stat-value">${value}</div>${
        sub ? `<div class="stat-sub">${sub}</div>` : ""
    }</div>`;
}

function fmtR(r) {
    return r !== null && r !== undefined ? `r = ${r.toFixed(2)}` : "unavailable";
}

function showErrorBanner(message) {
    const container = document.getElementById("about-error-banner");
    const div = document.createElement("div");
    div.className = "error-banner";
    div.textContent = message;
    container.appendChild(div);
}

function applyCityChrome() {
    document.getElementById("page-title").textContent = `About | ${CITY.displayName} Urban Heat Monitor`;
    document.getElementById("site-brand").textContent = `🌡️ ${CITY.displayName} Urban Heat Monitor`;
    document.getElementById("page-description").setAttribute(
        "content",
        `Why this dashboard exists: cross-referencing satellite-measured heat in ${CITY.displayName} with who's actually vulnerable to it, instead of just mapping temperature.`
    );
    document.getElementById("problem-text").textContent =
        `Land surface temperature maps are common — Landsat and Sentinel data are public, and "here's where ${CITY.displayName} is hottest" is a well-solved visualization problem by itself. What's missing in most public tools is the next step: cross-referencing that heat signal against who actually lives in the hot areas, at a granularity fine enough to act on. A citywide average hides exactly the pattern that matters — whether ${CITY.displayName}'s hottest ${CITY.wardLabel.toLowerCase()}s are also the densest, least-vegetated, most housing-insecure, or most pollution-burdened ones, or whether those risks are somewhere else entirely.`;
    renderCitySwitcher("city-switcher");
    wireCityAwareNavLinks();
}

async function main() {
    applyCityChrome();

    let data;
    try {
        const res = await fetch(cityDataPath("ward_vulnerability.json"), { cache: "no-store" });
        data = await res.json();
    } catch (err) {
        console.error("Failed to load ward_vulnerability.json", err);
        document.getElementById("finding-stats").textContent = "";
        document.getElementById("findings-text").textContent =
            "Current findings are unavailable right now — the underlying ward_vulnerability.json failed to load.";
        showErrorBanner("Findings data unavailable — try reloading.");
        return;
    }

    const validation = data.validation || {};
    const wards = data.wards || [];
    const keys = CITY.complementaryFieldKeys;
    const complementaryR = validation[keys.correlation];
    const no2R = validation.no2_correlation_r;

    document.getElementById("finding-stats").innerHTML = [
        statCard(`${CITY.complementaryLabel} vs vulnerability`, fmtR(complementaryR), `across ${wards.length} ${CITY.wardLabel.toLowerCase()}s`),
        statCard("NO₂ vs vulnerability", fmtR(no2R), "Sentinel-5P, ward mean"),
        statCard(`${CITY.wardLabel}s analyzed`, wards.length.toLocaleString(), CITY.displayName),
    ].join("");

    const complementaryStrength = complementaryR === null || complementaryR === undefined
        ? "unavailable"
        : Math.abs(complementaryR) < 0.2
        ? "weak-to-none"
        : Math.abs(complementaryR) < 0.4
        ? "weak-to-moderate"
        : "moderate-to-strong";
    const no2Strength = no2R === null || no2R === undefined
        ? "unavailable"
        : Math.abs(no2R) < 0.2
        ? "weak-to-none"
        : Math.abs(no2R) < 0.4
        ? "weak-to-moderate"
        : "moderate-to-strong";

    document.getElementById("findings-text").textContent =
        `In ${CITY.displayName}, the correlation between vulnerability score and ${CITY.complementaryLabel.toLowerCase()} is ${fmtR(complementaryR)} (${complementaryStrength}), and between vulnerability score and satellite-measured NO₂ is ${fmtR(no2R)} (${no2Strength}). Full charts and the same numbers for the other city are on the Analytics page.`;
}

main();
