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


@st.cache_data(ttl=600)
def obtener_total_registros():
  try:
    engine_pg = obtener_motor_postgres()
    with engine_pg.connect() as conn:
      result = conn.execute(
          text('SELECT COUNT(*) FROM "Usuarios"."usuarios_miaa_conmedidor"')
      )
      return result.scalar()
  except Exception as e:
    agregar_log(f"⚠️ [AVISO DB] No se pudo obtener el conteo de registros: {e}")
    return 0


@st.cache_data(ttl=60)
def obtener_total_etapa_1():
  try:
    engine_pg = obtener_motor_postgres()
    with engine_pg.connect() as conn:
      result = conn.execute(
          text(
              'SELECT COUNT(*) FROM "Usuarios"."usuarios_miaa_conmedidor"'
              " WHERE etapa = '1'"
          )
      )
      return result.scalar() or 0
  except Exception as e:
    agregar_log(f"⚠️ [AVISO DB] No se pudo obtener el conteo de etapa 1: {e}")
    return 0


@st.cache_data(ttl=60)
def obtener_total_etapa_2():
  try:
    engine_pg = obtener_motor_postgres()
    with engine_pg.connect() as conn:
      result = conn.execute(
          text(
              'SELECT COUNT(*) FROM "Usuarios"."usuarios_miaa_conmedidor"'
              " WHERE etapa = '2'"
          )
      )
      return result.scalar() or 0
  except Exception as e:
    agregar_log(f"⚠️ [AVISO DB] No se pudo obtener el conteo de etapa 2: {e}")
    return 0


@st.cache_data(ttl=60)
def cargar_pagina_usuarios_db(limit=50, offset=0):
  try:
    engine_pg = obtener_motor_postgres()
    query = text(
        'SELECT * FROM "Usuarios"."usuarios_miaa_conmedidor" LIMIT :lim OFFSET'
        " :off"
    )
    return pd.read_sql(
        query, con=engine_pg, params={"lim": limit, "off": offset}
    )
  except Exception as e:
    agregar_log(f"❌ [ERROR DB] Error al cargar página de PostgreSQL: {e}")
    return pd.DataFrame()


@st.cache_data(ttl=60)
def cargar_pagina_medidores_inteligentes(limit=50, offset=0):
  try:
    engine_pg = obtener_motor_postgres()
    query = text(
        'SELECT * FROM "Medidores"."medidores_inteligentes" LIMIT :lim OFFSET'
        " :off"
    )
    return pd.read_sql(
        query, con=engine_pg, params={"lim": limit, "off": offset}
    )
  except Exception as e:
    agregar_log(
        "❌ [ERROR DB] Error al cargar página de medidores_inteligentes:"
        f" {e}"
    )
    return pd.DataFrame()


@st.cache_data(ttl=300)
def cargar_datos_api():
  try:
    usuario = st.secrets["api"]["usuario"]
    password = st.secrets["api"]["password"]
    res_login = requests.post(
        url_login,
        json={"username": usuario, "password": password},
        headers={"Content-Type": "application/json"},
    )
    if res_login.status_code == 200:
      token = res_login.json().get("token") or res_login.json().get(
          "access_token"
      )
      if token:
        res_inst = requests.get(
            url_instalaciones,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
            },
        )
        if res_inst.status_code == 200:
          data = res_inst.json()
          if isinstance(data, list):
            df = pd.DataFrame(data)
          elif isinstance(data, dict):
            df = pd.DataFrame()
            for key in ["data", "result", "items", "instalaciones"]:
              if key in data and isinstance(data[key], list):
                df = pd.DataFrame(data[key])
                break
            if df.empty:
              df = pd.DataFrame([data])

          if not df.empty:
            if "numeroCliente" in df.columns:
              df["Cliente"] = df["numeroCliente"]
            elif "numero_cliente" in df.columns:
              df["Cliente"] = df["numero_cliente"]
            elif "numCliente" in df.columns:
              df["Cliente"] = df["numCliente"]

            col_api_predio = next(
                (
                    c
                    for c in [
                        "predio",
                        "predioViv",
                        "predio_viv",
                        "numeroPredio",
                    ]
                    if c in df.columns
                ),
                None,
            )
            col_api_unidad = next(
                (
                    c
                    for c in ["unidad", "unidadViv", "unidad_viv"]
                    if c in df.columns
                ),
                None,
            )

            if col_api_predio:

              def construir_predio_viv(row):
                p = row[col_api_predio]
                if pd.isna(p) or str(p).strip().lower() in ["none", "nan", ""]:
                  return ""

                p_str = str(p).strip()
                u = (
                    row[col_api_unidad]
                    if col_api_unidad and pd.notna(row[col_api_unidad])
                    else 0
                )
                u_str = str(u).strip()

                if u_str.lower() in ["none", "nan", ""]:
                  u_str = "0"

                return f"{p_str}-{u_str}"

              df["Predio_Viv"] = df.apply(construir_predio_viv, axis=1)

            columnas_a_quitar = [
                "predio",
                "predioViv",
                "predio_viv",
                "numeroPredio",
                "unidad",
                "unidadViv",
                "unidad_viv",
                "uuid",
                "numeroCliente",
                "numero_cliente",
                "numCliente",
            ]
            df = df.drop(columns=columnas_a_quitar, errors="ignore")

            cols_prioritarias = [
                c for c in ["Cliente", "Predio_Viv"] if c in df.columns
            ]
            otras_cols = [c for c in df.columns if c not in cols_prioritarias]
            df = df[cols_prioritarias + otras_cols]

          return df
    return pd.DataFrame()
  except Exception:
    return pd.DataFrame()


# ==========================================
# 4. FUNCIÓN DE CRUCE ULTRA RÁPIDO (STAGING + SQL)
# ==========================================
def ejecutar_sincronizacion_automatica(
    barra_progreso_placeholder=None,
    texto_estado_placeholder=None,
    consola_placeholder=None,
):
  def actualizar_progreso(valor_pct, mensaje):
    agregar_log(mensaje)
    if consola_placeholder is not None:
      logs_html = "<br>".join(st.session_state.logs)
      consola_placeholder.markdown(
          f'<div class="terminal-box">{logs_html}</div>', unsafe_allow_html=True
      )
    if barra_progreso_placeholder is not None:
      barra_progreso_placeholder.progress(
          valor_pct,
          text=f"Progreso de ejecución: {int(valor_pct * 100)}% - {mensaje}",
      )
    if texto_estado_placeholder is not None:
      texto_estado_placeholder.markdown(
          f"🔄 **{mensaje}** ({int(valor_pct * 100)}%)"
      )
    time.sleep(0.05)

  actualizar_progreso(
      0.15,
      "[PASO 1/4] Conectando con API de instalaciones para descargar registros...",
  )
  df_filtrado = cargar_datos_api()

  if df_filtrado.empty:
    actualizar_progreso(
        1.0, "[ERROR] No se pudo obtener respuesta o datos válidos de la API."
    )
    return False

  total_descargados = len(df_filtrado)
  actualizar_progreso(
      0.35,
      f"[PASO 2/4] API OK. {total_descargados:,} registros descargados."
      " Preparando tabla temporal en PostgreSQL...",
  )

  try:
    engine_pg = obtener_motor_postgres()

    df_staging = df_filtrado.copy()
    if "Predio_Viv" not in df_staging.columns:
      actualizar_progreso(
          1.0, "[ERROR] La columna Predio_Viv no existe en los datos de la API."
      )
      return False

    df_staging["Predio_Viv_clean"] = (
        df_staging["Predio_Viv"].astype(str).str.strip()
    )

    actualizar_progreso(
        0.55,
        "[PASO 3/4] Cargando datos de la API a la tabla temporal (Staging)"
        " en PostgreSQL...",
    )

    df_staging.to_sql(
        "_staging_api_instalaciones",
        con=engine_pg,
        schema="Usuarios",
        if_exists="replace",
        index=False,
        chunksize=5000,
    )

    actualizar_progreso(
        0.75,
        "[PASO 4/4] Ejecutando actualización masiva (UPDATE FROM JOIN) en"
        " PostgreSQL...",
    )

    query_update_masivo = text("""
            UPDATE "Usuarios"."usuarios_miaa_conmedidor" AS u
            SET 
                "_Serie" = COALESCE(s.serie, u."_Serie"),
                "_Colonia" = COALESCE(s.colonia, u."_Colonia"),
                "_Domicilio" = COALESCE(s.domicilio, u."_Domicilio"),
                "_Instalador" = COALESCE(s."usuarioNombre", u."_Instalador"),
                "_Tipo_instalador" = CASE 
                    WHEN TRIM(CAST(s."usuarioExterno" AS TEXT)) IN ('true', 'True', '1', 'YES', 'yes', 'S', 's', 'TRUE') THEN 'Externo'
                    ELSE 'MIAA'
                END,
                "_Lectura_actual" = CASE 
                    WHEN s."lecturaActual" IS NOT NULL AND TRIM(CAST(s."lecturaActual" AS TEXT)) NOT IN ('', 'none', 'nan', 'null') 
                    THEN CAST(s."lecturaActual" AS DOUBLE PRECISION)
                    ELSE u."_Lectura_actual"
                END,
                "_Fecha_registro" = CASE 
                    WHEN s."fechaRegistro" IS NOT NULL AND TRIM(CAST(s."fechaRegistro" AS TEXT)) NOT IN ('', 'none', 'nan', 'null') 
                    THEN CAST(s."fechaRegistro" AS TIMESTAMP WITH TIME ZONE)
                    ELSE u."_Fecha_registro"
                END,
                "_Fecha_instalacion" = CASE 
                    WHEN s."fechaInstalacion" IS NOT NULL AND TRIM(CAST(s."fechaInstalacion" AS TEXT)) NOT IN ('', 'none', 'nan', 'null') 
                    THEN CAST(s."fechaInstalacion" AS TIMESTAMP WITH TIME ZONE)
                    ELSE u."_Fecha_instalacion"
                END,
                etapa = '2'
            FROM "Usuarios"."_staging_api_instalaciones" AS s
            WHERE TRIM(CAST(u."Predio_Viv" AS TEXT)) = s."Predio_Viv_clean"
              AND s."Predio_Viv_clean" NOT IN ('none', 'nan', '', 'nat', '0', 'null', 'None', 'NaN');
        """)

    with engine_pg.connect() as conn:
      result_up = conn.execute(query_update_masivo)
      conn.commit()
      filas_actualizadas = (
          result_up.rowcount if hasattr(result_up, "rowcount") else 0
      )

      conn.execute(
          text('DROP TABLE IF EXISTS "Usuarios"."_staging_api_instalaciones"')
      )
      conn.commit()

    actualizar_progreso(
        1.0,
        f"🎉 [CICLO EXITOSO] Sincronización completada en segundos. Registros"
        f" cruzados y actualizados en DB: {filas_actualizadas:,}.",
    )
    return True

  except Exception as ex:
    actualizar_progreso(
        1.0, f"[ERROR CRÍTICO] Falló la sincronización en base de datos: {ex}"
    )
    return False


# ==========================================
# 5. TEMPORIZADOR Y RELOJ (HORA MÉXICO)
# ==========================================
def calcular_siguiente_tiempo_reloj(minutos_intervalo):
  ahora = datetime.now(ZONA_MEXICO)
  minuto_actual = ahora.minute
  segundo_actual = ahora.second

  residuo = minuto_actual % minutos_intervalo
  minutos_faltantes = (
      minutos_intervalo - residuo
      if residuo != 0
      else (0 if segundo_actual == 0 else minutos_intervalo)
  )

  if minutos_faltantes == 0 and segundo_actual > 0:
    minutos_faltantes = minutos_intervalo

  siguiente_tiempo = (
      ahora.replace(second=0, microsecond=0)
      + timedelta(minutes=minutos_faltantes)
  )
  total_segundos_hasta_siguiente = (
      siguiente_tiempo - ahora
  ).total_seconds()

  return siguiente_tiempo, int(total_segundos_hasta_siguiente)


if "is_running" not in st.session_state:
  st.session_state.is_running = False
if "next_run_time" not in st.session_state:
  st.session_state.next_run_time = None
if "intervalo_minutos_sel" not in st.session_state:
  st.session_state.intervalo_minutos_sel = 5

# ==========================================
# 6. CARGA DE DATOS PARA INDICADORES Y VISTAS
# ==========================================
total_registros_db = obtener_total_registros()
total_etapa_1_db = obtener_total_etapa_1()
total_etapa_2_db = obtener_total_etapa_2()
df_filtrado = cargar_datos_api()

total_serie_api = 0
if not df_filtrado.empty:
  if "serie" in df_filtrado.columns:
    ts = df_filtrado["serie"].dropna().astype(str).str.strip()
    total_serie_api = ts[
        ~ts.str.lower().isin(["", "none", "nan", "null"])
    ].count()

total_serie_pg_lleno = 0
try:
  engine_pg = obtener_motor_postgres()
  with engine_pg.connect() as conn:
    res_serie_pg = conn.execute(
        text("""
            SELECT COUNT(*) FROM "Usuarios"."usuarios_miaa_conmedidor" 
            WHERE "_Serie" IS NOT NULL 
              AND TRIM(CAST("_Serie" AS TEXT)) != '' 
              AND LOWER(TRIM(CAST("_Serie" AS TEXT))) NOT IN ('none', 'nan', 'null')
        """)
    )
    total_serie_pg_lleno = res_serie_pg.scalar()
except Exception:
  total_serie_pg_lleno = 0

# ==========================================
# 7. BARRA LATERAL IZQUIERDA (SIDEBAR - NUNCA SE OCULTA)
# ==========================================
with st.sidebar:
  st.image(
      "https://raw.githubusercontent.com/Miaa-Aguascalientes/Logos/38504978c8f77a4dac38ad476f74dbdee6af2cad/LogoMIAA.svg",
      use_container_width=True,
  )
  st.markdown("### 🚰 Panel de Control MIAA")
  st.markdown("---")
  st.markdown("#### ⚙ Configuración")

  opciones_intervalo = {
      "Cada 1 minuto": 1,
      "Cada 5 minutos": 5,
      "Cada 10 minutos": 10,
      "Cada 15 minutos": 15,
      "Cada 30 minutos": 30,
      "Cada hora": 60,
  }
  intervalo_sel = st.selectbox(
      "Intervalo de sincronización", list(opciones_intervalo.keys())
  )
  minutos_seleccionados = opciones_intervalo[intervalo_sel]

  col_s1, col_s2 = st.columns(2)
  with col_s1:
    btn_iniciar = st.button("INICIAR", type="primary", use_container_width=True)
  with col_s2:
    btn_parar = st.button("PARAR", type="secondary", use_container_width=True)

  if btn_iniciar:
    st.session_state.is_running = True
    st.session_state.intervalo_minutos_sel = minutos_seleccionados
    sig_tiempo, _ = calcular_siguiente_tiempo_reloj(minutos_seleccionados)
    st.session_state.next_run_time = sig_tiempo
    agregar_log(
        f"▶ Temporizador activado. Próxima ejecución sincronizada al reloj a"
        f" las {sig_tiempo.strftime('%H:%M:%S')}."
    )
    st.success(
        f"¡Temporizador iniciado! Siguiente ejecución a las"
        f" {sig_tiempo.strftime('%H:%M:%S')}."
    )
    st.rerun()

  if btn_parar:
    st.session_state.is_running = False
    st.session_state.next_run_time = None
    agregar_log("⏹ Temporizador detenido manualmente por el usuario.")
    st.warning("Temporizador detenido.")
    st.rerun()

# ==========================================
# 8. INTERFAZ PRINCIPAL Y BARRAS DE PROGRESO
# ==========================================
st.markdown(
    """
    <div style="text-align: center; margin-top: -20px; margin-bottom: 10px;">
        <h2 style="color: #f8fafc; font-weight: 700;">MIAA - Sistema de Registros e Instalaciones</h2>
    </div>
    """,
    unsafe_allow_html=True,
)

col_ind1, col_ind2, col_ind3, col_ind4 = st.columns(4)

with col_ind1:
  st.markdown(
      f"""
        <div class="metric-card">
            <div style="font-size: 28px; margin-right: 15px;">🎯</div>
            <div class="metric-content">
                <div class="metric-title">REGISTROS API CON SERIE</div>
                <div class="metric-value">{total_serie_api:,}</div>
            </div>
        </div>
    """,
      unsafe_allow_html=True,
  )

with col_ind2:
  st.markdown(
      f"""
        <div class="metric-card">
            <div style="font-size: 28px; margin-right: 15px;">✅</div>
            <div class="metric-content">
                <div class="metric-title">POSTGRESQL (_SERIE LLENO)</div>
                <div class="metric-value">{total_serie_pg_lleno:,}</div>
            </div>
        </div>
    """,
      unsafe_allow_html=True,
  )

with col_ind3:
  st.markdown(
      f"""
        <div class="metric-card">
            <div style="font-size: 28px; margin-right: 15px;">🔢</div>
            <div class="metric-content">
                <div class="metric-title">MEDIDORES ETAPA 1 / 2</div>
                <div class="metric-value" style="font-size: 16px; margin-top: 2px;">1: {total_etapa_1_db:,} | 2: {total_etapa_2_db:,}</div>
            </div>
        </div>
    """,
      unsafe_allow_html=True,
  )

with col_ind4:
  porcentaje_cobertura = (
      min(100.0, (total_serie_pg_lleno / total_serie_api) * 100)
      if total_serie_api > 0
      else 0.0
  )
  st.markdown(
      f"""
        <div class="metric-card">
            <div style="font-size: 28px; margin-right: 15px;">📊</div>
            <div class="metric-content">
                <div class="metric-title">SINCRONIZACIÓN</div>
                <div class="metric-value">{porcentaje_cobertura:.1f}%</div>
            </div>
        </div>
    """,
      unsafe_allow_html=True,
  )

st.markdown(
    "<div style='margin-bottom: 15px;'></div>", unsafe_allow_html=True
)

st.markdown("#### 🔄 Estado y Progreso del Sistema")
estado_ejecucion_placeholder = st.empty()
barra_progreso_placeholder = st.empty()

col_consola, col_limpieza = st.columns([1, 1], gap="medium")

with col_consola:
  st.markdown("#### 🖥️ Consola de Registros del Sistema")
  consola_placeholder = st.empty()
  logs_html = "<br>".join(st.session_state.logs)
  consola_placeholder.markdown(
      f'<div class="terminal-box">{logs_html}</div>', unsafe_allow_html=True
  )

if st.session_state.is_running and st.session_state.next_run_time:
  ahora = datetime.now(ZONA_MEXICO)
  if ahora >= st.session_state.next_run_time:
    ejecutar_sincronizacion_automatica(
        barra_progreso_placeholder,
        estado_ejecucion_placeholder,
        consola_placeholder,
    )
    sig_tiempo, _ = calcular_siguiente_tiempo_reloj(
        st.session_state.intervalo_minutos_sel
    )
    st.session_state.next_run_time = sig_tiempo
    st.rerun()
  else:
    segundos_totales_intervalo = st.session_state.intervalo_minutos_sel * 60
    segundos_restantes = max(
        0,
        int(
            (
                st.session_state.next_run_time
                - datetime.now(ZONA_MEXICO)
            ).total_seconds()
        ),
    )

    progreso_espera = max(
        0.0,
        min(
            1.0,
            1.0 - (segundos_restantes / float(segundos_totales_intervalo)),
        ),
    )

    mins_r = segundos_restantes // 60
    secs_r = segundos_restantes % 60
    tiempo_formateado = f"{mins_r:02d}:{secs_r:02d}"

    estado_ejecucion_placeholder.markdown(
        f"⏳ **Temporizador activo.** Próxima ejecución automática a las"
        f" **{st.session_state.next_run_time.strftime('%H:%M:%S')}** (Faltan"
        f" **{tiempo_formateado}**)"
    )
    barra_progreso_placeholder.progress(
        progreso_espera,
        text=(
            f"Tiempo en espera para ejecución: {int(progreso_espera * 100)}%"
            f" completado — Restan {tiempo_formateado}"
        ),
    )

    time.sleep(1)
    st.rerun()
else:
  estado_ejecucion_placeholder.markdown(
      "⏸️ **Temporizador inactivo.** Presiona **INICIAR** en la barra lateral."
  )
  barra_progreso_placeholder.progress(
      0, text="Listo para iniciar temporizador..."
  )

st.markdown("<div style='margin-bottom: 10px;'></div>", unsafe_allow_html=True)

with col_limpieza:
  st.markdown("#### &nbsp;")
  with st.container(border=True):
    st.markdown(
        """
            <h4 style="margin-top: 0; color: #f8fafc; font-size: 18px; display: flex; align-items: center;">
                🧹 <span style="margin-left: 8px;">Limpieza Masiva de Campos (Sin eliminar registros)</span>
            </h4>
            <p style="font-size: 13px; color: #94a3b8; margin-bottom: 15px;">
                Selecciona las columnas cuyos datos deseas <b>vaciar por completo en toda la tabla</b> a la vez. Las filas se mantendrán intactas.
            </p>
          """,
        unsafe_allow_html=True,
    )

    campos_disponibles = [
        "_Serie",
        "_Colonia",
        "_Domicilio",
        "_Instalador",
        "_Tipo_instalador",
        "_Lectura_actual",
        "_Fecha_registro",
        "_Fecha_instalacion",
        "etapa",
    ]

    campos_a_limpiar_masivo = []
    cols_check = st.columns(2)
    for i, campo in enumerate(campos_disponibles):
      with cols_check[i % 2]:
        if st.checkbox(f"Vaciar {campo}", key=f"chk_masivo_{campo}"):
          campos_a_limpiar_masivo.append(campo)

    confirmar_masivo = st.checkbox(
        "⚠️ Confirmo que quiero vaciar masivamente estos campos en TODA la tabla",
        key="chk_confirmar_masivo",
    )

    if st.button(
        "Ejecutar Limpieza Masiva",
        type="primary",
        key="btn_ejecutar_masivo",
        use_container_width=True,
    ):
      if not campos_a_limpiar_masivo:
        st.error("Por favor, selecciona al menos un campo para limpiar.")
      elif not confirmar_masivo:
        st.error(
            "Debes marcar la casilla de confirmación para ejecutar esta acción"
            " masiva."
        )
      else:
        try:
          engine_pg = obtener_motor_postgres()
          set_clausulas = [
              f'"{campo}" = NULL' for campo in campos_a_limpiar_masivo
          ]
          set_sql = ", ".join(set_clausulas)
          query_update_masivo = text(
              f'UPDATE "Usuarios"."usuarios_miaa_conmedidor" SET {set_sql}'
          )

          with engine_pg.connect() as conn_up:
            conn_up.execute(query_update_masivo)
            conn_up.commit()

          agregar_log(
              f"🧹 Limpieza masiva ejecutada. Campos vaciados en toda la tabla:"
              f" {campos_a_limpiar_masivo}"
          )
          st.success(
              "¡Los campos seleccionados fueron vaciados en todos los"
              " registros!"
          )
          st.rerun()
        except Exception as e:
          st.error(f"Error al ejecutar la limpieza masiva: {e}")

st.markdown("<div style='margin-bottom: 10px;'></div>", unsafe_allow_html=True)

# ==========================================
# 9. PESTAÑAS DE LA APLICACIÓN
# ==========================================
tab1, tab2, tab3 = st.tabs([
    "🚰 Panel Principal y Gestión",
    "📋 Tablas de Datos (PostgreSQL y API)",
    "🛠️ Gestión Medidores Inteligentes",
])

with tab1:
  st.markdown(
      "<p style='font-size:16px; font-weight:bold; margin-bottom:10px;'>Gestión"
      ' de Tabla PostgreSQL: usuarios_miaa_conmedidor</p>',
      unsafe_allow_html=True,
  )
  if total_registros_db > 0:
    c_m1, c_m2, c_m3 = st.columns(3)
    with c_m1:
      st.markdown(
          """
                <div class="metric-card">
                    <div class="metric-content">
                        <div class="metric-title">Total Registros (PG)</div>
                        <div class="metric-value">{:,}</div>
                    </div>
                </div>
            """.format(total_registros_db),
          unsafe_allow_html=True,
      )
    with c_m2:
      st.markdown(
          """
                <div class="metric-card">
                    <div class="metric-content">
                        <div class="metric-title">Estado de Carga</div>
                        <div class="metric-value" style="font-size: 15px; margin-top: 5px;">Consola en Vivo (Staging SQL)</div>
                    </div>
                </div>
            """,
          unsafe_allow_html=True,
      )
    with c_m3:
      st.markdown(
          """
                <div class="metric-card">
                    <div class="metric-content">
                        <div class="metric-title">Rendimiento</div>
                        <div class="metric-value" style="font-size: 15px; margin-top: 5px;">Ultra Rápido (Servidor DB)</div>
                    </div>
                </div>
            """,
          unsafe_allow_html=True,
      )
  else:
    st.warning("No se encontraron registros en la tabla.")

  st.markdown(
      "<div style='margin-bottom: 15px;'></div>", unsafe_allow_html=True
  )

  # ==========================================
  # SECCIÓN NUEVA: AUDITORÍA DE DISCREPANCIA (SERIE LLENA VS ETAPA 2)
  # ==========================================
  with st.container(border=True):
    st.markdown(
        "#### 🔍 Auditoría de Discrepancia: Serie Llena vs Etapa 2 (Los 2"
        " Registros)"
    )
    st.markdown(
        "Detecta aquellos registros en PostgreSQL que **tienen número de serie"
        " (`_Serie` lleno)** pero cuyo campo **etapa NO es '2'** (o está en"
        " blanco/etapa 1), explicando exactamente la discrepancia numérica."
    )

    col_disc1, col_disc2 = st.columns(2)
    with col_disc1:
      btn_analizar_disc = st.button(
          "Ver los Registros con Discrepancia",
          key="btn_ver_discrepancia_serie_etapa",
          use_container_width=True,
      )
    with col_disc2:
      btn_sinc_disc = st.button(
          "Corregir y Marcar Etapa = '2' a estos registros",
          type="primary",
          key="btn_corregir_discrepancia",
          use_container_width=True,
      )

    if btn_analizar_disc:
      try:
        engine_pg = obtener_motor_postgres()
        query_disc = text("""
                    SELECT * FROM "Usuarios"."usuarios_miaa_conmedidor"
                    WHERE "_Serie" IS NOT NULL 
                      AND TRIM(CAST("_Serie" AS TEXT)) != '' 
                      AND LOWER(TRIM(CAST("_Serie" AS TEXT))) NOT IN ('none', 'nan', 'null')
                      AND (etapa IS NULL OR TRIM(CAST(etapa AS TEXT)) != '2');
                """)
        with engine_pg.connect() as conn_disc:
          df_discrepancias = pd.read_sql(query_disc, con=conn_disc)

        if df_discrepancias.empty:
          st.success(
              "¡No hay discrepancias! Todos los medidores con serie tienen"
              " exactamente etapa 2."
          )
        else:
          st.warning(
              f"Se encontraron **{len(df_discrepancias):,}** registros con"
              " serie llena que no tienen etapa 2:"
          )
          st.dataframe(df_discrepancias, use_container_width=True, height=300)
      except Exception as e:
        st.error(f"Error al analizar la discrepancia: {e}")

    if btn_sinc_disc:
      try:
        engine_pg = obtener_motor_postgres()
        query_fix = text("""
                    UPDATE "Usuarios"."usuarios_miaa_conmedidor"
                    SET etapa = '2'
                    WHERE "_Serie" IS NOT NULL 
                      AND TRIM(CAST("_Serie" AS TEXT)) != '' 
                      AND LOWER(TRIM(CAST("_Serie" AS TEXT))) NOT IN ('none', 'nan', 'null')
                      AND (etapa IS NULL OR TRIM(CAST(etapa AS TEXT)) != '2');
                """)
        with engine_pg.connect() as conn_fix:
          res_fix = conn_fix.execute(query_fix)
          conn_fix.commit()
          filas_corregidas = (
              res_fix.rowcount if hasattr(res_fix, "rowcount") else 0
          )

        agregar_log(
            f"🛠️ [CORRECCIÓN DISCREPANCIA] Se actualizaron {filas_corregidas}"
            " registros para establecer etapa = '2'."
        )
        st.success(
            f"¡Se han actualizado correctamente **{filas_corregidas}**"
            " registros al etapa '2'!"
        )
        st.rerun()
      except Exception as e:
        st.error(f"Error al corregir la discrepancia: {e}")

  st.markdown(
      "<div style='margin-bottom: 15px;'></div>", unsafe_allow_html=True
  )

  # ==========================================
  # SECCIÓN: AUDITORÍA DE MEDIDORES DE LA API NO CRUZADOS
  # ==========================================
  with st.container(border=True):
    st.markdown("#### 🔍 Diagnóstico de Medidores de la API No Cruzados")
    st.markdown(
        "Analiza los registros obtenidos desde la API de instalaciones y detecta"
        " aquellos medidores que **no pudieron ser cruzados ni insertados** en"
        " la tabla `usuarios_miaa_conmedidor`, indicando la razón exacta."
    )

    if st.button(
        "Ejecutar Auditoría de Medidores API No Cruzados",
        key="btn_auditar_api_no_cruzados",
        use_container_width=True,
    ):
      if df_filtrado.empty:
        st.warning("No hay datos cargados desde la API en este momento.")
      else:
        try:
          engine_pg = obtener_motor_postgres()

          with engine_pg.connect() as conn_pg:
            df_pg_predios = pd.read_sql(
                'SELECT DISTINCT TRIM(CAST("Predio_Viv" AS TEXT)) as predio_pg FROM'
                ' "Usuarios"."usuarios_miaa_conmedidor" WHERE "Predio_Viv" IS'
                " NOT NULL",
                con=conn_pg,
            )
          set_predios_pg = set(
              df_pg_predios["predio_pg"].dropna().astype(str).str.strip()
          )

          df_api_diag = df_filtrado.copy()
          df_api_diag["key_predio"] = (
              df_api_diag["Predio_Viv"].astype(str).str.strip()
              if "Predio_Viv" in df_api_diag.columns
              else ""
          )
          invalidos_diag = {
              "none",
              "nan",
              "",
              "nat",
              "0",
              "null",
              "None",
              "NaN",
          }

          registros_no_cruzados_api = []

          for _, row in df_api_diag.iterrows():
            kp = str(row.get("key_predio", "")).strip()
            motivo = None

            if pd.isna(row.get("Predio_Viv")) or kp == "":
              motivo = "Predio Nulo o Vacío en la API"
            elif kp.lower() in invalidos_diag:
              motivo = f"Predio Inválido o Cero ('{kp}')"
            elif kp not in set_predios_pg:
              motivo = (
                  "El Predio_Viv de la API no existe en la tabla"
                  " usuarios_miaa_conmedidor"
              )

            if motivo:
              row_dict = row.to_dict()
              row_dict["Motivo_No_Cruzado"] = motivo
              registros_no_cruzados_api.append(row_dict)

          if not registros_no_cruzados_api:
            st.success(
                "¡Excelente! Absolutamente todos los medidores y registros de la"
                " API encontraron coincidencia y fueron cruzados"
                " correctamente."
            )
          else:
            df_no_cruzados_api = pd.DataFrame(registros_no_cruzados_api)
            st.warning(
                f"Se detectaron **{len(df_no_cruzados_api):,}** medidores de la"
                " API que NO pudieron cruzarse en la tabla de usuarios."
            )

            st.markdown(
                "##### 📊 Resumen de Motivos por los que no se cruzaron:"
            )
            conteo_motivos_api = df_no_cruzados_api[
                "Motivo_No_Cruzado"
            ].value_counts()
            st.dataframe(conteo_motivos_api, use_container_width=True)

            st.markdown(
                "##### 📋 Listado Detallado de Medidores API No Cruzados:"
            )
            cols_mostrar = [
                c
                for c in df_no_cruzados_api.columns
                if c not in ["key_predio"]
            ]
            st.dataframe(
                df_no_cruzados_api[cols_mostrar],
                use_container_width=True,
                height=350,
            )
        except Exception as e:
          st.error(f"Error al ejecutar la auditoría de la API: {e}")

  # ==========================================
  # SECCIÓN: GESTIÓN Y DETECCIÓN DE DUPLICADOS
  # ==========================================
  with st.container(border=True):
    st.markdown("#### 👥 Detección y Gestión de Registros Duplicados")
    st.markdown(
        "Detecta registros duplicados en la base de datos"
        " `usuarios_miaa_conmedidor` evaluando la coincidencia por el campo"
        " **Predio_Viv** u otros criterios de unicidad."
    )

    col_dup1, col_dup2 = st.columns(2)
    with col_dup1:
      columna_duplicidad = st.selectbox(
          "Columna para evaluar duplicidad",
          ["Predio_Viv", "_Serie", "Cliente"],
          key="sel_col_duplicados",
      )
    with col_dup2:
      accion_duplicados = st.selectbox(
          "Acción sobre duplicados",
          [
              "Ver listado de duplicados",
              "Eliminar duplicados (mantener el primero)",
              "Eliminar duplicados (mantener el último)",
          ],
          key="sel_accion_duplicados",
      )

    if st.button(
        "Ejecutar Análisis / Gestión de Duplicados",
        key="btn_ejecutar_duplicados",
        use_container_width=True,
    ):
      try:
        engine_pg = obtener_motor_postgres()
        query_check_dup = text(f"""
                    SELECT "{columna_duplicidad}", COUNT(*) as total_duplicados
                    FROM "Usuarios"."usuarios_miaa_conmedidor"
                    WHERE "{columna_duplicidad}" IS NOT NULL 
                      AND TRIM(CAST("{columna_duplicidad}" AS TEXT)) NOT IN ('', 'none', 'nan', 'null', '0')
                    GROUP BY "{columna_duplicidad}"
                    HAVING COUNT(*) > 1
                    ORDER BY total_duplicados DESC;
                """)
        with engine_pg.connect() as conn_dup:
          df_dup_res = pd.read_sql(query_check_dup, con=conn_dup)

        if df_dup_res.empty:
          st.success(
              f"✨ ¡No se encontraron registros duplicados evaluando por el"
              f" campo **{columna_duplicidad}**!"
          )
        else:
          total_grupos_dup = len(df_dup_res)
          total_filas_repetidas = (
              df_dup_res["total_duplicados"].sum() - total_grupos_dup
          )
          st.warning(
              f"⚠️ Se detectaron **{total_grupos_dup:,}** valores duplicados"
              f" (que agrupan un total de **{total_filas_repetidas:,}**"
              f" registros repetidos) en el campo `{columna_duplicidad}`."
          )

          if accion_duplicados == "Ver listado de duplicados":
            st.markdown(
                "##### 📋 Detalle de Grupos Duplicados en la Base de Datos:"
            )
            st.dataframe(df_dup_res, use_container_width=True, height=300)

            lista_valores_dup = df_dup_res[columna_duplicidad].tolist()
            if lista_valores_dup:
              format_strings = ",".join(
                  [f":val_{i}" for i in range(len(lista_valores_dup))]
              )
              params = {
                  f"val_{i}": val for i, val in enumerate(lista_valores_dup)
              }
              query_rows_dup = text(f"""
                                SELECT * FROM "Usuarios"."usuarios_miaa_conmedidor"
                                WHERE "{columna_duplicidad}" IN ({format_strings})
                                ORDER BY "{columna_duplicidad}";
                            """)
              with engine_pg.connect() as conn_drows:
                df_rows_dup = pd.read_sql(
                    query_rows_dup, con=conn_drows, params=params
                )
              st.markdown("##### 🔍 Registros Completos Afectados:")
              st.dataframe(df_rows_dup, use_container_width=True, height=350)

          else:
            keep_mode = (
                "MIN(ctid)"
                if "primero" in accion_duplicados.lower()
                else "MAX(ctid)"
            )
            query_delete_dup = text(f"""
                        DELETE FROM "Usuarios"."usuarios_miaa_conmedidor"
                        WHERE ctid NOT IN (
                            SELECT {keep_mode}
                            FROM "Usuarios"."usuarios_miaa_conmedidor"
                            WHERE "{columna_duplicidad}" IS NOT NULL 
                              AND TRIM(CAST("{columna_duplicidad}" AS TEXT)) NOT IN ('', 'none', 'nan', 'null', '0')
                            GROUP BY "{columna_duplicidad}"
                        )
                        AND "{columna_duplicidad}" IS NOT NULL
                        AND TRIM(CAST("{columna_duplicidad}" AS TEXT)) NOT IN ('', 'none', 'nan', 'null', '0');
                    """)
            with engine_pg.connect() as conn_del:
              res_del = conn_del.execute(query_delete_dup)
              conn_del.commit()
              filas_eliminadas = (
                  res_del.rowcount if hasattr(res_del, "rowcount") else 0
              )

            agregar_log(
                f"🗑️ [DUPLICADOS ELIMINADOS] Se eliminaron"
                f" {filas_eliminadas:,} registros duplicados basándose en"
                f" '{columna_duplicidad}'."
            )
            st.success(
                f"¡Se han eliminado correctamente **{filas_eliminadas:,}**"
                " registros duplicados de la tabla!"
            )
            st.rerun()

      except Exception as e:
        st.error(
            f"❌ Error al procesar la gestión de registros duplicados: {e}"
        )

with tab2:
  st.subheader(
      "🚰 Tabla 1: usuarios_miaa_conmedidor (PostgreSQL - Bloques SQL)"
  )
  if total_registros_db > 0:
    t2_filas = 50
    t2_total_pags = max(
        1,
        (total_registros_db // t2_filas)
        + (1 if total_registros_db % t2_filas > 0 else 0),
    )
    t2_pag = st.selectbox(
        "Seleccionar página", range(1, t2_total_pags + 1), key="select_pag_t2"
    )

    t2_off = (t2_pag - 1) * t2_filas
    df_t2 = cargar_pagina_usuarios_db(limit=t2_filas, offset=t2_off)

    st.dataframe(df_t2, use_container_width=True, height=350)
  else:
    st.warning("No hay datos cargados de PostgreSQL.")

  st.markdown(
      "<div style='margin-bottom: 20px;'></div>", unsafe_allow_html=True
  )

  st.subheader("🌐 Tabla 2: Datos Completos de la API de Instalación")


  # Descargamos los datos crudos de la API y filtramos para quitar campos de fotos
  @st.cache_data(ttl=300)
  def cargar_datos_api_sin_fotos():
    try:
      usuario = st.secrets["api"]["usuario"]
      password = st.secrets["api"]["password"]
      res_login = requests.post(
          url_login,
          json={"username": usuario, "password": password},
          headers={"Content-Type": "application/json"},
      )
      if res_login.status_code == 200:
        token = res_login.json().get("token") or res_login.json().get(
            "access_token"
        )
        if token:
          res_inst = requests.get(
              url_instalaciones,
              headers={
                  "Content-Type": "application/json",
                  "Authorization": f"Bearer {token}",
              },
          )
          if res_inst.status_code == 200:
            data = res_inst.json()
            if isinstance(data, list):
              df = pd.DataFrame(data)
            elif isinstance(data, dict):
              df = pd.DataFrame()
              for key in ["data", "result", "items", "instalaciones"]:
                if key in data and isinstance(data[key], list):
                  df = pd.DataFrame(data[key])
                  break
              if df.empty:
                df = pd.DataFrame([data])

            if not df.empty:
              if "numeroCliente" in df.columns:
                df["Cliente"] = df["numeroCliente"]
              elif "numero_cliente" in df.columns:
                df["Cliente"] = df["numero_cliente"]
              elif "numCliente" in df.columns:
                df["Cliente"] = df["numCliente"]

              col_api_predio = next(
                  (
                      c
                      for c in [
                          "predio",
                          "predioViv",
                          "predio_viv",
                          "numeroPredio",
                      ]
                      if c in df.columns
                  ),
                  None,
              )
              col_api_unidad = next(
                  (
                      c
                      for c in ["unidad", "unidadViv", "unidad_viv"]
                      if c in df.columns
                  ),
                  None,
              )

              if col_api_predio:

                def construir_predio_viv(row):
                  p = row[col_api_predio]
                  if pd.isna(p) or str(p).strip().lower() in [
                      "none",
                      "nan",
                      "",
                  ]:
                    return ""

                  p_str = str(p).strip()
                  u = (
                      row[col_api_unidad]
                      if col_api_unidad and pd.notna(row[col_api_unidad])
                      else 0
                  )
                  u_str = str(u).strip()

                  if u_str.lower() in ["none", "nan", ""]:
                    u_str = "0"

                  return f"{p_str}-{u_str}"

                df["Predio_Viv"] = df.apply(construir_predio_viv, axis=1)

              # Filtrar y eliminar columnas que contengan términos de fotos/imágenes
              cols_fotos_a_excluir = [
                  c
                  for c in df.columns
                  if any(
                      term in c.lower()
                      for term in ["foto", "imagen", "img", "fotografia"]
                  )
              ]
              df = df.drop(columns=cols_fotos_a_excluir, errors="ignore")

            return df
      return pd.DataFrame()
    except Exception:
      return pd.DataFrame()


  df_api_sin_fotos = cargar_datos_api_sin_fotos()
  if not df_api_sin_fotos.empty:
    st.dataframe(df_api_sin_fotos, use_container_width=True, height=350)
  else:
    st.warning("No hay datos cargados desde la API.")

with tab3:
  st.subheader("🛠 Gestión de la tabla: medidores_inteligentes")
  st.markdown(
      "Desde aquí puedes gestionar y actualizar de forma masiva los campos"
      " requeridos de la tabla `medidores_inteligentes` dentro del esquema"
      " `Medidores` en tu base de datos PostgreSQL."
  )

  with st.container(border=True):
    st.markdown("#### 🔢 Asignar Etapa 1 a todos los registros")
    st.markdown(
        "Esta acción actualizará el campo **etapa** con el valor **1** en"
        " absolutamente todos los registros de la tabla"
        " `medidores_inteligentes`."
    )

    confirmar_etapa = st.checkbox(
        "⚠️ Confirmo que deseo actualizar el campo etapa a 1 para todos los"
        " registros de medidores_inteligentes",
        key="chk_confirmar_etapa_1",
    )

    if st.button(
        "Establecer etapa = 1 en toda la tabla",
        type="primary",
        key="btn_ejecutar_etapa_1",
        use_container_width=True,
    ):
      if not confirmar_etapa:
        st.error(
            "Debes marcar la casilla de confirmación para ejecutar esta"
            " actualización masiva."
        )
      else:
        try:
          engine_pg = obtener_motor_postgres()
          query_update_etapa = text(
              'UPDATE "Medidores"."medidores_inteligentes" SET etapa = \'1\''
          )

          with engine_pg.connect() as conn_etapa:
            conn_etapa.execute(query_update_etapa)
            conn_etapa.commit()

          agregar_log(
              "⚡ [DB UPDATE] Se actualizó exitosamente el campo 'etapa' a '1'"
              " en todos los registros de Medidores.medidores_inteligentes."
          )
          st.success(
              "¡Se han actualizado correctamente todos los registros con la"
              " etapa 1!"
          )
          st.rerun()
        except Exception as e:
          st.error(f"Error al actualizar la tabla medidores_inteligentes: {e}")

  st.markdown(
      "<div style='margin-bottom: 15px;'></div>", unsafe_allow_html=True
  )

  with st.container(border=True):
    st.markdown(
        "#### 🔗 Sincronizar Etapa desde `medidores_inteligentes` hacia"
        " `usuarios_miaa_conmedidor`"
    )
    st.markdown(
        "Esta acción realiza un `JOIN` utilizando el campo de predio"
        " (`Predio_Viv`) para insertar o actualizar el número del campo"
        " **etapa** desde `medidores_inteligentes` hacia la tabla"
        ' `"Usuarios"."usuarios_miaa_conmedidor"`.'
    )

    confirmar_join_etapa = st.checkbox(
        "⚠ Confirmo que deseo actualizar el campo etapa en"
        " `usuarios_miaa_conmedidor` basado en la coincidencia de predio",
        key="chk_confirmar_join_etapa",
    )

    if st.button(
        "Ejecutar Sincronización de Etapa por Predio",
        type="primary",
        key="btn_ejecutar_join_etapa",
        use_container_width=True,
    ):
      if not confirmar_join_etapa:
        st.error(
            "Debes marcar la casilla de confirmación para ejecutar la"
            " sincronización."
        )
      else:
        try:
          engine_pg = obtener_motor_postgres()
          query_update_join = text("""
                        UPDATE "Usuarios"."usuarios_miaa_conmedidor" AS u
                        SET etapa = m.etapa
                        FROM "Medidores"."medidores_inteligentes" AS m
                        WHERE TRIM(CAST(u."Predio_Viv" AS TEXT)) = TRIM(CAST(m.predio AS TEXT))
                          AND m.etapa IS NOT NULL
                    """)

          with engine_pg.connect() as conn_join:
            resultado_update = conn_join.execute(query_update_join)
            conn_join.commit()
            filas_afectadas = (
                resultado_update.rowcount
                if hasattr(resultado_update, "rowcount")
                else "desconocido"
            )

          agregar_log(
              "🔗 [JOIN EXITOSO] Se sincronizó el campo 'etapa' desde"
              " medidores_inteligentes hacia usuarios_miaa_conmedidor por"
              f" predio. Filas afectadas: {filas_afectadas}"
          )
          st.success(
              f"¡Sincronización por predio completada con éxito! Filas"
              f" actualizadas: {filas_afectadas}"
          )
          st.rerun()
        except Exception as e:
          st.error(f"Error al ejecutar la actualización por JOIN: {e}")

  st.markdown(
      "<div style='margin-bottom: 15px;'></div>", unsafe_allow_html=True
  )

  with st.container(border=True):
    st.markdown("#### 🔍 Diagnóstico de Predios No Insertados / No Cruzados")
    st.markdown(
        "Identifica qué registros de `medidores_inteligentes` **no encontraron"
        " coincidencia** en `usuarios_miaa_conmedidor` y descubre la razón"
        " exacta por la que no se insertaron (por ejemplo: predio nulo,"
        " vacío, espacios en blanco o inexistente en la tabla destino)."
    )

    if st.button(
        "Analizar Predios No Cruzados (Auditoría)",
        key="btn_auditar_predios",
        use_container_width=True,
    ):
      try:
        engine_pg = obtener_motor_postgres()
        query_no_cruzados = text("""
                    SELECT m.* 
                    FROM "Medidores"."medidores_inteligentes" AS m
                    WHERE NOT EXISTS (
                        SELECT 1 
                        FROM "Usuarios"."usuarios_miaa_conmedidor" AS u
                        WHERE TRIM(CAST(u."Predio_Viv" AS TEXT)) = TRIM(CAST(m.predio AS TEXT))
                    )
                """)
        df_no_cruzados = pd.read_sql(query_no_cruzados, con=engine_pg)

        if df_no_cruzados.empty:
          st.success(
              "¡Excelente! Todos los registros de `medidores_inteligentes`"
              " tienen un predio válido que coincide en"
              " `usuarios_miaa_conmedidor`."
          )
        else:
          st.warning(
              f"Se encontraron **{len(df_no_cruzados):,}** registros en"
              " `medidores_inteligentes` que NO pudieron cruzarse."
          )

          def clasificar_motivo(row):
            p = row.get("predio")
            if pd.isna(p):
              return "Predio Nulo (NULL en base de datos)"
            p_str = str(p).strip()
            if p_str == "" or p_str.lower() in ["none", "nan", "null", "0"]:
              return "Predio Vacío, Cero o Inválido"
            return "Predio no existe en la tabla usuarios_miaa_conmedidor"

          df_no_cruzados["Motivo_No_Insercion"] = df_no_cruzados.apply(
              clasificar_motivo, axis=1
          )

          st.markdown(
              "##### 📊 Resumen de Motivos por los que no se cruzaron:"
          )
          conteo_motivos = df_no_cruzados["Motivo_No_Insercion"].value_counts()
          st.dataframe(conteo_motivos, use_container_width=True)

          st.markdown(
              "##### 📋 Listado Detallado de Registros No Cruzados:"
          )
          st.dataframe(df_no_cruzados, use_container_width=True, height=350)
      except Exception as e:
        st.error(f"Error al realizar el diagnóstico de predios: {e}")

  st.markdown(
      "<div style='margin-bottom: 15px;'></div>", unsafe_allow_html=True
  )
  st.markdown("#### 👁️ Vista previa de registros: `medidores_inteligentes`")

  try:
    engine_pg = obtener_motor_postgres()
    with engine_pg.connect() as conn_count:
      res_cnt = conn_count.execute(
          text('SELECT COUNT(*) FROM "Medidores"."medidores_inteligentes"')
      )
      total_mi = res_cnt.scalar() or 0

    if total_mi > 0:
      t3_filas = 50
      t3_total_pags = max(
          1,
          (total_mi // t3_filas)
          + (1 if total_mi % t3_filas > 0 else 0),
      )
      t3_pag = st.selectbox(
          "Seleccionar página (medidores_inteligentes)",
          range(1, t3_total_pags + 1),
          key="select_pag_t3",
      )
      t3_off = (t3_pag - 1) * t3_filas
      df_t3 = cargar_pagina_medidores_inteligentes(
          limit=t3_filas, offset=t3_off
      )
      st.dataframe(df_t3, use_container_width=True, height=400)
    else:
      st.warning("La tabla `medidores_inteligentes` está actualmente vacía.")
  except Exception as e:
    st.warning(
        f"No se pudo cargar la vista previa de `medidores_inteligentes`: {e}"
    )
