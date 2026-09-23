import streamlit as st
import pandas as pd
import requests
from sqlalchemy import create_engine, text
from datetime import datetime, timedelta
import time

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
# 2. CONEXIONES Y CONSULTAS OPTIMIZADAS (SQL)
# ==========================================
url_login = "https://prelec.miaa.mx/auth/v2/login"
url_instalaciones = "https://prelec.miaa.mx/msvc-tecnica/medidores/instalaciones"

def obtener_motor_postgres():
    pg = st.secrets["postgres"]
    connection_string = f"postgresql+psycopg2://{pg['user']}:{pg['password']}@{pg['host']}:{pg['port']}/{pg['database']}"
    return create_engine(connection_string)

@st.cache_data(ttl=600)
def obtener_total_registros():
    try:
        engine_pg = obtener_motor_postgres()
        with engine_pg.connect() as conn:
            result = conn.execute(text('SELECT COUNT(*) FROM "Usuarios"."usuarios_miaa_conmedidor"'))
            return result.scalar()
    except Exception:
        return 0

@st.cache_data(ttl=60)
def cargar_pagina_usuarios_db(limit=50, offset=0):
    try:
        engine_pg = obtener_motor_postgres()
        query = text('SELECT * FROM "Usuarios"."usuarios_miaa_conmedidor" LIMIT :lim OFFSET :off')
        return pd.read_sql(query, con=engine_pg, params={"lim": limit, "off": offset})
    except Exception as e:
        st.error(f"Error al conectar con PostgreSQL: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=300)
def cargar_datos_api():
    try:
        usuario = st.secrets["api"]["usuario"]
        password = st.secrets["api"]["password"]
        res_login = requests.post(url_login, json={"username": usuario, "password": password}, headers={"Content-Type": "application/json"})
        if res_login.status_code == 200:
            token = res_login.json().get("token") or res_login.json().get("access_token")
            if token:
                res_inst = requests.get(url_instalaciones, headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"})
                if res_inst.status_code == 200:
                    data = res_inst.json()
                    if isinstance(data, list):
                        df = pd.DataFrame(data)
                    elif isinstance(data, dict):
                        df = pd.DataFrame()
                        for key in ['data', 'result', 'items', 'instalaciones']:
                            if key in data and isinstance(data[key], list):
                                df = pd.DataFrame(data[key])
                                break
                        if df.empty:
                            df = pd.DataFrame([data])
                    
                    if not df.empty:
                        cols_a_remover = [c for c in df.columns if any(term in c.lower() for term in ['foto', 'imagen', 'img', 'fotografia'])]
                        df = df.drop(columns=cols_a_remover, errors='ignore')
                    
                    return df
        return pd.DataFrame()
    except Exception as e:
        st.sidebar.error(f"Error al conectar con la API: {e}")
        return pd.DataFrame()

# ==========================================
# 3. FUNCIÓN DE MAPEO Y CRUCE DE DATOS
# ==========================================
def procesar_cruce_datos(df_conmedidor_pg, df_filtrado):
    df_api_merge = df_filtrado.copy()
    
    col_api_predio = next((c for c in ['predio', 'predioViv', 'predio_viv', 'numeroPredio'] if c in df_api_merge.columns), None)
    if col_api_predio:
        df_api_merge['key_join'] = df_api_merge[col_api_predio].astype(str).str.strip()
    else:
        df_api_merge['key_join'] = ''

    dict_api_serie = dict(zip(df_api_merge['key_join'], df_api_merge.get('serie', '')))
    dict_api_colonia = dict(zip(df_api_merge['key_join'], df_api_merge.get('colonia', '')))
    dict_api_domicilio = dict(zip(df_api_merge['key_join'], df_api_merge.get('domicilio', '')))
    dict_api_instalador = dict(zip(df_api_merge['key_join'], df_api_merge.get('usuarioNombre', '')))
    
    def mapear_tipo_externo(val):
        if val in [True, 1, '1', 'true', 'True', 'YES', 'yes', 'S', 's']:
            return 'Externo'
        elif val in [False, 0, '0', 'false', 'False', 'NO', 'no', 'N', 'n']:
            return 'MIAA'
        return 'MIAA'

    if 'usuarioExterno' in df_api_merge.columns:
        df_api_merge['tipo_calculado'] = df_api_merge['usuarioExterno'].apply(mapear_tipo_externo)
        dict_api_tipo_inst = dict(zip(df_api_merge['key_join'], df_api_merge['tipo_calculado']))
    else:
        dict_api_tipo_inst = {}

    dict_api_lectura = dict(zip(df_api_merge['key_join'], df_api_merge.get('lecturaActual', 0)))
    dict_api_f_reg = dict(zip(df_api_merge['key_join'], df_api_merge.get('fechaRegistro', '')))
    dict_api_f_inst = dict(zip(df_api_merge['key_join'], df_api_merge.get('fechaInstalacion', '')))

    col_pg_predio = next((c for c in ['Predio_Viv', 'predio_viv', 'Predio', 'predio'] if c in df_conmedidor_pg.columns), None)
    if col_pg_predio:
        df_conmedidor_pg['key_join'] = df_conmedidor_pg[col_pg_predio].astype(str).str.strip().str.split('-').str[0]
    else:
        df_conmedidor_pg['key_join'] = ''
    
    df_conmedidor_pg['_Serie'] = df_conmedidor_pg['key_join'].map(dict_api_serie).fillna(df_conmedidor_pg.get('_Serie', ''))
    df_conmedidor_pg['_Colonia'] = df_conmedidor_pg['key_join'].map(dict_api_colonia).fillna(df_conmedidor_pg.get('_Colonia', ''))
    df_conmedidor_pg['_Domicilio'] = df_conmedidor_pg['key_join'].map(dict_api_domicilio).fillna(df_conmedidor_pg.get('_Domicilio', ''))
    df_conmedidor_pg['_Instalador'] = df_conmedidor_pg['key_join'].map(dict_api_instalador).fillna(df_conmedidor_pg.get('_Instalador', ''))
    df_conmedidor_pg['_Tipo_instalador'] = df_conmedidor_pg['key_join'].map(dict_api_tipo_inst).fillna(df_conmedidor_pg.get('_Tipo_instalador', 'MIAA'))
    df_conmedidor_pg['_Lectura_actual'] = pd.to_numeric(df_conmedidor_pg['key_join'].map(dict_api_lectura), errors='coerce').fillna(df_conmedidor_pg.get('_Lectura_actual', 0))
    df_conmedidor_pg['_Fecha_registro'] = pd.to_datetime(df_conmedidor_pg['key_join'].map(dict_api_f_reg), errors='coerce').fillna(df_conmedidor_pg.get('_Fecha_registro', pd.NaT))
    df_conmedidor_pg['_Fecha_instalacion'] = pd.to_datetime(df_conmedidor_pg['key_join'].map(dict_api_f_inst), errors='coerce').fillna(df_conmedidor_pg.get('_Fecha_instalacion', pd.NaT))
    
    df_conmedidor_pg = df_conmedidor_pg.drop(columns=['key_join'], errors='ignore')
    return df_conmedidor_pg

def ejecutar_sincronizacion_automatica():
    df_filtrado = cargar_datos_api()
    try:
        engine_pg = obtener_motor_postgres()
        df_conmedidor_pg = pd.read_sql('SELECT * FROM "Usuarios"."usuarios_miaa_conmedidor"', con=engine_pg)
    except Exception:
        df_conmedidor_pg = pd.DataFrame()

    if not df_conmedidor_pg.empty and not df_filtrado.empty:
        df_actualizado = procesar_cruce_datos(df_conmedidor_pg, df_filtrado)
        try:
            engine_pg = obtener_motor_postgres()
            df_actualizado.to_sql("usuarios_miaa_conmedidor", con=engine_pg, schema="Usuarios", if_exists="replace", index=False)
            return True
        except Exception as ex:
            st.error(f"Error al actualizar en PostgreSQL: {ex}")
            return False
    return False

# ==========================================
# 4. GESTIÓN DE ESTADO PARA EL TEMPORIZADOR
# ==========================================
if 'is_running' not in st.session_state:
    st.session_state.is_running = False
if 'next_run_time' not in st.session_state:
    st.session_state.next_run_time = None
if 'total_seconds_interval' not in st.session_state:
    st.session_state.total_seconds_interval = 300

# ==========================================
# 5. TÍTULO Y PANEL DE CONFIGURACIÓN DE TIEMPO
# ==========================================
st.markdown("<h2>MIAA - Sistema de Registros e Instalaciones</h2>", unsafe_allow_html=True)
st.markdown("---")

st.markdown("#### Configuración")

with st.container(border=True):
    c1, c2, c3, c4 = st.columns([2, 2, 1, 1])
    with c1:
        modo = st.selectbox("Modo", ["Periódico"], label_visibility="collapsed")
    with c2:
        opciones_intervalo = {
            "Cada 1 minuto": 60,
            "Cada 5 minutos": 300,
            "Cada 15 minutos": 900,
            "Cada 30 minutos": 1800,
            "Cada hora": 3600
        }
        intervalo_sel = st.selectbox("Intervalo", list(opciones_intervalo.keys()), label_visibility="collapsed")
        total_segundos = opciones_intervalo[intervalo_sel]
    with c3:
        btn_iniciar = st.button("INICIAR", type="primary", use_container_width=True)
    with c4:
        btn_parar = st.button("PARAR", type="secondary", use_container_width=True)

if btn_iniciar:
    st.session_state.is_running = True
    st.session_state.total_seconds_interval = total_segundos
    st.session_state.next_run_time = datetime.now() + timedelta(seconds=total_segundos)
    st.success("¡Temporizador iniciado correctamente!")
    st.rerun()

if btn_parar:
    st.session_state.is_running = False
    st.session_state.next_run_time = None
    st.warning("Temporizador detenido.")
    st.rerun()

placeholder_timer = st.empty()

if st.session_state.is_running and st.session_state.next_run_time:
    ahora = datetime.now()
    if ahora >= st.session_state.next_run_time:
        exito = ejecutar_sincronizacion_automatica()
        if exito:
            st.toast("¡Datos sincronizados y guardados en PostgreSQL con éxito!", icon="🚰")
        st.session_state.next_run_time = datetime.now() + timedelta(seconds=st.session_state.total_seconds_interval)
        st.rerun()
    else:
        restante = (st.session_state.next_run_time - ahora).total_seconds()
        porcentaje = int(((st.session_state.total_seconds_interval - restante) / st.session_state.total_seconds_interval) * 100)
        
        hrs_r = int(restante // 3600)
        min_r = int((restante % 3600) // 60)
        sec_r = int(restante % 60)
        tiempo_str = f"{hrs_r:02d}:{min_r:02d}:{sec_r:02d}"
        
        with placeholder_timer.container():
            st.markdown(f"<p style='color: #38bdf8; font-weight: bold; font-size: 15px; margin-top: 10px;'>PRÓXIMA CARGA EN: {tiempo_str}</p>", unsafe_allow_html=True)
            st.progress(min(max(porcentaje, 0), 100), text=f"Progreso del ciclo: {porcentaje}%")
        
        time.sleep(1)
        st.rerun()
else:
    placeholder_timer.markdown("<p style='color: #94a3b8; font-size: 13px; font-style: italic;'>El temporizador se encuentra detenido. Define el tiempo y haz clic en INICIAR.</p>", unsafe_allow_html=True)

st.markdown("---")

# ==========================================
# 6. ESTRUCTURA DE PESTAÑAS CON PAGINACIÓN SQL EFICIENTE
# ==========================================
tab1, tab2 = st.tabs([
    "🚰 Panel Principal y Gestión", 
    "📋 Tablas de Datos (PostgreSQL y API)"
])

total_registros_db = obtener_total_registros()

with tab1:
    st.markdown("<p style='font-size:16px; font-weight:bold; margin-bottom:10px;'>Gestión de Tabla PostgreSQL: usuarios_miaa_conmedidor</p>", unsafe_allow_html=True)
    if total_registros_db > 0:
        c_m1, c_m2, c_m3 = st.columns(3)
        with c_m1:
            st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-icon-box" style="color: #38bdf8;"><i class="fa-solid fa-database"></i></div>
                    <div class="metric-content">
                        <div class="metric-title">Total Registros (PG)</div>
                        <div class="metric-value">{total_registros_db:,}</div>
                    </div>
                </div>
            """, unsafe_allow_html=True)
        with c_m2:
            st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-icon-box" style="color: #4ade80;"><i class="fa-solid fa-circle-check"></i></div>
                    <div class="metric-content">
                        <div class="metric-title">Estado de Carga</div>
                        <div class="metric-value" style="font-size: 15px; margin-top: 5px;">Optimizado (SQL Paginado)</div>
                    </div>
                </div>
            """, unsafe_allow_html=True)
        with c_m3:
            st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-icon-box" style="color: #f59e0b;"><i class="fa-solid fa-bolt"></i></div>
                    <div class="metric-content">
                        <div class="metric-title">Rendimiento</div>
                        <div class="metric-value" style="font-size: 15px; margin-top: 5px;">Alta Velocidad</div>
                    </div>
                </div>
            """, unsafe_allow_html=True)

        st.markdown("<div style='margin-bottom: 15px;'></div>", unsafe_allow_html=True)

        with st.container(border=True):
            st.markdown("<p style='font-size:13px; font-weight:bold; margin-bottom:8px;'>Vista Previa Paginada (Carga instantánea)</p>", unsafe_allow_html=True)
            
            filas_por_pagina = 50
            total_paginas = max(1, (total_registros_db // filas_por_pagina) + (1 if total_registros_db % filas_por_pagina > 0 else 0))
            
            col_p1, col_p2 = st.columns([1, 3])
            with col_p1:
                pagina_actual = st.number_input("Página", min_value=1, max_value=total_paginas, value=1, step=1, key="num_pag_t1")
            with col_p2:
                st.markdown(f"<p style='margin-top: 25px; color: #94a3b8;'>Página {pagina_actual} de {total_paginas} (Mostrando bloques de 50 registros)</p>", unsafe_allow_html=True)
            
            offset_val = (pagina_actual - 1) * filas_por_pagina
            df_pagina_pg = cargar_pagina_usuarios_db(limit=filas_por_pagina, offset=offset_val)
            
            df_filtrado = cargar_datos_api()
            if not df_pagina_pg.empty and not df_filtrado.empty:
                df_pagina_pg = procesar_cruce_datos(df_pagina_pg, df_filtrado)

            st.dataframe(df_pagina_pg, use_container_width=True, height=400)
    else:
        st.warning("No se encontraron registros en la tabla.")

with tab2:
    st.subheader("🚰 Tabla: usuarios_miaa_conmedidor (PostgreSQL - Bloques SQL)")
    if total_registros_db > 0:
        t2_filas = 50
        t2_total_pags = max(1, (total_registros_db // t2_filas) + (1 if total_registros_db % t2_filas > 0 else 0))
        t2_pag = st.selectbox("Seleccionar página", range(1, t2_total_pags + 1), key="select_pag_t2")
        
        t2_off = (t2_pag - 1) * t2_filas
        df_t2 = cargar_pagina_usuarios_db(limit=t2_filas, offset=t2_off)
        if not df_t2.empty and not df_filtrado.empty:
            df_t2 = procesar_cruce_datos(df_t2, df_filtrado)
            
        st.dataframe(df_t2, use_container_width=True, height=350)
    else:
        st.warning("No hay datos cargados de PostgreSQL.")

    st.markdown("---")
    
    st.subheader("🌐 Tabla: Datos de la API de Instalación")
    if not df_filtrado.empty:
        st.dataframe(df_filtrado.head(100), use_container_width=True, height=350)
    else:
        st.warning("No hay datos cargados desde la API.")
