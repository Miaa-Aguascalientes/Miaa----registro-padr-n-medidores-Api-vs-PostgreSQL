import streamlit as st
import requests
import json
import pandas as pd
from sqlalchemy import create_engine
import plotly.express as px
import plotly.graph_objects as go
import folium
from folium.plugins import Fullscreen
from streamlit_folium import st_folium
import numpy as np
from shapely.geometry import Point, Polygon
import pydeck as pdk
import datetime

# ==============================================================================
# SECCIÓN 1: CONFIGURACIÓN GENERAL DE LA PÁGINA Y ESTILOS CSS
# ==============================================================================

st.set_page_config(
    page_title="Dashboard Instalación Medidores Inteligentes", 
    page_icon="https://www.miaa.mx/favicon.ico", 
    layout="wide",
    initial_sidebar_state="expanded"
)

custom_style = """
    <style>
    /* Importar FontAwesome para los iconos */
    @import url('https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css');

    header[data-testid="stHeader"] {visibility: hidden;}
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}

    /* Forzar que la barra lateral nunca se oculte ni colapse */
    [data-testid="stSidebar"] {
        min-width: 260px !important;
        max-width: 320px !important;
        transform: none !important;
        visibility: visible !important;
    }
    
    section[data-testid="stSidebar"] {
        display: block !important;
    }
    
    [data-testid="collapsedControl"] { display: none !important; }

    .block-container {
        padding-top: 0.5rem !important;
        padding-bottom: 0.5rem !important;
        margin-top: -30px !important;
    }

    /* Cabecera Superior */
    .dashboard-header-flex {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-top: 0px;
        margin-bottom: 8px;
        padding: 5px 0px;
        border-bottom: 1px solid rgba(255, 255, 255, 0.08);
        width: 100%;
    }

    .dashboard-main-title {
        font-size: 1.3rem;
        font-weight: 800;
        color: #38bdf8;
        text-transform: uppercase;
        letter-spacing: 0.8px;
        margin: 0;
        text-shadow: 0px 2px 15px rgba(56, 189, 248, 0.2);
    }

    .dashboard-subtitle-right {
        color: #94a3b8;
        font-size: 0.85rem;
        font-weight: 500;
        letter-spacing: 0.3px;
        white-space: nowrap;
    }

    /* Separador visual para las pestañas de Streamlit */
    .stTabs {
        margin-top: 5px;
    }

    /* Tarjetas Compactas: Indicadores KPI */
    .metric-card {
        background: linear-gradient(135deg, rgba(30, 41, 59, 0.7) 0%, rgba(15, 23, 42, 0.9) 100%);
        border: 1px solid rgba(255, 255, 255, 0.08);
        padding: 8px 12px;
        border-radius: 8px;
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 15px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.2);
        transition: all 0.3s ease;
        position: relative;
        overflow: hidden;
        height: 58px;
    }

    .metric-card:hover {
        transform: translateY(-2px);
        border-color: rgba(59, 130, 246, 0.5);
        box-shadow: 0 8px 12px -3px rgba(59, 130, 246, 0.2);
    }

    .metric-card::before {
        content: '';
        position: absolute;
        top: 0;
        left: -100%;
        width: 100%;
        height: 100%;
        background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.05), transparent);
        transition: 0.5s;
    }

    .metric-card:hover::before {
        left: 100%;
    }

    .metric-icon-box {
        font-size: 22px;
        display: flex;
        align-items: center;
        justify-content: center;
        min-width: 30px;
    }

    .metric-content {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        text-align: center;
        overflow: hidden;
        width: 100%;
    }

    .metric-title {
        color: #94a3b8;
        font-size: 10px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        line-height: 1.1;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }

    .metric-value {
        color: #ffffff;
        font-size: 17px;
        font-weight: 700;
        line-height: 1.2;
    }

    /* Estilos para Tarjetas Contenedoras de Gráficos (st.container(border=True)) */
    div[data-testid="stVerticalBlockBorderWrapper"] {
        background: linear-gradient(135deg, rgba(30, 41, 59, 0.7) 0%, rgba(15, 23, 42, 0.9) 100%) !important;
        border: 1px solid rgba(255, 255, 255, 0.08) !important;
        border-radius: 12px !important;
        padding: 12px !important;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.2) !important;
        transition: all 0.3s ease;
    }

    div[data-testid="stVerticalBlockBorderWrapper"]:hover {
        border-color: rgba(59, 130, 246, 0.4) !important;
        box-shadow: 0 8px 12px -3px rgba(59, 130, 246, 0.15) !important;
    }

    /* Fondo transparente para los gráficos Plotly */
    .js-plotly-plot .plotly .main-svg {
        background: transparent !important;
    }
    </style>
"""
st.markdown(custom_style, unsafe_allow_html=True)

# ==============================================================================
# SECCIÓN 2: FUNCIONES DE CONEXIÓN Y DATOS (API Y BASE DE DATOS)
# ==============================================================================

url_login = "https://prelec.miaa.mx/auth/v2/login"
url_instalaciones = "https://prelec.miaa.mx/msvc-tecnica/medidores/instalaciones"

@st.cache_data(ttl=300)
def cargar_datos_api():
    """Conecta con la API externa de MIAA usando credenciales de st.secrets para obtener registros de instalaciones."""
    try:
        usuario = st.secrets["api"]["usuario"]
        password = st.secrets["api"]["password"]
        res_login = requests.post(url_login, json={"username": usuario, "password": password}, headers={"Content-Type": "application/json"})
        if res_login.status_code == 200:
            token = res_login.json().get("token") or res_login.json().get("access_token")
            if token:
                res_inst = requests.get(url_instalaciones, headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"})
                if res_inst.status_code == 200:
                    return res_inst.json()
        return None
    except Exception:
        return None

@st.cache_data(ttl=600)
def cargar_metas_db():
    """Consulta la base de datos MySQL para obtener el diccionario de metas e instalaciones por colonia."""
    try:
        engine = create_engine(st.secrets["mysql"]["connection_string"])
        query = """
            SELECT 
                Colonia_ATL, 
                Usuarios_Reales, 
                Usuarios_con_medidor_inteligente, 
                Usuarios_nueva_instalacion, 
                Poligono_de_instalacion 
            FROM Diccionario_instalacion_medidores
        """
        return pd.read_sql(query, con=engine)
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=600)
def cargar_poligonos_db():
    """Consulta la base de datos MySQL para extraer los vértices y metadatos de los polígonos geográficos."""
    try:
        engine = create_engine(st.secrets["mysql"]["connection_string"])
        query = """
            SELECT 
                FID, 
                Sector_comercial, 
                Vertice, 
                coord, 
                Orden_inst, 
                Area_km2, 
                Medidores 
            FROM Diccionario_poligonos_instalacion
        """
        return pd.read_sql(query, con=engine)
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=600)
def cargar_tipos_instalacion_db():
    """Consulta la base de datos MySQL para obtener el catálogo de tipos de instalación."""
    try:
        engine = create_engine(st.secrets["mysql"]["connection_string"])
        query = "SELECT ID, tipo_instalacion FROM Diccionario_tipo_instalacion"
        return pd.read_sql(query, con=engine)
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=600)
def cargar_anomalias_db():
    """Consulta la base de datos MySQL para obtener el diccionario de anomalías."""
    try:
        engine = create_engine(st.secrets["mysql"]["connection_string"])
        query = "SELECT ID, anomalia FROM Diccionario_anomalias"
        return pd.read_sql(query, con=engine)
    except Exception:
        return pd.DataFrame()

# ==============================================================================
# SECCIÓN 3: FUNCIONES AUXILIARES PARA MAPAS
# ==============================================================================

def agregar_capas_base(m):
    """Agrega las capas base de mapa (Carto Dark Matter con API Key) y controles de pantalla completa."""
    api_key = "cb1_26ji_1_864817f3cb73c0bdbe0daccd"
    
    folium.TileLayer(
        tiles=f"https://{{s}}.basemaps.cartocdn.com/rastertiles/dark_all/{{z}}/{{x}}/{{y}}.png?key={api_key}",
        name="Vista Nocturna",
        attr='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
        subdomains="abcd",
        max_zoom=20,
        control=False
    ).add_to(m)

    Fullscreen(position="topright", title="Ampliar Mapa", cancel_title="Salir de pantalla completa").add_to(m)

# ==============================================================================
# SECCIÓN 4: PROCESAMIENTO Y LIMPIEZA INICIAL DE DATOS
# ==============================================================================

if 'datos_instalaciones' not in st.session_state:
    res = cargar_datos_api()
    if res:
        st.session_state['datos_instalaciones'] = res

if 'datos_instalaciones' in st.session_state:
    data = st.session_state['datos_instalaciones']
    lista_registros = []
    if isinstance(data, dict):
        for k, v in data.items():
            if isinstance(v, list): lista_registros.extend(v)
            elif isinstance(v, dict): lista_registros.append(v)
        df = pd.DataFrame(lista_registros) if lista_registros else pd.DataFrame([data])
    else:
        df = pd.DataFrame(data if isinstance(data, list) else [data])
else:
    df = pd.DataFrame()

col_fecha_ref = 'fechaRegistro' if 'fechaRegistro' in df.columns else None
df['fecha_dt'] = pd.to_datetime(df[col_fecha_ref], errors='coerce') if col_fecha_ref and not df.empty else pd.NaT

lat_centro, lon_centro = 21.8853, -102.2916
df['latitud'] = pd.to_numeric(df['latitud'], errors='coerce') if 'latitud' in df.columns else np.nan
df['longitud'] = pd.to_numeric(df['longitud'], errors='coerce') if 'longitud' in df.columns else np.nan

df_metas = cargar_metas_db()
df_poligonos = cargar_poligonos_db()
df_anomalias_db = cargar_anomalias_db()

# Mapeo del Diccionario de Tipos de Instalación
df_tipos_db = cargar_tipos_instalacion_db()
if not df_tipos_db.empty:
    dict_tipos_map = dict(zip(df_tipos_db['ID'].astype(str), df_tipos_db['tipo_instalacion']))
else:
    dict_tipos_map = {
        "1": "CAJA DE VALVULAS",
        "2": "CUADRO DENTRO",
        "3": "CUADRO FUERA",
        "4": "REGISTRO",
        "5": "EMPOTRADO DENTRO",
        "6": "EMPOTRADO FUERA"
    }

if not df.empty and 'lugarInstalacionId' in df.columns:
    df['lugarInstalacion_id_str'] = df['lugarInstalacionId'].fillna('').astype(str).str.replace(r'\.0$', '', regex=True)
    df['tipo_instalacion_nombre'] = df['lugarInstalacion_id_str'].map(dict_tipos_map).fillna("SIN ESPECIFICAR")
else:
    if not df.empty:
        df['tipo_instalacion_nombre'] = "SIN ESPECIFICAR"

# Mapeo del Diccionario de Anomalías
if not df_anomalias_db.empty:
    dict_anomalias_map = dict(zip(df_anomalias_db['ID'].astype(str), df_anomalias_db['anomalia']))
else:
    dict_anomalias_map = {}

if not df.empty and 'anomaliaId' in df.columns:
    df['anomalia_id_str'] = df['anomaliaId'].fillna('').astype(str).str.replace(r'\.0$', '', regex=True)
    df['anomalia_nombre'] = df['anomalia_id_str'].map(dict_anomalias_map).fillna("SIN ANOMALÍA / REGULAR")
else:
    if not df.empty:
        df['anomalia_nombre'] = "SIN ANOMALÍA / REGULAR"

if not df_metas.empty:
    for col_num in ['Usuarios_Reales', 'Usuarios_con_medidor_inteligente', 'Usuarios_nueva_instalacion']:
        if col_num in df_metas.columns:
            df_metas[col_num] = pd.to_numeric(df_metas[col_num].astype(str).str.replace(',', ''), errors='coerce').fillna(0)

    df_metas_valido = df_metas[df_metas['Usuarios_con_medidor_inteligente'] > 0].copy()
else:
    df_metas_valido = pd.DataFrame()

# ==============================================================================
# SECCIÓN 5: CABECERA SUPERIOR DEL TÍTULO DE LA PÁGINA (DATOS YA DISPONIBLES)
# ==============================================================================

try:
    if not df.empty and 'fecha_dt' in df.columns:
        max_dt = df['fecha_dt'].max()
        if pd.notna(max_dt):
            hoy = pd.to_datetime(max_dt).date()
        else:
            hoy = datetime.date.today()
    else:
        hoy = datetime.date.today()
except Exception:
    hoy = datetime.date.today()

try:
    fecha_actual_str = pd.to_datetime(hoy).strftime('%d/%m/%Y')
except Exception:
    fecha_actual_str = datetime.date.today().strftime('%d/%m/%Y')

st.markdown(
    f"""
    <div style="display: flex; justify-content: space-between; align-items: center; width: 100%; margin-bottom: 15px;">
        <div style="width: 180px;"></div>
        <div style="flex-grow: 1; text-align: center;">
            <h1 style="color: white; font-size: 26px; margin: 0; font-weight: bold;">DASHBOARD INSTALACIÓN MEDIDORES INTELIGENTES</h1>
        </div>
        <div style="width: 180px; text-align: right; color: #a0a0a0; font-size: 14px;">
            Actualizado al: {fecha_actual_str}
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ==============================================================================
# SECCIÓN 6: BARRA LATERAL (FILTROS Y CONTROLES)
# ==============================================================================

logo_url = "https://raw.githubusercontent.com/Miaa-Aguascalientes/Logos/38504978c8f77a4dac38ad476f74dbdee6af2cad/LogoMIAA.svg"
st.sidebar.image(logo_url, use_container_width=True)
st.sidebar.markdown("---")

st.sidebar.subheader("Periodo de Fechas")
opcion_periodo = st.sidebar.selectbox(
    "Seleccionar Rango",
    ["Este mes", "El mes pasado", "Últimos tres meses", "Últimos 6 meses", "Este año", "El año pasado"],
    index=0
)

if not df.empty and 'fecha_dt' in df.columns and not df['fecha_dt'].isna().all():
    hoy = df['fecha_dt'].max().date()
else:
    hoy = datetime.date.today()

if opcion_periodo == "Este mes":
    fecha_inicio = hoy.replace(day=1)
    fecha_fin = hoy
elif opcion_periodo == "El mes pasado":
    mes_anterior = hoy.replace(day=1) - pd.Timedelta(days=1)
    fecha_inicio = mes_anterior.replace(day=1)
    fecha_fin = mes_anterior
elif opcion_periodo == "Últimos tres meses":
    fecha_inicio = (pd.to_datetime(hoy) - pd.DateOffset(months=3)).date()
    fecha_fin = hoy
elif opcion_periodo == "Últimos 6 meses":
    fecha_inicio = (pd.to_datetime(hoy) - pd.DateOffset(months=6)).date()
    fecha_fin = hoy
elif opcion_periodo == "Este año":
    fecha_inicio = hoy.replace(month=1, day=1)
    fecha_fin = hoy
elif opcion_periodo == "El año pasado":
    fecha_inicio = hoy.replace(year=hoy.year - 1, month=1, day=1)
    fecha_fin = hoy.replace(year=hoy.year - 1, month=12, day=31)

st.sidebar.markdown("---")
st.sidebar.subheader("Polígonos")

lista_poligonos = []
if not df_metas_valido.empty and 'Poligono_de_instalacion' in df_metas_valido.columns:
    lista_poligonos = sorted([str(p) for p in df_metas_valido['Poligono_de_instalacion'].dropna().unique()], key=lambda x: int(x) if x.isdigit() else x)

for p in lista_poligonos:
    if f"chk_pol_{p}" not in st.session_state:
        st.session_state[f"chk_pol_{p}"] = True

col_c1, col_c2 = st.sidebar.columns(2)
seleccionar_todos = col_c1.button("Marcar todos")
deseleccionar_todos = col_c2.button("Desmarcar")

if seleccionar_todos:
    for p in lista_poligonos:
        st.session_state[f"chk_pol_{p}"] = True

if deseleccionar_todos:
    for p in lista_poligonos:
        st.session_state[f"chk_pol_{p}"] = False

with st.sidebar.container(height=220):
    poligonos_seleccionados = []
    for pol in lista_poligonos:
        estado = st.checkbox(f"Polígono {pol}", key=f"chk_pol_{pol}")
        if estado:
            poligonos_seleccionados.append(pol)

if not df_metas_valido.empty and 'Poligono_de_instalacion' in df_metas_valido.columns:
    df_metas_filtrado = df_metas_valido[df_metas_valido['Poligono_de_instalacion'].astype(str).isin(poligonos_seleccionados)].copy()
else:
    df_metas_filtrado = df_metas_valido.copy()

if col_fecha_ref and not df.empty and not df['fecha_dt'].isna().all():
    mask = (df['fecha_dt'].dt.date >= fecha_inicio) & (df['fecha_dt'].dt.date <= fecha_fin)
    df_filtrado = df.loc[mask].copy()
else:
    df_filtrado = df.copy()

meta_total = int(df_metas['Usuarios_nueva_instalacion'].sum()) if not df_metas.empty and 'Usuarios_nueva_instalacion' in df_metas.columns else len(df_filtrado)
total_instalados = len(df_filtrado)
porc_avance = round((total_instalados / meta_total) * 100, 2) if meta_total > 0 else 0.0

if not df_filtrado.empty and 'usuarioExterno' in df_filtrado.columns:
    total_externo = int(df_filtrado['usuarioExterno'].fillna(False).astype(bool).sum())
    total_miaa = int((~df_filtrado['usuarioExterno'].fillna(False).astype(bool)).sum())
    
    df_externo = df_filtrado[df_filtrado['usuarioExterno'].fillna(False).astype(bool)].copy()
    df_miaa_pers = df_filtrado[~df_filtrado['usuarioExterno'].fillna(False).astype(bool)].copy()
else:
    total_externo = 0
    total_miaa = len(df_filtrado)
    df_externo = pd.DataFrame(columns=df_filtrado.columns if not df_filtrado.empty else [])
    df_miaa_pers = df_filtrado.copy()

# CONSTRUCCIÓN DE LA TABLA DE EFICIENCIA
if not df_metas_filtrado.empty:
    df_tabla_eficiencia = df_metas_filtrado.copy()

    df_eficiencia = df_tabla_eficiencia.groupby(['Colonia_ATL', 'Poligono_de_instalacion'], as_index=False).agg({
        'Usuarios_nueva_instalacion': 'sum'
    })
    
    df_eficiencia['colonia_key'] = df_eficiencia['Colonia_ATL'].astype(str).str.strip().str.upper()
    
    if not df_filtrado.empty and 'colonia' in df_filtrado.columns:
        df_api_colonia = df_filtrado.copy()
        df_api_colonia['colonia_key'] = df_api_colonia['colonia'].astype(str).str.strip().str.upper()
        conteo_api_colonia = df_api_colonia.groupby('colonia_key', as_index=False).size().rename(columns={'size': 'Med_Instalados_API'})
    else:
        conteo_api_colonia = pd.DataFrame(columns=['colonia_key', 'Med_Instalados_API'])
        
    df_eficiencia = pd.merge(df_eficiencia, conteo_api_colonia, on='colonia_key', how='left')
    df_eficiencia['Med_Instalados_API'] = df_eficiencia['Med_Instalados_API'].fillna(0).astype(int)
    
    df_eficiencia['pct_sort'] = np.where(
        df_eficiencia['Usuarios_nueva_instalacion'] > 0, 
        (df_eficiencia['Med_Instalados_API'] / df_eficiencia['Usuarios_nueva_instalacion']) * 100, 
        0.0
    )
    
    df_eficiencia = df_eficiencia.sort_values(by='pct_sort', ascending=False).reset_index(drop=True)
    df_eficiencia['%'] = df_eficiencia['pct_sort'].round(2).astype(str) + '%'
    
    df_eficiencia = df_eficiencia.rename(columns={
        'Colonia_ATL': 'Colonia',
        'Usuarios_nueva_instalacion': 'Med. a instalar',
        'Med_Instalados_API': 'Med. instalados',
        'Poligono_de_instalacion': 'Polígono'
    })
    
    df_eficiencia = df_eficiencia[['Colonia', 'Med. a instalar', 'Med. instalados', '%', 'Polígono']]
else:
    df_eficiencia = pd.DataFrame(columns=['Colonia', 'Med. a instalar', 'Med. instalados', '%', 'Polígono'])

# ==============================================================================
# SECCIÓN 7: ESTRUCTURA DE PESTAÑAS PRINCIPALES
# ==============================================================================

tab_principal, tab_poligonos, tab_personal, tab_anomalias, tab_tabla = st.tabs([
    "📊 Dashboard Principal", 
    "🗺️ Mapa Polígonos",
    "👥 Personal (Externo y MIAA)",
    "⚠️ Análisis de Anomalías",
    "📋 Tabla Base de Datos Completa"
])

# ------------------------------------------------------------------------------
# PESTAÑA: DASHBOARD PRINCIPAL
# ------------------------------------------------------------------------------
with tab_principal:
    k1, k2, k3, k4, k5, k6 = st.columns(6)
    
    with k1:
        st.markdown(f"""
            <div class="metric-card">
                <div class="metric-icon-box" style="color: #38bdf8;"><i class="fa-solid fa-bullseye"></i></div>
                <div class="metric-content">
                    <div class="metric-title">Meta Total</div>
                    <div class="metric-value">{meta_total:,}</div>
                </div>
            </div>
        """, unsafe_allow_html=True)
        
    with k2:
        st.markdown(f"""
            <div class="metric-card">
                <div class="metric-icon-box" style="color: #4ade80;"><i class="fa-solid fa-circle-check"></i></div>
                <div class="metric-content">
                    <div class="metric-title">Instalados</div>
                    <div class="metric-value">{total_instalados:,}</div>
                </div>
            </div>
        """, unsafe_allow_html=True)
        
    with k3:
        st.markdown(f"""
            <div class="metric-card">
                <div class="metric-icon-box" style="color: #f59e0b;"><i class="fa-solid fa-hard-hat"></i></div>
                <div class="metric-content">
                    <div class="metric-title">Instalados Externo</div>
                    <div class="metric-value">{total_externo:,}</div>
                </div>
            </div>
        """, unsafe_allow_html=True)
        
    with k4:
        st.markdown(f"""
            <div class="metric-card">
                <div class="metric-icon-box" style="color: #a855f7;"><i class="fa-solid fa-building-user"></i></div>
                <div class="metric-content">
                    <div class="metric-title">Instalados MIAA</div>
                    <div class="metric-value">{total_miaa:,}</div>
                </div>
            </div>
        """, unsafe_allow_html=True)
        
    with k5:
        st.markdown(f"""
            <div class="metric-card">
                <div class="metric-icon-box" style="color: #f43f5e;"><i class="fa-solid fa-chart-pie"></i></div>
                <div class="metric-content">
                    <div class="metric-title">% Avance</div>
                    <div class="metric-value">{porc_avance}%</div>
                </div>
            </div>
        """, unsafe_allow_html=True)
        
    with k6:
        sin_coords = df_filtrado['latitud'].isna().sum() if not df_filtrado.empty and 'latitud' in df_filtrado.columns else 0
        st.markdown(f"""
            <div class="metric-card">
                <div class="metric-icon-box" style="color: #94a3b8;"><i class="fa-solid fa-triangle-exclamation"></i></div>
                <div class="metric-content">
                    <div class="metric-title">Sin Coordenadas</div>
                    <div class="metric-value">{sin_coords:,}</div>
                </div>
            </div>
        """, unsafe_allow_html=True)

    st.markdown("<div style='margin-bottom: 8px;'></div>", unsafe_allow_html=True)

    col_g1, col_g2, col_g3 = st.columns([2.6, 1.2, 0.9])

    with col_g1:
        with st.container(border=True):
            st.markdown("<p style='font-size:12px; margin-bottom:4px; font-weight:bold;'>Instalaciones por Día</p>", unsafe_allow_html=True)
            if col_fecha_ref and not df_filtrado.empty and not df_filtrado['fecha_dt'].isna().all():
                df_filtrado['fecha_dia'] = df_filtrado['fecha_dt'].dt.date
                df_dia = df_filtrado.groupby('fecha_dia', as_index=False).size()
                df_dia['fecha_dia'] = pd.to_datetime(df_dia['fecha_dia']).dt.strftime('%d/%m/%Y')
                fig_dia = px.bar(df_dia, x='fecha_dia', y='size', text='size', color_discrete_sequence=['#3b82f6'])
            else:
                fig_dia = px.bar(pd.DataFrame({'Aviso': ['Sin fechas'], 'Valor': [0]}), x='Aviso', y='Valor', text='Valor')
            
            fig_dia.update_traces(textposition='outside', textfont_size=10)
            fig_dia.update_layout(
                plot_bgcolor='rgba(0,0,0,0)', 
                paper_bgcolor='rgba(0,0,0,0)', 
                font_color='#ffffff', 
                margin=dict(t=25, b=5, l=5, r=5), 
                height=230, 
                xaxis_title=None, 
                yaxis_title=None,
                yaxis=dict(range=[0, 500])
            )
            st.plotly_chart(fig_dia, use_container_width=True)

    with col_g2:
        with st.container(border=True):
            st.markdown("<p style='font-size:12px; margin-bottom:4px; font-weight:bold;'>Distribución por Tipo de Instalación</p>", unsafe_allow_html=True)
            if not df_filtrado.empty and 'tipo_instalacion_nombre' in df_filtrado.columns:
                df_tipo_inst = df_filtrado['tipo_instalacion_nombre'].value_counts().reset_index()
                df_tipo_inst.columns = ['Tipo', 'Cantidad']
                
                colores_pie = ['#38bdf8', '#4ade80', '#f59e0b', '#a855f7', '#f43f5e', '#64748b']
                
                fig_pie = go.Figure(go.Pie(
                    labels=df_tipo_inst['Tipo'], 
                    values=df_tipo_inst['Cantidad'], 
                    hole=0.5,
                    domain=dict(x=[0.0, 0.62], y=[0.05, 0.95]), 
                    textinfo='value+percent',
                    texttemplate='%{value} (%{percent})', 
                    textposition='outside',             
                    textfont=dict(color='#ffffff', size=9), 
                    marker=dict(colors=colores_pie),
                    hovertemplate="<b>%{label}</b><br>Cantidad: %{value:,}<br>Porcentaje: %{percent}<extra></extra>"
                ))
            else:
                fig_pie = go.Figure(go.Pie(labels=['Sin Datos'], values=[len(df_filtrado)], hole=0.5))
                
            fig_pie.update_layout(
                plot_bgcolor='rgba(0,0,0,0)', 
                paper_bgcolor='rgba(0,0,0,0)', 
                font_color='#ffffff', 
                margin=dict(t=25, b=25, l=10, r=130), 
                height=230, 
                showlegend=True, 
                legend=dict(
                    orientation="v", 
                    yanchor="middle", 
                    y=0.5, 
                    xanchor="left", 
                    x=1.02, 
                    font=dict(size=9)
                )
            )
            st.plotly_chart(fig_pie, use_container_width=True)

    with col_g3:
        with st.container(border=True):
            st.markdown("<p style='font-size:12px; margin-bottom:4px; font-weight:bold;'>Cuadro vs Registro</p>", unsafe_allow_html=True)
            if not df_filtrado.empty and 'tipo_instalacion_nombre' in df_filtrado.columns:
                def clasificar_cuadro_registro(nombre):
                    n_str = str(nombre).upper()
                    if 'CUADRO' in n_str:
                        return 'CUADRO'
                    elif 'REGISTRO' in n_str:
                        return 'REGISTRO'
                    return None

                df_cr = df_filtrado.copy()
                df_cr['categoria_cr'] = df_cr['tipo_instalacion_nombre'].apply(clasificar_cuadro_registro)
                df_cr_val = df_cr.dropna(subset=['categoria_cr'])
                
                if not df_cr_val.empty:
                    df_counts_cr = df_cr_val['categoria_cr'].value_counts().reset_index()
                    df_counts_cr.columns = ['Tipo', 'Cantidad']
                    
                    tot_cr = df_counts_cr['Cantidad'].sum()
                    txt_centro = f"{tot_cr/1000:.1f} mil".replace('.', ',') if tot_cr >= 1000 else f"{tot_cr:,}"

                    color_cr_map = {'CUADRO': '#0066cc', 'REGISTRO': '#e83e8c'}
                    colores_cr = [color_cr_map.get(t, '#3b82f6') for t in df_counts_cr['Tipo']]

                    fig_cr = go.Figure(go.Pie(
                        labels=df_counts_cr['Tipo'], 
                        values=df_counts_cr['Cantidad'], 
                        hole=0.6,
                        textinfo='value+percent',
                        marker=dict(colors=colores_cr)
                    ))

                    fig_cr.update_layout(
                        annotations=[dict(text=txt_centro, x=0.5, y=0.5, font_size=16, font_color="white", font_weight="bold", showarrow=False)],
                        plot_bgcolor='rgba(0,0,0,0)', 
                        paper_bgcolor='rgba(0,0,0,0)', 
                        font_color='#ffffff', 
                        margin=dict(t=5, b=5, l=5, r=5), 
                        height=230, 
                        showlegend=True, 
                        legend=dict(orientation="h", y=-0.2, font=dict(size=9))
                    )
                else:
                    fig_cr = go.Figure(go.Pie(labels=['Sin Datos'], values=[0], hole=0.6))
                    fig_cr.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', font_color='#ffffff', height=230)
            else:
                fig_cr = go.Figure(go.Pie(labels=['Sin Datos'], values=[0], hole=0.6))
                fig_cr.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', font_color='#ffffff', height=230)

            st.plotly_chart(fig_cr, use_container_width=True)

    col_inf1, col_inf2 = st.columns([1, 1.6])

    with col_inf1:
        with st.container(border=True):
            st.markdown("<p style='font-size:12px; margin-bottom:4px; font-weight:bold;'>Eficiencia por Colonia y Polígono</p>", unsafe_allow_html=True)
            if not df_eficiencia.empty:
                st.dataframe(df_eficiencia, use_container_width=True, hide_index=True, height=330)
            else:
                st.info("No se encontraron datos para los polígonos seleccionados.")

    with col_inf2:
        col_map_h, col_graf_h = st.columns([2.2, 1])

        with col_map_h:
            with st.container(border=True):
                st.markdown("<p style='font-size:12px; margin-bottom:4px; font-weight:bold;'>Mapa de Instalaciones (Externo vs MIAA)</p>", unsafe_allow_html=True)
                
                df_mapa_valido = df_filtrado.dropna(subset=['latitud', 'longitud']) if not df_filtrado.empty else pd.DataFrame()
                if not df_mapa_valido.empty:
                    map_lat = df_mapa_valido['latitud'].mean()
                    map_lon = df_mapa_valido['longitud'].mean()
                else:
                    map_lat, map_lon = lat_centro, lon_centro

                mapa_miaa = folium.Map(location=[map_lat, map_lon], zoom_start=12, tiles=None)
                agregar_capas_base(mapa_miaa)

                for _, row in df_mapa_valido.iterrows():
                    es_externo = bool(row['usuarioExterno']) if 'usuarioExterno' in df_mapa_valido.columns else False
                    color_punto = '#f59e0b' if es_externo else '#a855f7'
                    
                    def get_clean(keys, default=''):
                        if isinstance(keys, str):
                            keys = [keys]
                        for k in keys:
                            if k in row:
                                val = row[k]
                                if pd.notna(val) and str(val).strip().lower() not in ['nan', 'none', 'nat', '']:
                                    return str(val).strip()
                        return default

                    nombre = get_clean('nombreCliente')
                    predio = get_clean(['numeroPredio', 'predio'])
                    cliente = get_clean(['cliente', 'numeroCliente'])
                    domicilio = get_clean('domicilio')
                    colonia = get_clean('colonia')
                    nivel = get_clean('nivel')
                    giro = get_clean('giro')
                    serie = get_clean(['serieMedidor', 'serie'])
                    lugar_inst = get_clean(['tipo_instalacion_nombre', 'lugarInstalacion'])
                    anomalia_str = get_clean(['anomalia_nombre'])
                    
                    raw_fecha = row.get('fechaInstalacion', None)
                    fecha_inst = ""
                    if pd.notna(raw_fecha) and str(raw_fecha).strip().lower() not in ['nan', 'none', 'nat', '']:
                        dt_obj = pd.to_datetime(raw_fecha, errors='coerce')
                        if pd.notna(dt_obj):
                            fecha_inst = dt_obj.strftime('%d/%m/%Y')
                        else:
                            fecha_inst = str(raw_fecha).strip()

                    raw_hora = row.get('horaInicio', None)
                    hora_inst = ""
                    if pd.notna(raw_hora) and str(raw_hora).strip().lower() not in ['nan', 'none', 'nat', '']:
                        hora_str = str(raw_hora).strip()
                        if 'T' in hora_str:
                            time_part = hora_str.split('T')[1]
                            hora_inst = time_part[:5]
                        elif ' ' in hora_str:
                            time_part = hora_str.split(' ')[1]
                            hora_inst = time_part[:5]
                        else:
                            hora_inst = hora_str[:5]

                    info_popup = f"""
                    <div style="font-size: 11px; line-height: 1.4; color: #000000;">
                        <b>Información del Servicio</b><br>
                        <b>Nombre:</b> {nombre}<br>
                        <b>Número de Predio:</b> {predio}<br>
                        <b>Cliente:</b> {cliente}<br>
                        <b>Domicilio:</b> {domicilio}<br>
                        <b>Colonia:</b> {colonia}<br>
                        <b>Nivel:</b> {nivel}<br>
                        <b>Giro:</b> {giro}<br>
                        <b>Serie del Medidor:</b> {serie}<br>
                        <b>Fecha de Instalación:</b> {fecha_inst}<br>
                        <b>Hora de Instalación:</b> {hora_inst}<br>
                        <b>Lugar de Instalación:</b> {lugar_inst}<br>
                        <b>Anomalía:</b> {anomalia_str}
                    </div>
                    """
                    
                    popup_obj = folium.Popup(info_popup, max_width=300)

                    folium.CircleMarker(
                        location=[float(row['latitud']), float(row['longitud'])], 
                        radius=2.5, 
                        color=color_punto, 
                        fill=True, 
                        fill_color=color_punto, 
                        fill_opacity=0.7,
                        popup=popup_obj
                    ).add_to(mapa_miaa)

                st_folium(mapa_miaa, width=None, height=320, key="mapa_estatico_instalaciones", returned_objects=[])
                
        with col_graf_h:
            with st.container(border=True):
                st.markdown("<p style='font-size:12px; margin-bottom:4px; font-weight:bold;'>Instalaciones por Mes</p>", unsafe_allow_html=True)
                
                if col_fecha_ref and not df.empty and not df['fecha_dt'].isna().all():
                    df_mes_total = df.copy()
                    df_mes_total['periodo_mes'] = df_mes_total['fecha_dt'].dt.to_period('M')
                    df_mes = df_mes_total.groupby('periodo_mes', as_index=False).size()
                    df_mes.columns = ['Periodo', 'Cantidad']
                    
                    meses_es = {
                        1: 'Enero', 2: 'Febrero', 3: 'Marzo', 4: 'Abril', 
                        5: 'Mayo', 6: 'Junio', 7: 'Julio', 8: 'Agosto', 
                        9: 'Septiembre', 10: 'Octubre', 11: 'Noviembre', 12: 'Diciembre'
                    }
                    
                    df_mes['Mes'] = df_mes['Periodo'].apply(lambda x: f"{meses_es[x.month]} {x.year}")
                    df_mes = df_mes.sort_values(by='Periodo', ascending=True)
                else:
                    df_mes = pd.DataFrame({'Mes': ['Sin datos'], 'Cantidad': [0]})

                colores_barras = ['#1e3a8a', '#3b82f6'] * ((len(df_mes) // 2) + 1)
                max_cant = df_mes['Cantidad'].max() if not df_mes.empty else 10

                fig_mes_h = px.bar(
                    df_mes, 
                    x='Cantidad', 
                    y='Mes', 
                    orientation='h',
                    text='Cantidad',
                    color='Mes',
                    color_discrete_sequence=colores_barras
                )
                
                fig_mes_h.update_traces(textposition='outside', textfont_size=10)
                fig_mes_h.update_layout(
                    plot_bgcolor='rgba(0,0,0,0)', 
                    paper_bgcolor='rgba(0,0,0,0)', 
                    font_color='#ffffff', 
                    margin=dict(t=2, b=2, l=5, r=40),  
                    height=130,  
                    xaxis=dict(showgrid=False, showticklabels=False, title=None, range=[0, max_cant * 1.25]), 
                    yaxis=dict(showgrid=False, title=None, tickfont=dict(size=10), categoryorder='array', categoryarray=df_mes['Mes'].tolist()),
                    showlegend=False
                )
                st.plotly_chart(fig_mes_h, use_container_width=True)

            with st.container(border=True):
                st.markdown("<p style='font-size:12px; margin-bottom:8px; font-weight:bold;'>Total de Anomalías</p>", unsafe_allow_html=True)
                total_anomalias_actual = len(df_filtrado[df_filtrado['anomalia_nombre'] != "SIN ANOMALÍA / REGULAR"]) if not df_filtrado.empty and 'anomalia_nombre' in df_filtrado.columns else 0
                
                st.markdown(f"""
                    <div style="display: flex; align-items: center; justify-content: center; gap: 20px; padding: 32px 0;">
                        <div style="font-size: 38px; color: #f43f5e;"><i class="fa-solid fa-triangle-exclamation"></i></div>
                        <div style="font-size: 36px; font-weight: bold; color: #ffffff;">{total_anomalias_actual:,}</div>
                    </div>
                """, unsafe_allow_html=True)

# ------------------------------------------------------------------------------
# PESTAÑA: ANÁLISIS DE ANOMALÍAS
# ------------------------------------------------------------------------------
with tab_anomalias:
    st.markdown("<p style='font-size:16px; font-weight:bold; margin-bottom:10px;'>⚠️ Análisis Completo de Anomalías en Instalaciones</p>", unsafe_allow_html=True)
    
    df_con_anomalia = df_filtrado[df_filtrado['anomalia_nombre'] != "SIN ANOMALÍA / REGULAR"].copy() if not df_filtrado.empty and 'anomalia_nombre' in df_filtrado.columns else pd.DataFrame()
    
    total_anomalias_reg = len(df_con_anomalia)
    total_registros_filtrados = len(df_filtrado)
    pct_anomalias = round((total_anomalias_reg / total_registros_filtrados) * 100, 2) if total_registros_filtrados > 0 else 0.0
    tipos_unicos_anomalias = df_con_anomalia['anomalia_nombre'].nunique() if not df_con_anomalia.empty else 0

    a_k1, a_k2, a_k3, a_k4 = st.columns(4)
    with a_k1:
        st.markdown(f"""
            <div class="metric-card">
                <div class="metric-icon-box" style="color: #f43f5e;"><i class="fa-solid fa-triangle-exclamation"></i></div>
                <div class="metric-content">
                    <div class="metric-title">Total con Anomalía</div>
                    <div class="metric-value">{total_anomalias_reg:,}</div>
                </div>
            </div>
        """, unsafe_allow_html=True)
    with a_k2:
        st.markdown(f"""
            <div class="metric-card">
                <div class="metric-icon-box" style="color: #f59e0b;"><i class="fa-solid fa-list-check"></i></div>
                <div class="metric-content">
                    <div class="metric-title">Tipos de Anomalías</div>
                    <div class="metric-value">{tipos_unicos_anomalias:,}</div>
                </div>
            </div>
        """, unsafe_allow_html=True)
    with a_k3:
        st.markdown(f"""
            <div class="metric-card">
                <div class="metric-icon-box" style="color: #a855f7;"><i class="fa-solid fa-percent"></i></div>
                <div class="metric-content">
                    <div class="metric-title">% Incidencia</div>
                    <div class="metric-value">{pct_anomalias}%</div>
                </div>
            </div>
        """, unsafe_allow_html=True)
    with a_k4:
        st.markdown(f"""
            <div class="metric-card">
                <div class="metric-icon-box" style="color: #38bdf8;"><i class="fa-solid fa-clipboard-check"></i></div>
                <div class="metric-content">
                    <div class="metric-title">Instalaciones Regulares</div>
                    <div class="metric-value">{(total_registros_filtrados - total_anomalias_reg):,}</div>
                </div>
            </div>
        """, unsafe_allow_html=True)

    st.markdown("<div style='margin-bottom: 15px;'></div>", unsafe_allow_html=True)

    col_anom_g1, col_anom_g2 = st.columns([1.5, 1])

    with col_anom_g1:
        with st.container(border=True):
            st.markdown("<p style='font-size:12px; margin-bottom:4px; font-weight:bold;'>Distribución por Tipo de Anomalía</p>", unsafe_allow_html=True)
            if not df_con_anomalia.empty:
                df_counts_anom = df_con_anomalia['anomalia_nombre'].value_counts().reset_index()
                df_counts_anom.columns = ['Anomalía', 'Cantidad']
                
                fig_anom_bar = px.bar(
                    df_counts_anom, 
                    x='Cantidad', 
                    y='Anomalía', 
                    orientation='h', 
                    text='Cantidad',
                    color='Anomalía',
                    color_discrete_sequence=px.colors.qualitative.Bold
                )
                fig_anom_bar.update_traces(textposition='outside', textfont_size=10)
                fig_anom_bar.update_layout(
                    plot_bgcolor='rgba(0,0,0,0)', 
                    paper_bgcolor='rgba(0,0,0,0)', 
                    font_color='#ffffff', 
                    margin=dict(t=10, b=10, l=10, r=30), 
                    height=270, 
                    xaxis=dict(showgrid=True, title=None), 
                    yaxis=dict(showgrid=False, title=None, categoryorder='total ascending'),
                    showlegend=False
                )
                st.plotly_chart(fig_anom_bar, use_container_width=True)
            else:
                st.info("No se registran anomalías en el periodo o filtros seleccionados.")

    with col_anom_g2:
        with st.container(border=True):
            st.markdown("<p style='font-size:12px; margin-bottom:4px; font-weight:bold;'>Proporción: Con Anomalía vs Regular</p>", unsafe_allow_html=True)
            if total_registros_filtrados > 0:
                df_prop = pd.DataFrame({
                    'Estado': ['Con Anomalía', 'Regular / Sin Anomalía'],
                    'Cantidad': [total_anomalias_reg, total_registros_filtrados - total_anomalias_reg]
                })
                
                fig_prop_pie = px.pie(
                    df_prop, 
                    names='Estado', 
                    values='Cantidad', 
                    hole=0.5,
                    color='Estado',
                    color_discrete_map={'Con Anomalía': '#f43f5e', 'Regular / Sin Anomalía': '#3b82f6'}
                )
                fig_prop_pie.update_traces(textinfo='value+percent', textfont=dict(size=11))
                fig_prop_pie.update_layout(
                    plot_bgcolor='rgba(0,0,0,0)', 
                    paper_bgcolor='rgba(0,0,0,0)', 
                    font_color='#ffffff', 
                    margin=dict(t=10, b=10, l=10, r=10), 
                    height=270,
                    showlegend=True,
                    legend=dict(orientation="h", y=-0.2, font=dict(size=9))
                )
                st.plotly_chart(fig_prop_pie, use_container_width=True)
            else:
                st.info("Sin datos para mostrar proporción.")

    st.markdown("<p style='font-size:14px; font-weight:bold; margin-top:20px; margin-bottom:8px;'>📋 Detalle de Registros con Anomalías Detectadas</p>", unsafe_allow_html=True)
    if not df_con_anomalia.empty:
        df_tabla_anom = df_con_anomalia.copy()
        terminos_excluidos = ['foto', 'fecharegistro', 'fechamodificacion', 'uuid', 'horafin', 'lecturaanterior', 'lecturaactual', 'folio']
        cols_ex = [c for c in df_tabla_anom.columns if any(term in c.lower() for term in terminos_excluidos)]
        df_tabla_anom = df_tabla_anom.drop(columns=cols_ex, errors='ignore')
        if 'fechaInstalacion' in df_tabla_anom.columns:
            df_tabla_anom['fechaInstalacion'] = pd.to_datetime(df_tabla_anom['fechaInstalacion'], errors='coerce').dt.strftime('%d/%m/%Y %H:%M:%S')
        df_tabla_anom = df_tabla_anom.drop(columns=['fecha_dt', 'Semana', 'fecha_dia', 'anio_mes', 'periodo_mes'], errors='ignore')
        st.dataframe(df_tabla_anom, use_container_width=True)
    else:
        st.success("¡Excelente! No hay registros con anomalías reportadas para los filtros seleccionados.")

# ------------------------------------------------------------------------------
# PESTAÑA: MAPA DE POLÍGONOS DE INSTALACIÓN
# ------------------------------------------------------------------------------
script_poligonos_procesados = {}
shapely_polygons = {}
lat_acumuladas, lon_acumuladas = [], []

with tab_poligonos:
    if not df_poligonos.empty:
        raw_fids_sucios = df_poligonos['FID'].dropna().unique().tolist()
        try:
            raw_fids = sorted(raw_fids_sucios, key=lambda x: float(x))
        except:
            raw_fids = sorted(raw_fids_sucios, key=str)
            
        tot_poligonos_val = len(raw_fids)
        fids_disponibles = [str(int(float(f))) if str(f).replace('.','',1).isdigit() else str(f) for f in raw_fids]
    else:
        raw_fids = []
        fids_disponibles = []
        tot_poligonos_val = 0

    poligonos_procesados = {}
    if not df_poligonos.empty:
        for raw_fid in raw_fids:
            fid_str = str(int(float(raw_fid))) if str(raw_fid).replace('.','',1).isdigit() else str(raw_fid)
            df_pol_sel = df_poligonos[df_poligonos['FID'].astype(str).str.contains(fid_str)]
            
            coordenadas_poligono = []
            df_ordenado = df_pol_sel.sort_values(by='Orden_inst', ascending=True)
            sec_comercial = df_pol_sel['Sector_comercial'].iloc[0] if 'Sector_comercial' in df_pol_sel.columns else "N/A"
            area_val = df_pol_sel['Area_km2'].iloc[0] if 'Area_km2' in df_pol_sel.columns else 0
            med_val = df_pol_sel['Medidores'].iloc[0] if 'Medidores' in df_pol_sel.columns else 0

            for _, r_vertice in df_ordenado.iterrows():
                c_val = r_vertice['coord']
                if pd.isna(c_val): continue
                c_str = str(c_val).strip()
                for char in ['(', ')', '[', ']', '"', "'", 'POINT', 'POLYGON']:
                    c_str = c_str.replace(char, '')
                pares = [p.strip() for p in c_str.split(',') if p.strip()]
                
                if len(pares) >= 2 and len(pares) % 2 == 0:
                    for i in range(0, len(pares), 2):
                        try:
                            p1, p2 = float(pares[i]), float(pares[i+1])
                            lat, lon = (p2, p1) if abs(p1) > abs(p2) else (p1, p2)
                            coordenadas_poligono.append([lat, lon])
                            lat_acumuladas.append(lat)
                            lon_acumuladas.append(lon)
                        except: pass
            
            if coordenadas_poligono:
                poligonos_procesados[fid_str] = {
                    'fid': fid_str, 
                    'coordenadas': coordenadas_poligono, 
                    'sector': sec_comercial,
                    'area': area_val, 
                    'medidores_db': med_val, 
                    'vertis': len(coordenadas_poligono)
                }
                try:
                    poly_geom = Polygon(coordenadas_poligono)
                    if not poly_geom.is_valid: poly_geom = poly_geom.buffer(0)
                    shapely_polygons[fid_str] = poly_geom
                except: pass

    conteo_medidores_instalados = {f_id: 0 for f_id in fids_disponibles}
    if shapely_polygons and not df_filtrado.empty and 'latitud' in df_filtrado.columns:
        try:
            for _, row_m in df_filtrado.dropna(subset=['latitud', 'longitud']).iterrows():
                pt = Point(row_m['latitud'], row_m['longitud'])
                for f_id, poly in shapely_polygons.items():
                    if poly.contains(pt):
                        conteo_medidores_instalados[f_id] += 1
                        break
        except: pass

    counts_list = list(conteo_medidores_instalados.values())
    max_inst_val = max(counts_list) if counts_list and max(counts_list) > 0 else 1

    col_c_izq, col_c_centro, col_c_der = st.columns([0.22, 0.52, 0.26])

    with col_c_izq:
        with st.container(border=True):
            st.markdown("<p style='font-size:12px; font-weight:bold; margin-bottom:4px;'>Seleccionar Polígonos (FID)</p>", unsafe_allow_html=True)
            
            b_col1, b_col2 = st.columns(2)
            if b_col1.button("Todos", key="btn_all_fids_ref"):
                for f_id in fids_disponibles:
                    st.session_state[f"map_fid_chk_{f_id}"] = True
            if b_col2.button("Ninguno", key="btn_none_fids_ref"):
                for f_id in fids_disponibles:
                    st.session_state[f"map_fid_chk_{f_id}"] = False

            busqueda_fid = st.text_input("Buscar FID...", placeholder="Buscar FID...", label_visibility="collapsed")
            st.markdown("<div style='margin-bottom: 4px;'></div>", unsafe_allow_html=True)

            with st.container(height=390):
                fids_seleccionados_mapa = []
                for f_id in fids_disponibles:
                    if f"map_fid_chk_{f_id}" not in st.session_state:
                        st.session_state[f"map_fid_chk_{f_id}"] = True
                    
                    if busqueda_fid and busqueda_fid.lower() not in str(f_id).lower():
                        continue
                        
                    inst_cnt_local = conteo_medidores_instalados.get(f_id, 0)
                    chk_estado = st.checkbox(f"FID {f_id} ({inst_cnt_local})", key=f"map_fid_chk_{f_id}")
                    if chk_estado:
                        fids_seleccionados_mapa.append(f_id)

    with col_c_centro:
        with st.container(border=True):
            st.markdown("<p style='font-size:12px; font-weight:bold; margin-bottom:2px;'>Mapa de Polígonos de Instalación</p>", unsafe_allow_html=True)
            
            m_p_lat = sum(lat_acumuladas) / len(lat_acumuladas) if lat_acumuladas else 21.8853
            m_p_lon = sum(lon_acumuladas) / len(lon_acumuladas) if lon_acumuladas else -102.2916

            pydeck_data = []
            for f_id, datos in poligonos_procesados.items():
                if f_id in fids_seleccionados_mapa:
                    inst_count = conteo_medidores_instalados.get(f_id, 0)
                    polygon_coords_lon_lat = [[coord[1], coord[0]] for coord in datos['coordenadas']]
                    
                    if inst_count == 0:
                        color = [239, 68, 68, 190]
                        elevation = 15
                    elif inst_count >= max_inst_val * 0.5:
                        color = [34, 197, 94, 190]
                        elevation = float(inst_count * 10 + 40)
                    else:
                        color = [234, 179, 8, 190]
                        elevation = float(inst_count * 10 + 25)
                        
                    pydeck_data.append({
                        "polygon": polygon_coords_lon_lat, "elevation": elevation, "color": color,
                        "fid": str(f_id), "sector": str(datos['sector']), "instalados": int(inst_count), "medidores_db": int(datos['medidores_db'])
                    })

            layer = pdk.Layer(
                "PolygonLayer", pydeck_data, get_polygon="polygon", get_elevation="elevation",
                get_fill_color="color", get_line_color=[255, 255, 255, 140], line_width_min_pixels=1,
                extruded=True, pickable=True, auto_highlight=True,
            )

            r = pdk.Deck(
                layers=[layer], initial_view_state=pdk.ViewState(latitude=m_p_lat, longitude=m_p_lon, zoom=11.5, pitch=45, bearing=0),
                tooltip={"html": "<b>Polígono FID: {fid}</b><br/>Sector: {sector}<br/>Medidores Instalados: {instalados}<br/>Medidores DB: {medidores_db}",
                         "style": {"backgroundColor": "rgba(15, 23, 42, 0.95)", "color": "white", "fontSize": "11px", "padding": "6px", "borderRadius": "4px"}}
            )

            st.pydeck_chart(r, use_container_width=True, height=520)

    with col_c_der:
        with st.container(border=True):
            st.markdown("<p style='font-size:14px; font-weight:bold; margin-bottom:8px;'>Resumen por Sector</p>", unsafe_allow_html=True)
            
            st.markdown("""
                <div style="display: flex; justify-content: space-between; align-items: center; font-size: 12px; color: #cbd5e1; font-weight: bold; border-bottom: 1px solid rgba(255,255,255,0.15); padding-bottom: 6px; margin-bottom: 8px;">
                    <div style="width: 25%;">Sector</div>
                    <div style="width: 25%; text-align: center;">Medidores (BD)</div>
                    <div style="width: 25%; text-align: center;">Instalados (API)</div>
                    <div style="width: 25%; text-align: right;">Avance</div>
                </div>
            """, unsafe_allow_html=True)
            
            if not df_poligonos.empty and 'Sector_comercial' in df_poligonos.columns:
                df_fids_unicos = df_poligonos.groupby(['FID', 'Sector_comercial']).agg({
                    'Medidores': 'first',
                    'Area_km2': 'first'
                }).reset_index()
                
                df_fids_unicos['f_id'] = df_fids_unicos['FID'].apply(lambda x: str(int(float(x))) if str(x).replace('.','',1).isdigit() else str(x))
                sectores_unicos = df_fids_unicos['Sector_comercial'].dropna().unique()
                
                lista_sectores_datos = []
                for s_nombre in sectores_unicos:
                    df_sec_subset = df_fids_unicos[df_fids_unicos['Sector_comercial'] == s_nombre]
                    
                    s_med_db = int(pd.to_numeric(df_sec_subset['Medidores'], errors='coerce').sum())
                    fids_del_sector = df_sec_subset['f_id'].tolist()
                    s_med_instalados = int(sum(conteo_medidores_instalados.get(f, 0) for f in fids_del_sector))
                    
                    s_avance = round((s_med_instalados / s_med_db * 100), 1) if s_med_db > 0 else 0.0
                    
                    lista_sectores_datos.append({
                        'sector': s_nombre,
                        'med_db': s_med_db,
                        'med_inst': s_med_instalados,
                        'avance': s_avance
                    })
                
                df_resumen_sectores = pd.DataFrame(lista_sectores_datos)
                if not df_resumen_sectores.empty:
                    df_resumen_sectores = df_resumen_sectores.sort_values(by='avance', ascending=False)
                    
                    for _, row_sec in df_resumen_sectores.iterrows():
                        s_nombre = row_sec['sector']
                        s_med_db = row_sec['med_db']
                        s_med_instalados = row_sec['med_inst']
                        s_avance = row_sec['avance']
                        s_avance_cap = min(s_avance, 100.0)
                        
                        dot_color = "#22c55e" if s_avance >= 80.0 else ("#ef4444" if s_avance <= 40.0 else "#eab308")
                        
                        st.markdown(f"""
                            <div style="display: flex; justify-content: space-between; align-items: center; font-size: 13px; margin-bottom: 10px; border-bottom: 1px solid rgba(255,255,255,0.06); padding-bottom: 8px;">
                                <div style="width: 25%; display: flex; align-items: center; gap: 8px; color: white; font-weight: bold; font-size: 14px;">
                                    <span style="width: 10px; height: 10px; background-color: {dot_color}; border-radius: 50%; display: inline-block;"></span>
                                    {s_nombre}
                                </div>
                                <div style="width: 25%; color: #cbd5e1; text-align: center; font-weight: 600; font-size: 13px;">{s_med_db:,}</div>
                                <div style="width: 25%; color: #ffffff; text-align: center; font-weight: bold; font-size: 13px;">{s_med_instalados:,}</div>
                                <div style="width: 25%; text-align: right;">
                                    <div style="font-size: 12px; color: white; font-weight: bold; margin-bottom: 3px;">{s_avance}%</div>
                                    <div style="background-color: rgba(255,255,255,0.12); border-radius: 4px; width: 100%; height: 8px; overflow: hidden;">
                                        <div style="background-color: {dot_color}; width: {s_avance_cap}%; height: 100%; border-radius: 4px;"></div>
                                    </div>
                                </div>
                            </div>
                        """, unsafe_allow_html=True)
            else:
                st.info("Sin datos de sectores disponibles.")

    with st.container(border=True):
        st.markdown("<p style='font-size:12px; font-weight:bold; margin-bottom:4px;'>Detalle de Polígonos de Instalación y Conteo de Medidores</p>", unsafe_allow_html=True)

        resumen_poligonos = []
        for f_id, datos in poligonos_procesados.items():
            if f_id in fids_seleccionados_mapa:
                med_db = datos['medidores_db']
                inst_count = conteo_medidores_instalados.get(f_id, 0)
                pct_avance_pol = round((inst_count / med_db * 100), 2) if med_db > 0 else 0.0
                
                try:
                    fid_val = int(float(datos.get('fid')))
                except:
                    fid_val = datos.get('fid')
                
                resumen_poligonos.append({
                    'FID': fid_val,  
                    'Sector Comercial': datos['sector'], 
                    'Área (km²)': datos['area'],
                    'Medidores (DB)': med_db, 
                    'Medidores Instalados (API)': inst_count,
                    'Avance (%)': f"{pct_avance_pol}%", 
                    'Vértices Totales': datos['vertis']
                })
        
        if resumen_poligonos:
            df_resumen_tabla = pd.DataFrame(resumen_poligonos)
            df_resumen_tabla['FID_num'] = pd.to_numeric(df_resumen_tabla['FID'], errors='coerce')
            df_resumen_tabla = df_resumen_tabla.sort_values(by='FID_num').drop(columns=['FID_num'])
        else:
            df_resumen_tabla = pd.DataFrame(columns=['FID', 'Sector Comercial', 'Área (km²)', 'Medidores (DB)', 'Medidores Instalados (API)', 'Avance (%)', 'Vértices Totales'])

        st.dataframe(df_resumen_tabla, use_container_width=True, hide_index=True, height=250)

# ------------------------------------------------------------------------------
# PESTAÑA: PERSONAL (EXTERNO Y MIAA)
# ------------------------------------------------------------------------------
with tab_personal:
    st.markdown("<p style='font-size:16px; font-weight:bold; margin-bottom:5px;'>👥 Resumen General de Instalaciones por Tipo de Personal</p>", unsafe_allow_html=True)
    st.markdown("<p style='font-size:13px; color: #94a3b8; margin-bottom:15px;'>Comparativa y desglose operacional entre Personal Externo y Personal Interno MIAA.</p>", unsafe_allow_html=True)

    sub_ext, sub_miaa_int = st.tabs(["👷 Personal Externo", "👤 Personal MIAA"])

    with sub_ext:
        ext_total = len(df_externo)
        ext_sin_coord = df_externo['latitud'].isna().sum() if not df_externo.empty and 'latitud' in df_externo.columns else 0
        ext_colonias = df_externo['colonia'].nunique() if not df_externo.empty and 'colonia' in df_externo.columns else 0

        e_k1, e_k2, e_k3 = st.columns(3)
        with e_k1:
            st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-icon-box" style="color: #f59e0b;"><i class="fa-solid fa-hard-hat"></i></div>
                    <div class="metric-content">
                        <div class="metric-title">Total Instalados (Externo)</div>
                        <div class="metric-value">{ext_total:,}</div>
                    </div>
                </div>
            """, unsafe_allow_html=True)
        with e_k2:
            st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-icon-box" style="color: #38bdf8;"><i class="fa-solid fa-map-location-dot"></i></div>
                    <div class="metric-content">
                        <div class="metric-title">Colonias Atendidas</div>
                        <div class="metric-value">{ext_colonias:,}</div>
                    </div>
                </div>
            """, unsafe_allow_html=True)
        with e_k3:
            st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-icon-box" style="color: #94a3b8;"><i class="fa-solid fa-triangle-exclamation"></i></div>
                    <div class="metric-content">
                        <div class="metric-title">Sin Coordenadas</div>
                        <div class="metric-value">{ext_sin_coord:,}</div>
                    </div>
                </div>
            """, unsafe_allow_html=True)

        st.markdown("<div style='margin-bottom: 10px;'></div>", unsafe_allow_html=True)
        col_ex_left, col_ex_right = st.columns([1.1, 1.3])

        with col_ex_left:
            with st.container(border=True):
                st.markdown("<p style='font-size:12px; margin-bottom:4px; font-weight:bold;'>Instalaciones por Día (Externo)</p>", unsafe_allow_html=True)
                if col_fecha_ref and not df_externo.empty and not df_externo['fecha_dt'].isna().all():
                    df_ext_dia = df_externo.copy()
                    df_ext_dia['fecha_dia'] = df_ext_dia['fecha_dt'].dt.date
                    df_ed = df_ext_dia.groupby('fecha_dia', as_index=False).size()
                    df_ed['fecha_dia'] = pd.to_datetime(df_ed['fecha_dia']).dt.strftime('%d/%m/%Y')
                    fig_ext_dia = px.bar(df_ed, x='fecha_dia', y='size', text='size', color_discrete_sequence=['#f59e0b'])
                else:
                    fig_ext_dia = px.bar(pd.DataFrame({'Aviso': ['Sin datos'], 'Valor': [0]}), x='Aviso', y='Valor', text='Valor')
                
                fig_ext_dia.update_traces(textposition='outside', textfont_size=10)
                fig_ext_dia.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', font_color='#ffffff', margin=dict(t=30, b=5, l=5, r=5), height=210, xaxis_title=None, yaxis_title=None)
                st.plotly_chart(fig_ext_dia, use_container_width=True)

            with st.container(border=True):
                st.markdown("<p style='font-size:12px; margin-bottom:4px; font-weight:bold;'>Distribución por Nivel Tarifario (Externo)</p>", unsafe_allow_html=True)
                if not df_externo.empty and 'nivel' in df_externo.columns:
                    df_ext_nivel = df_externo['nivel'].fillna("SIN NIVEL").value_counts().reset_index()
                    df_ext_nivel.columns = ['Nivel', 'Cantidad']
                    fig_ext_niv = px.bar(df_ext_nivel, x='Nivel', y='Cantidad', text='Cantidad', color='Nivel', color_discrete_sequence=px.colors.qualitative.Safe)
                    fig_ext_niv.update_traces(textposition='outside', textfont_size=10)
                else:
                    fig_ext_niv = px.bar(pd.DataFrame({'Nivel': ['Sin datos'], 'Cantidad': [0]}), x='Nivel', y='Cantidad', text='Cantidad')
                
                fig_ext_niv.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', font_color='#ffffff', margin=dict(t=30, b=5, l=5, r=5), height=210, xaxis_title=None, yaxis_title=None, showlegend=False)
                st.plotly_chart(fig_ext_niv, use_container_width=True)

        with col_ex_right:
            with st.container(border=True):
                st.markdown("<p style='font-size:12px; margin-bottom:4px; font-weight:bold;'>Mapa de Instalaciones - Personal Externo</p>", unsafe_allow_html=True)
                df_ext_map = df_externo.dropna(subset=['latitud', 'longitud']) if not df_externo.empty and 'latitud' in df_externo.columns else pd.DataFrame()
                m_lat = df_ext_map['latitud'].mean() if not df_ext_map.empty else lat_centro
                m_lon = df_ext_map['longitud'].mean() if not df_ext_map.empty else lon_centro
                
                mapa_ext = folium.Map(location=[m_lat, m_lon], zoom_start=12, tiles=None)
                agregar_capas_base(mapa_ext)

                for _, row in df_ext_map.iterrows():
                    folium.CircleMarker(location=[float(row['latitud']), float(row['longitud'])], radius=2.5, color='#f59e0b', fill=True, fill_color='#f59e0b', fill_opacity=0.7).add_to(mapa_ext)
                
                st_folium(mapa_ext, width=None, height=460, key="mapa_externo_unificado", returned_objects=[])

        st.markdown("<p style='font-size:14px; font-weight:bold; margin-top:15px; margin-bottom:5px;'>Tabla de Registros - Personal Externo</p>", unsafe_allow_html=True)
        df_tabla_ext = df_externo.copy()
        if not df_tabla_ext.empty:
            terminos_excluidos = ['foto', 'fecharegistro', 'fechamodificacion', 'uuid', 'horafin', 'lecturaanterior', 'lecturaactual', 'folio']
            cols_ex = [c for c in df_tabla_ext.columns if any(term in c.lower() for term in terminos_excluidos)]
            df_tabla_ext = df_tabla_ext.drop(columns=cols_ex, errors='ignore')
            if 'fechaInstalacion' in df_tabla_ext.columns:
                df_tabla_ext['fechaInstalacion'] = pd.to_datetime(df_tabla_ext['fechaInstalacion'], errors='coerce').dt.strftime('%d/%m/%Y %H:%M:%S')
            df_tabla_ext = df_tabla_ext.drop(columns=['fecha_dt', 'Semana', 'fecha_dia', 'anio_mes', 'periodo_mes'], errors='ignore')
        st.dataframe(df_tabla_ext, use_container_width=True)

    with sub_miaa_int:
        miaa_total = len(df_miaa_pers)
        miaa_sin_coord = df_miaa_pers['latitud'].isna().sum() if not df_miaa_pers.empty and 'latitud' in df_miaa_pers.columns else 0
        miaa_colonias = df_miaa_pers['colonia'].nunique() if not df_miaa_pers.empty and 'colonia' in df_miaa_pers.columns else 0

        m_k1, m_k2, m_k3 = st.columns(3)
        with m_k1:
            st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-icon-box" style="color: #10b981;"><i class="fa-solid fa-building-user"></i></div>
                    <div class="metric-content">
                        <div class="metric-title">Total Instalados (MIAA)</div>
                        <div class="metric-value">{miaa_total:,}</div>
                    </div>
                </div>
            """, unsafe_allow_html=True)
        with m_k2:
            st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-icon-box" style="color: #38bdf8;"><i class="fa-solid fa-map-location-dot"></i></div>
                    <div class="metric-content">
                        <div class="metric-title">Colonias Atendidas</div>
                        <div class="metric-value">{miaa_colonias:,}</div>
                    </div>
                </div>
            """, unsafe_allow_html=True)
        with m_k3:
            st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-icon-box" style="color: #94a3b8;"><i class="fa-solid fa-triangle-exclamation"></i></div>
                    <div class="metric-content">
                        <div class="metric-title">Sin Coordenadas</div>
                        <div class="metric-value">{miaa_sin_coord:,}</div>
                    </div>
                </div>
            """, unsafe_allow_html=True)

        st.markdown("<div style='margin-bottom: 10px;'></div>", unsafe_allow_html=True)
        col_mi_left, col_mi_right = st.columns([1.1, 1.3])

        with col_mi_left:
            with st.container(border=True):
                st.markdown("<p style='font-size:12px; margin-bottom:4px; font-weight:bold;'>Instalaciones por Día (MIAA)</p>", unsafe_allow_html=True)
                if col_fecha_ref and not df_miaa_pers.empty and not df_miaa_pers['fecha_dt'].isna().all():
                    df_miaa_dia = df_miaa_pers.copy()
                    df_miaa_dia['fecha_dia'] = df_miaa_dia['fecha_dt'].dt.date
                    df_md = df_miaa_dia.groupby('fecha_dia', as_index=False).size()
                    df_md['fecha_dia'] = pd.to_datetime(df_md['fecha_dia']).dt.strftime('%d/%m/%Y')
                    fig_miaa_dia = px.bar(df_md, x='fecha_dia', y='size', text='size', color_discrete_sequence=['#10b981'])
                else:
                    fig_miaa_dia = px.bar(pd.DataFrame({'Aviso': ['Sin datos'], 'Valor': [0]}), x='Aviso', y='Valor', text='Valor')
                
                fig_miaa_dia.update_traces(textposition='outside', textfont_size=10)
                fig_miaa_dia.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', font_color='#ffffff', margin=dict(t=30, b=5, l=5, r=5), height=210, xaxis_title=None, yaxis_title=None)
                st.plotly_chart(fig_miaa_dia, use_container_width=True)

            with st.container(border=True):
                st.markdown("<p style='font-size:12px; margin-bottom:4px; font-weight:bold;'>Distribución por Nivel Tarifario (MIAA)</p>", unsafe_allow_html=True)
                if not df_miaa_pers.empty and 'nivel' in df_miaa_pers.columns:
                    df_miaa_nivel = df_miaa_pers['nivel'].fillna("SIN NIVEL").value_counts().reset_index()
                    df_miaa_nivel.columns = ['Nivel', 'Cantidad']
                    fig_miaa_niv = px.bar(df_miaa_nivel, x='Nivel', y='Cantidad', text='Cantidad', color='Nivel', color_discrete_sequence=px.colors.qualitative.Pastel)
                    fig_miaa_niv.update_traces(textposition='outside', textfont_size=10)
                else:
                    fig_miaa_niv = px.bar(pd.DataFrame({'Nivel': ['Sin datos'], 'Cantidad': [0]}), x='Nivel', y='Cantidad', text='Cantidad')
                
                fig_miaa_niv.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', font_color='#ffffff', margin=dict(t=30, b=5, l=5, r=5), height=210, xaxis_title=None, yaxis_title=None, showlegend=False)
                st.plotly_chart(fig_miaa_niv, use_container_width=True)

        with col_mi_right:
            with st.container(border=True):
                st.markdown("<p style='font-size:12px; margin-bottom:4px; font-weight:bold;'>Mapa de Instalaciones - Personal MIAA</p>", unsafe_allow_html=True)
                df_miaa_map = df_miaa_pers.dropna(subset=['latitud', 'longitud']) if not df_miaa_pers.empty and 'latitud' in df_miaa_pers.columns else pd.DataFrame()
                mm_lat = df_miaa_map['latitud'].mean() if not df_miaa_map.empty else lat_centro
                mm_lon = df_miaa_map['longitud'].mean() if not df_miaa_map.empty else lon_centro
                
                mapa_miaa_pers = folium.Map(location=[mm_lat, mm_lon], zoom_start=12, tiles=None)
                agregar_capas_base(mapa_miaa_pers)

                for _, row in df_miaa_map.iterrows():
                    folium.CircleMarker(location=[float(row['latitud']), float(row['longitud'])], radius=2.5, color='#10b981', fill=True, fill_color='#10b981', fill_opacity=0.7).add_to(mapa_miaa_pers)
                
                st_folium(mapa_miaa_pers, width=None, height=460, key="mapa_miaa_personal_unificado", returned_objects=[])

        st.markdown("<p style='font-size:14px; font-weight:bold; margin-top:15px; margin-bottom:5px;'>Tabla de Registros - Personal MIAA</p>", unsafe_allow_html=True)
        df_tabla_miaa = df_miaa_pers.copy()
        if not df_tabla_miaa.empty:
            terminos_excluidos = ['foto', 'fecharegistro', 'fechamodificacion', 'uuid', 'horafin', 'lecturaanterior', 'lecturaactual', 'folio']
            cols_ex = [c for c in df_tabla_miaa.columns if any(term in c.lower() for term in terminos_excluidos)]
            df_tabla_miaa = df_tabla_miaa.drop(columns=cols_ex, errors='ignore')
            if 'fechaInstalacion' in df_tabla_miaa.columns:
                df_tabla_miaa['fechaInstalacion'] = pd.to_datetime(df_tabla_miaa['fechaInstalacion'], errors='coerce').dt.strftime('%d/%m/%Y %H:%M:%S')
            df_tabla_miaa = df_tabla_miaa.drop(columns=['fecha_dt', 'Semana', 'fecha_dia', 'anio_mes', 'periodo_mes'], errors='ignore')
        st.dataframe(df_tabla_miaa, use_container_width=True)

# ------------------------------------------------------------------------------
# PESTAÑA: TABLA BASE DE DATOS COMPLETA
# ------------------------------------------------------------------------------
with tab_tabla:
    st.markdown("<p style='font-size:16px; font-weight:bold; margin-bottom:10px;'>📋 Tabla Completa de Registros de la API</p>", unsafe_allow_html=True)
    
    total_registros_tabla = len(df_filtrado)
    total_colonias_tabla = df_filtrado['colonia'].nunique() if not df_filtrado.empty and 'colonia' in df_filtrado.columns else 0

    t_col1, t_col2 = st.columns(2)
    with t_col1:
        st.markdown(f"""
            <div class="metric-card">
                <div class="icon-box" style="color: #38bdf8;"><i class="fa-solid fa-table-list"></i></div>
                <div class="metric-content">
                    <div class="metric-title">Total de Registros</div>
                    <div class="metric-value">{total_registros_tabla:,}</div>
                </div>
            </div>
        """, unsafe_allow_html=True)
    with t_col2:
        st.markdown(f"""
            <div class="metric-card">
                <div class="metric-icon-box" style="color: #4ade80;"><i class="fa-solid fa-map-pin"></i></div>
                <div class="metric-content">
                    <div class="metric-title">Colonias Registradas</div>
                    <div class="metric-value">{total_colonias_tabla:,}</div>
                </div>
            </div>
        """, unsafe_allow_html=True)

    st.markdown("<div style='margin-bottom: 10px;'></div>", unsafe_allow_html=True)

    with st.container(border=True):
        st.markdown("<p style='font-size:13px; font-weight:bold; margin-bottom:4px;'>Distribución por Nivel (Comercial / Doméstico)</p>", unsafe_allow_html=True)
        if not df_filtrado.empty and 'nivel' in df_filtrado.columns:
            df_nivel = df_filtrado['nivel'].fillna("SIN NIVEL").value_counts().reset_index()
            df_nivel.columns = ['Nivel', 'Cantidad']
            
            fig_nivel = px.bar(
                df_nivel, 
                x='Nivel', 
                y='Cantidad', 
                text='Cantidad',
                color='Nivel',
                color_discrete_sequence=px.colors.qualitative.Prism
            )
            fig_nivel.update_traces(textposition='outside', textfont_size=11)
            fig_nivel.update_layout(
                plot_bgcolor='rgba(0,0,0,0)', 
                paper_bgcolor='rgba(0,0,0,0)', 
                font_color='#ffffff', 
                margin=dict(t=30, b=5, l=5, r=5), 
                height=220, 
                xaxis_title=None, 
                yaxis_title=None,
                showlegend=False
            )
            st.plotly_chart(fig_nivel, use_container_width=True)
        else:
            st.info("La columna 'nivel' no se encuentra disponible en los registros.")

    st.markdown("<div style='margin-bottom: 10px;'></div>", unsafe_allow_html=True)

    df_tabla_limpia = df_filtrado.copy()
    
    terminos_excluidos = ['foto', 'modoIdentificacion', 'giro','fecharegistro', 'fechamodificacion', 'uuid', 'horafin', 'lecturaanterior', 'lecturaactual', 'folio']
    columnas_a_excluir = [c for c in df_tabla_limpia.columns if any(term in c.lower() for term in terminos_excluidos)]
    df_tabla_limpia = df_tabla_limpia.drop(columns=columnas_a_excluir, errors='ignore')
    
    poligonos_asignados = []
    if shapely_polygons and not df_tabla_limpia.empty and 'latitud' in df_tabla_limpia.columns:
        for _, row_m in df_tabla_limpia.iterrows():
            lat, lon = row_m.get('latitud'), row_m.get('longitud')
            assigned_fid = "SIN POLÍGONO"
            if pd.notna(lat) and pd.notna(lon):
                pt = Point(lat, lon)
                for bi_label, poly in shapely_polygons.items():
                    if poly.contains(pt):
                        assigned_fid = str(bi_label)
                        break
            poligonos_asignados.append(assigned_fid)
    else:
        poligonos_asignados = ["SIN POLÍGONO"] * len(df_tabla_limpia)
    
    df_tabla_limpia['poligono'] = poligonos_asignados

    campos_a_quitar = ['anomaliaId', 'modoIdentificacion','giro', 'lugarInstalacionId', 'usuarioId', 'lugarInstalacion_id_str', 'anomalia_id_str']
    df_tabla_limpia = df_tabla_limpia.drop(columns=campos_a_quitar, errors='ignore')

    if 'fechaInstalacion' in df_tabla_limpia.columns:
        df_tabla_limpia['fechaInstalacion'] = pd.to_datetime(df_tabla_limpia['fechaInstalacion'], errors='coerce').dt.strftime('%d/%m/%Y %H:%M:%S')

    if 'horaInicio' in df_tabla_limpia.columns:
        df_tabla_limpia['horaInicio'] = pd.to_datetime(df_tabla_limpia['horaInicio'], errors='coerce').dt.strftime('%H:%M')

    df_tabla_limpia = df_tabla_limpia.drop(columns=['fecha_dt', 'Semana', 'fecha_dia', 'anio_mes', 'periodo_mes'], errors='ignore')

    for col in df_tabla_limpia.columns:
        if df_tabla_limpia[col].dtype == 'object':
            df_tabla_limpia[col] = df_tabla_limpia[col].astype(str).replace({'nan': None, 'None': None})

    st.dataframe(df_tabla_limpia, use_container_width=True)
