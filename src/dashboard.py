import streamlit as st
import snowflake.connector
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import folium
from streamlit_folium import folium_static
import datetime
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.utils import get_snowflake_connection

st.set_page_config(
    page_title="AirVue Pakistan",
    page_icon="🌿",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================================
# OLIVE & CREAM CSS - PERFECT COLOR BALANCE
# ============================================================
st.markdown("""
    <style>
        /* ----- MAIN BACKGROUND (CREAM) ----- */
        .stApp {
            background-color: #FDFBF7;
        }
        .stApp p, .stApp div, .stApp span, .stApp label {
            color: #2D2D2D !important;
        }

        /* ----- SIDEBAR (LIGHT OLIVE) ----- */
        .css-1d391kg, [data-testid="stSidebar"] {
            background-color: #EAE5D9 !important;
        }
        .css-1d391kg * {
            color: #2D2D2D !important;
        }

        /* ----- HEADINGS (OLIVE GREEN) ----- */
        h1, h2, h3, h4, .stMarkdown h1, .stMarkdown h2, .stMarkdown h3 {
            color: #4A5D23 !important;
            font-weight: bold !important;
        }

        /* ----- SUBHEADINGS / BODY TEXT (DARK) ----- */
        .stMarkdown p, .stMarkdown li, .stText, .stCaption {
            color: #2D2D2D !important;
        }

        /* ----- METRIC CARDS (White + Olive Border) ----- */
        [data-testid="metric-container"] {
            background-color: #FFFFFF !important;
            border: 2px solid #6B8E23 !important;
            border-radius: 12px !important;
            padding: 15px !important;
            box-shadow: 0 4px 12px rgba(107, 142, 35, 0.15) !important;
            transition: transform 0.2s !important;
        }
        [data-testid="metric-container"]:hover {
            transform: scale(1.02) !important;
            box-shadow: 0 6px 16px rgba(107, 142, 35, 0.25) !important;
        }
        [data-testid="metric-container"] .stMetricValue {
            color: #1A1A1A !important;
            font-weight: bold !important;
        }
        [data-testid="metric-container"] .stMetricLabel {
            color: #4A5D23 !important;
            font-weight: 600 !important;
        }

        /* ----- DATAFRAME TABLES ----- */
        .dataframe {
            background-color: #FFFFFF !important;
            border-radius: 8px !important;
            border-collapse: collapse !important;
        }
        .dataframe th {
            background-color: #6B8E23 !important;
            color: #FFFFFF !important;
            font-weight: bold !important;
            padding: 10px !important;
        }
        .dataframe td {
            background-color: #FFFFFF !important;
            color: #2D2D2D !important;
            border-bottom: 1px solid #EAE5D9 !important;
            padding: 8px 12px !important;
        }
        .dataframe tr:hover td {
            background-color: #F4F1EA !important;
        }

        /* ----- BUTTONS (OLIVE) ----- */
        .stButton>button {
            background-color: #6B8E23 !important;
            color: #FFFFFF !important;
            border-radius: 8px !important;
            border: none !important;
            padding: 8px 24px !important;
            font-weight: bold !important;
            transition: all 0.3s !important;
        }
        .stButton>button:hover {
            background-color: #4A5D23 !important;
            color: #FFFFFF !important;
            transform: scale(1.05) !important;
        }

        /* ----- SELECTBOX / INPUTS (White + Olive Border) ----- */
        .stSelectbox div, .stNumberInput input, .stTextInput input {
            background-color: #FFFFFF !important;
            border: 1px solid #6B8E23 !important;
            border-radius: 8px !important;
            color: #2D2D2D !important;
        }
        .stSelectbox label, .stNumberInput label, .stTextInput label {
            color: #2D2D2D !important;
        }

        /* 🔥 FORECAST PAGE SELECTBOX FIX */
        .stSelectbox div[data-baseweb="select"] {
            background-color: #FFFFFF !important;
            border: 2px solid #6B8E23 !important;
            border-radius: 8px !important;
        }
        .stSelectbox div[data-baseweb="select"] * {
            color: #2D2D2D !important;
        }
        .js-plotly-plot .plotly .main-svg text {
            fill: #2D2D2D !important;
        }

        /* ----- RADIO BUTTONS (SIDEBAR NAV) ----- */
        .stRadio > div label {
            color: #2D2D2D !important;
            font-weight: 500 !important;
        }
        .stRadio > div label:hover {
            color: #4A5D23 !important;
        }

        /* ----- ALERT / WARNING BOXES ----- */
        .stAlert {
            background-color: #F4F1EA !important;
            border-left: 5px solid #6B8E23 !important;
            color: #2D2D2D !important;
        }
        .stAlert .stMarkdown p {
            color: #2D2D2D !important;
        }

        /* ----- TABS ----- */
        .stTabs [data-baseweb="tab-list"] {
            gap: 8px !important;
        }
        .stTabs [data-baseweb="tab"] {
            background-color: #EAE5D9 !important;
            color: #2D2D2D !important;
            border-radius: 8px 8px 0 0 !important;
            padding: 10px 24px !important;
            font-weight: bold !important;
        }
        .stTabs [aria-selected="true"] {
            background-color: #6B8E23 !important;
            color: #FFFFFF !important;
        }

        /* ----- SIDEBAR BRANDING ----- */
        .sidebar-brand {
            color: #4A5D23 !important;
            font-size: 24px !important;
            font-weight: bold !important;
            text-align: center !important;
        }
        .sidebar-sub {
            color: #6B8E23 !important;
            text-align: center !important;
            font-size: 14px !important;
        }

        /* ----- FOOTER ----- */
        .footer {
            position: fixed !important;
            bottom: 0 !important;
            left: 0 !important;
            width: 100% !important;
            background-color: #EAE5D9 !important;
            border-top: 3px solid #6B8E23 !important;
            color: #4A5D23 !important;
            text-align: center !important;
            padding: 8px !important;
            font-size: 13px !important;
            font-weight: 500 !important;
            z-index: 100 !important;
        }

        /* ----- SCROLLBAR ----- */
        ::-webkit-scrollbar { width: 8px; }
        ::-webkit-scrollbar-track { background: #EAE5D9; }
        ::-webkit-scrollbar-thumb { background: #6B8E23; border-radius: 4px; }
        ::-webkit-scrollbar-thumb:hover { background: #4A5D23; }
    </style>
""", unsafe_allow_html=True)

# ============================================================
# SIDEBAR
# ============================================================
st.sidebar.image("https://www.airnow.gov/assets/img/aqi_square.png", width=100)
st.sidebar.markdown("<div class='sidebar-brand'>🌿 AirVue Pakistan</div>", unsafe_allow_html=True)
st.sidebar.markdown("<div class='sidebar-sub'>Smart City AQI Monitoring</div>", unsafe_allow_html=True)
st.sidebar.markdown("---")
page = st.sidebar.radio("📊 Navigate", ["Home", "🗺️ Live Map", "🔮 Forecast"])

# ============================================================
# CACHE FUNCTIONS
# ============================================================
@st.cache_data(ttl=30, show_spinner=False)
def load_gold_data():
    try:
        conn = get_snowflake_connection()
        df = pd.read_sql("SELECT * FROM ANALYTICS.CITY_DAILY ORDER BY REPORT_DATE DESC", conn)
        conn.close()
        df.columns = [col.lower() for col in df.columns]
        return df
    except Exception as e:
        st.error(f"❌ Gold data load failed: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=30, show_spinner=False)
def load_silver_recent():
    try:
        conn = get_snowflake_connection()
        df = pd.read_sql("""
            SELECT * FROM CLEAN.AQI_CLEAN 
            WHERE RECORDED_AT >= DATEADD(hour, -6, CURRENT_TIMESTAMP())
            ORDER BY RECORDED_AT DESC
        """, conn)
        conn.close()
        df.columns = [col.lower() for col in df.columns]
        return df
    except Exception as e:
        st.error(f"❌ Silver data load failed: {e}")
        return pd.DataFrame()

# ============================================================
# HOME PAGE
# ============================================================
if page == "Home":
    st.markdown("<h1 style='text-align:center;'>🌿 AirVue Pakistan</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align:center; color:#6B8E23; font-size:18px;'>Real-time Air Quality & Livability Index for 5 Major Cities</p>", unsafe_allow_html=True)
    
    gold_df = load_gold_data()
    silver_df = load_silver_recent()

    if gold_df.empty:
        st.warning("⏳ Gold table is empty. Please wait for the Task to run (2-3 mins) or run ETL manually.")
    if silver_df.empty:
        st.info("💡 No recent silver data. Start the simulator to generate readings.")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        if not gold_df.empty and 'avg_aqi' in gold_df.columns and 'city' in gold_df.columns:
            idx = gold_df['avg_aqi'].idxmax()
            st.metric("🔥 Highest AQI", f"{gold_df.loc[idx, 'city']} ({gold_df['avg_aqi'].max():.0f})")
        else:
            st.metric("🔥 Highest AQI", "N/A")
    with col2:
        st.metric("📊 Total Readings", f"{gold_df['reading_count'].sum():,}" if not gold_df.empty else "0")
    with col3:
        if not gold_df.empty and 'dominant_risk' in gold_df.columns:
            critical = gold_df[gold_df['dominant_risk']=='CRITICAL']['reading_count'].sum()
            total = gold_df['reading_count'].sum()
            pct = (critical / total * 100) if total > 0 else 0
            st.metric("⚠️ % Critical", f"{pct:.1f}%")
        else:
            st.metric("⚠️ % Critical", "0%")
    with col4:
        if not gold_df.empty and 'report_date' in gold_df.columns:
            st.metric("📅 Data As Of", gold_df['report_date'].max().strftime('%Y-%m-%d'))
        else:
            st.metric("📅 Data As Of", "No Data")

    st.subheader("📊 City-wise AQI & Livability Score")
    if not gold_df.empty and 'city' in gold_df.columns and 'avg_aqi' in gold_df.columns:
        hover = {'avg_aqi': ':.2f'}
        if 'livability_score' in gold_df.columns:
            hover['livability_score'] = ':.2f'
        if 'health_advisory' in gold_df.columns:
            hover['health_advisory'] = True
        fig = px.bar(gold_df, x='city', y='avg_aqi', color='avg_aqi',
                     color_continuous_scale='RdYlGn_r', hover_data=hover,
                     text=('livability_score' if 'livability_score' in gold_df.columns else None),
                     title="AQI with Livability Score")
        fig.update_traces(texttemplate='Liv: %{text}', textposition='outside')
        fig.update_layout(plot_bgcolor='#FAF8F4', paper_bgcolor='#FAF8F4', font_color='#2D2D2D', title_font_color='#4A5D23')
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("⏳ Waiting for gold data...")

    st.subheader("📈 AQI Trend (Last 6 Hours)")
    if not silver_df.empty and 'city' in silver_df.columns and 'recorded_at' in silver_df.columns:
        silver_df['time_bucket'] = silver_df['recorded_at'].dt.floor('10min')
        trend = silver_df.groupby(['time_bucket', 'city'])['aqi_value'].mean().reset_index()
        fig = px.line(trend, x='time_bucket', y='aqi_value', color='city', title="Real-time Trend")
        fig.update_layout(plot_bgcolor='#FAF8F4', paper_bgcolor='#FAF8F4', font_color='#2D2D2D', title_font_color='#4A5D23')
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No recent silver data.")

    st.subheader("📋 Live Critical Alerts")
    if not silver_df.empty:
        if 'health_risk' in silver_df.columns:
            def color_risk(v):
                c = 'green' if v=='LOW' else 'yellow' if v=='MEDIUM' else 'orange' if v=='HIGH' else 'red'
                return f'background-color:{c};color:white'
            st.dataframe(silver_df.head(20).style.map(color_risk, subset=['health_risk']), use_container_width=True)
        else:
            st.dataframe(silver_df.head(20), use_container_width=True)

# ============================================================
# MAP PAGE
# ============================================================
elif page == "🗺️ Live Map":
    st.markdown("<h1 style='color:#4A5D23;'>🗺️ Live AQI Map</h1>", unsafe_allow_html=True)
    silver_df = load_silver_recent()
    if not silver_df.empty and 'city' in silver_df.columns and 'recorded_at' in silver_df.columns:
        latest_city = silver_df.loc[silver_df.groupby('city')['recorded_at'].idxmax()]
        city_coords = {
            'Karachi': (24.8607, 67.0011),
            'Lahore': (31.5204, 74.3587),
            'Islamabad': (33.6844, 73.0479),
            'Peshawar': (34.0151, 71.5249),
            'Multan': (30.1575, 71.5249)
        }
        m = folium.Map(location=[30.3753, 69.3451], zoom_start=5, tiles='cartodbpositron')
        for _, row in latest_city.iterrows():
            city = row['city']
            lat, lng = city_coords.get(city, (30.0, 70.0))
            aqi = row['aqi_value']
            color = 'green' if aqi < 50 else 'yellow' if aqi < 100 else 'orange' if aqi < 200 else 'red'
            folium.CircleMarker(
                location=[lat, lng],
                radius=25,
                popup=f"<b>{city}</b><br>AQI: {aqi:.0f}<br>Risk: {row.get('health_risk', 'N/A')}",
                color=color,
                fill=True,
                fillColor=color,
                fillOpacity=0.8,
                tooltip=f"{city} - {aqi:.0f}"
            ).add_to(m)
        folium_static(m, width=1000)
    else:
        st.warning("No data for map.")
    st.caption("⚡ Map loads fast on subsequent clicks due to caching.")

# ============================================================
# FORECAST PAGE
# ============================================================
elif page == "🔮 Forecast":
    st.markdown("<h1 style='color:#4A5D23;'>🔮 6-Hour AQI Forecast</h1>", unsafe_allow_html=True)
    st.markdown("<p style='color:#2D2D2D;'>Select a city to see the predicted AQI trend for the next 6 hours.</p>", unsafe_allow_html=True)
    
    silver_df = load_silver_recent()
    if not silver_df.empty and 'city' in silver_df.columns:
        city = st.selectbox("📍 Select City", silver_df['city'].unique())
        city_data = silver_df[silver_df['city']==city].sort_values('recorded_at')
        
        if len(city_data) >= 10:
            try:
                from prophet import Prophet
                df_prophet = city_data[['recorded_at', 'aqi_value']].rename(columns={'recorded_at': 'ds', 'aqi_value': 'y'})
                model = Prophet()
                model.fit(df_prophet)
                future = model.make_future_dataframe(periods=6, freq='h')
                forecast = model.predict(future)
                fig = model.plot(forecast)
                st.pyplot(fig)
                st.caption("📌 Blue Line: Predicted AQI | Light Blue: Uncertainty Range")
            except Exception as e:
                st.warning(f"⚠️ Forecast error: {e}")
        else:
            st.warning(f"⚠️ Need at least 10 data points for forecast. Only {len(city_data)} available. Let the simulator run longer.")
    else:
        st.info("💡 No data available for forecasting. Start the simulator to generate readings.")

# ============================================================
# FOOTER
# ============================================================
st.markdown("""
    <div class="footer">
        🌿 Powered by Snowflake, Streamlit & OpenAQ | © 2026 AirVue Pakistan
    </div>
""", unsafe_allow_html=True)