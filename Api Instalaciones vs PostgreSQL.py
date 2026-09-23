import streamlit as st
import pandas as pd
import requests
from sqlalchemy import create_engine
import folium
from streamlit_folium import st_folium
import plotly.express as px

# ==========================================
# 1. CONFIGURACIÓN DE PÁGINA Y ESTILOS
# ==========================================
st.set_page_config(
    page_title="Gestor de Registros MIAA",
    page_icon="🚰",
    layout="wide"
)

st.markdown("""
    <style>
        .metric-card {
            background-color: #1e293b;
            border: 1px solid #334155;
            padding: 15px;
            border-radius: 8px;
            display: flex;
            align-items: center;
        }
        .metric-icon-box {
            font-size: 24px;
            margin-right: 15px;
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
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 2. CONEXIONES Y CARGA DE DATOS
# ==========================================
def obtener_motor_postgres():
    """Construye y retorna el engine de SQLAlchemy usando los secretos estructurados."""
    pg = st.secrets["postgres"]
    # Se usa psycopg2 explícitamente en la URL de conexión
    connection_string = f"postgresql+psycopg2://{pg['user']}:{pg['password']}@{pg['host']}:{pg['port']}/{pg['database']}"
    return create_engine(connection_string)

@st.cache_data(ttl=600)
def cargar_usuarios_conmedidor_db():
    """Consulta la base de datos PostgreSQL para obtener las primeras 10 filas de la tabla usuarios_miaa_conmedidor."""
    try:
        engine_pg = obtener_motor_postgres()
        # Se añade LIMIT 10 para restringir la carga únicamente a los primeros 10 registros
        query = 'SELECT * FROM "Usuarios"."usuarios_miaa_conmedidor" LIMIT 10'
        return pd.read_sql(query, con=engine_pg)
    except Exception as e:
        st.error(f"Error al conectar con PostgreSQL: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=300)
def cargar_datos_api():
    """Simula o realiza la petición a la API de instalaciones."""
    try:
        # Reemplaza o ajusta con tu endpoint real de la API
        response = requests.get("https://api.miaa.mx/instalaciones", timeout=15)
        if response.status_code == 200:
            return pd.DataFrame(response.json())
    except Exception:
        pass
    
    # Retorno de respaldo vacío en caso de fallo de red
    return pd.DataFrame()

# Carga inicial de fuentes
df_filtrado = cargar_datos_api()
df_conmedidor_pg = cargar_usuarios_conmedidor_db()

# ==========================================
# 3. FILTROS Y SIDEBAR
# ==========================================
st.sidebar.markdown("<h2>⚙️ Panel de Control</h2>", unsafe_allow_html=True)
st.sidebar.markdown("---")

# ==========================================
# 4. PROCESAMIENTO Y CRUCE DE DATOS (_CAMPOS)
# ==========================================
if not df_conmedidor_pg.empty and not df_filtrado.empty:
    df_api_merge = df_filtrado.copy()
    
    # Llave común para el cruce
    df_api_merge['key_join'] = df_api_merge.get('cliente', df_api_merge.get('numeroCliente', '')).astype(str).str.strip()
    
    dict_api_serie = dict(zip(df_api_merge['key_join'], df_api_merge.get('serieMedidor', df_api_merge.get('serie', ''))))
    dict_api_colonia = dict(zip(df_api_merge['key_join'], df_api_merge.get('colonia', '')))
    dict_api_domicilio = dict(zip(df_api_merge['key_join'], df_api_merge.get('domicilio', '')))
    dict_api_instalador = dict(zip(df_api_merge['key_join'], df_api_merge.get('usuarioNombre', df_api_merge.get('instalador', ''))))
    dict_api_tipo_inst = dict(zip(df_api_merge['key_join'], df_api_merge.get('tipo_instalacion_nombre', '')))
    dict_api_lectura = dict(zip(df_api_merge['key_join'], df_api_merge.get('lecturaActual', df_api_merge.get('lectura_actual', 0))))
    dict_api_f_reg = dict(zip(df_api_merge['key_join'], df_api_merge.get('fechaRegistro', '')))
    dict_api_f_inst = dict(zip(df_api_merge['key_join'], df_api_merge.get('fechaInstalacion', '')))

    df_conmedidor_pg['key_join'] = df_conmedidor_pg.get('Cliente', '').astype(str).str.strip()
    
    df_conmedidor_pg['_Serie'] = df_conmedidor_pg['key_join'].map(dict_api_serie).fillna(df_conmedidor_pg.get('_Serie', ''))
    df_conmedidor_pg['_Colonia'] = df_conmedidor_pg['key_join'].map(dict_api_colonia).fillna(df_conmedidor_pg.get('_Colonia', ''))
    df_conmedidor_pg['_Domicilio'] = df_conmedidor_pg['key_join'].map(dict_api_domicilio).fillna(df_conmedidor_pg.get('_Domicilio', ''))
    df_conmedidor_pg['_Instalador'] = df_conmedidor_pg['key_join'].map(dict_api_instalador).fillna(df_conmedidor_pg.get('_Instalador', ''))
    df_conmedidor_pg['_Tipo_instalador'] = df_conmedidor_pg['key_join'].map(dict_api_tipo_inst).fillna(df_conmedidor_pg.get('_Tipo_instalador', ''))
    df_conmedidor_pg['_Lectura_actual'] = pd.to_numeric(df_conmedidor_pg['key_join'].map(dict_api_lectura), errors='coerce').fillna(df_conmedidor_pg.get('_Lectura_actual', 0))
    df_conmedidor_pg['_Fecha_registro'] = pd.to_datetime(df_conmedidor_pg['key_join'].map(dict_api_f_reg), errors='coerce').fillna(df_conmedidor_pg.get('_Fecha_registro', pd.NaT))
    df_conmedidor_pg['_Fecha_instalacion'] = pd.to_datetime(df_conmedidor_pg['key_join'].map(dict_api_f_inst), errors='coerce').fillna(df_conmedidor_pg.get('_Fecha_instalacion', pd.NaT))
    
    df_conmedidor_pg = df_conmedidor_pg.drop(columns=['key_join'], errors='ignore')

# ==========================================
# 5. TÍTULO PRINCIPAL
# ==========================================
st.markdown("<h2>MIAA - Sistema de Registros e Instalaciones</h2>", unsafe_allow_html=True)
st.markdown("---")

# ==========================================
# 6. PESTAÑAS (TABS)
# ==========================================
tab_principal, tab_poligonos, tab_personal, tab_anomalias, tab_tabla, tab_conmedidor = st.tabs([
    "📊 Dashboard Principal", 
    "🗺️ Mapa Polígonos",
    "👥 Personal (Externo y MIAA)",
    "⚠️ Análisis de Anomalías",
    "📋 Tabla Base de Datos Completa",
    "🚰 Gestión usuarios_miaa_conmedidor"
])

with tab_principal:
    st.subheader("Métricas Generales del Sistema")
    st.info("Visualiza aquí los indicadores operativos generales.")

with tab_poligonos:
    st.subheader("Mapeo de Sectores e Instalaciones")
    m = folium.Map(location=[21.8853, -102.2916], zoom_start=12, tiles="CartoDB dark_matter")
    st_folium(m, width="100%", height=400)

with tab_personal:
    st.subheader("Control de Personal")

with tab_anomalias:
    st.subheader("Detección de Anomalías en Terreno")

with tab_tabla:
    st.subheader("Tabla General de Registros de API")
    if not df_filtrado.empty:
        st.dataframe(df_filtrado, use_container_width=True)
    else:
        st.warning("No hay datos cargados desde la API.")

with tab_conmedidor:
    st.markdown("<p style='font-size:16px; font-weight:bold; margin-bottom:10px;'>🚰 Gestión de Tabla PostgreSQL: usuarios_miaa_conmedidor</p>", unsafe_allow_html=True)
    st.markdown("<p style='font-size:13px; color: #94a3b8; margin-bottom:15px;'>Visualización y completado automático de columnas de control interno (con guion bajo) sincronizadas desde la API de instalaciones.</p>", unsafe_allow_html=True)

    if not df_conmedidor_pg.empty:
        c_m1, c_m2, c_m3 = st.columns(3)
        with c_m1:
            st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-icon-box" style="color: #38bdf8;"><i class="fa-solid fa-database"></i></div>
                    <div class="metric-content">
                        <div class="metric-title">Total Registros (PG)</div>
                        <div class="metric-value">{len(df_conmedidor_pg):,}</div>
                    </div>
                </div>
            """, unsafe_allow_html=True)
        with c_m2:
            completados_serie = df_conmedidor_pg['_Serie'].notna().sum() if '_Serie' in df_conmedidor_pg.columns else 0
            st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-icon-box" style="color: #4ade80;"><i class="fa-solid fa-circle-check"></i></div>
                    <div class="metric-content">
                        <div class="metric-title">Series Sincronizadas</div>
                        <div class="metric-value">{completados_serie:,}</div>
                    </div>
                </div>
            """, unsafe_allow_html=True)
        with c_m3:
            pendientes_serie = len(df_conmedidor_pg) - completados_serie
            st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-icon-box" style="color: #f59e0b;"><i class="fa-solid fa-triangle-exclamation"></i></div>
                    <div class="metric-content">
                        <div class="metric-title">Sin Serie API</div>
                        <div class="metric-value">{pendientes_serie:,}</div>
                    </div>
                </div>
            """, unsafe_allow_html=True)

        st.markdown("<div style='margin-bottom: 15px;'></div>", unsafe_allow_html=True)

        with st.container(border=True):
            st.markdown("<p style='font-size:13px; font-weight:bold; margin-bottom:8px;'>Vista Previa de la Tabla Actualizada con Datos de la API</p>", unsafe_allow_html=True)
            st.dataframe(df_conmedidor_pg, use_container_width=True, height=450)

            if st.button("💾 Guardar / Actualizar Cambios en PostgreSQL", key="btn_save_pg_conmedidor"):
                try:
                    engine_pg = obtener_motor_postgres()
                    df_conmedidor_pg.to_sql("usuarios_miaa_conmedidor", con=engine_pg, schema="Usuarios", if_exists="replace", index=False)
                    st.success("¡Los registros con las columnas completadas se han actualizado correctamente en PostgreSQL!")
                except Exception as ex:
                    st.error(f"Error al guardar en la base de datos: {ex}")
    else:
        st.warning("No se encontraron registros en la tabla `usuarios_miaa_conmedidor` del esquema de PostgreSQL.")
