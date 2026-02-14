# Münster Urban Heat Monitoring Dashboard

A real-time web application for monitoring urban heat in Münster, Germany using satellite data and weather APIs.

Link: https://munster-urban-heat.streamlit.app/
## Overview

This Streamlit dashboard combines real-time air temperature data from the OpenWeather API with satellite-derived Land Surface Temperature (LST) from NASA's MODIS satellite to provide comprehensive urban heat monitoring for Münster and the North Rhine-Westphalia (NRW) region.

## Features

- **Interactive Map Visualization**: Folium-based map centered on Münster showing the current region of interest with zoom level optimized for city-level analysis
- **Real-Time Weather Data**: Live air temperature, humidity, and "feels like" temperature for 5 key districts in Münster:
  - Altstadt (City Center)
  - Kreuzviertel (Cultural Quarter)
  - Mauritz (South District)
  - Gievenbeck (North District)
  - Kinderhaus (East District)
- **Satellite Temperature Overlay**: MODIS Land Surface Temperature (LST) data visualized on the map with a color gradient (blue to red) representing temperature ranges
- **Time Series Analysis**: Historical analysis of MODIS LST data with:
  - Customizable date range selector (default: last 60 days)
  - Interactive Plotly time series chart
  - Statistical summary (average, max, min temperatures, data points)
- **Heat Alerts**: Real-time alerts based on temperature thresholds:
  - 🔥 Extreme Heat Alert (≥40°C)
  - ⚠️ High Heat Warning (≥35°C)
  - 🌤️ Normal Temperature (<35°C)
- **Auto-Refresh**: Dashboard automatically refreshes every 60 seconds

## Requirements

- Python 3.8+
- Virtual environment (recommended)
- Google Earth Engine API access
- OpenWeather API key

## Installation

1. **Clone or download the repository**:
   ```bash
   cd a:\University_Work\GITHUB_PROJECTS\1-DELHIurbanHEAT
   ```

2. **Create and activate virtual environment**:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
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
3. The JSON credentials file is included in the repo (`gee-streamlit-service-dca01b062e23.json`)

### 3. Streamlit Secrets

Create a `.streamlit/secrets.toml` file in the project root:

```toml
OPENWEATHER_API_KEY = "your_openweather_api_key_here"
GEE_SERVICE_ACCOUNT = "your-service-account@project.iam.gserviceaccount.com"
GEE_PRIVATE_KEY = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
```

## Running the Application

### Option 1: Using Python Module (Recommended)
```powershell
&"A:\University_Work\GITHUB_PROJECTS\1-DELHIurbanHEAT\.venv\Scripts\python.exe" -m streamlit run "a:\University_Work\GITHUB_PROJECTS\1-DELHIurbanHEAT\app.py"
```

### Option 2: With Activated Virtual Environment
```powershell
.\.venv\Scripts\Activate.ps1
streamlit run app.py
```

The app will open in your default browser at `http://localhost:8501`

## Project Structure

```
1-DELHIurbanHEAT/
├── app.py                                    # Main Streamlit application
├── requirements.txt                          # Python dependencies
├── runtime.txt                               # Python version specification
├── environment_var.txt                       # Environment configuration
├── gee-streamlit-service-dca01b062e23.json  # GEE service account credentials
└── README.md                                 # This file
```

## Data Sources

### Real-Time Weather Data
- **Provider**: OpenWeatherMap API
- **Data**: Current temperature, feels-like temperature, humidity
- **Frequency**: Updated every API call

### Satellite Data
- **Provider**: NASA MODIS (Moderate Resolution Imaging Spectroradiometer)
- **Dataset**: MOD11A1 (Daily Land Surface Temperature)
- **Collection**: MODIS/061/MOD11A1
- **Resolution**: 1km
- **Temporal**: Daily observations

## Key Visualization Parameters

### MODIS LST Color Scale
- Blue: ≤25°C (coolest)
- Green: 25-35°C
- Yellow: 35-40°C
- Orange: 40-45°C
- Red: ≥50°C (hottest)

## Dashboard Sections

1. **Title & Introduction**: Overview of the dashboard capabilities
2. **MODIS LST Map**: Interactive Folium map with satellite temperature overlay and weather station markers
3. **Time Series Analysis**: 
   - Date range selector
   - Interactive Plotly chart
   - Statistical metrics
4. **Live Heat Alerts**: Current conditions for all 5 districts

## Troubleshooting

### Common Issues

**Error: "Import 'streamlit' could not be resolved"**
- Solution: Ensure virtual environment is activated and dependencies are installed

**Error: "Error fetching time series data"**
- Solution: Check GEE credentials and ensure service account has Earth Engine access

**Map not centering on Münster**
- Solution: Verify zoom_start parameter is set to 11 (city-level zoom)

**No MODIS data available**
- Solution: Check date range selection and ensure data exists for the period

## Future Enhancements

- Multiple region/city support
- Historical trend analysis and alerts
- Export capabilities for temperature data
- Integration with additional climate datasets
- Urban heat island effect analysis
- Predictive temperature modeling

## Dependencies

See `requirements.txt` for complete list:
- streamlit
- requests
- folium
- streamlit-folium
- streamlit-autorefresh
- geemap
- earthengine-api
- xyzservices
- google-auth
- pandas
- plotly


## Author

Ajay

## Contact

For issues or questions about this dashboard, please refer to the project documentation or contact the development team.

---
**Dashboard Coverage**: Münster, North Rhine-Westphalia (NRW), Germany
