# ==========================================
# 1. CONFIGURACIÓN DE PÁGINA Y ESTILOS
# ==========================================
from datetime import datetime, timedelta
import time
from zoneinfo import ZoneInfo
import pandas as pd
import requests
from sqlalchemy import create_engine, text
import streamlit as st

ZONA_MEXICO = ZoneInfo("America/Mexico_City")

st.set_page_config(
    page_title="Sistema Scada",
    page_icon="https://www.miaa.mx/favicon.ico",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
        /* Ocultar elementos predeterminados de la interfaz de Streamlit */
        #MainMenu {visibility: hidden;}
        header {visibility: hidden;}
        footer {visibility: hidden;}
        
        /* BLOQUEAR LA BARRA LATERAL PARA QUE NUNCA SE PUEDA OCULTAR O COLAPSAR */
        [data-testid="stSidebar"] {
            min-width: 280px !important;
            max-width: 320px !important;
            transform: none !important;
        }
        [data-testid="collapsedControl"] {
            display: none !important;
        }
        button[kind="header"] {
            display: none !important;
        }
        
        /* EVITAR COMPLETAMENTE LA OPACIDAD O EFECTO GRIS CUANDO STREAMLIT SE EJECUTA O ACTUALIZA */
        .stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"], .main, .block-container {
            opacity: 1 !important;
            filter: none !important;
            pointer-events: auto !important;
        }
        [data-testid="stStatusWidget"] {
            display: none !important;
        }
        
        /* Eliminar el espacio superior por defecto de la página */
        .block-container {
            padding-top: 1rem !important;
            padding-bottom: 0rem !important;
        }
        
        header hr, .stApp > header + div hr, [data-testid="stHeader"] hr, hr {
            display: none !important;
        }
        
        .metric-card {
            background-color: #1e293b;
            border: 1px solid #334155;
            padding: 15px;
            border-radius: 8px;
            display: flex;
            align-items: center;
        }
        .metric-content {
            display: flex;
            flex-direction: column;
        }
        .metric-title {
            font-size: 12px;
            color: #94a3b8;
        }
        .metric-value {
            font-size: 20px;
            font-weight: bold;
            color: #f8fafc;
        }
        
        /* Consola con altura exacta alineada */
        .terminal-box {
            background-color: #0b0f19;
            border: 1px solid #22c55e;
            color: #22c55e;
            font-family: 'Courier New', Courier, monospace;
            padding: 15px;
            border-radius: 6px;
            height: 505px;
            overflow-y: scroll;
            font-size: 13px;
            line-height: 1.4;
        }
        
        [data-testid="stVerticalBlock"] [data-testid="stVerticalBlockBorderWrapper"] {
            background-color: #0e1322 !important;
            border: 1px solid #334155 !important;
            border-radius: 8px !important;
            height: 567px !important;
            overflow-y: auto !important;
            padding: 15px !important;
        }
    </style>
""",
    unsafe_allow_html=True,
)

# ==========================================
# 2. GESTIÓN DE LOGS (CONSOLA - HORA MÉXICO)
# ==========================================
if "logs" not in st.session_state:
  st.session_state.logs = [
      f"[{datetime.now(ZONA_MEXICO).strftime('%H:%M:%S')}] Sistema inicializado"
      " correctamente. Esperando ciclo de ejecución..."
  ]


def agregar_log(mensaje):
  timestamp = datetime.now(ZONA_MEXICO).strftime("%H:%M:%S")
  st.session_state.logs.insert(0, f"[{timestamp}] {mensaje}")
  if len(st.session_state.logs) > 300:
    st.session_state.logs.pop()


# ==========================================
# 3. CONEXIONES Y CONSULTAS (SQL Y API)
# ==========================================
url_login = "https://prelec.miaa.mx/auth/v2/login"
url_instalaciones = "https://prelec.miaa.mx/msvc-tecnica/medidores/instalaciones"


def obtener_motor_postgres():
  pg = st.secrets["postgres"]
  connection_string = f"postgresql+psycopg2://{pg['user']}:{pg['password']}@{pg['host']}:{pg['port']}/{pg['database']}"
  return create_engine(connection_string)


@
