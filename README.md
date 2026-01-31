# 🌍 Delhi-NCR Urban Heat Monitoring Dashboard

A **Streamlit web application** that monitors and visualizes **urban heat conditions** across the **Delhi + NCR region** by combining:

- 🌡️ **Real-time air temperature** (OpenWeather API)
- 🛰️ **Satellite-derived Land Surface Temperature (LST)** (MODIS via Google Earth Engine)

This project helps track heat intensity and generate live alerts for major NCR cities.

---

## ✨ Features

✅ Real-time temperature, humidity, and “feels like” data  
✅ Heat alerts for extreme temperature zones  
✅ Interactive Folium map with city markers  
✅ MODIS Satellite Land Surface Temperature layer  
✅ Auto-refresh every 60 seconds  
✅ Covers major NCR cities:

- Delhi  
- Gurgaon  
- Noida  
- Faridabad  
- Ghaziabad  

---

## 🛠️ Tech Stack

- **Python**
- **Streamlit**
- **Folium + streamlit-folium**
- **Google Earth Engine API**
- **OpenWeather API**
- **MODIS Land Surface Temperature Dataset**
- **Streamlit Autorefresh**

---

## 📁 Project Structure

```bash
Delhi-Urban-Heat/
│
├── app.py
├── requirements.txt
├── README.md
└── .streamlit/
    └── secrets.toml
