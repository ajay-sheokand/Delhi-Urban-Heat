# Delhi Urban Heat Monitoring Dashboard

A real-time web application for monitoring urban heat across all 11 Delhi districts using satellite data and weather APIs.

## Overview

This Streamlit dashboard combines real-time air temperature data from the OpenWeather API with satellite-derived Land Surface Temperature (LST) from NASA's MODIS satellite, along with high-resolution Land Use/Land Cover data, to provide comprehensive urban heat monitoring and analysis for Delhi. The dashboard features multi-variable correlation analysis to understand the relationships between vegetation, temperature, and land use patterns.

## Features

- **Interactive Map Visualization**: Responsive Folium-based map centered on Delhi with multiple toggleable layers:
  - Land Surface Temperature (LST) with dynamic color scaling
  - Vegetation Index (NDVI) 
  - Land Use/Land Cover (LULC) at 10m resolution
  - District boundaries for all 11 Delhi districts
  - Real-time weather markers with custom icons
  
- **Real-Time Weather Data**: Live air temperature, humidity, and "feels like" temperature for all 11 Delhi districts:
  - Central Delhi, East Delhi, New Delhi
  - North, North East, North West
  - Shahadra, South, South East, South West, West Delhi
  
- **Satellite Temperature Analysis**: 
  - MODIS Land Surface Temperature (LST) with adaptive color scaling
  - Automatic min/max detection from actual data
  - Dynamic range display showing current temperature spread
  - 1km spatial resolution, daily temporal resolution
  
- **Vegetation Monitoring**:
  - MODIS NDVI (Normalized Difference Vegetation Index)
  - 500m spatial resolution for detailed greenery analysis
  - Sentinel-2 NDVI fallback (10m resolution) when MODIS unavailable
  - Interactive visualization with color-coded vegetation density
  
- **Land Use/Land Cover Analysis**:
  - ESA WorldCover 2021 (10m resolution) - primary source
  - MODIS Land Cover Type (500m resolution) - fallback
  - 11 land cover categories with accurate color coding
  - Interactive legend in lower right corner
  - Area distribution statistics
  
- **Multi-Variable Correlation Analysis**:
  - Analyze relationships between NDVI, LST, and LULC
  - Independent date selection for correlation studies
  - Sample 500 points across Delhi for statistical analysis
  - Visualizations:
    - Land cover area distribution (pie chart)
    - Area coverage by temperature (colored bar chart)
    - NDVI vs LST scatter plot with area-weighted markers
    - Temperature distribution by land use type (box plots)
  - Comprehensive statistics table with area coverage percentages
  - Automated insights on:
    - Dominant land cover types
    - Urban heat island intensity
    - Vegetation cooling effects
    - Temperature extremes by land use
  
- **Time Series Analysis**: Historical analysis of MODIS LST data with:
  - Customizable date range selector (MODIS data from 2000+)
  - Interactive Plotly time series chart
  - Statistical summary (average, max, min temperatures, data points)
  
- **Heat Alerts**: Real-time alerts based on temperature thresholds:
  - 🔥 Extreme Heat Alert (≥40°C)
  - ⚠️ High Heat Warning (≥35°C)
  - 🌤️ Normal Temperature (<35°C)
  
- **Responsive Design**: 
  - Mobile-optimized CSS with breakpoints for phones, tablets, and desktops
  - Adaptive layouts and font sizes
  - Scrollable tables and full-width charts on mobile
  
- **Auto-Refresh**: Dashboard automatically refreshes every 5 minutes

## Requirements

- Python 3.8+
- Virtual environment (recommended)
- Google Earth Engine API access
- OpenWeather API key

## Installation

1. **Clone or download the repository**:
   ```bash
   git clone <repository-url>
   cd 1-DELHIurbanHEAT
   ```

2. **Create and activate virtual environment**:
   ```bash
   python -m venv .venv
   ```
   
   On Windows (PowerShell):
   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```
   
   On Linux/Mac:
   ```bash
   source .venv/bin/activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

## Setup & Configuration

### 1. OpenWeather API Key

1. Sign up at [OpenWeatherMap](https://openweathermap.org/)
2. Get your API key from the account dashboard
3. Add to Streamlit secrets (see below)

### 2. Google Earth Engine API

1. Sign up at [Google Earth Engine](https://earthengine.google.com/)
2. Create a service account:
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create a project
   - Enable Earth Engine API
   - Create a service account with appropriate permissions
   - Generate a JSON key file
3. Save the JSON credentials file securely (do not commit to public repositories)

### 3. Streamlit Secrets

Create a `.streamlit/secrets.toml` file in the project root:

```toml
OPENWEATHER_API_KEY = "your_openweather_api_key_here"
GEE_SERVICE_ACCOUNT = "your-service-account@project.iam.gserviceaccount.com"
GEE_PRIVATE_KEY = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
```

## Running the Application

### Option 1: With Activated Virtual Environment (Recommended)
```bash
# Activate virtual environment first
# Windows PowerShell:
.\.venv\Scripts\Activate.ps1

# Linux/Mac:
# source .venv/bin/activate

# Run the app
streamlit run app.py
```

### Option 2: Using Python Module
```bash
# Windows:
.\.venv\Scripts\python.exe -m streamlit run app.py

# Linux/Mac:
./.venv/bin/python -m streamlit run app.py
```

The app will open in your default browser at `http://localhost:8501`

## Project Structure

```
1-DELHIurbanHEAT/
├── app.py                                    # Main Streamlit application (1500+ lines)
├── delhi_admin.geojson                       # District boundaries (GeoJSON format)
├── requirements.txt                          # Python dependencies
├── runtime.txt                               # Python version specification
├── README.md                                 # This file
├── .streamlit/
│   └── secrets.toml                          # API keys and credentials (not in repo)
├── gee-service-account.json                  # GEE credentials (not in repo)
└── .gitignore                                # Excludes credentials and venv
```

**Important Notes**: 
- `packages.txt` and `fiona` dependency removed to avoid GDAL conflicts in Streamlit Cloud deployment
- Credential files (JSON keys, secrets.toml) should never be committed to version control
- Add sensitive files to `.gitignore`

## Data Sources

### Real-Time Weather Data
- **Provider**: OpenWeatherMap API
- **Data**: Current temperature, feels-like temperature, humidity
- **Coverage**: All 11 Delhi districts
- **Frequency**: Updated every API call (approximately every 5 minutes with auto-refresh)

### Satellite Data - Land Surface Temperature (LST)
- **Provider**: NASA MODIS (Moderate Resolution Imaging Spectroradiometer)
- **Dataset**: MOD11A1.061 (Daily Land Surface Temperature & Emissivity)
- **Collection**: MODIS/061/MOD11A1
- **Spatial Resolution**: 1km
- **Temporal Resolution**: Daily observations
- **Band Used**: LST_Day_1km (Daytime Land Surface Temperature)
- **Data Availability**: 2000 - Present
- **Visualization**: Dynamic color scaling based on actual data range

### Satellite Data - Vegetation Index (NDVI)
- **Primary Source**: NASA MODIS MOD13A2.061
  - **Collection**: MODIS/061/MOD13A2
  - **Spatial Resolution**: 500m
  - **Temporal Resolution**: 16-day composite
  - **Data Availability**: 2000 - Present
- **Fallback Source**: Sentinel-2 MSI Harmonized
  - **Collection**: COPERNICUS/S2_SR_HARMONIZED
  - **Spatial Resolution**: 10m (higher detail)
  - **Temporal Resolution**: ~5 days (varies by location)
  - **Bands Used**: B8 (NIR), B4 (Red)
  - **Cloud Filtering**: <50% cloud coverage

### Land Use/Land Cover (LULC) Data
- **Primary Source**: ESA WorldCover 2021
  - **Collection**: ESA/WorldCover/v200
  - **Spatial Resolution**: 10m (high detail)
  - **Year**: 2021
  - **Classes**: 11 land cover types (Tree Cover, Shrubland, Grassland, Cropland, Built-up, etc.)
  - **Global Coverage**: Based on Sentinel-1 & Sentinel-2 imagery
- **Fallback Source**: MODIS Land Cover Type
  - **Collection**: MODIS/061/MCD12Q1
  - **Spatial Resolution**: 500m
  - **Temporal Resolution**: Annual
  - **Classification**: IGBP (International Geosphere-Biosphere Programme)

### District Boundaries
- **Source**: delhi_admin.geojson
- **Format**: GeoJSON (converted from KML for cloud compatibility)
- **Coverage**: All 11 Delhi administrative districts
- **Size**: 1.26 MB
- **Geometry Type**: MultiPolygon

## Key Visualization Parameters

### MODIS LST Color Scale (Dynamic Range)
The Land Surface Temperature visualization uses an **adaptive color scale** that automatically adjusts to the actual temperature range in the data:

- **Dynamic Min/Max Calculation**: The app analyzes actual LST values to determine the optimal color range
- **10% Buffer**: Adds padding above and below the data range for better visualization
- **Real-time Display**: Shows the actual temperature range being visualized (e.g., "LST Range: 18.5°C to 25.3°C")

**Color Palette** (Blue → Red gradient):
- **Blue tones**: Coolest areas (lower range)
- **Cyan/Light Blue**: Cool-moderate areas
- **Yellow**: Moderate temperatures (mid-range)
- **Orange**: Warm areas
- **Red tones**: Hottest areas (upper range)

This dynamic approach ensures optimal color distribution regardless of season or weather conditions, making temperature variations clearly visible across all Delhi districts.

## Analysis Methodology

### Multi-Variable Correlation Analysis

The dashboard implements a comprehensive statistical analysis to understand the relationships between vegetation (NDVI), temperature (LST), and land use patterns (LULC):

**1. Data Sampling:**
- Collects 500 random sample points across Delhi districts
- Each point contains: LST value, NDVI value, and Land Cover classification
- Spatial resolution: 500m (balanced between detail and processing speed)
- Temporal averaging: Mean values over selected date range

**2. Statistical Calculations:**
- **Pearson Correlation**: Measures linear relationship between NDVI and LST
- **Area Coverage**: Percentage of study area for each land cover type
- **Temperature Statistics**: Mean, standard deviation, min/max by land use type
- **Urban Heat Island Intensity**: Temperature difference between built-up and vegetated areas

**3. Visualizations:**
- **Pie Chart**: Land cover distribution by area
- **Bar Chart**: Area coverage colored by temperature to show impact
- **Scatter Plot**: NDVI vs LST with trend line and area-weighted markers
- **Box Plots**: Temperature distribution within each land cover category

**4. Automated Insights:**
The system analyzes results to identify:
- Dominant land cover types (by area)
- Strength of vegetation cooling effect (correlation coefficient)
- Urban heat island magnitude
- Temperature extremes and their spatial extent
- Total vegetation coverage and adequacy

**5. Recommendations:**
Data-driven strategies generated based on:
- Areas with high temperature and low vegetation
- Land use types with highest thermal impact
- Cooling potential of different interventions

This evidence-based approach helps urban planners and policymakers make informed decisions about heat mitigation strategies.

### NDVI Color Scale
- **Red/Brown**: Low vegetation (NDVI < 0.2)
- **Yellow/Light Green**: Sparse vegetation (NDVI 0.2-0.4)
- **Green**: Moderate vegetation (NDVI 0.4-0.6)
- **Dark Green**: Dense vegetation (NDVI > 0.6)

### Land Use/Land Cover (LULC) Colors
Based on ESA WorldCover 2021 classification:
- **Dark Green** (#006400): Tree Cover
- **Orange-Yellow** (#FFBB22): Shrubland
- **Light Yellow** (#FFFF4C): Grassland
- **Pink-Purple** (#F096FF): Cropland
- **Red** (#FA0000): Built-up/Urban Areas
- **Gray** (#B4B4B4): Bare/Sparse Vegetation
- **White** (#F0F0F0): Snow/Ice
- **Blue** (#0064C8): Permanent Water Bodies
- **Cyan** (#0096A0): Herbaceous Wetland
- **Sea Green** (#00CF75): Mangroves
- **Beige** (#FAE6A0): Moss/Lichen

## Dashboard Sections

1. **Header & Introduction**: 
   - Overview of dashboard capabilities
   - Key features and data sources
   - Mobile device optimization tips

2. **Date Selection**: 
   - Unified date picker for MODIS LST and NDVI layers
   - Date range validation
   - Data availability information

3. **Interactive Map (Main Visualization)**:
   - **Land Surface Temperature Layer**: Dynamic color scaling with real-time range display
   - **NDVI Layer**: Vegetation density visualization
   - **Land Use/Land Cover Layer**: 10m resolution ESA WorldCover with legend
   - **District Boundaries**: All 11 Delhi districts outlined
   - **Weather Markers**: Real-time temperature for each district with custom icons
   - **Layer Control**: Toggle layers on/off in top-right corner
   - **LULC Legend**: Fixed legend in lower-right showing all land cover types

4. **Land Use/Land Cover Analysis**:
   - Area distribution statistics
   - Top 4 land use types by coverage
   - Detailed breakdown table
   - Coverage percentages

5. **Time Series Analysis**: 
   - Date range selector (independent from map visualization)
   - Interactive Plotly chart showing LST trends
   - Statistical metrics (mean, max, min, standard deviation)
   - Data point count

6. **Spatial Distribution Analysis**:
   - Temperature distribution across all 11 districts
   - Urban Heat Island (UHI) intensity analysis
   - Heat distribution visualization
   - District comparison table with rankings

7. **Greenery Impact Analysis**:
   - NDVI distribution by district
   - Vegetation vs Temperature correlation
   - Scatter plot analysis
   - Statistical insights on cooling effects

8. **Multi-Variable Correlation Analysis**:
   - **Independent date selection** for correlation studies
   - **Land Cover Distribution**: Pie chart showing area percentages
   - **Area-Temperature Analysis**: Bar chart colored by temperature
   - **NDVI vs LST**: Scatter plot with area-weighted markers and trend line
   - **Temperature by Land Use**: Box plots showing distribution
   - **Comprehensive Statistics Table**: 
     - Sample counts and area coverage
     - Mean temperature and NDVI by land use
     - Color-coded gradients for easy interpretation
   - **Automated Insights**:
     - Dominant land cover identification
     - NDVI-LST correlation strength
     - Urban heat island quantification
     - Temperature extremes with area context
     - Total vegetation coverage assessment
   - **Recommendations**: Data-driven strategies for urban cooling

9. **Live Heat Alerts**: 
   - Current conditions for all 11 Delhi districts
   - Temperature, feels-like, and humidity
   - Color-coded alerts based on thresholds

## Troubleshooting

### Common Issues

**Error: "Import 'streamlit' could not be resolved"**
- Solution: Ensure virtual environment is activated and dependencies are installed
  ```powershell
  .\.venv\Scripts\Activate.ps1
  pip install -r requirements.txt
  ```

**Error: "Error fetching time series data"**
- Solution: Check GEE credentials and ensure service account has Earth Engine access
- Verify the service account JSON file path is correct

**Map not centering on Delhi**
- Solution: Verify zoom_start parameter is set to 10 (city-level zoom)
- Check that delhi_admin.geojson file exists

**No MODIS data available**
- Solution: Check date range selection and ensure data exists for the period
- MODIS data availability: 2000 - Present
- Try selecting a more recent date range

**LST layer showing single color**
- Solution: This is fixed with dynamic color scaling. If issue persists, check that Earth Engine is calculating min/max properly
- Verify the data range is displayed in the info message

**District boundaries not loading**
- Solution: Ensure delhi_admin.geojson exists in the project root
- Check that geopandas is installed correctly
- Verify file permissions

**Correlation analysis showing no data**
- Solution: 
  - Ensure date range has sufficient MODIS data
  - Try a longer date range (at least 7-14 days)
  - Check that Earth Engine sampling completed successfully

**Deployment errors on Streamlit Cloud**
- Solution:
  - Verify all secrets are configured (OPENWEATHER_API_KEY, GEE credentials)
  - Ensure delhi_admin.geojson is committed to repository
  - Check that packages.txt is NOT present (causes GDAL conflicts)
  - Verify runtime.txt specifies compatible Python version

**LULC legend not visible**
- Solution: The legend is fixed position in lower-right corner. Try scrolling or zooming the page
- On mobile, it may overlap with other elements - this is expected

**Responsive design issues on mobile**
- Solution: 
  - Use landscape orientation for better view
  - Zoom out to see full width of charts
  - Tables are horizontally scrollable

## Recent Enhancements (Implemented)

- ✅ **Dynamic LST Color Scaling**: Adaptive visualization range based on actual data
- ✅ **Land Use/Land Cover Integration**: High-resolution ESA WorldCover layer with legend
- ✅ **Multi-Variable Correlation Analysis**: NDVI-LST-LULC relationships with statistical insights
- ✅ **All 11 Delhi Districts**: Complete coverage with individual weather monitoring
- ✅ **Responsive Design**: Mobile, tablet, and desktop optimization
- ✅ **Area-Weighted Analysis**: Land cover statistics by area coverage
- ✅ **Independent Date Selection**: Separate date pickers for map layers and correlation analysis
- ✅ **Vegetation Fallback**: Sentinel-2 NDVI when MODIS unavailable
- ✅ **District Boundaries**: GeoJSON format for cloud compatibility
- ✅ **Interactive Legends**: Fixed LULC legend, layer control, custom weather icons

## Future Enhancements

- Temporal comparison tools (year-over-year, seasonal analysis)
- Anomaly detection for unusual heat patterns
- Machine learning models for temperature prediction
- Export capabilities (CSV, GeoJSON, images)
- Integration with air quality data
- Historical trend analysis with statistical forecasting
- Custom area selection and analysis
- Report generation for specific districts
- Enhanced mobile features (offline capability, push notifications)
- Integration with urban planning datasets (building density, road networks)

## Dependencies

See `requirements.txt` for complete list. Key dependencies:

**Core Framework:**
- streamlit - Web dashboard framework
- streamlit-folium - Folium maps in Streamlit
- streamlit-autorefresh - Auto-refresh functionality

**Geospatial & Satellite Data:**
- earthengine-api - Google Earth Engine Python API
- geemap - Earth Engine data visualization
- geopandas - Geospatial data processing
- shapely - Geometric operations
- folium - Interactive maps

**Data Processing:**
- pandas - Data manipulation and analysis
- numpy - Numerical computations

**Visualization:**
- plotly - Interactive charts and graphs

**APIs & Authentication:**
- requests - HTTP requests for OpenWeather API
- google-auth - Google Cloud authentication
- xyzservices - Base map tiles

**Note**: `fiona` and GDAL removed to avoid dependency conflicts in cloud deployment. GeoJSON format used instead of KML for district boundaries.


## Author

University Research Project - Delhi Urban Heat Monitoring

## License

This project is for educational and research purposes.

## Contact

For questions, issues, or contributions:
- Open an issue on the project repository
- Refer to the comprehensive documentation above

## Acknowledgments

- **NASA MODIS**: Land Surface Temperature and NDVI satellite data
- **ESA WorldCover**: High-resolution land cover classification
- **Google Earth Engine**: Geospatial analysis platform
- **OpenWeatherMap**: Real-time weather data API
- **Streamlit**: Web application framework

---
**Last Updated**: February 19, 2026  
**Coverage Area**: Delhi, India (All 11 Administrative Districts)  
**Version**: 2.0 - Multi-variable correlation analysis with LULC integration
