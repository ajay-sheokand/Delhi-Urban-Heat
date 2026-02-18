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

st.title("Delhi-NCR Urban Heat Monitoring Dashboard")

# Add info expander for better mobile experience
with st.expander("ℹ️ About this Dashboard", expanded=False):
    st.markdown("""
    This dashboard combines:
    - **Real-Time Air Temperature** - Live data from OpenWeather API for 11 Delhi districts
    - **Satellite-Derived Land Surface Temperature (LST)** - MODIS satellite data from NASA
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

st.subheader("MODIS Satellite-Derived Daily Land Surface Temperature (LST)")

# Date selection controls for MODIS layers
st.markdown("### 📅 Select Date Range for Satellite Data")

col1, col2 = st.columns([1, 1], gap="medium")

with col1:
    modis_start_date = st.date_input(
        "Start Date",
        value=datetime(2025, 12, 31).date(),
        min_value=datetime(2000, 1, 1).date(),
        max_value=datetime.now().date(),
        key="modis_start"
    )

with col2:
    modis_end_date = st.date_input(
        "End Date",
        value=datetime(2026, 1, 30).date(),
        min_value=datetime(2000, 1, 1).date(),
        max_value=datetime.now().date(),
        key="modis_end"
    )

# Validate date ranges
if modis_start_date >= modis_end_date:
    st.error("⚠️ Start Date must be before End Date")

# Display selected date range
st.info(f"📊 Loading satellite data (LST & NDVI) from **{modis_start_date}** to **{modis_end_date}** ({(modis_end_date - modis_start_date).days} days)")

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
            st.success(f"✅ Loaded {len(gdf)} districts from GeoJSON")
        else:
            st.warning(f"⚠️ District boundary files not found")
            st.info(f"📂 Current directory: {current_dir}")
            st.info(f"📁 Available files: {[f for f in os.listdir(current_dir) if not f.startswith('.')][:10]}")
            return None
        
        # Filter for Delhi districts only (should already be all Delhi from this file)
        if 'STATE' in gdf.columns:
            delhi_gdf = gdf[gdf['STATE'].str.contains('DELHI', case=False, na=False)]
        else:
            delhi_gdf = gdf
        
        return delhi_gdf
    except Exception as e:
        st.error(f"❌ Error loading district boundaries: {str(e)}")
        st.info("💡 Tip: Ensure delhi_admin.geojson is in the repository and deployed")
        import traceback
        st.code(traceback.format_exc())
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
    except Exception as e:
        st.warning(f"Using bounding box for clipping: {str(e)}")
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
    except Exception as e:
        st.warning(f"Could not load layer {name}: {str(e)}")

folium.Map.add_ee_layer = add_ee_layer

# Add MODIS LST layer with enhanced styling
try:
    # Fetch MODIS LST
    lst = (
        ee.ImageCollection("MODIS/061/MOD11A1")
        .filterDate(modis_start_date.isoformat(), modis_end_date.isoformat())
        .select("LST_Day_1km")
        .mean()
    )
    
    # Convert LST to Celsius
    lst_celsius = lst.multiply(0.02).subtract(273.15)
    
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
            scale=1000,
            maxPixels=1e9
        ).getInfo()
        
        # Extract min/max values with fallback
        data_min = stats.get('LST_Day_1km_min', 10)
        data_max = stats.get('LST_Day_1km_max', 40)
        
        # Add some buffer to the range for better color distribution
        buffer = (data_max - data_min) * 0.1
        viz_min = max(data_min - buffer, -5)
        viz_max = min(data_max + buffer, 55)
        
        st.info(f"📊 LST Range: {data_min:.1f}°C to {data_max:.1f}°C (Visualization: {viz_min:.1f}°C to {viz_max:.1f}°C)")
    except:
        # Fallback to seasonal defaults if calculation fails
        viz_min = 10
        viz_max = 40
        st.warning("Using default temperature range (10-40°C)")
    
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
    m.add_ee_layer(display_layer, vis_params, "🌡️ Land Surface Temperature (°C)", opacity=0.6)
    
except Exception as lst_error:
    st.error(f"Error loading LST layer: {str(lst_error)}")

# Add NDVI layer for greenery visualization with enhanced colors
try:
    # Use MODIS NDVI which is more reliable and always available
    modis_ndvi = (
        ee.ImageCollection("MODIS/061/MOD13A2")  # MODIS Vegetation Indices
        .filterDate(modis_start_date.isoformat(), modis_end_date.isoformat())
        .select("NDVI")
        .mean()
    )
    
    # Scale NDVI values (MODIS returns values 0-10000, need to scale to -1 to 1)
    ndvi = modis_ndvi.divide(10000)
    
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
        m.add_ee_layer(ndvi_clipped, ndvi_vis_params, "🌿 Vegetation Index - NDVI", opacity=0.45)
    else:
        m.add_ee_layer(ndvi, ndvi_vis_params, "🌿 Vegetation Index - NDVI", opacity=0.45)
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
            m.add_ee_layer(ndvi_sent_clipped, ndvi_vis_params, "🌿 Vegetation Index - NDVI", opacity=0.45)
        else:
            m.add_ee_layer(ndvi_sent, ndvi_vis_params, "🌿 Vegetation Index - NDVI", opacity=0.45)
    except Exception as fallback_e:
        st.warning(f"Vegetation layer temporarily unavailable")

# Add Land Use / Land Cover Layers
st.subheader("🏙️ Land Use / Land Cover Analysis")

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
        m.add_ee_layer(worldcover_clipped, worldcover_vis, "🌍 Land Cover (ESA 10m)", opacity=0.5)
    else:
        m.add_ee_layer(worldcover, worldcover_vis, "🌍 Land Cover (ESA 10m)", opacity=0.5)
    
    # Calculate land use statistics
    try:
        land_use_stats = worldcover_clipped.reduceRegion(
            reducer=ee.Reducer.frequencyHistogram(),
            geometry=districts_geometry if districts_geometry else region,
            scale=100,
            maxPixels=1e9
        ).getInfo()
        
        if land_use_stats and 'Map' in land_use_stats:
            land_class_names = {
                '10': 'Tree Cover', '20': 'Shrubland', '30': 'Grassland', 
                '40': 'Cropland', '50': 'Built-up (Urban)', '60': 'Bare/Sparse Vegetation',
                '70': 'Snow/Ice', '80': 'Water Bodies', '90': 'Wetland', 
                '95': 'Mangroves', '100': 'Moss/Lichen'
            }
            
            histogram = land_use_stats['Map']
            total_pixels = sum(histogram.values())
            
            st.markdown("### 📊 Land Use Distribution")
            
            # Create columns for land use stats
            col1, col2, col3, col4 = st.columns(4, gap="small")
            
            # Calculate percentages
            land_use_pct = {land_class_names.get(k, k): (v/total_pixels)*100 
                           for k, v in histogram.items()}
            
            # Sort by percentage
            sorted_land_use = sorted(land_use_pct.items(), key=lambda x: x[1], reverse=True)
            
            # Display top land uses in metrics
            for idx, (land_type, percentage) in enumerate(sorted_land_use[:4]):
                with [col1, col2, col3, col4][idx]:
                    st.metric(land_type, f"{percentage:.1f}%")
            
            # Show all land uses in a table
            if len(sorted_land_use) > 4:
                import pandas as pd
                df_land_use = pd.DataFrame(sorted_land_use, columns=['Land Use Type', 'Coverage (%)'])
                df_land_use['Coverage (%)'] = df_land_use['Coverage (%)'].round(2)
                st.dataframe(df_land_use, width='stretch', hide_index=True)
                
    except Exception as stats_error:
        st.info("💡 Land use statistics calculation in progress...")
    
    st.success("✅ High-resolution land cover layer (10m) added to map")
    
except Exception as worldcover_error:
    st.warning(f"ESA WorldCover not available, trying MODIS Land Cover...")
    
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
            m.add_ee_layer(modis_lc_clipped, modis_lc_vis, "🌍 Land Cover (MODIS 500m)", opacity=0.5)
        else:
            m.add_ee_layer(modis_lc, modis_lc_vis, "🌍 Land Cover (MODIS 500m)", opacity=0.5)
        
        st.info("ℹ️ Using MODIS Land Cover (500m resolution)")
        
    except Exception as modis_lc_error:
        st.warning("Land cover layers temporarily unavailable")

except Exception as lc_error:
    st.warning(f"Could not load land cover data: {str(lc_error)}")


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

# Function for heat alerts
def heat_alert(temp):
    if temp >= 40:
        return "🔥 Extreme Heat Alert! Stay Hydrated and Avoid Outdoor Activities."
    elif temp >= 35:
        return "⚠️ High Heat Warning! Take Precautions."
    else:
        return "🌤️ Normal Temperature."

# Add weather markers to map with enhanced styling
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
    ).add_to(m)

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

# Add LULC Legend to lower right corner
lulc_legend_html = """
<div style="position: fixed; 
            bottom: 50px; 
            right: 10px; 
            width: 220px; 
            background-color: white; 
            border: 2px solid grey; 
            border-radius: 5px; 
            z-index: 9999; 
            font-size: 12px;
            padding: 10px;
            box-shadow: 2px 2px 6px rgba(0,0,0,0.3);">
    <div style="text-align: center; font-weight: bold; font-size: 14px; margin-bottom: 8px; border-bottom: 1px solid #ccc; padding-bottom: 5px;">
        🌍 Land Cover Legend
    </div>
    <div style="max-height: 300px; overflow-y: auto;">
        <div style="margin: 3px 0; display: flex; align-items: center;">
            <span style="background-color: #006400; width: 20px; height: 15px; display: inline-block; margin-right: 8px; border: 1px solid #000;"></span>
            <span>Tree Cover</span>
        </div>
        <div style="margin: 3px 0; display: flex; align-items: center;">
            <span style="background-color: #FFBB22; width: 20px; height: 15px; display: inline-block; margin-right: 8px; border: 1px solid #000;"></span>
            <span>Shrubland</span>
        </div>
        <div style="margin: 3px 0; display: flex; align-items: center;">
            <span style="background-color: #FFFF4C; width: 20px; height: 15px; display: inline-block; margin-right: 8px; border: 1px solid #000;"></span>
            <span>Grassland</span>
        </div>
        <div style="margin: 3px 0; display: flex; align-items: center;">
            <span style="background-color: #F096FF; width: 20px; height: 15px; display: inline-block; margin-right: 8px; border: 1px solid #000;"></span>
            <span>Cropland</span>
        </div>
        <div style="margin: 3px 0; display: flex; align-items: center;">
            <span style="background-color: #FA0000; width: 20px; height: 15px; display: inline-block; margin-right: 8px; border: 1px solid #000;"></span>
            <span><b>Built-up (Urban)</b></span>
        </div>
        <div style="margin: 3px 0; display: flex; align-items: center;">
            <span style="background-color: #B4B4B4; width: 20px; height: 15px; display: inline-block; margin-right: 8px; border: 1px solid #000;"></span>
            <span>Bare/Sparse Veg</span>
        </div>
        <div style="margin: 3px 0; display: flex; align-items: center;">
            <span style="background-color: #F0F0F0; width: 20px; height: 15px; display: inline-block; margin-right: 8px; border: 1px solid #000;"></span>
            <span>Snow/Ice</span>
        </div>
        <div style="margin: 3px 0; display: flex; align-items: center;">
            <span style="background-color: #0064C8; width: 20px; height: 15px; display: inline-block; margin-right: 8px; border: 1px solid #000;"></span>
            <span>Water Bodies</span>
        </div>
        <div style="margin: 3px 0; display: flex; align-items: center;">
            <span style="background-color: #0096A0; width: 20px; height: 15px; display: inline-block; margin-right: 8px; border: 1px solid #000;"></span>
            <span>Wetland</span>
        </div>
        <div style="margin: 3px 0; display: flex; align-items: center;">
            <span style="background-color: #00CF75; width: 20px; height: 15px; display: inline-block; margin-right: 8px; border: 1px solid #000;"></span>
            <span>Mangroves</span>
        </div>
        <div style="margin: 3px 0; display: flex; align-items: center;">
            <span style="background-color: #FAE6A0; width: 20px; height: 15px; display: inline-block; margin-right: 8px; border: 1px solid #000;"></span>
            <span>Moss/Lichen</span>
        </div>
    </div>
    <div style="margin-top: 8px; padding-top: 5px; border-top: 1px solid #ccc; font-size: 10px; color: #666; text-align: center;">
        ESA WorldCover 2021 (10m)
    </div>
</div>
"""

m.get_root().html.add_child(folium.Element(lulc_legend_html))

# Add layer control to the map
folium.LayerControl(position='topright', collapsed=False).add_to(m)

# Render map in Streamlit - Responsive width
st_folium(m, width=None, height=600, returned_objects=[])

# Time Series Analysis of MODIS LST
st.subheader("Time Series Analysis - Historical MODIS Land Surface Temperature")

# Date range selector
col1, col2 = st.columns([1, 1], gap="medium")
with col1:
    start_date = st.date_input("Start Date", datetime.now() - timedelta(days=60))
with col2:
    end_date = st.date_input("End Date", datetime.now())

try:
    # Fetch MODIS data for the selected date range
    modis_collection = (
        ee.ImageCollection("MODIS/061/MOD11A1")
        .filterDate(start_date.isoformat(), end_date.isoformat())
        .select("LST_Day_1km")
    )
    
    # Extract time series data for the region
    def extract_lst_stats(image):
        date = ee.Date(image.get('system:time_start')).format('YYYY-MM-dd')
        lst_celsius = image.multiply(0.02).subtract(273.15)
        
        # Calculate mean LST for the region
        mean_lst = lst_celsius.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=region,
            scale=1000,
            maxPixels=1e9
        ).get('LST_Day_1km')
        
        return ee.Feature(None, {
            'date': date,
            'mean_lst': mean_lst
        })
    
    # Map the function over the collection
    ts_data = modis_collection.map(extract_lst_stats)
    
    # Get the data
    ts_list = ts_data.toList(ts_data.size()).getInfo()
    
    # Create DataFrame
    dates = []
    temps = []
    
    for feature in ts_list:
        if feature and 'properties' in feature:
            props = feature['properties']
            if props.get('mean_lst') is not None:
                dates.append(props['date'])
                temps.append(float(props['mean_lst']))
    
    if dates:
        df_ts = pd.DataFrame({
            'Date': pd.to_datetime(dates),
            'Mean LST (°C)': temps
        })
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
            title='MODIS Land Surface Temperature Time Series (Delhi-NCR Region)',
            xaxis_title='Date',
            yaxis_title='Temperature (°C)',
            hovermode='x unified',
            height=400,
            template='plotly_white'
        )
        
        st.plotly_chart(fig, width='stretch')
        
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
        st.warning("No MODIS data available for the selected date range.")
        
except Exception as e:
    st.error(f"Error fetching time series data: {str(e)}")

# Spatial Distribution Analysis
st.subheader("Spatial Distribution Analysis - Temperature Variation Across Districts")

try:
    # Fetch current weather for all districts
    district_temps = []
    for name, lat, lon in locations:
        w = get_weather(lat, lon)
        district_temps.append({
            'District': name,
            'Temperature': w['temperature'],
            'Feels Like': w['feels_like'],
            'Humidity': w['humidity'],
            'Latitude': lat,
            'Longitude': lon
        })
    
    df_spatial = pd.DataFrame(district_temps)
    
    # Create visualizations
    col1, col2 = st.columns([1, 1], gap="medium")
    
    # Spatial heatmap - Bar chart showing temperature distribution
    with col1:
        fig_bar = go.Figure()
        fig_bar.add_trace(go.Bar(
            x=df_spatial['District'],
            y=df_spatial['Temperature'],
            marker=dict(
                color=df_spatial['Temperature'],
                colorscale='RdYlBu_r',
                colorbar=dict(title="Temp (°C)"),
                showscale=True
            ),
            text=df_spatial['Temperature'].round(2),
            textposition='outside',
            name='Temperature'
        ))
        
        fig_bar.update_layout(
            title='Current Temperature Distribution Across Districts',
            xaxis_title='District',
            yaxis_title='Temperature (°C)',
            height=400,
            template='plotly_white',
            showlegend=False
        )
        
        st.plotly_chart(fig_bar, width='stretch')
    
    # Scatter plot - showing temperature vs feels like
    with col2:
        fig_scatter = go.Figure()
        fig_scatter.add_trace(go.Scatter(
            x=df_spatial['Temperature'],
            y=df_spatial['Feels Like'],
            mode='markers+text',
            marker=dict(
                size=15,
                color=df_spatial['Temperature'],
                colorscale='RdYlBu_r',
                showscale=True,
                colorbar=dict(title="Temp (°C)")
            ),
            text=df_spatial['District'],
            textposition='top center',
            name='Districts'
        ))
        
        fig_scatter.update_layout(
            title='Temperature vs Feels Like Temperature',
            xaxis_title='Actual Temperature (°C)',
            yaxis_title='Feels Like Temperature (°C)',
            height=400,
            template='plotly_white'
        )
        
        st.plotly_chart(fig_scatter, width='stretch')
    
    # Spatial statistics
    st.subheader("Spatial Temperature Statistics")
    
    col1, col2, col3, col4, col5 = st.columns(5, gap="small")
    with col1:
        st.metric("Max Temp District", df_spatial.loc[df_spatial['Temperature'].idxmax(), 'District'], 
                 f"{df_spatial['Temperature'].max():.1f}°C")
    with col2:
        st.metric("Min Temp District", df_spatial.loc[df_spatial['Temperature'].idxmin(), 'District'],
                 f"{df_spatial['Temperature'].min():.1f}°C")
    with col3:
        temp_range = df_spatial['Temperature'].max() - df_spatial['Temperature'].min()
        st.metric("Temperature Range", f"{temp_range:.1f}°C", 
                 f"(Spatial Variation)")
    with col4:
        st.metric("Avg Temperature", f"{df_spatial['Temperature'].mean():.1f}°C",
                 f"(All Districts)")
    with col5:
        st.metric("Avg Humidity", f"{df_spatial['Humidity'].mean():.0f}%",
                 f"(All Districts)")
    
    # Detailed district comparison table
    st.subheader("Detailed District Comparison")
    
    df_display = df_spatial[['District', 'Temperature', 'Feels Like', 'Humidity']].copy()
    df_display['Temp Anomaly'] = df_display['Temperature'] - df_display['Temperature'].mean()
    df_display['Temperature'] = df_display['Temperature'].round(2)
    df_display['Feels Like'] = df_display['Feels Like'].round(2)
    df_display['Humidity'] = df_display['Humidity'].round(0).astype(int)
    df_display['Temp Anomaly'] = df_display['Temp Anomaly'].round(2)
    
    st.dataframe(df_display, width='stretch')
    
    # Heat gradient map visualization
    st.subheader("Heat Distribution Map")
    
    # Create map with temperature-based colors
    m_heat = folium.Map(location=[28.6139, 77.2090], zoom_start=10)
    
    # Add districts with color intensity based on temperature
    for idx, row in df_spatial.iterrows():
        # Normalize temperature to 0-1 for color mapping
        temp_normalized = (row['Temperature'] - df_spatial['Temperature'].min()) / (df_spatial['Temperature'].max() - df_spatial['Temperature'].min())
        
        # Color mapping: blue (cold) to red (hot)
        if temp_normalized < 0.33:
            color = 'blue'
        elif temp_normalized < 0.66:
            color = 'orange'
        else:
            color = 'red'
        
        popup_text = f"""
<b>{row['District']}</b><br>
Temperature: {row['Temperature']:.1f}°C<br>
Feels Like: {row['Feels Like']:.1f}°C<br>
Humidity: {row['Humidity']:.0f}%<br>
Anomaly: {row['Temperature'] - df_spatial['Temperature'].mean():+.2f}°C
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
    
    # Urban Heat Island Analysis
    st.subheader("Urban Heat Island (UHI) Analysis")
    
    mean_temp = df_spatial['Temperature'].mean()
    df_uhi = df_spatial.copy()
    df_uhi['UHI Intensity'] = df_uhi['Temperature'] - mean_temp
    
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
        title='Urban Heat Island Intensity (Deviation from Mean)',
        xaxis_title='District',
        yaxis_title='Temperature Anomaly (°C)',
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
        **Hottest Zone**: {hottest_district['District']}
        - Temperature Anomaly: +{hottest_district['UHI Intensity']:.2f}°C (above mean)
        - Actual Temperature: {hottest_district['Temperature']:.1f}°C
        """)
    with col2:
        st.info(f"""
        **Coolest Zone**: {coolest_district['District']}
        - Temperature Anomaly: {coolest_district['UHI Intensity']:.2f}°C (below mean)
        - Actual Temperature: {coolest_district['Temperature']:.1f}°C
        """)

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
                'Temperature': next((item['Temperature'] for item in district_temps if item['District'] == name), None)
            })
        except:
            # If sampling fails, use default NDVI
            ndvi_values.append({
                'City': name,
                'NDVI': 0.3,  # Default moderate vegetation
                'Temperature': next((item['Temperature'] for item in district_temps if item['District'] == name), None)
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
        value=datetime.date(2025, 12, 31),
        min_value=datetime.date(2000, 1, 1),
        max_value=datetime.date.today(),
        help="Select start date for correlation analysis (MODIS data available from 2000)"
    )

with col_date2:
    corr_end_date = st.date_input(
        "Analysis End Date",
        value=datetime.date(2026, 1, 30),
        min_value=datetime.date(2000, 1, 1),
        max_value=datetime.date.today(),
        help="Select end date for correlation analysis"
    )

# Validate date range
if corr_start_date >= corr_end_date:
    st.error("⚠️ Start date must be before end date!")
    st.stop()

st.info(f"📊 Analyzing data from **{corr_start_date}** to **{corr_end_date}** ({(corr_end_date - corr_start_date).days} days)")

try:
    # Sample data from Delhi districts using Earth Engine
    import pandas as pd
    import numpy as np
    
    # Create sample points across Delhi
    if districts_geometry:
        sampling_geometry = districts_geometry
    else:
        sampling_geometry = region
    
    # Get LST data using selected date range
    lst_image = (
        ee.ImageCollection("MODIS/061/MOD11A1")
        .filterDate(corr_start_date.isoformat(), corr_end_date.isoformat())
        .select("LST_Day_1km")
        .mean()
    )
    lst_celsius_sample = lst_image.multiply(0.02).subtract(273.15)
    
    # Get NDVI data using selected date range
    ndvi_image = (
        ee.ImageCollection("MODIS/061/MOD13A2")
        .filterDate(corr_start_date.isoformat(), corr_end_date.isoformat())
        .select("NDVI")
        .mean()
    ).divide(10000)
    
    # Get Land Cover data
    lulc_image = ee.ImageCollection("ESA/WorldCover/v200").first()
    
    # Combine all bands
    combined_image = lst_celsius_sample.addBands(ndvi_image).addBands(lulc_image)
    combined_image = combined_image.select(['LST_Day_1km', 'NDVI', 'Map'], ['LST', 'NDVI', 'LandCover'])
    
    # Sample random points
    with st.spinner("Sampling data across Delhi districts..."):
        sample_points = combined_image.sample(
            region=sampling_geometry,
            scale=500,  # 500m resolution
            numPixels=500,  # Sample 500 points
            seed=42,
            geometries=True
        )
        
        # Get the data
        sample_data = sample_points.getInfo()
        
        if sample_data and 'features' in sample_data and len(sample_data['features']) > 0:
            # Extract data into DataFrame
            data_list = []
            for feature in sample_data['features']:
                props = feature['properties']
                if 'LST' in props and 'NDVI' in props and 'LandCover' in props:
                    data_list.append({
                        'LST': props['LST'],
                        'NDVI': props['NDVI'],
                        'LandCover': props['LandCover']
                    })
            
            df_corr = pd.DataFrame(data_list)
            
            # Filter out invalid values
            df_corr = df_corr[(df_corr['LST'] > -50) & (df_corr['LST'] < 60)]  # Reasonable temperature range
            df_corr = df_corr[(df_corr['NDVI'] >= -1) & (df_corr['NDVI'] <= 1)]  # Valid NDVI range
            
            # Map land cover codes to names
            lulc_names = {
                10: 'Tree Cover', 20: 'Shrubland', 30: 'Grassland', 40: 'Cropland',
                50: 'Built-up', 60: 'Bare/Sparse', 70: 'Snow/Ice', 80: 'Water',
                90: 'Wetland', 95: 'Mangroves', 100: 'Moss/Lichen'
            }
            df_corr['LandCover_Name'] = df_corr['LandCover'].map(lulc_names).fillna('Other')
            
            if len(df_corr) > 10:  # Need sufficient data points
                st.success(f"✅ Sampled {len(df_corr)} points across Delhi districts")
                
                # Calculate correlations
                corr_ndvi_lst = df_corr['NDVI'].corr(df_corr['LST'])
                
                # Display key metrics
                st.subheader("Correlation Statistics")
                col1, col2, col3, col4 = st.columns(4, gap="small")
                
                with col1:
                    st.metric(
                        "NDVI-LST Correlation",
                        f"{corr_ndvi_lst:.3f}",
                        "Negative = vegetation cools"
                    )
                
                with col2:
                    urban_temp = df_corr[df_corr['LandCover'] == 50]['LST'].mean() if 50 in df_corr['LandCover'].values else 0
                    st.metric(
                        "Avg Urban Temperature",
                        f"{urban_temp:.1f}°C" if urban_temp > 0 else "N/A",
                        "Built-up areas"
                    )
                
                with col3:
                    veg_temp = df_corr[df_corr['LandCover'].isin([10, 20, 30])]['LST'].mean() if any(lc in df_corr['LandCover'].values for lc in [10, 20, 30]) else 0
                    st.metric(
                        "Avg Vegetation Temperature",
                        f"{veg_temp:.1f}°C" if veg_temp > 0 else "N/A",
                        "Green areas"
                    )
                
                with col4:
                    if urban_temp > 0 and veg_temp > 0:
                        temp_diff = urban_temp - veg_temp
                        st.metric(
                            "Urban Heat Island Effect",
                            f"{temp_diff:.1f}°C",
                            "Urban vs Vegetation"
                        )
                    else:
                        st.metric("Urban Heat Island Effect", "N/A", "Insufficient data")
                
                # Visualizations
                st.subheader("Correlation Visualizations")
                
                col1, col2 = st.columns([1, 1], gap="medium")
                
                # NDVI vs LST scatter plot
                with col1:
                    fig_scatter = go.Figure()
                    
                    # Color by land cover
                    for lc_code, lc_name in lulc_names.items():
                        df_lc = df_corr[df_corr['LandCover'] == lc_code]
                        if len(df_lc) > 0:
                            fig_scatter.add_trace(go.Scatter(
                                x=df_lc['NDVI'],
                                y=df_lc['LST'],
                                mode='markers',
                                name=lc_name,
                                marker=dict(size=8, opacity=0.6)
                            ))
                    
                    # Add trend line
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
                        height=450,
                        template='plotly_white',
                        showlegend=True
                    )
                    
                    st.plotly_chart(fig_scatter, width='stretch')
                
                # Temperature by Land Cover boxplot
                with col2:
                    fig_box = go.Figure()
                    
                    for lc_code, lc_name in lulc_names.items():
                        df_lc = df_corr[df_corr['LandCover'] == lc_code]
                        if len(df_lc) > 0:
                            fig_box.add_trace(go.Box(
                                y=df_lc['LST'],
                                name=lc_name,
                                boxmean='sd'
                            ))
                    
                    fig_box.update_layout(
                        title='Temperature Distribution by Land Use Type',
                        yaxis_title='Land Surface Temperature (°C)',
                        height=450,
                        template='plotly_white',
                        showlegend=False
                    )
                    
                    st.plotly_chart(fig_box, width='stretch')
                
                # Land cover statistics table
                st.subheader("Temperature Statistics by Land Use Type")
                
                lulc_stats = df_corr.groupby('LandCover_Name')['LST'].agg([
                    ('Count', 'count'),
                    ('Mean Temp (°C)', 'mean'),
                    ('Std Dev', 'std'),
                    ('Min Temp (°C)', 'min'),
                    ('Max Temp (°C)', 'max')
                ]).round(2)
                
                lulc_stats = lulc_stats.sort_values('Mean Temp (°C)', ascending=False)
                st.dataframe(lulc_stats, width='stretch')
                
                # Key Insights
                st.subheader("🔍 Key Insights")
                
                insights = []
                
                # NDVI-LST correlation insight
                if corr_ndvi_lst < -0.3:
                    insights.append(
                        "✅ **Strong Cooling Effect of Vegetation**: Strong negative correlation between NDVI and LST "
                        f"({corr_ndvi_lst:.3f}) confirms that vegetation significantly reduces surface temperatures."
                    )
                elif corr_ndvi_lst < -0.1:
                    insights.append(
                        "⚠️ **Moderate Cooling Effect**: Moderate negative correlation "
                        f"({corr_ndvi_lst:.3f}) shows vegetation provides some cooling, but other factors also matter."
                    )
                
                # Urban heat island insight
                if urban_temp > 0 and veg_temp > 0 and (urban_temp - veg_temp) > 2:
                    insights.append(
                        f"🔥 **Significant Urban Heat Island**: Built-up areas are {(urban_temp - veg_temp):.1f}°C hotter "
                        f"than vegetated areas on average, highlighting the need for urban greening strategies."
                    )
                
                # Hottest land cover
                if len(lulc_stats) > 0:
                    hottest_lc = lulc_stats.index[0]
                    hottest_temp = lulc_stats.iloc[0]['Mean Temp (°C)']
                    insights.append(
                        f"🌡️ **Hottest Land Cover Type**: {hottest_lc} areas show the highest average temperature "
                        f"({hottest_temp:.1f}°C), indicating priority zones for cooling interventions."
                    )
                
                # Coolest land cover
                if len(lulc_stats) > 1:
                    coolest_lc = lulc_stats.index[-1]
                    coolest_temp = lulc_stats.iloc[-1]['Mean Temp (°C)']
                    insights.append(
                        f"❄️ **Coolest Land Cover Type**: {coolest_lc} areas maintain the lowest temperatures "
                        f"({coolest_temp:.1f}°C), demonstrating effective natural cooling."
                    )
                
                for insight in insights:
                    st.info(insight)
                
                # Recommendations
                st.subheader("💡 Recommendations")
                
                recommendations = [
                    "🌳 **Increase Urban Vegetation**: Target built-up areas with low NDVI for tree planting and green space development.",
                    "🏙️ **Smart Urban Planning**: Design new developments with adequate green spaces to mitigate heat buildup.",
                    "💧 **Expand Water Bodies**: Consider adding water features in hot zones for localized cooling effects.",
                    "🌿 **Green Roofs & Walls**: Implement vegetation on buildings in dense urban areas where ground space is limited.",
                    "📊 **Continuous Monitoring**: Regular satellite monitoring to track vegetation health and temperature trends."
                ]
                
                for rec in recommendations:
                    st.markdown(f"- {rec}")
                
            else:
                st.warning("Insufficient data points for correlation analysis. Try adjusting the date range.")
        else:
            st.warning("No data available for correlation analysis. Check your date range and area selection.")
            
except Exception as corr_error:
    st.error(f"Error in correlation analysis: {str(corr_error)}")
    st.info("This analysis requires Earth Engine data. Make sure your date range has available data.")

# ==================== End of Correlation Analysis ====================

st.subheader("Live Heat Alerts for Delhi-NCR Region")
for name, lat, lon in locations:
    w = get_weather(lat, lon)
    st.write(f"**{name}**: {w['temperature']} °C, Feels Like: {w['feels_like']} °C, Humidity: {w['humidity']} %")

st.caption("Satellite Data Source: MODIS LST | Weather Data Source: OpenWeather API")
