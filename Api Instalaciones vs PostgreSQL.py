from datetime import datetime, timedelta
import threading
import time
from zoneinfo import ZoneInfo
import pandas as pd
import requests
from sqlalchemy import create_engine, text
import streamlit as st
from streamlit.runtime.scriptrunner import add_script_run_ctx

# ==========================================
# 1. CONFIGURACIÓN DE PÁGINA Y ESTILOS
# ==========================================
st.set_page_config(
    page_title="Gestor de Registros MIAA", page_icon="🚰", layout="wide"
)

st.markdown(
    """
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
        .terminal-box {
            background-color: #0b0f19;
            border: 1px solid #22c55e;
            color: #22c55e;
            font-family: 'Courier New', Courier, monospace;
            padding: 15px;
            border-radius: 6px;
            height: 220px;
            overflow-y: scroll;
            font-size: 13px;
            line-height: 1.4;
        }
    </style>
""",
    unsafe_allow_html=True,
)

# ==========================================
# 2. GESTIÓN DE ESTADOS Y HILO SEGURO
# ==========================================
ZONA_MEXICO = ZoneInfo("America/Mexico_City")

if "logs" not in st.session_state:
  hora_actual_mx = datetime.now(ZONA_MEXICO).strftime("%H:%M:%S")
  st.session_state.logs = [
      f"[{hora_actual_mx}] Sistema inicializado en segundo plano. Listo para"
      " operar."
  ]

if "is_syncing" not in st.session_state:
  st.session_state.is_syncing = False

if "sync_progress" not in st.session_state:
  st.session_state.sync_progress = 0.0  # 0.0 a 1.0

if "sync_status_text" not in st.session_state:
  st.session_state.sync_status_text = "Sistema en reposo."

log_lock = threading.Lock()


def actualizar_estado_proceso(progreso, texto, log_msj=None):
  with log_lock:
    st.session_state.sync_progress = float(progreso)
    st.session_state.sync_status_text = str(texto)
    if log_msj:
      timestamp = datetime.now(ZONA_MEXICO).strftime("%H:%M:%S")
      st.session_state.logs.insert(0, f"[{timestamp}] {log_msj}")
      if len(st.session_state.logs) > 150:
        st.session_state.logs.pop()


# ==========================================
# 3. CONEXIONES Y CONSULTAS SQL
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
  except Exception:
    return 0


@st.cache_data(ttl=600)
def obtener_total_con_serie():
  try:
    engine_pg = obtener_motor_postgres()
    with engine_pg.connect() as conn:
      result = conn.execute(
          text(
              'SELECT COUNT(*) FROM "Usuarios"."usuarios_miaa_conmedidor" WHERE'
              ' "_Serie" IS NOT NULL AND TRIM(CAST("_Serie" AS TEXT)) != \'\''
          )
      )
      return result.scalar()
  except Exception:
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
  except Exception:
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
        timeout=15,
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
            timeout=30,
        )
        if res_inst.status_code == 200:
          data = res_inst.json()
          if isinstance(data, list):
            return pd.DataFrame(data)
          elif isinstance(data, dict):
            for key in ["data", "result", "items", "instalaciones"]:
              if key in data and isinstance(data[key], list):
                return pd.DataFrame(data[key])
            return pd.DataFrame([data])
    return pd.DataFrame()
  except Exception:
    return pd.DataFrame()


# ==========================================
# 4. PROCESO EN SEGUNDO PLANO (HILO SEGURO)
# ==========================================
def ejecutar_sincronizacion_background(
    api_user, api_pass, pg_user, pg_pass, pg_host, pg_port, pg_db
):
  if st.session_state.is_syncing:
    return
  st.session_state.is_syncing = True

  try:
    actualizar_estado_proceso(
        0.1,
        "Conectando con la API de MIAA...",
        "🔄 [Paso 1/4] Iniciando autenticación con la API de MIAA...",
    )

    try:
      res_login = requests.post(
          url_login,
          json={"username": api_user, "password": api_pass},
          headers={"Content-Type": "application/json"},
          timeout=15,
      )
    except requests.exceptions.Timeout:
      actualizar_estado_proceso(
          0.0,
          "Error: Timeout en login API",
          "❌ Error crítico: La API de MIAA tardó demasiado en responder en el"
          " login (Timeout).",
      )
      return
    except Exception as ex_log:
      actualizar_estado_proceso(
          0.0,
          f"Error de red: {ex_log}",
          f"❌ Error de red al conectar con el login de la API: {ex_log}",
      )
      return

    if res_login.status_code != 200:
      actualizar_estado_proceso(
          0.0,
          f"Error HTTP {res_login.status_code} en Login",
          f"❌ Error crítico: Falló la autenticación con la API (Código"
          f" {res_login.status_code}).",
      )
      return

    token = res_login.json().get("token") or res_login.json().get(
        "access_token"
    )
    if not token:
      actualizar_estado_proceso(
          0.0,
          "Error: Token no encontrado",
          "❌ Error crítico: La respuesta del login no contiene token de acceso.",
      )
      return

    actualizar_estado_proceso(
        0.3,
        "Descargando registros de instalaciones...",
        "✅ Autenticación exitosa. Descargando registros de instalaciones"
        " desde la API...",
    )

    try:
      res_inst = requests.get(
          url_instalaciones,
          headers={
              "Content-Type": "application/json",
              "Authorization": f"Bearer {token}",
          },
          timeout=45,
      )
    except requests.exceptions.Timeout:
      actualizar_estado_proceso(
          0.0,
          "Error: Timeout descargando instalaciones",
          "❌ Error crítico: La API tardó demasiado tiempo en devolver las"
          " instalaciones (Timeout).",
      )
      return
    except Exception as ex_inst:
      actualizar_estado_proceso(
          0.0,
          f"Error descargando: {ex_inst}",
          f"❌ Error al solicitar las instalaciones a la API: {ex_inst}",
      )
      return

    if res_inst.status_code != 200:
      actualizar_estado_proceso(
          0.0,
          f"Error HTTP {res_inst.status_code} en instalaciones",
          f"❌ Error crítico: La API devolvió código HTTP"
          f" {res_inst.status_code} al pedir instalaciones.",
      )
      return

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
    else:
      df = pd.DataFrame()

    if df.empty:
      actualizar_estado_proceso(
          0.0, "Error: Dataset vacío", "❌ Error: La API devolvió datos vacíos."
      )
      return

    actualizar_estado_proceso(
        0.5,
        f"Procesando {len(df):,} registros descargados...",
        f"📦 Registros obtenidos de la API: {len(df):,}. Limpiando columnas y"
        " armando Predio_Viv...",
    )

    cols_a_remover = [
        c
        for c in df.columns
        if any(
            term in c.lower() for term in ["foto", "imagen", "img", "fotografia"]
        )
    ]
    df = df.drop(columns=cols_a_remover, errors="ignore")

    col_api_predio = next(
        (
            c
            for c in ["predio", "predioViv", "predio_viv", "numeroPredio"]
            if c in df.columns
        ),
        None,
    )
    col_api_unidad = next(
        (c for c in ["unidad", "unidadViv", "unidad_viv"] if c in df.columns),
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

    actualizar_estado_proceso(
        0.7,
        "Creando tabla temporal en PostgreSQL...",
        "🔄 [Paso 2/4] Conectando con PostgreSQL y creando tabla temporal"
        " (temp_api_staging)...",
    )
    connection_string = f"postgresql+psycopg2://{pg_user}:{pg_pass}@{pg_host}:{pg_port}/{pg_db}"
    engine_pg = create_engine(connection_string)

    df_staging = pd.DataFrame()
    col_predio = next(
        (
            c
            for c in ["Predio_Viv", "predioViv", "predio_viv", "predio"]
            if c in df.columns
        ),
        None,
    )
    col_cliente = next(
        (
            c
            for c in ["numeroCliente", "numero_cliente", "cliente", "Cliente"]
            if c in df.columns
        ),
        None,
    )
    col_serie = next(
        (c for c in ["serie", "Serie", "numeroSerie"] if c in df.columns), None
    )
    col_colonia = next((c for c in ["colonia", "Colonia"] if c in df.columns), None)
    col_domicilio = next(
        (c for c in ["domicilio", "Domicilio", "direccion"] if c in df.columns),
        None,
    )
    col_instalador = next(
        (c for c in ["usuarioNombre", "instalador"] if c in df.columns), None
    )
    col_ext = next((c for c in ["usuarioExterno"] if c in df.columns), None)
    col_lec = next(
        (c for c in ["lecturaActual", "lectura"] if c in df.columns), None
    )
    col_freg = next((c for c in ["fechaRegistro"] if c in df.columns), None)
    col_finst = next((c for c in ["fechaInstalacion"] if c in df.columns), None)

    df_staging["api_predio"] = (
        df[col_predio].astype(str).str.strip() if col_predio else ""
    )
    df_staging["api_cliente"] = (
        df[col_cliente].astype(str).str.strip() if col_cliente else ""
    )
    df_staging["api_serie"] = (
        df[col_serie].astype(str).str.strip() if col_serie else None
    )
    df_staging["api_colonia"] = (
        df[col_colonia].astype(str).str.strip() if col_colonia else None
    )
    df_staging["api_domicilio"] = (
        df[col_domicilio].astype(str).str.strip() if col_domicilio else None
    )
    df_staging["api_instalador"] = (
        df[col_instalador].astype(str).str.strip() if col_instalador else None
    )
    df_staging["api_lectura"] = (
        pd.to_numeric(df[col_lec], errors="coerce") if col_lec else None
    )
    df_staging["api_freg"] = (
        pd.to_datetime(df[col_freg], errors="coerce") if col_freg else None
    )
    df_staging["api_finst"] = (
        pd.to_datetime(df[col_finst], errors="coerce") if col_finst else None
    )

    if col_ext:

      def map_ext(val):
        if val in [True, 1, "1", "true", "True", "YES", "yes", "S", "s"]:
          return "Externo"
        return "MIAA"

      df_staging["api_tipo"] = df[col_ext].apply(map_ext)
    else:
      df_staging["api_tipo"] = "MIAA"

    with engine_pg.begin() as conn:
      actualizar_estado_proceso(
          0.85,
          "Insertando en tabla staging (temp_api_staging)...",
          "💾 Subiendo registros en bloques a 'temp_api_staging' en PostgreSQL...",
      )
      df_staging.to_sql(
          "temp_api_staging",
          con=conn,
          if_exists="replace",
          index=False,
          method="multi",
          chunksize=5000,
      )

    actualizar_estado_proceso(
        0.95,
        "Ejecutando UPDATE masivo en base de datos...",
        "🔄 [Paso 3/4] Ejecutando sentencia UPDATE masiva en PostgreSQL (cruces"
        " por Predio o Cliente)...",
    )
    query_update = text("""
            UPDATE "Usuarios"."usuarios_miaa_conmedidor" AS u
            SET 
                "_Serie" = COALESCE(NULLIF(u."_Serie"::text, ''), t.api_serie),
                "_Colonia" = COALESCE(NULLIF(u."_Colonia"::text, ''), t.api_colonia),
                "_Domicilio" = COALESCE(NULLIF(u."_Domicilio"::text, ''), t.api_domicilio),
                "_Instalador" = COALESCE(NULLIF(u."_Instalador"::text, ''), t.api_instalador),
                "_Tipo_instalador" = COALESCE(NULLIF(u."_Tipo_instalador"::text, ''), t.api_tipo),
                "_Lectura_actual" = COALESCE(u."_Lectura_actual", t.api_lectura),
                "_Fecha_registro" = COALESCE(u."_Fecha_registro", t.api_freg),
                "_Fecha_instalacion" = COALESCE(u."_Fecha_instalacion", t.api_finst)
            FROM temp_api_staging AS t
            WHERE 
                (u."Predio_Viv" IS NOT NULL AND TRIM(u."Predio_Viv"::text) != '' AND u."Predio_Viv"::text = t.api_predio)
                OR 
                (u."Cliente" IS NOT NULL AND TRIM(u."Cliente"::text) != '' AND u."Cliente"::text = t.api_cliente);
        """)

    with engine_pg.begin() as conn:
      conn.execute(query_update)

    actualizar_estado_proceso(
        1.0,
        "¡Sincronización completada con éxito!",
        "✅ [Paso 4/4] Sincronización completada exitosamente en la base de"
        " datos!",
    )

  except Exception as e:
    actualizar_estado_proceso(
        0.0, f"Error crítico: {e}", f"❌ Excepción crítica en el proceso: {e}"
    )
  finally:
    st.session_state.is_syncing = False


def disparar_hilo():
  if not st.session_state.is_syncing:
    with log_lock:
      timestamp = datetime.now(ZONA_MEXICO).strftime("%H:%M:%S")
      st.session_state.logs.insert(
          0, f"[{timestamp}] 🚀 Hilo de ejecución en segundo plano iniciado."
      )

    # LEEMOS LOS SECRETOS AQUÍ EN EL HILO PRINCIPAL ANTES DE ARRANCAR
    api_user = st.secrets["api"]["usuario"]
    api_pass = st.secrets["api"]["password"]
    pg = st.secrets["postgres"]

    hilo = threading.Thread(
        target=ejecutar_sincronizacion_background,
        args=(
            api_user,
            api_pass,
            pg["user"],
            pg["password"],
            pg["host"],
            pg["port"],
            pg["database"],
        ),
        daemon=True,
    )
    add_script_run_ctx(hilo)
    hilo.start()


# ==========================================
# 5. CONFIGURACIÓN DE ESTADOS TEMPORIZADOR
# ==========================================
if "is_running_timer" not in st.session_state:
  st.session_state.is_running_timer = False
if "next_run_time" not in st.session_state:
  st.session_state.next_run_time = None
if "total_seconds_interval" not in st.session_state:
  st.session_state.total_seconds_interval = 300

# ==========================================
# 6. BARRA LATERAL (SIDEBAR)
# ==========================================
with st.sidebar:
  st.markdown("<h2>⚙️ Configuración</h2>", unsafe_allow_html=True)
  st.markdown("---")

  st.markdown("#### Ejecución Manual")
  if st.button("🚀 Ejecutar Ahora", type="primary", use_container_width=True):
    if not st.session_state.is_syncing:
      disparar_hilo()
      st.rerun()
    else:
      st.warning(
          "El sistema ya se encuentra ejecutando un proceso de inserción."
      )

  st.markdown("---")
  st.markdown("#### Ejecución Periódica")

  opciones_intervalo = {
      "Cada 1 minuto": 60,
      "Cada 5 minutos": 300,
      "Cada 15 minutos": 900,
      "Cada 30 minutos": 1800,
      "Cada hora": 3600,
  }
  intervalo_sel = st.selectbox(
      "Seleccionar Intervalo", list(opciones_intervalo.keys())
  )
  total_segundos = opciones_intervalo[intervalo_sel]

  col_sb1, col_sb2 = st.columns(2)
  with col_sb1:
    btn_iniciar = st.button("INICIAR", type="primary", use_container_width=True)
  with col_sb2:
    btn_parar = st.button("PARAR", type="secondary", use_container_width=True)

  if btn_iniciar:
    st.session_state.is_running_timer = True
    st.session_state.total_seconds_interval = total_segundos
    st.session_state.next_run_time = datetime.now(ZONA_MEXICO) + timedelta(
        seconds=total_segundos
    )
    with log_lock:
      ts = datetime.now(ZONA_MEXICO).strftime("%H:%M:%S")
      st.session_state.logs.insert(
          0, f"[{ts}] Temporizador automático activado ({intervalo_sel.lower()})."
      )
    st.success("¡Temporizador activo!")
    st.rerun()

  if btn_parar:
    st.session_state.is_running_timer = False
    st.session_state.next_run_time = None
    with log_lock:
      ts = datetime.now(ZONA_MEXICO).strftime("%H:%M:%S")
      st.session_state.logs.insert(
          0, f"[{ts}] Temporizador automático detenido."
      )
    st.warning("Temporizador detenido.")
    st.rerun()

# ==========================================
# 7. TÍTULO PRINCIPAL
# ==========================================
st.markdown(
    "<h2>MIAA - Sistema de Registros e Instalaciones</h2>", unsafe_allow_html=True
)
st.markdown("---")


# ==========================================
# 8. FRAGMENTO REACTIVO EN VIVO (CONSOLA + BARRA DE PROGRESO REAL)
# ==========================================
@st.fragment(run_every=0.5)
def renderizar_consola_y_progreso():
  if st.session_state.is_running_timer and st.session_state.next_run_time:
    ahora_mx = datetime.now(ZONA_MEXICO)
    if ahora_mx >= st.session_state.next_run_time:
      if not st.session_state.is_syncing:
        disparar_hilo()
      st.session_state.next_run_time = datetime.now(ZONA_MEXICO) + timedelta(
          seconds=st.session_state.total_seconds_interval
      )

  if st.session_state.is_running_timer and st.session_state.next_run_time:
    ahora_mx = datetime.now(ZONA_MEXICO)
    restante = max(
        0, int((st.session_state.next_run_time - ahora_mx).total_seconds())
    )
    total = st.session_state.total_seconds_interval
    progreso_timer = min(1.0, max(0.0, (total - restante) / total))
    mins, secs = divmod(restante, 60)
    st.markdown(
        f"<p style='font-size: 13px; color: #38bdf8; font-weight: bold;"
        f" margin-bottom: 2px;'>⏱️ Próxima ejecución automática en:"
        f" {mins:02d}:{secs:02d}</p>",
        unsafe_allow_html=True,
    )
    st.progress(progreso_timer)
  else:
    st.markdown(
        "<p style='font-size: 13px; color: #94a3b8; font-style: italic;"
        " margin-bottom: 2px;'>⏸️ Temporizador inactivo. Usa 'Ejecutar Ahora'"
        " en la barra lateral.</p>",
        unsafe_allow_html=True,
    )
    st.progress(0.0)

  st.markdown("#### 🖥️ Consola de Registros en Tiempo Real")
  with log_lock:
    logs_html = "<br>".join(st.session_state.logs)
  st.markdown(
      f'<div class="terminal-box">{logs_html}</div>', unsafe_allow_html=True
  )

  st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)
  current_prog = st.session_state.sync_progress
  current_text = st.session_state.sync_status_text

  if st.session_state.is_syncing:
    st.markdown(
        f"<p style='font-size: 13px; color: #f59e0b; font-weight: bold;"
        f" margin-bottom: 4px;'>🔄 Estado de Inserción: {current_text}"
        f" ({int(current_prog * 100)}%)</p>",
        unsafe_allow_html=True,
    )
  elif current_prog >= 1.0:
    st.markdown(
        f"<p style='font-size: 13px; color: #22c55e; font-weight: bold;"
        f" margin-bottom: 4px;'>✅ Estado de Inserción: {current_text}"
        " (100%)</p>",
        unsafe_allow_html=True,
    )
  else:
    st.markdown(
        f"<p style='font-size: 13px; color: #94a3b8; font-style: italic;"
        f" margin-bottom: 4px;'>💤 Estado de Inserción: {current_text}</p>",
        unsafe_allow_html=True,
    )

  st.progress(current_prog)


renderizar_consola_y_progreso()

st.markdown("---")

# ==========================================
# 9. INDICADORES Y PESTAÑAS
# ==========================================
total_registros_db = obtener_total_registros()
total_con_serie = obtener_total_con_serie()
df_filtrado = cargar_datos_api()
total_registros_api = len(df_filtrado) if not df_filtrado.empty else 0

if total_registros_db > 0:
  c_m1, c_m2, c_m3 = st.columns(3)
  with c_m1:
    st.markdown(
        f"""
            <div class="metric-card">
                <div class="metric-icon-box" style="color: #38bdf8;"><i class="fa-solid fa-database"></i></div>
                <div class="metric-content">
                    <div class="metric-title">Total Registros (PG)</div>
                    <div class="metric-value">{total_registros_db:,}</div>
                </div>
            </div>
        """,
        unsafe_allow_html=True,
    )
  with c_m2:
    st.markdown(
        f"""
            <div class="metric-card">
                <div class="metric-icon-box" style="color: #4ade80;"><i class="fa-solid fa-barcode"></i></div>
                <div class="metric-content">
                    <div class="metric-title">Predios con Serie</div>
                    <div class="metric-value">{total_con_serie:,}</div>
                </div>
            </div>
        """,
        unsafe_allow_html=True,
    )
  with c_m3:
    st.markdown(
        f"""
            <div class="metric-card">
                <div class="metric-icon-box" style="color: #f59e0b;"><i class="fa-solid fa-cloud-arrow-down"></i></div>
                <div class="metric-content">
                    <div class="metric-title">Registros en la API</div>
                    <div class="metric-value">{total_registros_api:,}</div>
                </div>
            </div>
        """,
        unsafe_allow_html=True,
    )

  st.markdown("<div style='margin-bottom: 15px;'></div>", unsafe_allow_html=True)

tab1, tab2 = st.tabs([
    "🚰 Panel Principal y Gestión",
    "📋 Tablas de Datos (PostgreSQL y API)",
])

with tab1:
  st.markdown(
      "<p style='font-size:16px; font-weight:bold; margin-bottom:10px;'>Gestión"
      ' de Tabla PostgreSQL: usuarios_miaa_conmedidor</p>',
      unsafe_allow_html=True,
  )
  if total_registros_db > 0:
    with st.container(border=True):
      st.markdown(
          "#### 🧹 Limpieza Masiva de Campos (Sin eliminar registros)"
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
      ]

      campos_a_limpiar_masivo = []
      cols_check = st.columns(4)
      for i, campo in enumerate(campos_disponibles):
        with cols_check[i % 4]:
          if st.checkbox(f"Vaciar {campo}", key=f"chk_masivo_{campo}"):
            campos_a_limpiar_masivo.append(campo)

      confirmar_masivo = st.checkbox(
          "⚠️ Confirmo que quiero vaciar masivamente estos campos en TODA la"
          " tabla",
          key="chk_confirmar_masivo",
      )

      if st.button(
          "Ejecutar Limpieza Masiva",
          type="primary",
          key="btn_ejecutar_masivo",
      ):
        if not campos_a_limpiar_masivo:
          st.error("Por favor, selecciona al menos un campo para limpiar.")
        elif not confirmar_masivo:
          st.error(
              "Debes marcar la casilla de confirmación para ejecutar esta"
              " acción masiva."
          )
        else:
          try:
            engine_pg = obtener_motor_postgres()
            set_clausulas = [f'"{campo}" = NULL' for campo in campos_a_limpiar_masivo]
            set_sql = ", ".join(set_clausulas)
            query_update_masivo = text(
                f'UPDATE "Usuarios"."usuarios_miaa_conmedidor" SET {set_sql}'
            )

            with engine_pg.connect() as conn_up:
              conn_up.execute(query_update_masivo)
              conn_up.commit()

            with log_lock:
              ts = datetime.now(ZONA_MEXICO).strftime("%H:%M:%S")
              st.session_state.logs.insert(
                  0,
                  f"[{ts}] Limpieza masiva ejecutada en campos:"
                  f" {campos_a_limpiar_masivo}",
              )
            st.success("¡Los campos seleccionados han sido vaciados con éxito!")
            st.rerun()
          except Exception as e:
            st.error(f"Error al ejecutar la limpieza masiva: {e}")

    st.markdown("<div style='margin-bottom: 15px;'></div>", unsafe_allow_html=True)

    with st.container(border=True):
      st.markdown(
          "<p style='font-size:13px; font-weight:bold;"
          " margin-bottom:8px;'>Vista Previa Paginada (Carga instantánea)</p>",
          unsafe_allow_html=True,
      )

      filas_por_pagina = 50
      total_paginas = max(
          1,
          (total_registros_db // filas_por_pagina)
          + (1 if total_registros_db % filas_por_pagina > 0 else 0),
      )

      col_p1, col_p2 = st.columns([1, 3])
      with col_p1:
        pagina_actual = st.number_input(
            "Página",
            min_value=1,
            max_value=total_paginas,
            value=1,
            step=1,
            key="num_pag_t1",
        )
      with col_p2:
        st.markdown(
            f"<p style='margin-top: 25px; color: #94a3b8;'>Página"
            f" {pagina_actual} de {total_paginas} (Bloques de 50 registros)</p>",
            unsafe_allow_html=True,
        )

      offset_val = (pagina_actual - 1) * filas_por_pagina
      df_pagina_pg = cargar_pagina_usuarios_db(
          limit=filas_por_pagina, offset=offset_val
      )

      st.dataframe(df_pagina_pg, use_container_width=True, height=400)
  else:
    st.warning("No se encontraron registros en la tabla.")

with tab2:
  st.subheader(
      "🚰 Tabla: usuarios_miaa_conmedidor (PostgreSQL - Bloques SQL)"
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

  st.markdown("---")

  st.subheader(
      "🌐 Tabla: Datos de la API de Instalación (Todos los registros)"
  )
  if not df_filtrado.empty:
    st.dataframe(df_filtrado, use_container_width=True, height=350)
  else:
    st.warning("No hay datos cargados desde la API.")
