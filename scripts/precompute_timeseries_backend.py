import json
import os
from datetime import datetime, timedelta

import ee
from google.oauth2 import service_account


def load_delhi_geometry_from_geojson(path: str) -> ee.Geometry:
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    features = payload.get("features", [])
    merged = None
    for feature in features:
        geom = ee.Geometry(feature.get("geometry"))
        merged = geom if merged is None else merged.union(geom)

    if merged is None:
        # Fallback rectangle around Delhi
        return ee.Geometry.Rectangle([76.8388, 28.4044, 77.3465, 28.8833])
    return merged


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
    lst_k = image.select("ST_B10").multiply(0.00341802).add(149.0)
    lst_c = lst_k.subtract(273.15).rename("LST")
    return image.addBands([lst_c]).select(["LST"])


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


def main() -> None:
    init_ee()

    workspace = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    geojson_path = os.path.join(workspace, "delhi_admin.geojson")
    region = load_delhi_geometry_from_geojson(geojson_path)

    days_back = int(os.environ.get("PRECOMPUTE_DAYS", "730"))
    end_dt = datetime.utcnow().date()
    start_dt = end_dt - timedelta(days=days_back)

    collection = get_landsat8_collection(start_dt.isoformat(), end_dt.isoformat(), region)

    # Compute mean LST once per image on the server, then aggregate arrays in bulk.
    def add_scene_mean_lst(image: ee.Image) -> ee.Image:
        mean_lst = image.reduceRegion(
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

    out_dir = os.path.join(workspace, "backend-data")
    os.makedirs(out_dir, exist_ok=True)

    output = {
        "generated_at_utc": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "coverage_start": start_dt.isoformat(),
        "coverage_end": end_dt.isoformat(),
        "source": "LANDSAT/LC08/C02/T1_L2",
        "records": records,
    }

    with open(os.path.join(out_dir, "timeseries_scenes.json"), "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=True)

    print(f"Wrote {len(records)} records to backend-data/timeseries_scenes.json")


if __name__ == "__main__":
    main()
