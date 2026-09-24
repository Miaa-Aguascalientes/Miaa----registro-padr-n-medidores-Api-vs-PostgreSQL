from datetime import datetime, timedelta
import time
from zoneinfo import ZoneInfo
import pandas as pd
import requests
from sqlalchemy import create_engine, text
import streamlit as st

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
            height: 250px;
            overflow-y: scroll;
            font-size: 13px;
            line-height: 1.4;
        }
    </style>
""",
    unsafe_allow_html=True,
)

# ==========================================
# 2. GESTIÓN DE ESTADOS
# ==========================================
ZONA_MEXICO = ZoneInfo("America/Mexico_City")

if "logs" not in st.session_state:
  hora_actual_mx = datetime.now(ZONA_MEXICO).strftime("%H:%M:%S")
  st.session_state.logs = [
      f"[{hora_actual_mx}] Sistema inicializado. Listo para operar."
  ]

if "is_running_timer" not in st.session_state:
  st.session_state.is_running_timer = False
if "next_run_time" not in st.session_state:
  st.session_state.next_run_time = None
if "total_seconds_interval" not in st.session_state:
  st.session_state.total_seconds_interval = 300  # 5 minutos por defecto

if "sync_progress" not in st.session_state:
  st.session_state.sync_progress = 0.0
if "sync_status_text" not in st.session_state:
  st.session_state.sync_status_text = "Sistema en reposo."


def agregar_log(mensaje):
  timestamp = datetime.now(ZONA_MEXICO).strftime("%H:%M:%S")
  st.session_state.logs.insert(0, f"[{timestamp}] {mensaje}")
  if len(st.session_state.logs) > 200:
    st.session_state.logs.pop()


def actualizar_estado_proceso(progreso, texto, log_msj=None):
  st.session_state.sync_progress = float(progreso)
  st.session_state.sync_status_text = str(texto)
  if log_msj:
    agregar_log(log_msj)


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
# 4. PROCESO DE SINCRONIZACIÓN RÁPIDO Y SEGURO
# ==========================================
def ejecutar_proceso_sincronizacion(es_automatico=False):
  tipo_ejec = "automático (periódico)" if es_automatico else "manual"
  actualizar_estado_proceso(
      0.05,
      "Iniciando ciclo...",
      f"🚀 Iniciando proceso de sincronización ({tipo_ejec}) con la API...",
  )

  try:
    usuario = st.secrets["api"]["usuario"]
    password = st.secrets["api"]["password"]
  except Exception as e:
    actualizar_estado_proceso(0.0, "Error en secretos", f"❌ Error leyendo st.secrets: {e}")
    return

  actualizar_estado_proceso(
      0.15,
      "Conectando al login de MIAA...",
      "🔄 [Paso 1/3] Conectando al login de MIAA...",
  )
  try:
    res_login = requests.post(
        url_login,
        json={"username": usuario, "password": password},
        headers={"Content-Type": "application/json"},
        timeout=20,
    )
  except Exception as e:
    actualizar_estado_proceso(0.0, "Error de red en login", f"❌ Error de red al conectar al login: {e}")
    return

  if res_login.status_code != 200:
    actualizar_estado_proceso(0.0, f"Error HTTP {res_login.status_code}", f"❌ Falló la autenticación. Código: {res_login.status_code}")
    return

  try:
    token = res_login.json().get("token") or res_login.json().get(
        "access_token"
    )
  except Exception:
    token = None

  if not token:
    actualizar_estado_proceso(0.0, "Token no encontrado", "❌ No se pudo extraer el token de acceso.")
    return

  actualizar_estado_proceso(
      0.30,
      "Descargando instalaciones de la API...",
      "✅ Autenticación exitosa. Solicitando endpoint de instalaciones...",
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
  except Exception as e:
    actualizar_estado_proceso(0.0, "Error descargando instalaciones", f"❌ Error al descargar instalaciones: {e}")
    return

  if res_inst.status_code != 200:
    actualizar_estado_proceso(0.0, f"Error HTTP {res_inst.status_code}", f"❌ Error HTTP en instalaciones: {res_inst.status_code}")
    return

  try:
    data = res_inst.json()
  except Exception as e:
    actualizar_estado_proceso(0.0, "Error decodificando JSON", f"❌ Error al decodificar JSON: {e}")
    return

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
    actualizar_estado_proceso(0.0, "Dataset vacío", "❌ El dataset devuelto por la API está vacío.")
    return

  actualizar_estado_proceso(
      0.50,
      f"Procesando {len(df):,} registros...",
      f"📦 Se obtuvieron {len(df):,} registros de la API. Mapeando y cargando en tabla temporal...",
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

  actualizar_estado_proceso(
      0.70,
      "Conectando a PostgreSQL y aplicando cambios masivos...",
      "🔄 [Paso 3/3] Conectando a PostgreSQL para actualizar registros en lote...",
  )
  try:
    engine_pg = obtener_motor_postgres()
  except Exception as e:
    actualizar_estado_proceso(0.0, f"Error PG: {e}", f"❌ Error al conectar a PostgreSQL: {e}")
    return

  # Preparamos un DataFrame limpio optimizado para inserción en lote (staging temporal)
  df_staging = pd.DataFrame()
  df_staging["p_val"] = df[col_predio].astype(str).str.strip() if col_predio else ""
  df_staging["c_val"] = df[col_cliente].astype(str).str.strip() if col_cliente else ""
  df_staging["s_val"] = df[col_serie].astype(str).str.strip() if col_serie else None
  df_staging["col_val"] = df[col_colonia].astype(str).str.strip() if col_colonia else None
  df_staging["dom_val"] = df[col_domicilio].astype(str).str.strip() if col_domicilio else None
  df_staging["inst_val"] = df[col_instalador].astype(str).str.strip() if col_instalador else None

  def parsear_tipo(val):
    if pd.isna(val):
      return "MIAA"
    if str(val).strip().lower() in ["true", "1", "yes", "s", "true"]:
      return "Externo"
    return "MIAA"

  df_staging["tipo_val"] = df[col_ext].apply(parsear_tipo) if col_ext else "MIAA"
  df_staging["lec_val"] = pd.to_numeric(df[col_lec], errors="coerce") if col_lec else None
  df_staging["freg_val"] = pd.to_datetime(df[col_freg], errors="coerce") if col_freg else None
  df_staging["finst_val"] = pd.to_datetime(df[col_finst], errors="coerce") if col_finst else None

  # Eliminamos filas sin predio ni cliente válidos
  df_staging = df_staging[
      (df_staging["p_val"] != "") & (df_staging["p_val"].str.lower() != "nan")
      | (df_staging["c_val"] != "") & (df_staging["c_val"].str.lower() != "nan")
  ]

  total_a_procesar = len(df_staging)
  agregar_log(f"🛠️ Subiendo {total_a_procesar:,} registros limpios a tabla temporal y sincronizando...")

  try:
    with engine_pg.begin() as conn:
      # Crear tabla temporal de staging en PostgreSQL
      conn.execute(text("DROP TABLE IF EXISTS temp_staging_miaa;"))
      df_staging.to_sql(
          "temp_staging_miaa",
          con=conn,
          if_exists="replace",
          index=False,
          chunksize=5000,
      )

      # Ejecutar UPDATE masivo optimizado por lote en la base de datos
      conn.execute(text("""
                UPDATE "Usuarios"."usuarios_miaa_conmedidor" AS t
                SET 
                    "_Serie" = COALESCE(NULLIF(t."_Serie"::text, ''), s.s_val),
                    "_Colonia" = COALESCE(NULLIF(t."_Colonia"::text, ''), s.col_val),
                    "_Domicilio" = COALESCE(NULLIF(t."_Domicilio"::text, ''), s.dom_val),
                    "_Instalador" = COALESCE(NULLIF(t."_Instalador"::text, ''), s.inst_val),
                    "_Tipo_instalador" = COALESCE(NULLIF(t."_Tipo_instalador"::text, ''), s.tipo_val),
                    "_Lectura_actual" = COALESCE(t."_Lectura_actual", s.lec_val),
                    "_Fecha_registro" = COALESCE(t."_Fecha_registro", s.freg_val),
                    "_Fecha_instalacion" = COALESCE(t."_Fecha_instalacion", s.finst_val)
                FROM temp_staging_miaa AS s
                WHERE 
                    (s.p_val != '' AND t."Predio_Viv"::text = s.p_val)
                    OR 
                    (s.c_val != '' AND t."Cliente"::text = s.c_val);
            """))

      conn.execute(text("DROP TABLE IF EXISTS temp_staging_miaa;"))

    resumen_final = (
        f"✅ ¡Sincronización masiva en PostgreSQL completada con éxito!<br>• Registros"
        f" procesados: {total_a_procesar:,}"
    )
    actualizar_estado_proceso(1.0, "¡Sincronización completada!", resumen_final)
    st.session_state.ultimo_tiempo_ejecucion = time.time()
  except Exception as e:
    actualizar_estado_proceso(0.0, f"Error en DB: {e}", f"❌ Error crítico en lote con PostgreSQL: {e}")


# ==========================================
# 5. BARRA LATERAL (SIDEBAR)
# ==========================================
with st.sidebar:
  st.markdown("<h2>⚙️ Configuración</h2>", unsafe_allow_html=True)
  st.markdown("---")

  st.markdown("#### Ejecución Manual")
  if st.button("🚀 Ejecutar Ahora", type="primary", use_container_width=True):
    if st.session_state.sync_progress > 0 and st.session_state.sync_progress < 1.0:
      st.warning("Ya hay un proceso en ejecución.")
    else:
      ejecutar_proceso_sincronizacion(es_automatico=False)
      st.rerun()

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
  st.session_state.total_seconds_interval = opciones_intervalo[intervalo_sel]

  col_sb1, col_sb2 = st.columns(2)
  with col_sb1:
    btn_iniciar = st.button("INICIAR", type="primary", use_container_width=True)
  with col_sb2:
    btn_parar = st.button("PARAR", type="secondary", use_container_width=True)

  if btn_iniciar:
    st.session_state.is_running_timer = True
    st.session_state.next_run_time = datetime.now(ZONA_MEXICO) + timedelta(
        seconds=st.session_state.total_seconds_interval
    )
    agregar_log(
        f"⏱️ Temporizador automático activado ({intervalo_sel.lower()})."
    )
    st.success("¡Temporizador activo!")
    st.rerun()

  if btn_parar:
    st.session_state.is_running_timer = False
    st.session_state.next_run_time = None
    agregar_log("🛑 Temporizador automático detenido.")
    st.warning("Temporizador detenido.")
    st.rerun()

# ==========================================
# 6. TÍTULO PRINCIPAL
# ==========================================
st.markdown(
    "<h2>MIAA - Sistema de Registros e Instalaciones</h2>", unsafe_allow_html=True
)
st.markdown("---")


# ==========================================
# 7. CONTROLADOR DEL TEMPORIZADOR (SEGURO SIN CONGELAMIENTO)
# ==========================================
if st.session_state.is_running_timer and st.session_state.next_run_time:
  ahora_mx = datetime.now(ZONA_MEXICO)
  if ahora_mx >= st.session_state.next_run_time:
    ejecutar_proceso_sincronizacion(es_automatico=True)
    st.session_state.next_run_time = datetime.now(ZONA_MEXICO) + timedelta(
        seconds=st.session_state.total_seconds_interval
    )
    st.rerun()

# ==========================================
# 8. VISUALIZACIÓN DE ESTADO Y CONSOLA EN VIVO
# ==========================================
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
      " margin-bottom: 2px;'>⏸️ Temporizador inactivo. Usa 'INICIAR' en la"
      " barra lateral.</p>",
      unsafe_allow_html=True,
  )
  st.progress(0.0)

st.markdown("#### 🖥️ Consola de Registros en Tiempo Real (Trazas PostgreSQL)")
logs_html = "<br>".join(st.session_state.logs)
st.markdown(
    f'<div class="terminal-box">{logs_html}</div>', unsafe_allow_html=True
)

st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)
current_prog = st.session_state.sync_progress
current_text = st.session_state.sync_status_text

if 0.0 < current_prog < 1.0:
  st.markdown(
      f"<p style='font-size: 13px; color: #f59e0b; font-weight: bold;"
      f" margin-bottom: 4px;'>🔄 Base de Datos (PostgreSQL): {current_text}"
      f" ({int(current_prog * 100)}%)</p>",
      unsafe_allow_html=True,
  )
elif current_prog >= 1.0:
  st.markdown(
      f"<p style='font-size: 13px; color: #22c55e; font-weight: bold;"
      f" margin-bottom: 4px;'>{current_text}</p>",
      unsafe_allow_html=True,
  )
else:
  st.markdown(
      f"<p style='font-size: 13px; color: #94a3b8; font-style: italic;"
      f" margin-bottom: 4px;'>💤 Estado: {current_text}</p>",
      unsafe_allow_html=True,
  )

st.progress(current_prog)

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

            agregar_log(
                f"Limpieza masiva ejecutada en campos: {campos_a_limpiar_masivo}"
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
