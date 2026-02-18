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

st.set_page_config(layout="wide")
st_autorefresh(interval=300000)

st.title("Delhi-NCR Urban Heat Monitoring Dashboard")
st.markdown("""
This dashboard combines:
- **Real-Time Air temperature** (OpenWeather API)
- **Satellite-Derived Land Surface Temperature** (MODIS LST)
Covering **Delhi + NCR Region**.
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

col1, col2 = st.columns(2)

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

# Function to load Delhi districts from KML file
@st.cache_data
def load_delhi_districts_from_kml():
    """Load Delhi district boundaries from GeoJSON/KML file"""
    try:
        import geopandas as gpd
        
        # Get absolute path (works in both local and cloud deployment)
        current_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Try GeoJSON first (more reliable in cloud deployments)
        geojson_path = os.path.join(current_dir, "delhi_admin.geojson")
        kml_path = os.path.join(current_dir, "delhi_admin.kml")
        
        # Prefer GeoJSON if available
        if os.path.exists(geojson_path):
            gdf = gpd.read_file(geojson_path)
            st.success(f"✅ Loaded {len(gdf)} districts from GeoJSON")
        elif os.path.exists(kml_path):
            # Fallback to KML if GeoJSON not available
            import fiona
            try:
                fiona.drvsupport.supported_drivers['KML'] = 'rw'
                fiona.drvsupport.supported_drivers['LIBKML'] = 'rw'
            except:
                pass
            gdf = gpd.read_file(kml_path, driver='KML')
            st.success(f"✅ Loaded {len(gdf)} districts from KML")
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
vis_params = {
    "min": -5,
    "max": 50,
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
    
    # Clip to district boundaries if available
    if districts_geometry:
        lst_clipped = lst_celsius.clip(districts_geometry)
        m.add_ee_layer(lst_clipped, vis_params, "🌡️ Land Surface Temperature (°C)", opacity=0.6)
    else:
        m.add_ee_layer(lst_celsius, vis_params, "🌡️ Land Surface Temperature (°C)", opacity=0.6)
    
    # Add NDVI-LST Correlation Layer
    try:
        modis_ndvi = (
            ee.ImageCollection("MODIS/061/MOD13A2")
            .filterDate(modis_start_date.isoformat(), modis_end_date.isoformat())
            .select("NDVI")
            .mean()
        )
        ndvi = modis_ndvi.divide(10000)
        
        # Compute correlation using local neighborhood statistics
        ndvi_mean = ndvi.reduceNeighborhood(ee.Reducer.mean(), ee.Kernel.square(3))
        lst_mean = lst_celsius.reduceNeighborhood(ee.Reducer.mean(), ee.Kernel.square(3))
        
        ndvi_diff = ndvi.subtract(ndvi_mean)
        lst_diff = lst_celsius.subtract(lst_mean)
        
        covariance = ndvi_diff.multiply(lst_diff).reduceNeighborhood(ee.Reducer.mean(), ee.Kernel.square(3))
        ndvi_std = ndvi.reduceNeighborhood(ee.Reducer.stdDev(), ee.Kernel.square(3))
        lst_std = lst_celsius.reduceNeighborhood(ee.Reducer.stdDev(), ee.Kernel.square(3))
        
        # Calculate Pearson correlation
        correlation = covariance.divide(ndvi_std.multiply(lst_std))
        
        # Clip to Delhi region for all districts
        if districts_geometry:
            correlation_clipped = correlation.clip(districts_geometry)
        else:
            correlation_clipped = correlation.clip(region)
        
        # Visualization parameters for correlation with enhanced color palette
        corr_vis_params = {
            'min': -1,
            'max': 1,
            'palette': [
                '#2c0735',  # Deep purple - Strong negative
                '#5D1C97',  # Purple - Negative
                '#1F77B4',  # Blue - Negative
                '#17BECF',  # Cyan - Weak negative
                '#E8E8E8',  # Light gray - Neutral
                '#FFEB3B',  # Bright yellow - Weak positive
                '#FF9800',  # Orange - Positive
                '#E74C3C',  # Red - Strong positive
                '#8B0000',  # Dark red - Very strong positive
            ]
        }
        
        m.add_ee_layer(correlation_clipped, corr_vis_params, "📊 NDVI-LST Correlation", opacity=0.5)
        
    except Exception as corr_error:
        st.warning(f"Could not load correlation layer: {str(corr_error)}")
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

# Add layer control to the map
folium.LayerControl(position='topright', collapsed=False).add_to(m)

# Render map in Streamlit
st_folium(m, width=1500, height=600)

# Time Series Analysis of MODIS LST
st.subheader("Time Series Analysis - Historical MODIS Land Surface Temperature")# Date range selector
col1, col2 = st.columns(2)
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
        col1, col2, col3, col4 = st.columns(4)
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
    col1, col2 = st.columns(2)
    
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
    
    col1, col2, col3, col4, col5 = st.columns(5)
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
    
    st_folium(m_heat, width=1500, height=600)
    
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
    
    col1, col2 = st.columns(2)
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
    col1, col2 = st.columns(2)
    
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
    
    # Calculate correlation
    correlation = df_greenery['NDVI'].corr(df_greenery['Temperature'])
    
    # Greenery Impact Analysis
    st.subheader("Greenery Impact on UHI - Statistical Analysis")
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Correlation Coefficient", f"{correlation:.3f}",
                 "Negative = More vegetation = Lower temp")
    with col2:
        avg_ndvi = df_greenery['NDVI'].mean()
        st.metric("Avg Vegetation (NDVI)", f"{avg_ndvi:.3f}",
                 "Range: -1 to 1")
    with col3:
        max_ndvi_city = df_greenery.loc[df_greenery['NDVI'].idxmax()]
        st.metric("Greenest City", max_ndvi_city['City'],
                 f"NDVI: {max_ndvi_city['NDVI']:.3f}")
    with col4:
        min_ndvi_city = df_greenery.loc[df_greenery['NDVI'].idxmin()]
        st.metric("Least Green City", min_ndvi_city['City'],
                 f"NDVI: {min_ndvi_city['NDVI']:.3f}")
    
    # Detailed analysis table
    st.subheader("Greenery-Temperature Relationship Details")
    
    df_analysis = df_greenery.copy()
    df_analysis['Temperature'] = df_analysis['Temperature'].round(2)
    df_analysis['NDVI'] = df_analysis['NDVI'].round(4)
    df_analysis['Temp from Mean'] = (df_analysis['Temperature'] - df_analysis['Temperature'].mean()).round(2)
    df_analysis = df_analysis.sort_values('NDVI', ascending=False)
    
    st.dataframe(df_analysis, width='stretch')
    
    # Key Insights
    st.subheader("Key Insights")
    
    if correlation < -0.3:
        insight_text = f"""
        ✅ **Strong Inverse Relationship**: There is a strong negative correlation ({correlation:.3f}) between 
        vegetation and temperature. Cities with more vegetation tend to be cooler, indicating that greenery 
        effectively mitigates the urban heat island effect.
        
        **Recommendation**: Increase green spaces (parks, trees, gardens) in areas with low vegetation 
        to reduce local temperatures.
        """
    elif correlation < 0:
        insight_text = f"""
        ⚠️ **Moderate Inverse Relationship**: There is a moderate negative correlation ({correlation:.3f}) 
        between vegetation and temperature. Some greenery helps cool urban areas, but other factors 
        (building density, traffic, etc.) also play significant roles.
        
        **Recommendation**: Expand vegetation coverage, especially in high-temperature areas.
        """
    else:
        insight_text = f"""
        ⚠️ **Weak/Positive Relationship**: The correlation ({correlation:.3f}) suggests that vegetation 
        alone may not be the dominant factor in temperature variations. Urban form, water bodies, 
        and building materials also significantly influence local temperatures.
        
        **Recommendation**: Implement comprehensive urban cooling strategies combining vegetation, 
        reflective surfaces, and improved urban planning.
        """
    
    st.info(insight_text)
    
    # City-specific recommendations
    st.subheader("City-Specific Recommendations")
    
    for idx, row in df_analysis.iterrows():
        if row['NDVI'] < 0.3:
            recommendation = f"🌳 **Priority for Greening**: {row['City']} has low vegetation ({row['NDVI']:.3f}). Urgent action needed to increase green spaces."
            color = "red"
        elif row['NDVI'] < 0.5:
            recommendation = f"🌱 **Moderate Greening**: {row['City']} has moderate vegetation ({row['NDVI']:.3f}). Continue expanding green infrastructure."
            color = "orange"
        else:
            recommendation = f"✅ **Well-Vegetated**: {row['City']} has good vegetation coverage ({row['NDVI']:.3f}). Maintain and expand existing green spaces."
            color = "green"
        
        st.write(recommendation)

except Exception as e:
    st.error(f"Error in greenery analysis: {str(e)}")


st.subheader("Live Heat Alerts for Delhi-NCR Region")
for name, lat, lon in locations:
    w = get_weather(lat, lon)
    st.write(f"**{name}**: {w['temperature']} °C, Feels Like: {w['feels_like']} °C, Humidity: {w['humidity']} %")

st.caption("Satellite Data Source: MODIS LST | Weather Data Source: OpenWeather API")
