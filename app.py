from enum import auto
import streamlit as st
import requests
import folium
from streamlit_folium import st_folium
from streamlit_autorefresh import st_autorefresh
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import json
import os

import ee
from google.oauth2 import service_account
from branca.element import MacroElement, Template

st.set_page_config(
    page_title="Delhi Urban Heat Monitor",
    page_icon="🌡️",
    layout="wide",
    initial_sidebar_state="collapsed",
    menu_items={
        'About': "Delhi Urban Heat Monitoring Dashboard - Real-time satellite and weather data analysis"
    }
)
st_autorefresh(interval=300000)

# Add responsive CSS for mobile devices
st.markdown("""
<style>
    /* Responsive typography */
    @media (max-width: 768px) {
        .stApp h1 { font-size: 1.5rem !important; }
        .stApp h2 { font-size: 1.3rem !important; }
        .stApp h3 { font-size: 1.1rem !important; }
        
        /* Make metrics stack nicely on mobile */
        [data-testid="stMetricValue"] { font-size: 1.2rem !important; }
        [data-testid="stMetricLabel"] { font-size: 0.9rem !important; }
        
        /* Adjust padding for mobile */
        .block-container { padding: 1rem 0.5rem !important; }
        
        /* Make dataframes scrollable */
        [data-testid="stDataFrame"] { overflow-x: auto !important; }
        
        /* Improve map display on mobile */
        iframe { max-width: 100% !important; }
        
        /* Better button and input sizing */
        .stButton > button { width: 100% !important; }
        .stDateInput { width: 100% !important; }
    }
    
    /* Tablet view adjustments */
    @media (min-width: 769px) and (max-width: 1024px) {
        .stApp h1 { font-size: 2rem !important; }
        .block-container { padding: 2rem 1rem !important; }
    }
    
    /* Improve chart responsiveness */
    .js-plotly-plot { width: 100% !important; }
    
    /* Better spacing for all screen sizes */
    .stPlotlyChart { margin-bottom: 1rem; }
    .element-container { margin-bottom: 0.5rem; }
    
    /* Improve folium maps responsiveness */
    .folium-map { width: 100% !important; height: auto !important; }
    
    /* Better column gaps on all devices */
    [data-testid="column"] { padding: 0.25rem !important; }
</style>
""", unsafe_allow_html=True)

st.title("Delhi Urban Heat Monitoring Dashboard")

# Add info expander for better mobile experience
with st.expander("ℹ️ About this Dashboard", expanded=False):
    st.markdown("""
    This dashboard combines:
    - **Air Temperature** - Live (OpenWeather) + Historical (NASA POWER) for 11 Delhi districts
    - **Satellite-Derived Land Surface Temperature (LST)** - Landsat 8 L2 data (100m)
    - **Vegetation Index (NDVI)** - Greenery analysis and correlation with temperature
    - **Urban Heat Island Analysis** - Spatial heat distribution patterns
    
    **📱 Mobile Users:** Pinch to zoom on maps, scroll horizontally on tables for best experience.
    
    **🔄 Auto-refresh:** Data updates every 5 minutes automatically.
    """)

API_KEY = st.secrets["OPENWEATHER_API_KEY"]

# Load Earth Engine credentials
service_account_info = {
    "type": "service_account",
    "client_email": st.secrets["GEE_SERVICE_ACCOUNT"],
    "private_key": st.secrets["GEE_PRIVATE_KEY"],
    "token_uri": "https://oauth2.googleapis.com/token",
}

credentials = service_account.Credentials.from_service_account_info(
    service_account_info,
    scopes=["https://www.googleapis.com/auth/earthengine"]
)

ee.Initialize(credentials)

# Create a merged geometry from all NCR districts for accurate clipping
@st.cache_data
def create_delhi_region_geometry():
    """Create merged geometry from all 11 Delhi districts only"""
    try:
        geoboundaries_path = "geoBoundaries-IND-ADM2-all/geoBoundaries-IND-ADM2_simplified.geojson"
        
        if not os.path.exists(geoboundaries_path):
            # Fallback to Delhi rectangle if file not found
            return ee.Geometry.Rectangle([76.84, 27.39, 78.57, 28.88])
        
        with open(geoboundaries_path, 'r', encoding='utf-8') as f:
            districts_data = json.load(f)
        
        # Filter to only Delhi districts (11 districts)
        delhi_districts = [
            'Central Delhi', 'East Delhi', 'New Delhi', 'North Delhi', 'North East Delhi', 
            'North West Delhi', 'Shahdara', 'South Delhi', 'South East Delhi', 'South West Delhi', 'West Delhi'
        ]
        
        # Extract and merge all Delhi district geometries
        merged_geometry = None
        for feature in districts_data.get('features', []):
            district_name = feature.get('properties', {}).get('shapeName', '')
            if district_name in delhi_districts:
                geom = ee.Geometry(feature['geometry'])
                if merged_geometry is None:
                    merged_geometry = geom
                else:
                    merged_geometry = merged_geometry.union(geom)
        
        if merged_geometry is not None:
            return merged_geometry
        else:
            # Fallback to Delhi rectangle if no districts found
            return ee.Geometry.Rectangle([76.84, 27.39, 78.57, 28.88])
    except Exception as e:
        # Fallback to Delhi rectangle if any error occurs
        return ee.Geometry.Rectangle([76.84, 27.39, 78.57, 28.88])

# Define region for Delhi only
region = create_delhi_region_geometry()

# Cache geoBoundaries data for efficient loading
@st.cache_data
def load_geoboundaries():
    """Load and filter geoBoundaries for Delhi-NCR states"""
    try:
        # Use simplified version for better performance
        geoboundaries_path = "geoBoundaries-IND-ADM1-all/geoBoundaries-IND-ADM1_simplified.geojson"
        
        if not os.path.exists(geoboundaries_path):
            return None
        
        with open(geoboundaries_path, 'r', encoding='utf-8') as f:
            geoboundaries_data = json.load(f)
        
        # Filter to only Delhi + NCR states
        ncr_states = ['Delhi', 'Haryana', 'Uttar Pradesh', 'Rajasthan']
        filtered_features = [
            feature for feature in geoboundaries_data.get('features', [])
            if feature.get('properties', {}).get('shapeName', '') in ncr_states
        ]
        
        if filtered_features:
            return {
                'type': 'FeatureCollection',
                'features': filtered_features
            }
        return None
    except Exception as e:
        return None

# Cache district boundaries for efficient loading
@st.cache_data
def load_district_boundaries():
    """Load and filter district boundaries for NCR region"""
    try:
        geoboundaries_path = "geoBoundaries-IND-ADM2-all/geoBoundaries-IND-ADM2_simplified.geojson"
        
        if not os.path.exists(geoboundaries_path):
            return None
        
        with open(geoboundaries_path, 'r', encoding='utf-8') as f:
            districts_data = json.load(f)
        
        # Filter to only NCR districts - Official 35 Districts
        ncr_districts = [
            # Delhi (11 districts)
            'Central Delhi', 'East Delhi', 'New Delhi', 'North Delhi', 'North East Delhi', 
            'North West Delhi', 'Shahdara', 'South Delhi', 'South East Delhi', 'South West Delhi', 'West Delhi',
            # Haryana (14 districts)
            'Faridabad', 'Gurugram', 'Gurgaon', 'Nuh', 'Mewat', 'Rohtak', 'Sonipat', 'Rewari', 
            'Jhajjar', 'Panipat', 'Palwal', 'Bhiwani', 'Charkhi Dadri', 'Mahendragarh', 'Jind', 'Karnal',
            # Uttar Pradesh (8 districts)
            'Meerut', 'Ghaziabad', 'Gautam Budh Nagar', 'Bulandshahr', 'Baghpat', 'Hapur', 'Shamli', 'Muzaffarnagar',
            # Rajasthan (2 districts)
            'Alwar', 'Bharatpur'
        ]
        
        filtered_features = [
            feature for feature in districts_data.get('features', [])
            if feature.get('properties', {}).get('shapeName', '') in ncr_districts
        ]
        
        if filtered_features:
            return {
                'type': 'FeatureCollection',
                'features': filtered_features
            }
        return None
    except Exception as e:
        return None

st.subheader("Landsat 8 Satellite-Derived Land Surface Temperature (LST) - 100m")

# Date selection controls for Landsat 8 layers
st.markdown("### 📅 Select Date Range for Satellite Data")

col1, col2 = st.columns([1, 1], gap="medium")

with col1:
    modis_start_date = st.date_input(
        "Start Date",
        value=datetime(2025, 12, 31).date(),
        min_value=datetime(2013, 4, 11).date(),
        max_value=datetime.now().date(),
        key="modis_start"
    )

with col2:
    modis_end_date = st.date_input(
        "End Date",
        value=datetime(2026, 1, 30).date(),
        min_value=datetime(2013, 4, 11).date(),
        max_value=datetime.now().date(),
        key="modis_end"
    )

# Validate date ranges
if modis_start_date >= modis_end_date:
    st.error("⚠️ Start Date must be before End Date")

# Function to load Delhi districts from GeoJSON file
@st.cache_data
def load_delhi_districts_from_kml():
    """Load Delhi district boundaries from GeoJSON file"""
    try:
        import geopandas as gpd
        
        # Get absolute path (works in both local and cloud deployment)
        current_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Use GeoJSON format for cloud deployment compatibility
        geojson_path = os.path.join(current_dir, "delhi_admin.geojson")
        
        if os.path.exists(geojson_path):
            gdf = gpd.read_file(geojson_path)
        else:
            return None
        
        # Filter for Delhi districts only (should already be all Delhi from this file)
        if 'STATE' in gdf.columns:
            delhi_gdf = gdf[gdf['STATE'].str.contains('DELHI', case=False, na=False)]
        else:
            delhi_gdf = gdf
        
        return delhi_gdf
    except Exception as e:
        st.error(f"❌ Error loading district boundaries: {str(e)}")
        return None

# Function to create merged district geometry from KML for Earth Engine
def get_districts_ee_geometry():
    """Get merged EE geometry for Delhi from KML file"""
    try:
        delhi_gdf = load_delhi_districts_from_kml()
        
        if delhi_gdf is None or delhi_gdf.empty:
            # Fallback to bounding box if KML loading fails
            return ee.Geometry.Rectangle([76.8388, 28.4044, 77.3465, 28.8833])
        
        # Merge all district geometries and fix any invalid geometries
        merged_geom = delhi_gdf.union_all()
        
        # Validate and fix geometry if needed
        if not merged_geom.is_valid:
            from shapely.validation import make_valid
            merged_geom = make_valid(merged_geom)
        
        # Simplify the geometry to reduce complexity
        merged_geom = merged_geom.simplify(0.001, preserve_topology=True)
        
        # Convert to Earth Engine geometry based on type
        if merged_geom.geom_type == 'Polygon':
            # Extract coordinates as list of [lon, lat] pairs (ignore z if present)
            coords = [[coord[0], coord[1]] for coord in merged_geom.exterior.coords]
            ee_geom = ee.Geometry.Polygon([coords])
        elif merged_geom.geom_type == 'MultiPolygon':
            # Extract coordinates for each polygon
            polygons = []
            for poly in merged_geom.geoms:
                coords = [[coord[0], coord[1]] for coord in poly.exterior.coords]
                polygons.append([coords])  # Each polygon needs to be wrapped in a list
            ee_geom = ee.Geometry.MultiPolygon(polygons)
        else:
            return ee.Geometry.Rectangle([76.8388, 28.4044, 77.3465, 28.8833])
        
        return ee_geom
    except Exception:
        # Fallback to bounding box
        return ee.Geometry.Rectangle([76.8388, 28.4044, 77.3465, 28.8833])

# Get district geometry for clipping
districts_geometry = get_districts_ee_geometry()

# Create a plain Folium map
m = folium.Map(location=[28.6139, 77.2090], zoom_start=10)

# Function to add Earth Engine layer to Folium
def add_ee_layer(self, ee_image_object, vis_params, name, opacity=1.0):
    try:
        map_id_dict = ee.Image(ee_image_object).getMapId(vis_params)
        folium.raster_layers.TileLayer(
            tiles=map_id_dict['tile_fetcher'].url_format,
            attr='Google Earth Engine',
            name=name,
            overlay=True,
            control=True,
            opacity=opacity,
        ).add_to(self)
    except Exception:
        # Keep map rendering even if one Earth Engine layer fails.
        pass

folium.Map.add_ee_layer = add_ee_layer

# Landsat 8 L2 helpers (cloud masking + scaling)
def mask_landsat_l2(image):
    # QA_PIXEL bit positions per the official Landsat 8-9 Collection 2 Level-2
    # Science Product Guide (LSDS-1619): bit 2 = Cirrus, bit 3 = Cloud,
    # bit 4 = Cloud Shadow, bit 5 = Snow. (Water is bit 7, not used here.)
    qa = image.select("QA_PIXEL")
    cirrus_bit = 1 << 2
    cloud_bit = 1 << 3
    cloud_shadow_bit = 1 << 4
    snow_bit = 1 << 5
    mask = (
        qa.bitwiseAnd(cloud_shadow_bit).eq(0)
        .And(qa.bitwiseAnd(snow_bit).eq(0))
        .And(qa.bitwiseAnd(cloud_bit).eq(0))
        .And(qa.bitwiseAnd(cirrus_bit).eq(0))
    )
    return image.updateMask(mask)


def prep_landsat8_l2(image):
    # LST (Kelvin) -> Celsius
    lst_k = image.select("ST_B10").multiply(0.00341802).add(149.0)
    lst_c = lst_k.subtract(273.15).rename("LST")

    # Surface reflectance scaling for NDVI
    red = image.select("SR_B4").multiply(0.0000275).add(-0.2)
    nir = image.select("SR_B5").multiply(0.0000275).add(-0.2)
    ndvi = nir.subtract(red).divide(nir.add(red)).rename("NDVI")

    return image.addBands([lst_c, ndvi]).select(["LST", "NDVI"])


def get_landsat8_collection(start_date, end_date, geom):
    return (
        ee.ImageCollection("LANDSAT/LC08/C02/T1_L2")
        .filterDate(start_date, end_date)
        .filterBounds(geom)
        .filter(ee.Filter.lt("CLOUD_COVER", 60))
        .map(mask_landsat_l2)
        .map(prep_landsat8_l2)
    )


def get_landsat8_scene_collection_near_date(target_date, geom, window_days=8):
    start_date = (target_date - timedelta(days=window_days)).isoformat()
    end_date = (target_date + timedelta(days=window_days)).isoformat()
    return get_landsat8_collection(start_date, end_date, geom)


# Prepare Landsat 8 collection once for LST and NDVI
landsat_collection = get_landsat8_collection(
    modis_start_date.isoformat(),
    modis_end_date.isoformat(),
    districts_geometry if districts_geometry else region
)


@st.cache_data(ttl=3600)
def get_available_landsat_scenes(_collection):
    try:
        time_starts = _collection.aggregate_array("system:time_start").getInfo()
        cloud_covers = _collection.aggregate_array("CLOUD_COVER").getInfo()
        product_ids = _collection.aggregate_array("LANDSAT_PRODUCT_ID").getInfo()
        system_indexes = _collection.aggregate_array("system:index").getInfo()
    except Exception:
        return []
    if not time_starts:
        return []

    scenes = []
    for ms, cloud_value_raw, product_id, system_index in zip(time_starts, cloud_covers, product_ids, system_indexes):
        if ms is None:
            continue
        scene_dt = datetime.utcfromtimestamp(ms / 1000)
        scene_date = scene_dt.date()
        scene_time = scene_dt.strftime("%H:%M UTC")
        cloud_value = float(cloud_value_raw) if cloud_value_raw is not None else None
        scene_id = str(product_id or system_index or "Unknown Scene")
        if cloud_value is None:
            label = f"{scene_date.isoformat()} {scene_time} | Cloud: N/A | {scene_id}"
        else:
            label = f"{scene_date.isoformat()} {scene_time} | Cloud: {cloud_value:.1f}% | {scene_id}"
        scenes.append({
            "date": scene_date,
            "datetime": scene_dt,
            "time_start_ms": int(ms),
            "cloud_cover": cloud_value,
            "scene_id": scene_id,
            "label": label,
        })
    scenes.sort(key=lambda x: x["datetime"])
    return scenes

# Map display mode: median composite vs explicit scene selection
map_mode = st.radio(
    "Map display mode",
    ["Median composite (range)", "Scene selection (single scene)"],
    index=1,
    horizontal=True
)

map_lst = None
map_ndvi = None
map_scene_label = None

if map_mode == "Scene selection (single scene)":
    available_scenes = get_available_landsat_scenes(landsat_collection)
    if available_scenes:
        st.caption("Scene source: Landsat 8 Collection 2 Level-2 (LANDSAT/LC08/C02/T1_L2)")

        scene_labels = [scene["label"] for scene in available_scenes]
        selected_label = st.selectbox(
            "Select scene",
            options=scene_labels,
            index=len(scene_labels) - 1,
        )

        selected_scene = next(scene for scene in available_scenes if scene["label"] == selected_label)
        selected_cloud_text = "N/A" if selected_scene["cloud_cover"] is None else f"{selected_scene['cloud_cover']:.1f}%"
        st.caption(
            f"Selected scene: {selected_scene['scene_id']} | "
            f"{selected_scene['datetime'].strftime('%Y-%m-%d %H:%M UTC')} | "
            f"Cloud cover: {selected_cloud_text}"
        )
        map_date = selected_scene["date"]
        # Primary match by system time: most reliable after cloud-mask and band-map transforms.
        scene_collection = landsat_collection.filter(
            ee.Filter.eq("system:time_start", selected_scene["time_start_ms"])
        )
        if scene_collection.size().getInfo() == 0:
            scene_collection = landsat_collection.filter(
                ee.Filter.eq("LANDSAT_PRODUCT_ID", selected_scene["scene_id"])
            )
        if scene_collection.size().getInfo() == 0:
            scene_collection = landsat_collection.filter(
                ee.Filter.eq("system:index", selected_scene["scene_id"])
            )
    else:
        st.warning("No Landsat 8 scenes available in the selected date range.")
        map_date = modis_end_date
        scene_collection = get_landsat8_scene_collection_near_date(
            map_date,
            districts_geometry if districts_geometry else region
        )
    try:
        scene_count = scene_collection.size().getInfo()
    except Exception:
        scene_count = 0

    if scene_count == 0:
        st.warning("Selected scene could not be loaded. Using range median instead.")
        map_lst = landsat_collection.select("LST").median()
        map_ndvi = landsat_collection.select("NDVI").median()
        map_scene_label = "Median composite"
    else:
        scene = scene_collection.sort("CLOUD_COVER").first()
        map_lst = ee.Image(scene).select("LST")
        map_ndvi = ee.Image(scene).select("NDVI")
        try:
            scene_date = ee.Date(ee.Image(scene).get("system:time_start")).format("YYYY-MM-dd").getInfo()
            map_scene_label = f"Selected scene: {scene_date}"
        except Exception:
            map_scene_label = "Selected scene"
else:
    map_lst = landsat_collection.select("LST").median()
    map_ndvi = landsat_collection.select("NDVI").median()
    map_scene_label = "Median composite"

lst_layer_name = None
ndvi_layer_name = None
land_cover_layer_name = None
land_cover_source_note = None
viz_min = 10
viz_max = 40

# Add Landsat 8 LST layer with enhanced styling
try:
    # LST map layer (composite or selected scene)
    lst_celsius = map_lst
    
    # Calculate dynamic min/max values from the actual data for better visualization
    if districts_geometry:
        lst_clipped = lst_celsius.clip(districts_geometry)
        display_layer = lst_clipped
    else:
        display_layer = lst_celsius
    
    # Get statistics from the actual data
    try:
        stats = display_layer.reduceRegion(
            reducer=ee.Reducer.minMax(),
            geometry=districts_geometry if districts_geometry else region,
            scale=100,
            maxPixels=1e9
        ).getInfo()
        
        # Extract min/max values with fallback
        data_min = stats.get('LST_min', 10)
        data_max = stats.get('LST_max', 40)
        
        # Add some buffer to the range for better color distribution
        buffer = (data_max - data_min) * 0.1
        viz_min = max(data_min - buffer, -5)
        viz_max = min(data_max + buffer, 55)
        
    except:
        # Fallback to seasonal defaults if calculation fails
        viz_min = 10
        viz_max = 40
    
    # Set visualization parameters with dynamic range
    vis_params = {
        "min": viz_min,
        "max": viz_max,
        "palette": [
            "#0000ff",  # Deep Blue - Coldest
            "#00ccff",  # Cyan - Very Cool
            "#00ff00",  # Green - Cool
            "#ffff00",  # Yellow - Warm
            "#ff8800",  # Orange - Hot
            "#ff0000",  # Red - Very Hot
            "#8b0000",  # Dark Red - Hottest
        ],
    }
    
    # Add the layer to the map
    lst_layer_name = f"🌡️ Land Surface Temperature (°C) - Landsat 8 ({map_scene_label})"
    m.add_ee_layer(display_layer, vis_params, lst_layer_name, opacity=0.6)
    
except Exception as lst_error:
    st.error(f"Error loading LST layer: {str(lst_error)}")

# Add NDVI layer for greenery visualization with enhanced colors
try:
    ndvi = map_ndvi
    
    # NDVI false color visualization parameters
    ndvi_vis_params = {
        "min": -0.3,
        "max": 1,
        "palette": [
            "#8B0000",  # Dark Red - No Vegetation/Water
            "#DC143C",  # Crimson - Very Low Vegetation
            "#FF4500",  # Orange-Red - Low Vegetation
            "#FFD700",  # Gold - Sparse Vegetation
            "#FFFF00",  # Yellow - Moderate Vegetation
            "#7FFF00",  # Chartreuse - Good Vegetation
            "#00FF00",  # Lime Green - Dense Vegetation
            "#006400",  # Dark Forest Green - Very Dense Vegetation
        ],
    }
    
    # Clip to district boundaries if available
    if districts_geometry:
        ndvi_clipped = ndvi.clip(districts_geometry)
        ndvi_layer_name = f"🌿 Vegetation Index - NDVI (Landsat 8, {map_scene_label})"
        m.add_ee_layer(ndvi_clipped, ndvi_vis_params, ndvi_layer_name, opacity=0.45)
    else:
        ndvi_layer_name = f"🌿 Vegetation Index - NDVI (Landsat 8, {map_scene_label})"
        m.add_ee_layer(ndvi, ndvi_vis_params, ndvi_layer_name, opacity=0.45)
except Exception as ndvi_error:
    try:
        # Fallback to Sentinel-2 with very lenient filtering
        sentinel_collection = (
            ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
            .filterDate(modis_start_date.isoformat(), modis_end_date.isoformat())
            .filterBounds(districts_geometry if districts_geometry else region)
            .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 50))  # Very lenient
            .sort('CLOUDY_PIXEL_PERCENTAGE')
            .first()
        )
        
        ndvi_sent = sentinel_collection.normalizedDifference(['B8', 'B4'])
        
        ndvi_vis_params = {
            "min": -0.3,
            "max": 1,
            "palette": [
                "#8B4513", "#CD853F", "#FFD700", "#ADFF2F",
                "#32CD32", "#00AA00", "#006400",
            ],
        }
        
        # Clip to district boundaries if available
        if districts_geometry:
            ndvi_sent_clipped = ndvi_sent.clip(districts_geometry)
            ndvi_layer_name = "🌿 Vegetation Index - NDVI"
            m.add_ee_layer(ndvi_sent_clipped, ndvi_vis_params, ndvi_layer_name, opacity=0.45)
        else:
            ndvi_layer_name = "🌿 Vegetation Index - NDVI"
            m.add_ee_layer(ndvi_sent, ndvi_vis_params, ndvi_layer_name, opacity=0.45)
    except Exception as fallback_e:
        st.warning(f"Vegetation layer temporarily unavailable")

# Add Land Use / Land Cover layers (stats shown after the map)
land_use_stats = None
land_use_histogram = None
land_use_total_pixels = None
land_use_layer_note = None

try:
    # Option 1: ESA WorldCover (10m resolution - High detail)
    worldcover = ee.ImageCollection("ESA/WorldCover/v200").first()
    
    # ESA WorldCover classification:
    # 10: Tree cover, 20: Shrubland, 30: Grassland, 40: Cropland, 
    # 50: Built-up, 60: Bare/sparse vegetation, 70: Snow and ice, 
    # 80: Permanent water bodies, 90: Herbaceous wetland, 95: Mangroves, 100: Moss and lichen
    
    worldcover_vis = {
        'min': 10,
        'max': 100,
        'palette': [
            '#006400',  # 10 - Tree cover (dark green)
            '#FFBB22',  # 20 - Shrubland (orange-yellow)
            '#FFFF4C',  # 30 - Grassland (light yellow)
            '#F096FF',  # 40 - Cropland (pink-purple)
            '#FA0000',  # 50 - Built-up (red) - URBAN AREAS
            '#B4B4B4',  # 60 - Bare/sparse vegetation (gray)
            '#F0F0F0',  # 70 - Snow and ice (white)
            '#0064C8',  # 80 - Permanent water (blue)
            '#0096A0',  # 90 - Herbaceous wetland (cyan)
            '#00CF75',  # 95 - Mangroves (sea green)
            '#FAE6A0',  # 100 - Moss and lichen (beige)
        ]
    }
    
    if districts_geometry:
        worldcover_clipped = worldcover.clip(districts_geometry)
        land_cover_layer_name = "🌍 Land Cover (ESA 10m)"
        m.add_ee_layer(worldcover_clipped, worldcover_vis, land_cover_layer_name, opacity=0.5)
        stats_image = worldcover_clipped
    else:
        land_cover_layer_name = "🌍 Land Cover (ESA 10m)"
        m.add_ee_layer(worldcover, worldcover_vis, land_cover_layer_name, opacity=0.5)
        stats_image = worldcover
    land_cover_source_note = "ESA WorldCover 2021 (10m)"
    
    try:
        land_use_stats = stats_image.reduceRegion(
            reducer=ee.Reducer.frequencyHistogram(),
            geometry=districts_geometry if districts_geometry else region,
            scale=100,
            maxPixels=1e9
        ).getInfo()
        
        if land_use_stats and 'Map' in land_use_stats:
            land_use_histogram = land_use_stats['Map']
            land_use_total_pixels = sum(land_use_histogram.values())
    except Exception:
        land_use_layer_note = "Land use statistics calculation in progress..."

    land_use_layer_note = "✅ High-resolution land cover layer (10m) added to map"
    
except Exception:
    land_use_layer_note = "ESA WorldCover not available, trying MODIS Land Cover..."
    
    try:
        # Fallback: MODIS Land Cover (500m resolution)
        modis_lc = ee.ImageCollection("MODIS/061/MCD12Q1").first().select('LC_Type1')
        
        # MODIS IGBP classification colors
        modis_lc_vis = {
            'min': 1,
            'max': 17,
            'palette': [
                '05450a', '086a10', '54a708', '78d203', '009900', 'c6b044',
                'dcd159', 'dade48', 'fbff13', 'b6ff05', '27ff87', 'c24f44',
                'a5a5a5', 'ff6d4c', '69fff8', 'f9ffa4', '1c0dff'
            ]
        }
        
        if districts_geometry:
            modis_lc_clipped = modis_lc.clip(districts_geometry)
            land_cover_layer_name = "🌍 Land Cover (MODIS 500m)"
            m.add_ee_layer(modis_lc_clipped, modis_lc_vis, land_cover_layer_name, opacity=0.5)
        else:
            land_cover_layer_name = "🌍 Land Cover (MODIS 500m)"
            m.add_ee_layer(modis_lc, modis_lc_vis, land_cover_layer_name, opacity=0.5)
        land_cover_source_note = "MODIS MCD12Q1 (500m) - IGBP LC_Type1 classes"
        
        land_use_layer_note = "ℹ️ Using MODIS Land Cover (500m resolution)"
        
    except Exception:
        land_use_layer_note = "Land cover layers temporarily unavailable"


# Locations for weather monitoring - All 11 Delhi districts
locations = [
    ("Central", 28.6422, 77.2183),
    ("East", 28.6261, 77.3006),
    ("New Delhi", 28.6107, 77.2193),
    ("North", 28.7043, 77.2074),
    ("North East", 28.7234, 77.2701),
    ("North West", 28.7717, 77.0986),
    ("Shahadra", 28.7100, 77.3150),
    ("South", 28.5032, 77.2332),
    ("South East", 28.5550, 77.2850),
    ("South West", 28.5732, 77.0396),
    ("West", 28.6564, 77.0709),
]

# Function to get live weather
def get_weather(lat, lon):
    url = f"http://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={API_KEY}&units=metric"
    data = requests.get(url).json()
    return {
        "temperature": data["main"]["temp"],
        "humidity": data["main"]["humidity"],
        "feels_like": data["main"]["feels_like"]
    }


@st.cache_data(ttl=86400)
def get_power_air_temp(lat, lon, start_date, end_date):
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


def get_lst_at_point(lst_image, lon, lat):
    try:
        point = ee.Geometry.Point([lon, lat])
        sample = lst_image.sample(point, 100).first()
        if sample is None:
            return None
        return ee.Number(sample.get("LST")).getInfo()
    except Exception:
        return None

# Function for heat alerts
def heat_alert(temp):
    if temp >= 40:
        return "🔥 Extreme Heat Alert! Stay Hydrated and Avoid Outdoor Activities."
    elif temp >= 35:
        return "⚠️ High Heat Warning! Take Precautions."
    else:
        return "🌤️ Normal Temperature."

# Add weather markers to map with enhanced styling
weather_markers_group = folium.FeatureGroup(name="🌤️ Live Weather Markers", show=True)

for name, lat, lon in locations:
    w = get_weather(lat, lon)
    alert = heat_alert(w["temperature"])
    
    # Determine icon color and size based on temperature
    if w["temperature"] >= 40:
        icon_color = "darkred"
        icon_prefix = "fa"
        icon_name = "fire"
    elif w["temperature"] >= 35:
        icon_color = "red"
        icon_prefix = "fa"
        icon_name = "thermometer-three-quarters"
    elif w["temperature"] >= 30:
        icon_color = "orange"
        icon_prefix = "fa"
        icon_name = "sun"
    elif w["temperature"] >= 25:
        icon_color = "green"
        icon_prefix = "fa"
        icon_name = "cloud-sun"
    else:
        icon_color = "blue"
        icon_prefix = "fa"
        icon_name = "cloud"
    
    popup_html = f"""
    <div style="font-family: Arial; width: 250px; padding: 10px; border-radius: 8px; background-color: #f0f0f0;">
        <h4 style="margin: 0 0 10px 0; color: #333;">{name}</h4>
        <div style="background-color: white; padding: 10px; border-radius: 5px; border-left: 4px solid {icon_color};">
            <p style="margin: 5px 0;"><b>🌡️ Temperature:</b> {w['temperature']:.1f}°C</p>
            <p style="margin: 5px 0;"><b>🤔 Feels Like:</b> {w['feels_like']:.1f}°C</p>
            <p style="margin: 5px 0;"><b>💧 Humidity:</b> {w['humidity']:.0f}%</p>
            <p style="margin: 10px 0 0 0; padding-top: 8px; border-top: 1px solid #ddd;"><b>Status:</b> {alert}</p>
        </div>
    </div>
    """
    
    folium.Marker(
        location=[lat, lon],
        popup=folium.Popup(popup_html, max_width=300),
        tooltip=f"{name}: {w['temperature']:.1f}°C",
        icon=folium.Icon(
            color=icon_color,
            icon=icon_name,
            prefix=icon_prefix,
            icon_color='white'
        ),
    ).add_to(weather_markers_group)

weather_markers_group.add_to(m)

# Add district boundaries from KML to map
try:
    delhi_gdf = load_delhi_districts_from_kml()
    
    if delhi_gdf is not None and not delhi_gdf.empty:
        # Create a feature group for district boundaries
        district_group = folium.FeatureGroup(name="🏘️ District Boundaries", show=True)
        
        # Add each district boundary
        for idx, row in delhi_gdf.iterrows():
            # Get district name from the District field or Name field
            district_name = row.get('District', row.get('Name', 'Unknown'))
            if isinstance(district_name, str):
                district_name = district_name.title()
            
            # Add district boundary as GeoJSON
            folium.GeoJson(
                row.geometry,
                name=district_name,
                style_function=lambda x: {
                    'fillColor': 'transparent',
                    'color': '#0066cc',
                    'weight': 2,
                    'fillOpacity': 0
                },
                tooltip=district_name
            ).add_to(district_group)
        
        district_group.add_to(m)
    else:
        st.warning("Could not load district boundaries from KML file")
except Exception as e:
    st.warning(f"Could not load district boundaries: {str(e)}")
    pass

# Add dynamic legends for raster layers (visible only when corresponding layer is selected)
legend_layer_map = {}
if lst_layer_name:
    legend_layer_map[lst_layer_name] = "legend-lst"
if ndvi_layer_name:
    legend_layer_map[ndvi_layer_name] = "legend-ndvi"
if land_cover_layer_name:
    legend_layer_map[land_cover_layer_name] = "legend-landcover"

land_cover_footer = land_cover_source_note if land_cover_source_note else "Land cover source"

if land_cover_layer_name == "🌍 Land Cover (MODIS 500m)":
    land_cover_classes = [
        ("1", "#05450a", "Evergreen Needleleaf Forest"),
        ("2", "#086a10", "Evergreen Broadleaf Forest"),
        ("3", "#54a708", "Deciduous Needleleaf Forest"),
        ("4", "#78d203", "Deciduous Broadleaf Forest"),
        ("5", "#009900", "Mixed Forest"),
        ("6", "#c6b044", "Closed Shrublands"),
        ("7", "#dcd159", "Open Shrublands"),
        ("8", "#dade48", "Woody Savannas"),
        ("9", "#fbff13", "Savannas"),
        ("10", "#b6ff05", "Grasslands"),
        ("11", "#27ff87", "Permanent Wetlands"),
        ("12", "#c24f44", "Croplands"),
        ("13", "#a5a5a5", "Urban/Built-up"),
        ("14", "#ff6d4c", "Cropland/Natural Mosaic"),
        ("15", "#69fff8", "Snow/Ice"),
        ("16", "#f9ffa4", "Barren/Sparsely Vegetated"),
        ("17", "#1c0dff", "Water Bodies"),
    ]
else:
    land_cover_classes = [
        ("10", "#006400", "Tree Cover"),
        ("20", "#FFBB22", "Shrubland"),
        ("30", "#FFFF4C", "Grassland"),
        ("40", "#F096FF", "Cropland"),
        ("50", "#FA0000", "Built-up (Urban)"),
        ("60", "#B4B4B4", "Bare/Sparse Veg"),
        ("70", "#F0F0F0", "Snow/Ice"),
        ("80", "#0064C8", "Water Bodies"),
        ("90", "#0096A0", "Wetland"),
        ("95", "#00CF75", "Mangroves"),
        ("100", "#FAE6A0", "Moss/Lichen"),
    ]

# Filter legend to only classes that are present in the current land-cover histogram.
present_class_ids = set(str(k) for k in land_use_histogram.keys()) if isinstance(land_use_histogram, dict) else set()
if present_class_ids:
    filtered_land_cover_classes = [c for c in land_cover_classes if c[0] in present_class_ids]
    if filtered_land_cover_classes:
        land_cover_classes = filtered_land_cover_classes
        land_cover_footer = f"{land_cover_footer} | Showing {len(land_cover_classes)} present classes"

land_cover_items_html = "".join(
    f'<div class="legend-item"><span class="legend-swatch" style="background-color: {color};"></span><span>{label}</span></div>'
    for _, color, label in land_cover_classes
)

dynamic_legends_html = f"""
<style>
    .dynamic-legend {{
        position: fixed !important;
        right: 10px !important;
        width: 250px !important;
        background-color: #ffffff !important;
        border: 2px solid #808080 !important;
        border-radius: 6px !important;
        z-index: 10000 !important;
        font-size: 12px !important;
        padding: 10px !important;
        color: #111111 !important;
        box-shadow: 2px 2px 6px rgba(0, 0, 0, 0.3) !important;
        bottom: 50px !important;
    }}
    @media (max-width: 768px) {{
        .dynamic-legend {{
            width: min(250px, calc(100vw - 20px)) !important;
            right: 8px !important;
        }}
    }}
    .dynamic-legend-title {{
        text-align: center !important;
        font-weight: bold !important;
        font-size: 13px !important;
        margin-bottom: 8px !important;
        border-bottom: 1px solid #cccccc !important;
        padding-bottom: 5px !important;
        color: inherit !important;
    }}
    .legend-gradient {{
        width: 100% !important;
        height: 14px !important;
        border: 1px solid #333333 !important;
        border-radius: 3px !important;
        margin: 6px 0 4px 0 !important;
    }}
    .legend-scale {{
        display: flex !important;
        justify-content: space-between !important;
        font-size: 10px !important;
        color: #555555 !important;
    }}
    .legend-items {{
        max-height: 180px !important;
        overflow-y: auto !important;
    }}
    .legend-item {{
        margin: 3px 0 !important;
        display: flex !important;
        align-items: center !important;
        color: inherit !important;
    }}
    .legend-swatch {{
        width: 18px !important;
        height: 13px !important;
        display: inline-block !important;
        margin-right: 8px !important;
        border: 1px solid #000000 !important;
    }}
    .legend-footer {{
        margin-top: 8px !important;
        padding-top: 5px !important;
        border-top: 1px solid #cccccc !important;
        font-size: 10px !important;
        color: #666666 !important;
        text-align: center !important;
    }}
    @media (prefers-color-scheme: dark) {{
        .dynamic-legend {{
            background-color: rgba(18, 18, 18, 0.95) !important;
            border-color: #b0b0b0 !important;
            color: #f2f2f2 !important;
        }}
        .legend-scale,
        .legend-footer {{
            color: #d0d0d0 !important;
        }}
        .dynamic-legend-title,
        .legend-footer {{
            border-color: #555555 !important;
        }}
    }}
</style>

<div id="legend-lst" class="dynamic-legend" style="display: block; bottom: 50px !important;">
    <div class="dynamic-legend-title">🌡️ LST Legend (deg C)</div>
    <div class="legend-gradient" style="background: linear-gradient(to right, #0000ff, #00ccff, #00ff00, #ffff00, #ff8800, #ff0000, #8b0000) !important;"></div>
    <div class="legend-scale">
        <span>{viz_min:.1f} deg C</span>
        <span>{viz_max:.1f} deg C</span>
    </div>
</div>

<div id="legend-ndvi" class="dynamic-legend" style="display: block; bottom: 140px !important;">
    <div class="dynamic-legend-title">🌿 NDVI Legend</div>
    <div class="legend-gradient" style="background: linear-gradient(to right, #8B0000, #DC143C, #FF4500, #FFD700, #FFFF00, #7FFF00, #00FF00, #006400) !important;"></div>
    <div class="legend-scale">
        <span>-0.3</span>
        <span>1.0</span>
    </div>
</div>

<div id="legend-landcover" class="dynamic-legend" style="display: block; bottom: 230px !important;">
    <div class="dynamic-legend-title">🌍 Land Cover Legend</div>
    <div class="legend-items">
        {land_cover_items_html}
    </div>
    <div class="legend-footer">{land_cover_footer}</div>
</div>
"""

m.get_root().html.add_child(folium.Element(dynamic_legends_html))

# Attach legend behavior directly to the Folium map context.
legend_script = f"""
{{% macro script(this, kwargs) %}}
var map = {{{{this._parent.get_name()}}}};
var legendLayerMap = {json.dumps(legend_layer_map)};
var legendOrder = ["legend-landcover", "legend-ndvi", "legend-lst"];

function layoutVisibleLegends() {{
    var bottomOffset = 50;
    var gap = 10;
    legendOrder.forEach(function(legendId) {{
        var legend = document.getElementById(legendId);
        if (!legend) return;
        if (legend.style.display === "block") {{
            legend.style.bottom = bottomOffset + "px";
            bottomOffset += legend.offsetHeight + gap;
        }}
    }});
}}

function toggleLegend(legendId, isVisible) {{
    var legend = document.getElementById(legendId);
    if (!legend) return;
    legend.style.display = isVisible ? "block" : "none";
    layoutVisibleLegends();
}}

function syncLegendsWithMapState() {{
    var visibleByLegendId = {{}};

    // Start with all legend panels hidden.
    Object.keys(legendLayerMap).forEach(function(layerName) {{
        visibleByLegendId[legendLayerMap[layerName]] = false;
    }});

    // Preferred method: read checked overlays from LayerControl DOM.
    var overlayLabels = document.querySelectorAll('.leaflet-control-layers-overlays label');
    if (overlayLabels && overlayLabels.length > 0) {{
        overlayLabels.forEach(function(labelEl) {{
            var input = labelEl.querySelector('input[type="checkbox"]');
            if (!input || !input.checked) return;
            var labelText = (labelEl.textContent || '').trim();
            var legendId = legendLayerMap[labelText];
            if (legendId) visibleByLegendId[legendId] = true;
        }});
    }} else {{
        // Fallback: inspect active map layers.
        Object.keys(map._layers).forEach(function(layerKey) {{
            var layer = map._layers[layerKey];
            if (!layer || !layer.options || !layer.options.name) return;
            var legendId = legendLayerMap[layer.options.name];
            if (!legendId) return;
            if (map.hasLayer(layer)) visibleByLegendId[legendId] = true;
        }});
    }}

    Object.keys(visibleByLegendId).forEach(function(legendId) {{
        toggleLegend(legendId, visibleByLegendId[legendId]);
    }});
}}

window.addEventListener("resize", layoutVisibleLegends);
syncLegendsWithMapState();

// Keep legend state in sync even if overlay events are not propagated by the host iframe.
setInterval(syncLegendsWithMapState, 400);
{{% endmacro %}}
"""

legend_macro = MacroElement()
legend_macro._template = Template(legend_script)
m.get_root().add_child(legend_macro)

# Add layer control to the map
folium.LayerControl(position='topright', collapsed=False).add_to(m)

# Render map in Streamlit - Responsive width
st_folium(m, width=None, height=600, returned_objects=[])

# Land Use / Land Cover Analysis (after map)
st.subheader("🏙️ Land Use / Land Cover Analysis")

if land_use_layer_note:
    pass

if land_use_histogram and land_use_total_pixels:
    land_class_names = {
        '10': 'Tree Cover', '20': 'Shrubland', '30': 'Grassland',
        '40': 'Cropland', '50': 'Built-up (Urban)', '60': 'Bare/Sparse Vegetation',
        '70': 'Snow/Ice', '80': 'Water Bodies', '90': 'Wetland',
        '95': 'Mangroves', '100': 'Moss/Lichen'
    }
    
    st.markdown("### 📊 Land Use Distribution")
    
    # Create columns for land use stats
    col1, col2, col3, col4 = st.columns(4, gap="small")
    
    # Calculate percentages
    land_use_pct = {
        land_class_names.get(k, k): (v / land_use_total_pixels) * 100
        for k, v in land_use_histogram.items()
    }
    
    # Sort by percentage
    sorted_land_use = sorted(land_use_pct.items(), key=lambda x: x[1], reverse=True)
    
    # Display top land uses in metrics
    for idx, (land_type, percentage) in enumerate(sorted_land_use[:4]):
        with [col1, col2, col3, col4][idx]:
            st.metric(land_type, f"{percentage:.1f}%")
    
    # Show all land uses in a table
    if len(sorted_land_use) > 4:
        df_land_use = pd.DataFrame(sorted_land_use, columns=['Land Use Type', 'Coverage (%)'])
        df_land_use['Coverage (%)'] = df_land_use['Coverage (%)'].round(2)
        st.dataframe(df_land_use, width='stretch', hide_index=True)

# Time Series Analysis of Landsat 8 LST
st.subheader("Time Series Analysis - Historical Landsat 8 Land Surface Temperature")

# Date range selector
col1, col2 = st.columns([1, 1], gap="medium")
with col1:
    start_date = st.date_input("Start Date", datetime.now() - timedelta(days=60))
with col2:
    end_date = st.date_input("End Date", datetime.now())

if "ts_last_range" not in st.session_state:
    st.session_state.ts_last_range = (start_date, end_date)
if "ts_ready" not in st.session_state:
    st.session_state.ts_ready = False

current_ts_range = (start_date, end_date)
if current_ts_range != st.session_state.ts_last_range:
    st.session_state.ts_ready = False
    st.session_state.ts_last_range = current_ts_range

if st.button("Run Time Series Analysis", key="run_ts_analysis", type="primary"):
    st.session_state.ts_ready = True

include_lulc_split = st.checkbox(
    "Include land-cover split in time series (slower)",
    value=False,
    help="When enabled, LST-by-land-cover lines are computed for every scene."
)


@st.cache_data(ttl=900)
def load_precomputed_timeseries_dataset():
    base_url = st.secrets.get("PRECOMPUTED_DATA_BASE_URL", "")
    if not base_url:
        return None
    try:
        base_url = str(base_url).rstrip("/")
        response = requests.get(f"{base_url}/timeseries_scenes.json", timeout=20)
        if response.status_code != 200:
            return None
        payload = response.json()
        records = payload.get("records", []) if isinstance(payload, dict) else []
        if not records:
            return None
        return payload
    except Exception:
        return None


@st.cache_data(ttl=900)
def get_time_series_scene_inventory(start_iso: str, end_iso: str):
    scene_collection = get_landsat8_collection(start_iso, end_iso, region)
    scenes = get_available_landsat_scenes(scene_collection)
    rows = [
        {
            "Date": s["date"].isoformat(),
            "Time (UTC)": s["datetime"].strftime("%H:%M"),
            "Cloud Cover (%)": "N/A" if s["cloud_cover"] is None else round(s["cloud_cover"], 1),
            "Scene ID": s["scene_id"],
        }
        for s in scenes
    ]
    return {"rows": rows, "count": len(rows)}


@st.cache_data(ttl=1800)
def compute_lst_time_series(start_iso: str, end_iso: str, include_lulc_split: bool):
    lst_scene_collection = get_landsat8_collection(start_iso, end_iso, region).select("LST")
    scene_count_estimate = lst_scene_collection.size().getInfo()

    # Full-fidelity time series: use every available scene in range.
    ts_collection = lst_scene_collection.sort('system:time_start')

    worldcover_ts = ee.ImageCollection("ESA/WorldCover/v200").first().select("Map").rename("LandCover")
    land_cover_name_map = {
        "10": "Tree Cover", "20": "Shrubland", "30": "Grassland", "40": "Cropland",
        "50": "Built-up (Urban)", "60": "Bare/Sparse Vegetation", "70": "Snow/Ice",
        "80": "Water Bodies", "90": "Wetland", "95": "Mangroves", "100": "Moss/Lichen",
    }

    ts_count = ts_collection.size().getInfo()
    if ts_count == 0:
        return {"df_ts": [], "df_lulc_ts": [], "total_scene_count": scene_count_estimate, "processed_points": 0}

    ts_images = ts_collection.toList(ts_count)

    dates = []
    temps = []
    lulc_ts_rows = []

    for idx in range(ts_count):
        img = ee.Image(ts_images.get(idx))
        date_str = ee.Date(img.get('system:time_start')).format('YYYY-MM-dd').getInfo()

        mean_lst = img.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=region,
            scale=250,
            maxPixels=1e9,
            bestEffort=True,
            tileScale=4
        ).get('LST').getInfo()

        if mean_lst is not None:
            dates.append(date_str)
            temps.append(float(mean_lst))

        if include_lulc_split:
            grouped_stats = img.addBands(worldcover_ts).reduceRegion(
                reducer=ee.Reducer.mean().group(groupField=1, groupName='landcover'),
                geometry=region,
                scale=500,
                maxPixels=1e9,
                bestEffort=True,
                tileScale=4
            ).get('groups').getInfo()

            for group_item in grouped_stats or []:
                lc_code_raw = group_item.get('landcover')
                lc_mean = group_item.get('mean')
                if lc_code_raw is None or lc_mean is None:
                    continue
                lc_code = str(int(lc_code_raw))
                lulc_ts_rows.append({
                    'Date': date_str,
                    'Land Cover': land_cover_name_map.get(lc_code, f'Class {lc_code}'),
                    'Mean LST (°C)': float(lc_mean),
                })

    df_ts = pd.DataFrame({
        'Date': pd.to_datetime(dates),
        'Mean LST (°C)': temps
    }).sort_values('Date') if dates else pd.DataFrame(columns=['Date', 'Mean LST (°C)'])

    df_lulc_ts = pd.DataFrame(lulc_ts_rows)
    if not df_lulc_ts.empty:
        df_lulc_ts['Date'] = pd.to_datetime(df_lulc_ts['Date'])
        df_lulc_ts = df_lulc_ts.sort_values(['Land Cover', 'Date'])

    return {
        "df_ts": df_ts.to_dict(orient='records'),
        "df_lulc_ts": df_lulc_ts.to_dict(orient='records') if not df_lulc_ts.empty else [],
        "total_scene_count": scene_count_estimate,
        "processed_points": len(df_ts),
    }

try:
    precomputed_payload = load_precomputed_timeseries_dataset()
    using_precomputed = False

    try:
        if precomputed_payload:
            all_rows = precomputed_payload.get("records", [])
            inv_rows = []
            for r in all_rows:
                date_val = datetime.fromisoformat(str(r.get("date"))).date()
                if start_date <= date_val <= end_date:
                    inv_rows.append({
                        "Date": r.get("date"),
                        "Time (UTC)": r.get("time_utc", "N/A"),
                        "Cloud Cover (%)": "N/A" if r.get("cloud_cover") is None else round(float(r.get("cloud_cover")), 1),
                        "Scene ID": r.get("scene_id", "Unknown"),
                    })
            ts_inventory = {"rows": inv_rows, "count": len(inv_rows)}
            using_precomputed = True
            st.caption("Using precomputed backend data for time-series inventory.")
        else:
            ts_inventory = get_time_series_scene_inventory(start_date.isoformat(), end_date.isoformat())

        inv_col1, inv_col2 = st.columns(2, gap="small")
        with inv_col1:
            st.metric("Scenes Available", ts_inventory["count"])
        with inv_col2:
            st.metric("Available Data Points", ts_inventory["count"])

    except Exception:
        st.caption("Could not fetch full scene inventory for this date range.")

    if not st.session_state.ts_ready:
        st.caption("Set date range and click 'Run Time Series Analysis'.")
        raise StopIteration

    if using_precomputed and not include_lulc_split:
        pre_df = pd.DataFrame(ts_inventory["rows"])
        if not pre_df.empty:
            pre_df["Date"] = pd.to_datetime(pre_df["Date"])
            raw_records = precomputed_payload.get("records", []) if precomputed_payload else []
            means = pd.DataFrame([
                {
                    "Date": pd.to_datetime(r.get("date")),
                    "Mean LST (°C)": r.get("mean_lst_c"),
                }
                for r in raw_records
                if r.get("mean_lst_c") is not None and start_date <= datetime.fromisoformat(str(r.get("date"))).date() <= end_date
            ])
            means = means.dropna().sort_values("Date")
            ts_result = {
                "df_ts": means.to_dict(orient="records"),
                "df_lulc_ts": [],
                "total_scene_count": len(means),
                "processed_points": len(means),
            }
        else:
            ts_result = {"df_ts": [], "df_lulc_ts": [], "total_scene_count": 0, "processed_points": 0}
    else:
        ts_result = compute_lst_time_series(start_date.isoformat(), end_date.isoformat(), include_lulc_split)

    df_ts = pd.DataFrame(ts_result["df_ts"])
    lulc_ts_rows = ts_result["df_lulc_ts"]

    dp_col1, dp_col2 = st.columns(2, gap="small")
    with dp_col1:
        st.metric("Scenes Used by Engine", ts_result.get("total_scene_count", 0))
    with dp_col2:
        st.metric("Plotted Data Points", ts_result.get("processed_points", 0))
    
    if not df_ts.empty:
        df_ts['Date'] = pd.to_datetime(df_ts['Date'])
        df_ts = df_ts.sort_values('Date')
        
        # Create interactive time series plot
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df_ts['Date'],
            y=df_ts['Mean LST (°C)'],
            mode='lines+markers',
            name='Mean LST',
            line=dict(color='orangered', width=2),
            marker=dict(size=6)
        ))
        
        fig.update_layout(
            title='Landsat 8 Land Surface Temperature Time Series (Delhi Region)',
            xaxis_title='Date',
            yaxis_title='Temperature (°C)',
            hovermode='x unified',
            height=400,
            template='plotly_white'
        )
        
        st.plotly_chart(fig, width='stretch')

        if lulc_ts_rows:
            import numpy as np

            df_lulc_ts = pd.DataFrame(lulc_ts_rows)
            df_lulc_ts = df_lulc_ts.sort_values(['Land Cover', 'Date'])

            fig_lulc = go.Figure()
            palette = [
                '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
                '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf',
                '#393b79', '#637939'
            ]
            lc_names = sorted(df_lulc_ts['Land Cover'].unique())
            for idx, lc_name in enumerate(lc_names):
                df_lc = df_lulc_ts[df_lulc_ts['Land Cover'] == lc_name]
                line_color = palette[idx % len(palette)]
                fig_lulc.add_trace(go.Scatter(
                    x=df_lc['Date'],
                    y=df_lc['Mean LST (°C)'],
                    mode='lines+markers',
                    name=lc_name,
                    marker=dict(size=5),
                    line=dict(width=2, color=line_color),
                    legendgroup=lc_name
                ))

            # Single overall trend line across all land-cover time-series points.
            if len(df_lulc_ts) >= 2:
                df_trend = df_lulc_ts.sort_values('Date')
                x_ord_all = df_trend['Date'].map(lambda d: d.toordinal()).to_numpy()
                y_all = df_trend['Mean LST (°C)'].to_numpy()
                trend_coeff_all = np.polyfit(x_ord_all, y_all, 1)
                trend_fn_all = np.poly1d(trend_coeff_all)

                # High-contrast halo so the trend remains visible in light and dark themes.
                fig_lulc.add_trace(go.Scatter(
                    x=df_trend['Date'],
                    y=trend_fn_all(x_ord_all),
                    mode='lines',
                    name='Overall trend',
                    line=dict(width=6, dash='dash', color='white'),
                    opacity=0.95,
                    showlegend=False,
                    hoverinfo='skip'
                ))

                fig_lulc.add_trace(go.Scatter(
                    x=df_trend['Date'],
                    y=trend_fn_all(x_ord_all),
                    mode='lines',
                    name='Overall trend',
                    line=dict(width=2.5, dash='dash', color='#111111'),
                    opacity=1.0,
                    showlegend=True
                ))

            fig_lulc.update_layout(
                title='LST Time Series by Land Cover Type with Trend Lines (ESA WorldCover)',
                xaxis_title='Date',
                yaxis_title='Temperature (°C)',
                hovermode='x unified',
                height=460,
                template='plotly_white',
                legend_title='Land Cover Type'
            )

            st.plotly_chart(fig_lulc, width='stretch')
        
        # Display statistics
        col1, col2, col3, col4 = st.columns(4, gap="small")
        with col1:
            st.metric("Average LST", f"{df_ts['Mean LST (°C)'].mean():.2f}°C")
        with col2:
            st.metric("Max LST", f"{df_ts['Mean LST (°C)'].max():.2f}°C")
        with col3:
            st.metric("Min LST", f"{df_ts['Mean LST (°C)'].min():.2f}°C")
        with col4:
            st.metric("Data Points", len(df_ts))
    else:
        st.warning("No Landsat 8 data available for the selected date range.")

except StopIteration:
    pass

except Exception as e:
    st.error(f"Error fetching time series data: {str(e)}")

# Spatial Distribution Analysis
st.subheader("Spatial Distribution Analysis - Air Temperature vs LST (Historical)")

try:
    lst_image = landsat_collection.select("LST").median()
    district_temps = []
    for name, lat, lon in locations:
        air_temp = get_power_air_temp(lat, lon, modis_start_date, modis_end_date)
        lst_value = get_lst_at_point(lst_image, lon, lat)
        if air_temp is None:
            w = get_weather(lat, lon)
            air_temp = w["temperature"]
        district_temps.append({
            'District': name,
            'Air Temperature': air_temp,
            'LST': lst_value,
            'Latitude': lat,
            'Longitude': lon
        })
    
    df_spatial = pd.DataFrame(district_temps)
    
    # Create visualizations
    col1, col2 = st.columns([1, 1], gap="medium")
    
    # Spatial heatmap - Bar chart showing air temperature distribution
    with col1:
        fig_bar = go.Figure()
        fig_bar.add_trace(go.Bar(
            x=df_spatial['District'],
            y=df_spatial['Air Temperature'],
            marker=dict(
                color=df_spatial['Air Temperature'],
                colorscale='RdYlBu_r',
                colorbar=dict(title="Air Temp (°C)"),
                showscale=True
            ),
            text=df_spatial['Air Temperature'].round(2),
            textposition='outside',
            name='Air Temperature'
        ))
        
        fig_bar.update_layout(
            title='Historical Air Temperature Distribution Across Districts',
            xaxis_title='District',
            yaxis_title='Air Temperature (°C)',
            height=400,
            template='plotly_white',
            showlegend=False
        )
        
        st.plotly_chart(fig_bar, width='stretch')
    
    # Scatter plot - air temperature vs LST
    with col2:
        fig_scatter = go.Figure()
        fig_scatter.add_trace(go.Scatter(
            x=df_spatial['Air Temperature'],
            y=df_spatial['LST'],
            mode='markers+text',
            marker=dict(
                size=15,
                color=df_spatial['Air Temperature'],
                colorscale='RdYlBu_r',
                showscale=True,
                colorbar=dict(title="Air Temp (°C)")
            ),
            text=df_spatial['District'],
            textposition='top center',
            name='Districts'
        ))
        
        fig_scatter.update_layout(
            title='Air Temperature vs LST',
            xaxis_title='Air Temperature (°C)',
            yaxis_title='Land Surface Temperature (°C)',
            height=400,
            template='plotly_white'
        )
        
        st.plotly_chart(fig_scatter, width='stretch')
    
    # Spatial statistics
    st.subheader("Spatial Temperature Statistics")
    
    col1, col2, col3, col4, col5 = st.columns(5, gap="small")
    with col1:
        st.metric("Max Air Temp District", df_spatial.loc[df_spatial['Air Temperature'].idxmax(), 'District'], 
                 f"{df_spatial['Air Temperature'].max():.1f}°C")
    with col2:
        st.metric("Min Air Temp District", df_spatial.loc[df_spatial['Air Temperature'].idxmin(), 'District'],
                 f"{df_spatial['Air Temperature'].min():.1f}°C")
    with col3:
        temp_range = df_spatial['Air Temperature'].max() - df_spatial['Air Temperature'].min()
        st.metric("Air Temp Range", f"{temp_range:.1f}°C", 
                 f"(Spatial Variation)")
    with col4:
        st.metric("Avg Air Temp", f"{df_spatial['Air Temperature'].mean():.1f}°C",
                 f"(All Districts)")
    with col5:
        lst_mean = df_spatial['LST'].mean()
        st.metric("Avg LST", f"{lst_mean:.1f}°C" if pd.notna(lst_mean) else "N/A")
    
    # Detailed district comparison table
    st.subheader("Detailed District Comparison")
    
    df_display = df_spatial[['District', 'Air Temperature', 'LST']].copy()
    df_display['Air Temp Anomaly'] = df_display['Air Temperature'] - df_display['Air Temperature'].mean()
    df_display['Air Temperature'] = df_display['Air Temperature'].round(2)
    df_display['LST'] = df_display['LST'].round(2)
    df_display['Air Temp Anomaly'] = df_display['Air Temp Anomaly'].round(2)
    
    st.dataframe(df_display, width='stretch')
    
    # Heat gradient map visualization
    st.subheader("Air Temperature Distribution Map")
    
    # Create map with temperature-based colors
    m_heat = folium.Map(location=[28.6139, 77.2090], zoom_start=10)
    
    # Add districts with color intensity based on temperature
    for idx, row in df_spatial.iterrows():
        # Normalize temperature to 0-1 for color mapping
        temp_normalized = (row['Air Temperature'] - df_spatial['Air Temperature'].min()) / (df_spatial['Air Temperature'].max() - df_spatial['Air Temperature'].min())
        
        # Color mapping: blue (cold) to red (hot)
        if temp_normalized < 0.33:
            color = 'blue'
        elif temp_normalized < 0.66:
            color = 'orange'
        else:
            color = 'red'
        
        popup_text = f"""
<b>{row['District']}</b><br>
Air Temperature: {row['Air Temperature']:.1f}°C<br>
LST: {row['LST']:.1f}°C<br>
Anomaly: {row['Air Temperature'] - df_spatial['Air Temperature'].mean():+.2f}°C
"""
        
        folium.CircleMarker(
            location=[row['Latitude'], row['Longitude']],
            radius=20,
            popup=folium.Popup(popup_text, max_width=250),
            color=color,
            fill=True,
            fillColor=color,
            fillOpacity=0.7,
            weight=2,
            opacity=0.9
        ).add_to(m_heat)
    
    st_folium(m_heat, width=None, height=600, returned_objects=[])
    
    # Urban Heat Island Analysis (Air)
    st.subheader("Urban Heat Island (UHI) Analysis - Air Temperature")
    
    mean_temp = df_spatial['Air Temperature'].mean()
    df_uhi = df_spatial.copy()
    df_uhi['UHI Intensity'] = df_uhi['Air Temperature'] - mean_temp
    
    # Create UHI intensity chart
    fig_uhi = go.Figure()
    colors = ['red' if x > 0 else 'blue' for x in df_uhi['UHI Intensity']]
    
    fig_uhi.add_trace(go.Bar(
        x=df_uhi['District'],
        y=df_uhi['UHI Intensity'],
        marker=dict(color=colors),
        text=df_uhi['UHI Intensity'].round(2),
        textposition='outside',
        name='UHI Intensity'
    ))
    
    fig_uhi.update_layout(
        title='Air UHI Intensity (Deviation from Mean)',
        xaxis_title='District',
        yaxis_title='Air Temperature Anomaly (°C)',
        height=400,
        template='plotly_white',
        hovermode='x unified',
        showlegend=False
    )
    
    fig_uhi.add_hline(y=0, line_dash="dash", line_color="gray")
    
    st.plotly_chart(fig_uhi, width='stretch')
    
    # UHI Summary
    hottest_district = df_uhi.loc[df_uhi['UHI Intensity'].idxmax()]
    coolest_district = df_uhi.loc[df_uhi['UHI Intensity'].idxmin()]
    
    col1, col2 = st.columns([1, 1], gap="medium")
    with col1:
        st.info(f"""
        **Hottest Zone (Air)**: {hottest_district['District']}
        - Temperature Anomaly: +{hottest_district['UHI Intensity']:.2f}°C (above mean)
        - Air Temperature: {hottest_district['Air Temperature']:.1f}°C
        """)
    with col2:
        st.info(f"""
        **Coolest Zone (Air)**: {coolest_district['District']}
        - Temperature Anomaly: {coolest_district['UHI Intensity']:.2f}°C (below mean)
        - Air Temperature: {coolest_district['Air Temperature']:.1f}°C
        """)

    if df_spatial['LST'].notna().any():
        st.subheader("Surface Urban Heat Island (LST) Analysis")
        cropland_mean_lst = None
        try:
            worldcover = ee.ImageCollection("ESA/WorldCover/v200").first()
            cropland_mask = worldcover.select("Map").eq(40)
            cropland_lst = lst_image.updateMask(cropland_mask)
            cropland_stats = cropland_lst.reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=districts_geometry if districts_geometry else region,
                scale=100,
                maxPixels=1e9
            ).getInfo()
            cropland_mean_lst = cropland_stats.get("LST")
        except Exception:
            cropland_mean_lst = None

        if cropland_mean_lst is None:
            cropland_mean_lst = df_spatial['LST'].mean()
            st.info("Cropland baseline unavailable; using Delhi mean LST.")
        else:
            st.info(f"Cropland baseline LST (WorldCover class 40): {cropland_mean_lst:.2f}°C")
        df_uhi_lst = df_spatial.copy()
        df_uhi_lst['UHI Intensity (LST)'] = df_uhi_lst['LST'] - cropland_mean_lst

        fig_uhi_lst = go.Figure()
        colors_lst = ['red' if x > 0 else 'blue' for x in df_uhi_lst['UHI Intensity (LST)']]

        fig_uhi_lst.add_trace(go.Bar(
            x=df_uhi_lst['District'],
            y=df_uhi_lst['UHI Intensity (LST)'],
            marker=dict(color=colors_lst),
            text=df_uhi_lst['UHI Intensity (LST)'].round(2),
            textposition='outside',
            name='UHI Intensity (LST)'
        ))

        fig_uhi_lst.update_layout(
            title='Surface UHI Intensity from LST (vs Cropland Baseline)',
            xaxis_title='District',
            yaxis_title='LST Anomaly (°C)',
            height=400,
            template='plotly_white',
            hovermode='x unified',
            showlegend=False
        )

        fig_uhi_lst.add_hline(y=0, line_dash="dash", line_color="gray")
        st.plotly_chart(fig_uhi_lst, width='stretch')

except Exception as e:
    st.error(f"Error in spatial distribution analysis: {str(e)}")

# Greenery Effect on Urban Heat Island Analysis
st.subheader("Impact of Vegetation on Urban Heat Island Effect")

try:
    # Fetch NDVI data for each location
    ndvi_values = []
    
    for name, lat, lon in locations:
        try:
            # Create point geometry
            point = ee.Geometry.Point([lon, lat])
            
            # Fetch Sentinel-2 NDVI for the location
            sentinel_collection = (
                ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
                .filterDate(modis_start_date.isoformat(), modis_end_date.isoformat())
                .filterBounds(point.buffer(500))
                .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20))
                .median()
            )
            
            ndvi = sentinel_collection.normalizedDifference(['B8', 'B4'])
            
            # Sample NDVI value
            ndvi_sample = ndvi.sample(point, 500).first().get('nd').getInfo()
            
            ndvi_values.append({
                'City': name,
                'NDVI': ndvi_sample if ndvi_sample else 0,
                'Temperature': next((item['Air Temperature'] for item in district_temps if item['District'] == name), None)
            })
        except:
            # If sampling fails, use default NDVI
            ndvi_values.append({
                'City': name,
                'NDVI': 0.3,  # Default moderate vegetation
                'Temperature': next((item['Air Temperature'] for item in district_temps if item['District'] == name), None)
            })
    
    df_greenery = pd.DataFrame(ndvi_values)
    
    # Create visualizations for greenery-temperature relationship
    col1, col2 = st.columns([1, 1], gap="medium")
    
    # NDVI distribution chart
    with col1:
        fig_ndvi = go.Figure()
        fig_ndvi.add_trace(go.Bar(
            x=df_greenery['City'],
            y=df_greenery['NDVI'],
            marker=dict(
                color=df_greenery['NDVI'],
                colorscale='RdYlGn',
                showscale=True,
                colorbar=dict(title="NDVI")
            ),
            text=df_greenery['NDVI'].round(3),
            textposition='outside',
            name='NDVI'
        ))
        
        fig_ndvi.update_layout(
            title='Vegetation Index (NDVI) Distribution',
            xaxis_title='City',
            yaxis_title='NDVI Value',
            height=400,
            template='plotly_white',
            showlegend=False
        )
        
        st.plotly_chart(fig_ndvi, width='stretch')
    
    # Correlation scatter plot - NDVI vs Temperature
    with col2:
        fig_corr = go.Figure()
        fig_corr.add_trace(go.Scatter(
            x=df_greenery['NDVI'],
            y=df_greenery['Temperature'],
            mode='markers+text',
            marker=dict(
                size=15,
                color=df_greenery['Temperature'],
                colorscale='RdYlBu_r',
                showscale=True,
                colorbar=dict(title="Temp (°C)")
            ),
            text=df_greenery['City'],
            textposition='top center',
            name='Cities'
        ))
        
        fig_corr.update_layout(
            title='Vegetation vs Temperature Relationship',
            xaxis_title='Vegetation Index (NDVI)',
            yaxis_title='Temperature (°C)',
            height=400,
            template='plotly_white'
        )
        
        st.plotly_chart(fig_corr, width='stretch')

except Exception as e:
    st.error(f"Error in greenery analysis: {str(e)}")

# ==================== Multi-Variable Correlation Analysis ====================
st.header("📊 Multi-Variable Correlation Analysis: NDVI, LST & Land Use")
st.markdown("""
Analyze the relationships between vegetation (NDVI), land surface temperature (LST), 
and land use/land cover (LULC) to understand urban heat dynamics.
""")

# Date range selection for correlation analysis
st.subheader("📅 Select Date Range for Analysis")
col_date1, col_date2 = st.columns([1, 1], gap="medium")

with col_date1:
    corr_start_date = st.date_input(
        "Analysis Start Date",
        value=datetime(2025, 12, 31).date(),
        min_value=datetime(2000, 1, 1).date(),
        max_value=datetime.now().date(),
        help="Select start date for correlation analysis (Landsat 8 data available from 2013)"
    )

with col_date2:
    corr_end_date = st.date_input(
        "Analysis End Date",
        value=datetime(2026, 1, 30).date(),
        min_value=datetime(2000, 1, 1).date(),
        max_value=datetime.now().date(),
        help="Select end date for correlation analysis"
    )

run_corr_analysis = st.button("Run Correlation Analysis", type="primary")

# Validate date range
if corr_start_date >= corr_end_date:
    st.error("⚠️ Start date must be before end date!")
    st.stop()

try:
    if not run_corr_analysis:
        st.caption("Click 'Run Correlation Analysis' to compute correlation statistics and charts.")
        raise StopIteration

    # Sample data from Delhi districts using Earth Engine
    import pandas as pd
    import numpy as np
    
    # Create sample points across Delhi
    if districts_geometry:
        sampling_geometry = districts_geometry
    else:
        sampling_geometry = region
    
    # Get LST and NDVI using selected date range
    landsat_corr_collection = get_landsat8_collection(
        corr_start_date.isoformat(),
        corr_end_date.isoformat(),
        sampling_geometry
    )
    lst_celsius_sample = landsat_corr_collection.select("LST").median()
    ndvi_image = landsat_corr_collection.select("NDVI").median()
    
    # Get Land Cover data
    lulc_image = ee.ImageCollection("ESA/WorldCover/v200").first()
    
    # Combine all bands
    combined_image = lst_celsius_sample.addBands(ndvi_image).addBands(lulc_image)
    combined_image = combined_image.select(['LST', 'NDVI', 'Map'], ['LST', 'NDVI', 'LandCover'])
    
    sample_points = combined_image.sample(
        region=sampling_geometry,
        scale=250,
        numPixels=300,
        seed=42,
        geometries=False,
        tileScale=4
    )

    sample_data = sample_points.getInfo()

    if not sample_data or 'features' not in sample_data or len(sample_data['features']) == 0:
        st.warning("No data available for correlation analysis. Check your date range and area selection.")
        raise StopIteration

    data_list = []
    for feature in sample_data['features']:
        props = feature.get('properties', {})
        if 'LST' in props and 'NDVI' in props and 'LandCover' in props:
            data_list.append({
                'LST': props['LST'],
                'NDVI': props['NDVI'],
                'LandCover': props['LandCover']
            })

    df_corr = pd.DataFrame(data_list)
    if df_corr.empty:
        st.warning("No valid sampled pixels found for correlation analysis.")
        raise StopIteration

    # Filter out invalid values
    df_corr = df_corr[(df_corr['LST'] > -50) & (df_corr['LST'] < 60)]
    df_corr = df_corr[(df_corr['NDVI'] >= -1) & (df_corr['NDVI'] <= 1)]

    if len(df_corr) <= 10:
        st.warning("Insufficient data points for correlation analysis. Try adjusting the date range.")
        raise StopIteration

    lulc_names = {
        10: 'Tree Cover', 20: 'Shrubland', 30: 'Grassland', 40: 'Cropland',
        50: 'Built-up', 60: 'Bare/Sparse', 70: 'Snow/Ice', 80: 'Water',
        90: 'Wetland', 95: 'Mangroves', 100: 'Moss/Lichen'
    }
    df_corr['LandCover_Name'] = df_corr['LandCover'].map(lulc_names).fillna('Other')

    corr_ndvi_lst = df_corr['NDVI'].corr(df_corr['LST'])
    urban_temp = df_corr[df_corr['LandCover'] == 50]['LST'].mean() if 50 in df_corr['LandCover'].values else 0
    veg_temp = df_corr[df_corr['LandCover'].isin([10, 20, 30])]['LST'].mean() if any(lc in df_corr['LandCover'].values for lc in [10, 20, 30]) else 0

    st.subheader("Correlation Statistics")
    c1, c2, c3, c4 = st.columns(4, gap="small")
    with c1:
        st.metric("NDVI-LST Correlation", f"{corr_ndvi_lst:.3f}", "Negative = vegetation cools")
    with c2:
        st.metric("Avg Urban Temperature", f"{urban_temp:.1f}°C" if urban_temp > 0 else "N/A", "Built-up areas")
    with c3:
        st.metric("Avg Vegetation Temperature", f"{veg_temp:.1f}°C" if veg_temp > 0 else "N/A", "Green areas")
    with c4:
        temp_diff = urban_temp - veg_temp if (urban_temp > 0 and veg_temp > 0) else None
        st.metric("Urban Heat Island Effect", f"{temp_diff:.1f}°C" if temp_diff is not None else "N/A", "Urban vs Vegetation")

    st.subheader("Correlation Visualizations")
    v1, v2 = st.columns([1, 1], gap="medium")

    with v1:
        fig_scatter = go.Figure()
        fig_scatter.add_trace(go.Scatter(
            x=df_corr['NDVI'],
            y=df_corr['LST'],
            mode='markers',
            marker=dict(size=7, opacity=0.55),
            name='Samples'
        ))

        z = np.polyfit(df_corr['NDVI'], df_corr['LST'], 1)
        p = np.poly1d(z)
        x_trend = np.linspace(df_corr['NDVI'].min(), df_corr['NDVI'].max(), 100)
        fig_scatter.add_trace(go.Scatter(
            x=x_trend,
            y=p(x_trend),
            mode='lines',
            name='Trend Line',
            line=dict(color='black', width=2, dash='dash')
        ))

        fig_scatter.update_layout(
            title=f'NDVI vs LST (Correlation: {corr_ndvi_lst:.3f})',
            xaxis_title='Vegetation Index (NDVI)',
            yaxis_title='Land Surface Temperature (°C)',
            height=430,
            template='plotly_white'
        )
        st.plotly_chart(fig_scatter, width='stretch')

    with v2:
        lulc_summary = df_corr.groupby('LandCover_Name').agg({
            'LST': 'mean',
            'LandCover': 'count'
        }).rename(columns={'LandCover': 'Area_Count'})
        lulc_summary['Area_Percent'] = (lulc_summary['Area_Count'] / len(df_corr) * 100).round(2)
        lulc_summary = lulc_summary.sort_values('Area_Percent', ascending=True)

        fig_area_temp = go.Figure()
        fig_area_temp.add_trace(go.Bar(
            y=lulc_summary.index,
            x=lulc_summary['Area_Percent'],
            orientation='h',
            marker=dict(
                color=lulc_summary['LST'],
                colorscale='RdYlBu_r',
                showscale=True,
                colorbar=dict(title="Temp (°C)", x=1.12)
            ),
            text=lulc_summary['Area_Percent'].apply(lambda x: f'{x:.1f}%'),
            textposition='auto'
        ))
        fig_area_temp.update_layout(
            title='Land Cover Area Share (colored by temperature)',
            xaxis_title='Area Share (%)',
            yaxis_title='Land Use Type',
            height=430,
            template='plotly_white',
            showlegend=False
        )
        st.plotly_chart(fig_area_temp, width='stretch')

    st.subheader("Temperature & Area Statistics by Land Use Type")
    lulc_stats = df_corr.groupby('LandCover_Name').agg({
        'LST': ['count', 'mean', 'std', 'min', 'max'],
        'NDVI': 'mean'
    }).round(2)
    lulc_stats.columns = ['Sample Count', 'Mean Temp (°C)', 'Std Dev', 'Min Temp (°C)', 'Max Temp (°C)', 'Avg NDVI']
    lulc_stats['Area Coverage (%)'] = (lulc_stats['Sample Count'] / len(df_corr) * 100).round(2)
    lulc_stats = lulc_stats[['Sample Count', 'Area Coverage (%)', 'Mean Temp (°C)', 'Avg NDVI', 'Std Dev', 'Min Temp (°C)', 'Max Temp (°C)']]
    lulc_stats = lulc_stats.sort_values('Area Coverage (%)', ascending=False)
    st.dataframe(lulc_stats, width='stretch')

except StopIteration:
    pass
            
except Exception as corr_error:
    st.error(f"Error in correlation analysis: {str(corr_error)}")

# ==================== End of Correlation Analysis ====================

st.subheader("Live Heat Alerts for Delhi Region")
for name, lat, lon in locations:
    w = get_weather(lat, lon)
    st.write(f"**{name}**: {w['temperature']} °C, Feels Like: {w['feels_like']} °C, Humidity: {w['humidity']} %")

st.caption("Satellite Data Source: Landsat 8 L2 (LST & NDVI, 100m) | Weather Data Sources: OpenWeather (live) + NASA POWER (historical)")
