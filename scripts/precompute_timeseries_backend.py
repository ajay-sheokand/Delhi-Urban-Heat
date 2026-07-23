import json
import os
from datetime import datetime, timedelta

import ee
import geopandas as gpd
import requests
from google.oauth2 import service_account
from shapely.validation import make_valid


def shapely_geom_to_ee(geom) -> ee.Geometry:
    """Exterior-ring-only conversion (no holes) — same simplification app.py's
    own get_districts_ee_geometry() already makes for this same dataset."""
    if geom.geom_type == "Polygon":
        coords = [[pt[0], pt[1]] for pt in geom.exterior.coords]
        return ee.Geometry.Polygon([coords])
    if geom.geom_type == "MultiPolygon":
        polygons = [[[list(pt[:2]) for pt in poly.exterior.coords]] for poly in geom.geoms]
        return ee.Geometry.MultiPolygon(polygons)
    raise ValueError(f"Unsupported geometry type: {geom.geom_type}")


def repair_shapely_geometry(geom):
    """Fix invalid ring winding/self-intersections (delhi_admin.geojson has
    several) so EE's strict GeoJSON validator accepts it — mirrors app.py's
    get_districts_ee_geometry(), which already solves this for the same file."""
    fixed = make_valid(geom)
    return fixed.simplify(0.0001, preserve_topology=True)


def load_delhi_geometry_from_geojson(path: str) -> ee.Geometry:
    gdf = gpd.read_file(path)
    gdf["geometry"] = gdf["geometry"].apply(repair_shapely_geometry)
    merged = repair_shapely_geometry(gdf.union_all())
    return shapely_geom_to_ee(merged)


def load_delhi_geometry_from_ee() -> ee.Geometry:
    # Delhi boundary from GAUL level-1 is typically robust for server-side reducers.
    delhi_fc = (
        ee.FeatureCollection("FAO/GAUL_SIMPLIFIED_500m/2015/level1")
        .filter(ee.Filter.eq("ADM0_NAME", "India"))
        .filter(ee.Filter.eq("ADM1_NAME", "Delhi"))
    )
    return delhi_fc.geometry()


def init_ee() -> None:
    service_account_email = os.environ.get("GEE_SERVICE_ACCOUNT", "").strip()
    private_key = os.environ.get("GEE_PRIVATE_KEY", "").strip()

    if not service_account_email:
        raise RuntimeError("Missing required env var: GEE_SERVICE_ACCOUNT")
    if not private_key:
        raise RuntimeError("Missing required env var: GEE_PRIVATE_KEY")

    # Support both literal '\\n' and real newlines from secret stores.
    private_key = private_key.replace("\\n", "\n")

    service_account_info = {
        "type": "service_account",
        "client_email": service_account_email,
        "private_key": private_key,
        "token_uri": "https://oauth2.googleapis.com/token",
    }

    credentials = service_account.Credentials.from_service_account_info(
        service_account_info,
        scopes=["https://www.googleapis.com/auth/earthengine"],
    )
    ee.Initialize(credentials)


def mask_landsat_l2(image: ee.Image) -> ee.Image:
    qa = image.select("QA_PIXEL")
    cloud_shadow_bit = 1 << 3
    snow_bit = 1 << 4
    cloud_bit = 1 << 5
    cirrus_bit = 1 << 7
    mask = (
        qa.bitwiseAnd(cloud_shadow_bit).eq(0)
        .And(qa.bitwiseAnd(snow_bit).eq(0))
        .And(qa.bitwiseAnd(cloud_bit).eq(0))
        .And(qa.bitwiseAnd(cirrus_bit).eq(0))
    )
    return image.updateMask(mask)


def prep_landsat8_l2(image: ee.Image) -> ee.Image:
    # LST (Kelvin) -> Celsius
    lst_k = image.select("ST_B10").multiply(0.00341802).add(149.0)
    lst_c = lst_k.subtract(273.15).rename("LST")

    # Surface reflectance scaling for NDVI
    red = image.select("SR_B4").multiply(0.0000275).add(-0.2)
    nir = image.select("SR_B5").multiply(0.0000275).add(-0.2)
    ndvi = nir.subtract(red).divide(nir.add(red)).rename("NDVI")

    return image.addBands([lst_c, ndvi]).select(["LST", "NDVI"])


def get_landsat8_collection(start_date: str, end_date: str, geom: ee.Geometry) -> ee.ImageCollection:
    return (
        ee.ImageCollection("LANDSAT/LC08/C02/T1_L2")
        .filterDate(start_date, end_date)
        .filterBounds(geom)
        .filter(ee.Filter.lt("CLOUD_COVER", 60))
        .map(mask_landsat_l2)
        .map(prep_landsat8_l2)
        .sort("system:time_start")
    )


def load_region(workspace: str) -> ee.Geometry:
    geojson_path = os.path.join(workspace, "delhi_admin.geojson")
    try:
        region = load_delhi_geometry_from_geojson(geojson_path)
        # Force a lightweight server validation so invalid geometries fail here.
        _ = region.area(1).getInfo()
        print("Using local geometry: delhi_admin.geojson")
        return region
    except Exception as exc:
        print(f"Local GeoJSON geometry invalid or unavailable: {exc}")
    try:
        region = load_delhi_geometry_from_ee()
        _ = region.area(1).getInfo()
        print("Using fallback geometry: FAO/GAUL_SIMPLIFIED_500m/2015/level1 (Delhi)")
        return region
    except Exception as ee_exc:
        print(f"EE Delhi geometry fallback failed: {ee_exc}")
        print("Using final fallback geometry: Delhi rectangle")
        return ee.Geometry.Rectangle([76.8388, 28.4044, 77.3465, 28.8833])


def load_district_features(workspace: str) -> list:
    """Per-district (name, ee.Geometry) pairs from delhi_admin.geojson's 11 features.

    Uses the same shapely repair as load_delhi_geometry_from_geojson() so
    these polygons are the exact same source geometry drawn as the district
    boundary lines on the map — not a different fallback boundary — so
    raster clipping and the vector overlay line up. A buffered point around
    the district's known centroid (DISTRICT_LOCATIONS) is a last-resort
    fallback if repair genuinely can't fix a given polygon.
    """
    geojson_path = os.path.join(workspace, "delhi_admin.geojson")
    gdf = gpd.read_file(geojson_path)
    name_col = "District" if "District" in gdf.columns else "Name"

    districts = []
    for _, row in gdf.iterrows():
        name = str(row[name_col]).title() if name_col in row and row[name_col] else "Unknown"

        geom = None
        try:
            repaired = repair_shapely_geometry(row.geometry)
            candidate = shapely_geom_to_ee(repaired)
            _ = candidate.area(1).getInfo()  # force server-side validation now
            geom = candidate
        except Exception as exc:
            print(f"District polygon invalid for {name} even after repair, using buffered centroid fallback: {exc}")
            loc = next((d for d in DISTRICT_LOCATIONS if d["name"] == name), None)
            if loc:
                geom = ee.Geometry.Point([loc["lon"], loc["lat"]]).buffer(3000)

        if geom is not None:
            districts.append((name, geom))

    return districts


def load_ward_features(workspace: str) -> ee.FeatureCollection:
    """Single batched FeatureCollection of Delhi's 290 wards (pre-2022
    delimitation — see README for provenance/license), keyed by the file's
    unique Ward_No property. Built as one FeatureCollection rather than a
    Python list of per-ward ee.Geometry (contrast load_district_features)
    so build_ward_vulnerability_dataset can run zonal stats via reduceRegions
    in a couple of batched server-side calls instead of ~290 sequential ones.
    delhi_wards.geojson was verified clean (no Z-coordinates, all valid
    polygons) at import time, so unlike load_district_features there is no
    per-feature forced-validation round trip here — that would defeat the
    point of batching.
    """
    geojson_path = os.path.join(workspace, "delhi_wards.geojson")
    gdf = gpd.read_file(geojson_path)

    features = []
    for _, row in gdf.iterrows():
        try:
            geom = shapely_geom_to_ee(repair_shapely_geometry(row.geometry))
        except Exception as exc:
            print(f"Ward polygon invalid for {row.get('Ward_Name')}, skipping: {exc}")
            continue
        features.append(
            ee.Feature(
                geom,
                {
                    "ward_name": str(row.get("Ward_Name") or "Unknown").title(),
                    "ward_no": str(row.get("Ward_No") or ""),
                },
            )
        )
    return ee.FeatureCollection(features)


# Same 11 district centroids used by the weather markers (names match
# load_district_features()'s .title()-cased "District" property exactly).
DISTRICT_LOCATIONS = [
    {"name": "Central", "lat": 28.6422, "lon": 77.2183},
    {"name": "East", "lat": 28.6261, "lon": 77.3006},
    {"name": "New Delhi", "lat": 28.6107, "lon": 77.2193},
    {"name": "North", "lat": 28.7043, "lon": 77.2074},
    {"name": "North East", "lat": 28.7234, "lon": 77.2701},
    {"name": "North West", "lat": 28.7717, "lon": 77.0986},
    {"name": "Shahadra", "lat": 28.7100, "lon": 77.3150},
    {"name": "South", "lat": 28.5032, "lon": 77.2332},
    {"name": "South East", "lat": 28.5550, "lon": 77.2850},
    {"name": "South West", "lat": 28.5732, "lon": 77.0396},
    {"name": "West", "lat": 28.6564, "lon": 77.0709},
]


def get_power_air_temp(lat: float, lon: float, start_date, end_date):
    start_str = start_date.strftime("%Y%m%d")
    end_str = end_date.strftime("%Y%m%d")
    url = (
        "https://power.larc.nasa.gov/api/temporal/daily/point"
        f"?parameters=T2M&start={start_str}&end={end_str}"
        f"&latitude={lat}&longitude={lon}&community=RE&format=JSON"
    )
    response = requests.get(url, timeout=30)
    if response.status_code != 200:
        return None
    payload = response.json()
    values = payload.get("properties", {}).get("parameter", {}).get("T2M", {})
    temps = [v for v in values.values() if v is not None and v > -900]
    if not temps:
        return None
    return sum(temps) / len(temps)


def pearson_correlation(xs: list, ys: list):
    n = len(xs)
    if n < 2:
        return None
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    var_x = sum((x - mean_x) ** 2 for x in xs)
    var_y = sum((y - mean_y) ** 2 for y in ys)
    denom = (var_x * var_y) ** 0.5
    if denom == 0:
        return None
    return cov / denom


def heat_alert(temp_c: float) -> dict:
    if temp_c >= 40:
        return {"level": "extreme", "label": "🔥 Extreme Heat Alert"}
    if temp_c >= 35:
        return {"level": "high", "label": "⚠️ High Heat Warning"}
    return {"level": "normal", "label": "🌤️ Normal Temperature"}


def build_timeseries_dataset(region: ee.Geometry) -> dict:
    days_back = int(os.environ.get("PRECOMPUTE_DAYS", "730"))
    end_dt = datetime.utcnow().date()
    start_dt = end_dt - timedelta(days=days_back)

    collection = get_landsat8_collection(start_dt.isoformat(), end_dt.isoformat(), region)

    # Compute mean LST once per image on the server, then aggregate arrays in bulk.
    def add_scene_mean_lst(image: ee.Image) -> ee.Image:
        mean_lst = image.select("LST").reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=region,
            scale=250,
            maxPixels=1e9,
            bestEffort=True,
            tileScale=4,
        ).get("LST")
        return image.set("mean_lst_c", mean_lst)

    enriched = collection.map(add_scene_mean_lst)

    time_starts = enriched.aggregate_array("system:time_start").getInfo() or []
    cloud_covers = enriched.aggregate_array("CLOUD_COVER").getInfo() or []
    product_ids = enriched.aggregate_array("LANDSAT_PRODUCT_ID").getInfo() or []
    system_indexes = enriched.aggregate_array("system:index").getInfo() or []
    mean_lsts = enriched.aggregate_array("mean_lst_c").getInfo() or []

    count = len(time_starts)

    records = []
    for i in range(count):
        ts = time_starts[i]
        dt = datetime.utcfromtimestamp(ts / 1000)

        records.append(
            {
                "date": dt.strftime("%Y-%m-%d"),
                "time_utc": dt.strftime("%H:%M"),
                "scene_id": product_ids[i] or system_indexes[i] or "Unknown",
                "cloud_cover": cloud_covers[i],
                "mean_lst_c": mean_lsts[i] if i < len(mean_lsts) else None,
            }
        )

    return {
        "generated_at_utc": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "coverage_start": start_dt.isoformat(),
        "coverage_end": end_dt.isoformat(),
        "source": "LANDSAT/LC08/C02/T1_L2",
        "records": records,
    }


# Same palettes/ranges as the live LST/NDVI/land-cover layers in app.py, so the
# precomputed tiles look identical to what the Streamlit map used to render.
LST_PALETTE = [
    "#0000ff", "#00ccff", "#00ff00", "#ffff00", "#ff8800", "#ff0000", "#8b0000",
]
NDVI_PALETTE = [
    "#8B0000", "#DC143C", "#FF4500", "#FFD700", "#FFFF00", "#7FFF00", "#00FF00", "#006400",
]
WORLDCOVER_PALETTE = [
    "#006400", "#FFBB22", "#FFFF4C", "#F096FF", "#FA0000",
    "#B4B4B4", "#F0F0F0", "#0064C8", "#0096A0", "#00CF75", "#FAE6A0",
]
WORLDCOVER_CLASSES = [
    {"id": 10, "color": "#006400", "label": "Tree Cover"},
    {"id": 20, "color": "#FFBB22", "label": "Shrubland"},
    {"id": 30, "color": "#FFFF4C", "label": "Grassland"},
    {"id": 40, "color": "#F096FF", "label": "Cropland"},
    {"id": 50, "color": "#FA0000", "label": "Built-up (Urban)"},
    {"id": 60, "color": "#B4B4B4", "label": "Bare/Sparse Veg"},
    {"id": 70, "color": "#F0F0F0", "label": "Snow/Ice"},
    {"id": 80, "color": "#0064C8", "label": "Water Bodies"},
    {"id": 90, "color": "#0096A0", "label": "Wetland"},
    {"id": 95, "color": "#00CF75", "label": "Mangroves"},
    {"id": 100, "color": "#FAE6A0", "label": "Moss/Lichen"},
]
WORLDCOVER_NAME_BY_ID = {c["id"]: c["label"] for c in WORLDCOVER_CLASSES}


def build_map_layers_dataset(
    region: ee.Geometry,
    lst_image: ee.Image,
    ndvi_image: ee.Image,
    start_dt,
    end_dt,
) -> dict:
    lst_clipped = lst_image.clip(region)
    ndvi_clipped = ndvi_image.clip(region)

    try:
        lst_stats = lst_clipped.reduceRegion(
            reducer=ee.Reducer.minMax(),
            geometry=region,
            scale=100,
            maxPixels=1e9,
            bestEffort=True,
            tileScale=4,
        ).getInfo()
        data_min = lst_stats.get("LST_min", 10)
        data_max = lst_stats.get("LST_max", 40)
        buffer = (data_max - data_min) * 0.1
        lst_min = max(data_min - buffer, -5)
        lst_max = min(data_max + buffer, 55)
    except Exception as exc:
        print(f"LST min/max calculation failed, using fallback range: {exc}")
        lst_min, lst_max = 10, 40

    lst_vis = {"min": lst_min, "max": lst_max, "palette": LST_PALETTE}
    lst_mapid = lst_clipped.getMapId(lst_vis)

    ndvi_vis = {"min": -0.3, "max": 1, "palette": NDVI_PALETTE}
    ndvi_mapid = ndvi_clipped.getMapId(ndvi_vis)

    worldcover = ee.ImageCollection("ESA/WorldCover/v200").first().clip(region)
    worldcover_vis = {"min": 10, "max": 100, "palette": WORLDCOVER_PALETTE}
    worldcover_mapid = worldcover.getMapId(worldcover_vis)

    try:
        histogram = worldcover.reduceRegion(
            reducer=ee.Reducer.frequencyHistogram(),
            geometry=region,
            scale=100,
            maxPixels=1e9,
            bestEffort=True,
            tileScale=4,
        ).getInfo()
        land_cover_histogram = histogram.get("Map", {}) if histogram else {}
    except Exception as exc:
        print(f"Land cover histogram calculation failed: {exc}")
        land_cover_histogram = {}

    return {
        "generated_at_utc": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "coverage_start": start_dt.isoformat(),
        "coverage_end": end_dt.isoformat(),
        "layers": {
            "lst": {
                "tile_url": lst_mapid["tile_fetcher"].url_format,
                "min": lst_min,
                "max": lst_max,
                "palette": LST_PALETTE,
                "opacity": 0.6,
            },
            "ndvi": {
                "tile_url": ndvi_mapid["tile_fetcher"].url_format,
                "min": -0.3,
                "max": 1,
                "palette": NDVI_PALETTE,
                "opacity": 0.45,
            },
            "land_cover": {
                "tile_url": worldcover_mapid["tile_fetcher"].url_format,
                "source": "ESA WorldCover 2021 (10m)",
                "classes": WORLDCOVER_CLASSES,
                "histogram": land_cover_histogram,
                "opacity": 0.5,
            },
        },
    }


def build_district_analytics_dataset(
    region: ee.Geometry,
    district_features: list,
    lst_image: ee.Image,
    ndvi_image: ee.Image,
    composite_collection: ee.ImageCollection,
) -> dict:
    air_temp_days = int(os.environ.get("ANALYTICS_AIR_TEMP_DAYS", "90"))
    air_end_dt = datetime.utcnow().date()
    air_start_dt = air_end_dt - timedelta(days=air_temp_days)

    combined = lst_image.addBands(ndvi_image)

    district_rows = []
    for name, geom in district_features:
        loc = next((d for d in DISTRICT_LOCATIONS if d["name"] == name), None)
        lat = loc["lat"] if loc else None
        lon = loc["lon"] if loc else None

        mean_lst = None
        mean_ndvi = None
        try:
            stats = combined.reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=geom,
                scale=100,
                maxPixels=1e9,
                bestEffort=True,
                tileScale=4,
            ).getInfo()
            mean_lst = stats.get("LST")
            mean_ndvi = stats.get("NDVI")
        except Exception as exc:
            print(f"District LST/NDVI stats failed for {name}: {exc}")

        air_temp = None
        if lat is not None and lon is not None:
            try:
                air_temp = get_power_air_temp(lat, lon, air_start_dt, air_end_dt)
            except Exception as exc:
                print(f"NASA POWER fetch failed for {name}: {exc}")

        district_rows.append(
            {
                "name": name,
                "lat": lat,
                "lon": lon,
                "mean_lst_c": mean_lst,
                "mean_ndvi": mean_ndvi,
                "air_temp_c": air_temp,
            }
        )

    valid_air_temps = [d["air_temp_c"] for d in district_rows if d["air_temp_c"] is not None]
    citywide_air_temp = sum(valid_air_temps) / len(valid_air_temps) if valid_air_temps else None

    cropland_baseline_lst = None
    try:
        worldcover = ee.ImageCollection("ESA/WorldCover/v200").first()
        cropland_lst = lst_image.updateMask(worldcover.select("Map").eq(40))
        cropland_stats = cropland_lst.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=region,
            scale=100,
            maxPixels=1e9,
            bestEffort=True,
            tileScale=4,
        ).getInfo()
        cropland_baseline_lst = cropland_stats.get("LST")
    except Exception as exc:
        print(f"Cropland baseline LST failed: {exc}")

    for d in district_rows:
        d["uhi_air_c"] = (
            d["air_temp_c"] - citywide_air_temp
            if d["air_temp_c"] is not None and citywide_air_temp is not None
            else None
        )
        d["uhi_surface_c"] = (
            d["mean_lst_c"] - cropland_baseline_lst
            if d["mean_lst_c"] is not None and cropland_baseline_lst is not None
            else None
        )

    correlation = None
    try:
        worldcover = ee.ImageCollection("ESA/WorldCover/v200").first()
        sample_image = combined.addBands(worldcover.select("Map").rename("LandCover"))
        sample_data = sample_image.sample(
            region=region, scale=250, numPixels=300, seed=42, geometries=False, tileScale=4
        ).getInfo()

        points = []
        for feat in (sample_data or {}).get("features", []):
            props = feat.get("properties", {})
            lst_v, ndvi_v, lc_v = props.get("LST"), props.get("NDVI"), props.get("LandCover")
            if lst_v is None or ndvi_v is None or lc_v is None:
                continue
            if not (-50 < lst_v < 60) or not (-1 <= ndvi_v <= 1):
                continue
            points.append({"lst": lst_v, "ndvi": ndvi_v, "land_cover": int(lc_v)})

        if len(points) > 10:
            r = pearson_correlation([p["ndvi"] for p in points], [p["lst"] for p in points])
            urban_lsts = [p["lst"] for p in points if p["land_cover"] == 50]
            veg_lsts = [p["lst"] for p in points if p["land_cover"] in (10, 20, 30)]
            urban_mean = sum(urban_lsts) / len(urban_lsts) if urban_lsts else None
            veg_mean = sum(veg_lsts) / len(veg_lsts) if veg_lsts else None

            buckets = {}
            for p in points:
                bucket = buckets.setdefault(p["land_cover"], {"lst": [], "ndvi": []})
                bucket["lst"].append(p["lst"])
                bucket["ndvi"].append(p["ndvi"])

            land_cover_stats = [
                {
                    "land_cover": WORLDCOVER_NAME_BY_ID.get(lc, f"Class {lc}"),
                    "count": len(vals["lst"]),
                    "area_pct": round(len(vals["lst"]) / len(points) * 100, 2),
                    "mean_lst_c": sum(vals["lst"]) / len(vals["lst"]),
                    "mean_ndvi": sum(vals["ndvi"]) / len(vals["ndvi"]),
                }
                for lc, vals in buckets.items()
            ]
            land_cover_stats.sort(key=lambda x: x["area_pct"], reverse=True)

            correlation = {
                "ndvi_lst_r": r,
                "urban_mean_lst_c": urban_mean,
                "vegetation_mean_lst_c": veg_mean,
                "uhi_effect_c": (urban_mean - veg_mean) if urban_mean is not None and veg_mean is not None else None,
                "sample_points": points,
                "land_cover_stats": land_cover_stats,
            }
    except Exception as exc:
        print(f"Correlation analysis failed: {exc}")

    lulc_time_series = []
    try:
        worldcover_ts = ee.ImageCollection("ESA/WorldCover/v200").first().select("Map").rename("LandCover")
        scene_count = composite_collection.size().getInfo()
        if scene_count > 0:
            scene_list = composite_collection.toList(scene_count)
            for idx in range(scene_count):
                img = ee.Image(scene_list.get(idx))
                date_str = ee.Date(img.get("system:time_start")).format("YYYY-MM-dd").getInfo()
                grouped = (
                    img.select("LST")
                    .addBands(worldcover_ts)
                    .reduceRegion(
                        reducer=ee.Reducer.mean().group(groupField=1, groupName="landcover"),
                        geometry=region,
                        scale=500,
                        maxPixels=1e9,
                        bestEffort=True,
                        tileScale=4,
                    )
                    .get("groups")
                    .getInfo()
                )
                for group_item in grouped or []:
                    lc_code_raw, lc_mean = group_item.get("landcover"), group_item.get("mean")
                    if lc_code_raw is None or lc_mean is None:
                        continue
                    lc_code = int(lc_code_raw)
                    lulc_time_series.append(
                        {
                            "date": date_str,
                            "land_cover": WORLDCOVER_NAME_BY_ID.get(lc_code, f"Class {lc_code}"),
                            "mean_lst_c": float(lc_mean),
                        }
                    )
    except Exception as exc:
        print(f"LST-by-land-cover time series failed: {exc}")

    return {
        "generated_at_utc": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "air_temp_window": {"start": air_start_dt.isoformat(), "end": air_end_dt.isoformat()},
        "citywide_air_temp_c": citywide_air_temp,
        "cropland_baseline_lst_c": cropland_baseline_lst,
        "districts": district_rows,
        "correlation": correlation,
        "lulc_time_series": lulc_time_series,
    }


def _minmax_normalizer(values: list, invert: bool = False):
    """Returns a fn mapping a raw value to its 0-1 min-max position across
    `values` (None-safe). `invert=True` flips the scale, for inputs where a
    lower raw value means more vulnerable (e.g. NDVI)."""
    clean = [v for v in values if v is not None]
    if len(clean) < 2 or max(clean) == min(clean):
        return lambda v: None
    lo, hi = min(clean), max(clean)
    span = hi - lo

    def norm(v):
        if v is None:
            return None
        n = (v - lo) / span
        return 1 - n if invert else n

    return norm


def build_ward_vulnerability_dataset(
    region: ee.Geometry,
    ward_fc: ee.FeatureCollection,
    lst_image: ee.Image,
    ndvi_image: ee.Image,
) -> dict:
    """Ward-resolution LST/NDVI/population — the inputs that are genuinely
    fine-grained at the satellite/gridded-population level. Air temperature
    deliberately stays district-level only (build_district_analytics_dataset):
    NASA POWER's ~50km grid and OpenWeather's station data don't carry real
    per-ward signal across a city Delhi's size, so computing them per-ward
    would be false precision, not more information.
    """
    ward_fc = ward_fc.map(lambda f: f.set("area_km2", f.geometry().area(1).divide(1e6)))

    combined = lst_image.addBands(ndvi_image)
    lst_ndvi_rows = combined.reduceRegions(
        collection=ward_fc, reducer=ee.Reducer.mean(), scale=100, tileScale=4
    ).getInfo().get("features", [])

    worldpop = (
        ee.ImageCollection("WorldPop/GP/100m/pop")
        .filter(ee.Filter.eq("country", "IND"))
        .sort("year", False)
        .first()
    )
    population_year = int(worldpop.get("year").getInfo())
    pop_rows = (
        worldpop.select("population")
        .unmask(0)
        .reduceRegions(collection=ward_fc, reducer=ee.Reducer.sum(), scale=100, tileScale=4)
        .getInfo()
        .get("features", [])
    )
    # ee.Reducer.sum()'s output property is named "sum", not the band name -
    # unlike mean() (used above), which keeps the band name ("LST"/"NDVI").
    pop_by_ward = {f["properties"].get("ward_no"): f["properties"].get("sum") for f in pop_rows}

    wards = []
    for feat in lst_ndvi_rows:
        props = feat.get("properties", {})
        ward_no = props.get("ward_no")
        area_km2 = props.get("area_km2")
        population = pop_by_ward.get(ward_no)
        population_density_km2 = (
            population / area_km2 if population is not None and area_km2 else None
        )
        wards.append(
            {
                "ward_name": props.get("ward_name"),
                "ward_no": ward_no,
                "mean_lst_c": props.get("LST"),
                "mean_ndvi": props.get("NDVI"),
                "area_km2": area_km2,
                "population": population,
                "population_density_km2": population_density_km2,
            }
        )

    lst_norm = _minmax_normalizer([w["mean_lst_c"] for w in wards])
    ndvi_norm = _minmax_normalizer([w["mean_ndvi"] for w in wards], invert=True)
    density_norm = _minmax_normalizer([w["population_density_km2"] for w in wards])

    for w in wards:
        components = [
            lst_norm(w["mean_lst_c"]),
            ndvi_norm(w["mean_ndvi"]),
            density_norm(w["population_density_km2"]),
        ]
        valid = [c for c in components if c is not None]
        w["vulnerability_score"] = round(sum(valid) / len(valid) * 100, 1) if valid else None

    ranked = sorted(
        (w for w in wards if w["vulnerability_score"] is not None),
        key=lambda w: w["vulnerability_score"],
        reverse=True,
    )

    return {
        "generated_at_utc": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "population_year": population_year,
        "source_note": (
            "Ward boundaries: datameet/Municipal_Spatial_Data (CC-BY-SA 2.5 India), "
            "pre-2022 delimitation (erstwhile North/South/East Delhi Municipal "
            "Corporations + NDMC + Delhi Cantonment). Population: WorldPop 100m "
            "(CC-BY 4.0). Vulnerability score = average of min-max normalized LST, "
            "inverse-normalized NDVI, and normalized population density (0-100, "
            "higher = more vulnerable). Air temperature is not part of this score "
            "and remains district-level only — see district_analytics.json."
        ),
        "wards": wards,
        "ranking": [
            {
                k: w[k]
                for k in (
                    "ward_name",
                    "ward_no",
                    "mean_lst_c",
                    "mean_ndvi",
                    "population_density_km2",
                    "vulnerability_score",
                )
            }
            for w in ranked[:20]
        ],
    }


def should_run_weekly_job() -> bool:
    """True on the first 6-hourly cron run of the week (Monday 00:xx UTC), or
    whenever manually forced via the workflow_dispatch input (e.g. to backfill
    on first deploy rather than waiting for the next Monday)."""
    if os.environ.get("FORCE_HISTORICAL_TRENDS", "").strip().lower() == "true":
        return True
    now = datetime.utcnow()
    return now.weekday() == 0 and now.hour < 6


def _month_starts(start_dt, end_dt) -> list:
    months = []
    cursor = start_dt.replace(day=1)
    while cursor <= end_dt:
        months.append(cursor)
        if cursor.month == 12:
            cursor = cursor.replace(year=cursor.year + 1, month=1)
        else:
            cursor = cursor.replace(month=cursor.month + 1)
    return months


def build_historical_trends_dataset(region: ee.Geometry) -> dict:
    """LST-by-land-cover, one monthly median composite at a time, over the
    full PRECOMPUTE_DAYS history — too expensive to run every 6h (~24 EE
    calls vs. the few-scene short window elsewhere), so main() only calls
    this on a weekly cadence via should_run_weekly_job()."""
    days_back = int(os.environ.get("PRECOMPUTE_DAYS", "730"))
    end_dt = datetime.utcnow().date()
    start_dt = end_dt - timedelta(days=days_back)

    worldcover_ts = ee.ImageCollection("ESA/WorldCover/v200").first().select("Map").rename("LandCover")

    rows = []
    for month_start in _month_starts(start_dt, end_dt):
        month_end = (
            month_start.replace(year=month_start.year + 1, month=1)
            if month_start.month == 12
            else month_start.replace(month=month_start.month + 1)
        )
        month_end = min(month_end, end_dt)

        collection = get_landsat8_collection(month_start.isoformat(), month_end.isoformat(), region)
        try:
            scene_count = collection.size().getInfo()
            if scene_count == 0:
                continue
            composite = collection.select("LST").median()
            grouped = (
                composite.addBands(worldcover_ts)
                .reduceRegion(
                    reducer=ee.Reducer.mean().group(groupField=1, groupName="landcover"),
                    geometry=region,
                    scale=500,
                    maxPixels=1e9,
                    bestEffort=True,
                    tileScale=4,
                )
                .get("groups")
                .getInfo()
            )
        except Exception as exc:
            print(f"Historical trend month {month_start.isoformat()} failed: {exc}")
            continue

        month_label = month_start.strftime("%Y-%m")
        for group_item in grouped or []:
            lc_code_raw, lc_mean = group_item.get("landcover"), group_item.get("mean")
            if lc_code_raw is None or lc_mean is None:
                continue
            lc_code = int(lc_code_raw)
            rows.append(
                {
                    "month": month_label,
                    "land_cover": WORLDCOVER_NAME_BY_ID.get(lc_code, f"Class {lc_code}"),
                    "mean_lst_c": float(lc_mean),
                    "scene_count": scene_count,
                }
            )

    return {
        "generated_at_utc": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "coverage_start": start_dt.isoformat(),
        "coverage_end": end_dt.isoformat(),
        "monthly_land_cover_lst": rows,
    }


def build_weather_dataset() -> dict:
    api_key = os.environ.get("OPENWEATHER_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("Missing required env var: OPENWEATHER_API_KEY")

    districts = []
    for loc in DISTRICT_LOCATIONS:
        url = (
            "https://api.openweathermap.org/data/2.5/weather"
            f"?lat={loc['lat']}&lon={loc['lon']}&appid={api_key}&units=metric"
        )
        try:
            response = requests.get(url, timeout=15)
            response.raise_for_status()
            payload = response.json()
            temp_c = payload["main"]["temp"]
            alert = heat_alert(temp_c)
            districts.append(
                {
                    "name": loc["name"],
                    "lat": loc["lat"],
                    "lon": loc["lon"],
                    "temp_c": temp_c,
                    "feels_like_c": payload["main"]["feels_like"],
                    "humidity": payload["main"]["humidity"],
                    "heat_alert_level": alert["level"],
                    "heat_alert_label": alert["label"],
                }
            )
        except Exception as exc:
            print(f"Weather fetch failed for {loc['name']}: {exc}")

    return {
        "generated_at_utc": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "districts": districts,
    }


def main() -> None:
    init_ee()

    workspace = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    region = load_region(workspace)

    out_dir = os.path.join(workspace, "backend-data")
    os.makedirs(out_dir, exist_ok=True)

    timeseries_output = build_timeseries_dataset(region)
    with open(os.path.join(out_dir, "timeseries_scenes.json"), "w", encoding="utf-8") as f:
        json.dump(timeseries_output, f, ensure_ascii=True)
    print(f"Wrote {len(timeseries_output['records'])} records to backend-data/timeseries_scenes.json")

    # Build the rolling-window composite once; map layers and district analytics share it.
    window_days = int(os.environ.get("MAP_COMPOSITE_DAYS", "45"))
    composite_end = datetime.utcnow().date()
    composite_start = composite_end - timedelta(days=window_days)
    composite_collection = get_landsat8_collection(
        composite_start.isoformat(), composite_end.isoformat(), region
    )
    lst_image = composite_collection.select("LST").median()
    ndvi_image = composite_collection.select("NDVI").median()

    try:
        map_layers_output = build_map_layers_dataset(
            region, lst_image, ndvi_image, composite_start, composite_end
        )
        with open(os.path.join(out_dir, "map_layers.json"), "w", encoding="utf-8") as f:
            json.dump(map_layers_output, f, ensure_ascii=True)
        print("Wrote backend-data/map_layers.json")
    except Exception as exc:
        print(f"Map layer precompute failed, leaving previous map_layers.json in place if any: {exc}")

    try:
        district_features = load_district_features(workspace)
        analytics_output = build_district_analytics_dataset(
            region, district_features, lst_image, ndvi_image, composite_collection
        )
        with open(os.path.join(out_dir, "district_analytics.json"), "w", encoding="utf-8") as f:
            json.dump(analytics_output, f, ensure_ascii=True)
        print(f"Wrote district_analytics.json for {len(analytics_output['districts'])} districts")
    except Exception as exc:
        print(f"District analytics precompute failed, leaving previous district_analytics.json in place if any: {exc}")

    try:
        ward_fc = load_ward_features(workspace)
        ward_output = build_ward_vulnerability_dataset(region, ward_fc, lst_image, ndvi_image)
        with open(os.path.join(out_dir, "ward_vulnerability.json"), "w", encoding="utf-8") as f:
            json.dump(ward_output, f, ensure_ascii=True)
        print(f"Wrote ward_vulnerability.json for {len(ward_output['wards'])} wards")
    except Exception as exc:
        print(f"Ward vulnerability precompute failed, leaving previous ward_vulnerability.json in place if any: {exc}")

    if should_run_weekly_job():
        try:
            historical_output = build_historical_trends_dataset(region)
            with open(os.path.join(out_dir, "historical_trends.json"), "w", encoding="utf-8") as f:
                json.dump(historical_output, f, ensure_ascii=True)
            print(f"Wrote historical_trends.json ({len(historical_output['monthly_land_cover_lst'])} rows)")
        except Exception as exc:
            print(f"Historical trends precompute failed, leaving previous historical_trends.json in place if any: {exc}")
    else:
        print("Skipping historical_trends.json this run (weekly job, seeded copy from previous publish stays in place)")

    try:
        weather_output = build_weather_dataset()
        with open(os.path.join(out_dir, "weather.json"), "w", encoding="utf-8") as f:
            json.dump(weather_output, f, ensure_ascii=True)
        print(f"Wrote weather.json for {len(weather_output['districts'])} districts")
    except Exception as exc:
        print(f"Weather precompute failed, leaving previous weather.json in place if any: {exc}")


if __name__ == "__main__":
    main()
