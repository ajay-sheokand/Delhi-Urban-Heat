from enum import auto
import streamlit as st
import requests
import folium
from streamlit_folium import st_folium
from streamlit_autorefresh import st_autorefresh
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta

import ee
from google.oauth2 import service_account

st.set_page_config(layout="wide")
st_autorefresh(interval=60000)

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

# Define Delhi-NCR region
#region = ee.Geometry.Rectangle([76.84, 27.39, 78.57, 28.88])
region = ee.Geometry.Rectangle([76.84, 27.39, 78.57, 28.88])


st.subheader("MODIS Satellite-Derived Daily Land Surface Temperature (LST)")

# Fetch MODIS LST
lst = (
    ee.ImageCollection("MODIS/061/MOD11A1")
    .filterDate("2025-12-31", "2026-01-30")
    .select("LST_Day_1km")
    .mean()
)

lst_celsius = lst.multiply(0.02).subtract(273.15)

# Create a plain Folium map
m = folium.Map(location=[28.6139, 77.2090], zoom_start=10)

# Function to add Earth Engine layer to Folium
def add_ee_layer(self, ee_image_object, vis_params, name, opacity=1.0):
    map_id_dict = ee.Image(ee_image_object).getMapId(vis_params)
    folium.raster_layers.TileLayer(
        tiles=map_id_dict['tile_fetcher'].url_format,
        attr='Google Earth Engine',
        name=name,
        overlay=True,
        control=True,
        opacity= opacity,
    ).add_to(self)

folium.Map.add_ee_layer = add_ee_layer

# Add MODIS LST layer
vis_params = {
    "min": 25,
    "max": 50,
    "palette": ["blue", "green", "yellow", "orange", "red"],
}

lst = (
    ee.ImageCollection("MODIS/061/MOD11A1")  # Updated collection
    .filterDate("2025-12-31", "2026-01-30")
    .select("LST_Day_1km")
    .mean()
)


if lst.bandNames().size().getInfo() == 0:
    st.error("No MODIS images found for the selected date!")
else:
    lst_celsius = lst.multiply(0.02).subtract(273.15)
    lst_smooth = (
        lst_celsius.resample("bilinear").reproject(crs="EPSG:4326", scale=250)
    )
    m.add_ee_layer(lst_smooth.clip(region), vis_params, "MODIS LST Smooth Heat Map(°C)", opacity=0.5)

# Locations for weather monitoring - Delhi-NCR cities
locations = [
    ("Delhi", 28.6139, 77.2090),
    ("Gurgaon", 28.4595, 77.0266),
    ("Noida", 28.5355, 77.3910),
    ("Faridabad", 28.4089, 77.3178),
    ("Ghaziabad", 28.6692, 77.4538),
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

# Add weather markers to map
for name, lat, lon in locations:
    w = get_weather(lat, lon)
    alert = heat_alert(w["temperature"])
    popup = f"""
<b>{name}</b><br>
Temperature: {w['temperature']} °C<br>
Feels Like: {w['feels_like']} °C<br>
Humidity: {w['humidity']} %<br>
Status: {alert}
"""
    folium.Marker(
        location=[lat, lon],
        popup=popup,
        icon=folium.Icon(color="red" if w["temperature"] >= 35 else "green"),
    ).add_to(m)

# Render map in Streamlit
st_folium(m, width=1500, height=600)

# Time Series Analysis of MODIS LST
st.subheader("Time Series Analysis - Historical MODIS Land Surface Temperature")

# Date range selector
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
        
        st.plotly_chart(fig, use_container_width=True)
        
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
        
        st.plotly_chart(fig_bar, use_container_width=True)
    
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
        
        st.plotly_chart(fig_scatter, use_container_width=True)
    
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
    
    st.dataframe(df_display, use_container_width=True)
    
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
    
    st.plotly_chart(fig_uhi, use_container_width=True)
    
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


st.subheader("Live Heat Alerts for Delhi-NCR Region")
for name, lat, lon in locations:
    w = get_weather(lat, lon)
    st.write(f"**{name}**: {w['temperature']} °C, Feels Like: {w['feels_like']} °C, Humidity: {w['humidity']} %")

st.caption("Satellite Data Source: MODIS LST | Weather Data Source: OpenWeather API")
