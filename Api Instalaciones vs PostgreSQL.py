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
      f"[{datetime.now(ZONA_MEXICO).strftime('%H:%M:%S')}] Sistema inicializado correctamente. Esperando ciclo de ejecución..."
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

            cols_a_remover = [
                c
                for c in df.columns
                if any(
                    term in c.lower()
                    for term in ["foto", "imagen", "img", "fotografia"]
                )
            ]
            df = df.drop(columns=cols_a_remover, errors="ignore")

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
# 4. FUNCIÓN DE CRUCE ESTRICTO Y EJECUCIÓN CON PROGRESO VIVO
# ==========================================
def procesar_cruce_datos(
    df_conmedidor_pg, df_filtrado, registrar_auditoria=False
):
  if df_filtrado.empty or df_conmedidor_pg.empty:
    agregar_log(
        "⚠️ [CRUCE] Uno de los DataFrames está vacío. No se puede realizar el"
        " cruce."
    )
    return df_conmedidor_pg, 0, 0

  df_api = df_filtrado.copy()
  df_api["key_predio"] = (
      df_api["Predio_Viv"].astype(str).str.strip()
      if "Predio_Viv" in df_api.columns
      else ""
  )
  invalidos = {"none", "nan", "", "nat", "0", "null", "None", "NaN"}

  def mapear_tipo_externo(val):
    if val in [True, 1, "1", "true", "True", "YES", "yes", "S", "s"]:
      return "Externo"
    elif val in [False, 0, "0", "false", "False", "NO", "no", "N", "n"]:
      return "MIAA"
    return "MIAA"

  if "usuarioExterno" in df_api.columns:
    df_api["tipo_calculado"] = df_api["usuarioExterno"].apply(
        mapear_tipo_externo
    )
  else:
    df_api["tipo_calculado"] = "MIAA"

  df_api_con_predio = df_api[
      ~df_api["key_predio"].str.lower().isin(invalidos)
  ].copy()

  dict_serie_p = dict(
      zip(df_api_con_predio["key_predio"], df_api_con_predio.get("serie", ""))
  )
  dict_colonia_p = dict(
      zip(
          df_api_con_predio["key_predio"], df_api_con_predio.get("colonia", "")
      )
  )
  dict_domicilio_p = dict(
      zip(
          df_api_con_predio["key_predio"],
          df_api_con_predio.get("domicilio", ""),
      )
  )
  dict_instalador_p = dict(
      zip(
          df_api_con_predio["key_predio"],
          df_api_con_predio.get("usuarioNombre", ""),
      )
  )
  dict_lectura_p = dict(
      zip(
          df_api_con_predio["key_predio"],
          df_api_con_predio.get("lecturaActual", 0),
      )
  )
  dict_f_reg_p = dict(
      zip(
          df_api_con_predio["key_predio"],
          df_api_con_predio.get("fechaRegistro", ""),
      )
  )
  dict_f_inst_p = dict(
      zip(
          df_api_con_predio["key_predio"],
          df_api_con_predio.get("fechaInstalacion", ""),
      )
  )
  dict_tipo_p = dict(
      zip(
          df_api_con_predio["key_predio"],
          df_api_con_predio.get("tipo_calculado", "MIAA"),
      )
  )

  df_conmedidor_pg["key_predio"] = (
      df_conmedidor_pg["Predio_Viv"].astype(str).str.strip()
      if "Predio_Viv" in df_conmedidor_pg.columns
      else ""
  )

  predios_usados_pg = set()
  (
      nuevas_series,
      nuevas_colonias,
      nuevos_domicilios,
      nuevos_instaladores,
      nuevos_tipos,
      nuevas_lecturas,
      nuevas_f_reg,
      nuevas_f_inst,
  ) = (
      [],
      [],
      [],
      [],
      [],
      [],
      [],
      [],
  )

  contador_predio = 0
  for _, r in df_conmedidor_pg.iterrows():
    kp = str(r.get("key_predio", "")).strip()
    match_encontrado = False

    if kp and kp.lower() not in invalidos and kp in dict_serie_p:
      val_s = dict_serie_p[kp]
      if pd.notna(val_s) and str(val_s).strip().lower() not in invalidos:
        predios_usados_pg.add(kp)
        match_encontrado = True
        contador_predio += 1

        nuevas_series.append(val_s)
        nuevas_colonias.append(dict_colonia_p.get(kp, r.get("_Colonia", "")))
        nuevos_domicilios.append(
            dict_domicilio_p.get(kp, r.get("_Domicilio", ""))
        )
        nuevos_instaladores.append(
            dict_instalador_p.get(kp, r.get("_Instalador", ""))
        )
        nuevos_tipos.append(dict_tipo_p.get(kp, r.get("_Tipo_instalador", "")))

        lec = dict_lectura_p.get(kp, 0)
        nuevas_lecturas.append(lec if not isinstance(lec, (list, dict)) else 0)

        nuevas_f_reg.append(dict_f_reg_p.get(kp, pd.NaT))
        nuevas_f_inst.append(dict_f_inst_p.get(kp, pd.NaT))

    if not match_encontrado:
      nuevas_series.append(r.get("_Serie", ""))
      nuevas_colonias.append(r.get("_Colonia", ""))
      nuevos_domicilios.append(r.get("_Domicilio", ""))
      nuevos_instaladores.append(r.get("_Instalador", ""))
      nuevos_tipos.append(r.get("_Tipo_instalador", "MIAA"))
      nuevas_lecturas.append(r.get("_Lectura_actual", 0))
      nuevas_f_reg.append(r.get("_Fecha_registro", pd.NaT))
      nuevas_f_inst.append(r.get("_Fecha_instalacion", pd.NaT))

  if registrar_auditoria:
    for _, api_row in df_api.iterrows():
      kp_val = str(api_row.get("key_predio", "")).strip()
      if (
          kp_val
          and kp_val not in predios_usados_pg
          and kp_val.lower() not in invalidos
      ):
        agregar_log(
            f"⚠️ [API NO MATCH] Registro API no encontrado en Postgres ->"
            f" Predio_Viv: '{kp_val}'"
        )

  df_conmedidor_pg["_Serie"] = nuevas_series
  df_conmedidor_pg["_Colonia"] = nuevas_colonias
  df_conmedidor_pg["_Domicilio"] = nuevos_domicilios
  df_conmedidor_pg["_Instalador"] = nuevos_instaladores
  df_conmedidor_pg["_Tipo_instalador"] = nuevos_tipos

  lecturas_limpias = []
  for v in nuevas_lecturas:
    try:
      if pd.isna(v) or str(v).strip().lower() in ["none", "nan", "", "nat"]:
        lecturas_limpias.append(0.0)
      else:
        lecturas_limpias.append(float(v))
    except (ValueError, TypeError):
      lecturas_limpias.append(0.0)

  df_conmedidor_pg["_Lectura_actual"] = lecturas_limpias

  def convertir_a_zona_mexico_segura(serie_entrada):
    s_dt = pd.to_datetime(serie_entrada, errors="coerce")
    resultados = []
    for val in s_dt:
      if pd.isna(val):
        resultados.append(pd.NaT)
      else:
        try:
          if val.tzinfo is not None:
            resultados.append(val.astimezone(ZONA_MEXICO))
          else:
            localizada = val.tz_localize(
                "UTC", nonexistent="shift_forward", ambiguous="NaT"
            )
            resultados.append(localizada.astimezone(ZONA_MEXICO))
        except Exception:
          resultados.append(pd.NaT)
    return pd.Series(resultados, index=df_conmedidor_pg.index)

  df_conmedidor_pg["_Fecha_registro"] = convertir_a_zona_mexico_segura(
      nuevas_f_reg
  )
  df_conmedidor_pg["_Fecha_instalacion"] = convertir_a_zona_mexico_segura(
      nuevas_f_inst
  )

  df_conmedidor_pg = df_conmedidor_pg.drop(
      columns=["key_predio"], errors="ignore"
  )
  return df_conmedidor_pg, contador_predio, 0


def ejecutar_sincronizacion_automatica(
    barra_progreso_placeholder=None, texto_estado_placeholder=None
):
  def actualizar_progreso(valor_pct, mensaje):
    agregar_log(mensaje)
    if barra_progreso_placeholder is not None:
      barra_progreso_placeholder.progress(
          valor_pct,
          text=f"Progreso de ejecución: {int(valor_pct * 100)}% - {mensaje}",
      )
    if texto_estado_placeholder is not None:
      texto_estado_placeholder.markdown(
          f"🔄 **{mensaje}** ({int(valor_pct * 100)}%)"
      )

  # Paso 1: Inicio (25%)
  actualizar_progreso(
      0.25, "[PASO 1/4] Iniciando sincronización y conectando a la API..."
  )
  df_filtrado = cargar_datos_api()

  if df_filtrado.empty:
    actualizar_progreso(
        1.0, "[ERROR] No se pudo obtener respuesta o datos válidos de la API."
    )
    return False

  actualizar_progreso(
      0.50,
      f"[PASO 2/4] API OK. Se descargaron {len(df_filtrado):,} registros."
      " Leyendo PostgreSQL...",
  )

  # Paso 3: Lectura PostgreSQL (75%)
  try:
    engine_pg = obtener_motor_postgres()
    df_conmedidor_pg = pd.read_sql(
        'SELECT * FROM "Usuarios"."usuarios_miaa_conmedidor"', con=engine_pg
    )
  except Exception as ex:
    actualizar_progreso(1.0, f"[ERROR PG] Falló la lectura de PostgreSQL: {ex}")
    return False

  if not df_conmedidor_pg.empty:
    total_registros = len(df_conmedidor_pg)
    actualizar_progreso(
        0.75,
        f"[PASO 3/4] Procesando cruce estricto para {total_registros:,}"
        " registros...",
    )

    df_actualizado, c_p, _ = procesar_cruce_datos(
        df_conmedidor_pg, df_filtrado, registrar_auditoria=True
    )

    actualizar_progreso(
        0.90, "[PASO 4/4] Guardando cambios actualizados en PostgreSQL..."
    )

    try:
      df_actualizado.to_sql(
          "usuarios_miaa_conmedidor",
          con=engine_pg,
          schema="Usuarios",
          if_exists="replace",
          index=False,
      )
      actualizar_progreso(
          1.0,
          f"🎉 [CICLO EXITOSO] Sincronización completada. {total_registros:,}"
          " registros actualizados.",
      )
      return True
    except Exception as ex:
      actualizar_progreso(
          1.0, f"[ERROR ESCRITURA PG] No se pudo guardar en SQL: {ex}"
      )
      return False
  else:
    actualizar_progreso(
        1.0, "[AVISO] La tabla en PostgreSQL está vacía actualmente."
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
        text(
            'SELECT COUNT(*) FROM "Usuarios"."usuarios_miaa_conmedidor" WHERE'
            ' "_Serie" IS NOT NULL AND TRIM(CAST("_Serie" AS TEXT)) != \'\' AND'
            " LOWER(TRIM(CAST(\"_Serie\" AS TEXT))) NOT IN ('none', 'nan',"
            " 'null')"
        )
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
  st.markdown("#### ⚙️ Configuración")

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
        f"▶️ Temporizador activado. Próxima ejecución sincronizada al reloj a"
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
    agregar_log("⏹️ Temporizador detenido manualmente por el usuario.")
    st.warning("Temporizador detenido.")
    st.rerun()

# ==========================================
# 8. INTERFAZ PRINCIPAL Y BARRAS DE PROGRESO (ESPERA Y EJECUCIÓN)
# ==========================================
st.markdown(
    """
    <div style="text-align: center; margin-top: -20px; margin-bottom: 10px;">
        <h2 style="color: #f8fafc; font-weight: 700;">MIAA - Sistema de Registros e Instalaciones</h2>
    </div>
    """,
    unsafe_allow_html=True,
)

# Indicadores de Cobertura
col_ind1, col_ind2, col_ind3 = st.columns(3)

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

# Contenedores para Estado y Barras (Espera y Ejecución)
st.markdown("#### 🔄 Estado y Progreso del Sistema")
estado_ejecucion_placeholder = st.empty()
barra_progreso_placeholder = st.empty()

# Lógica del Temporizador y Cuenta Regresiva (Segundero y su barra de progreso de espera)
if st.session_state.is_running and st.session_state.next_run_time:
  ahora = datetime.now(ZONA_MEXICO)
  if ahora >= st.session_state.next_run_time:
    ejecutar_sincronizacion_automatica(
        barra_progreso_placeholder, estado_ejecucion_placeholder
    )
    sig_tiempo, _ = calcular_siguiente_tiempo_reloj(
        st.session_state.intervalo_minutos_sel
    )
    st.session_state.next_run_time = sig_tiempo
    st.rerun()
  else:
    _, segundos_restantes = calcular_siguiente_tiempo_reloj(
        st.session_state.intervalo_minutos_sel
    )
    # Recalcular segundos exactos restantes hasta la hora objetivo
    segundos_totales_intervalo = (
        st.session_state.intervalo_minutos_sel * 60
    )
    segundos_restantes = max(
        0,
        int(
            (
                st.session_state.next_run_time
                - datetime.now(ZONA_MEXICO)
            ).total_seconds()
        ),
    )

    # Progreso inverso para la barra de espera (de 0.0 a 1.0 según transcurre el tiempo)
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
  barra_progreso_placeholder.progress(0, text="Listo para iniciar temporizador...")

st.markdown("<div style='margin-bottom: 10px;'></div>", unsafe_allow_html=True)

# Consola y Limpieza Masiva
col_consola, col_limpieza = st.columns([1, 1], gap="medium")

with col_consola:
  st.markdown("#### 🖥️ Consola de Registros del Sistema")
  logs_html = "<br>".join(st.session_state.logs)
  st.markdown(
      f'<div class="terminal-box">{logs_html}</div>', unsafe_allow_html=True
  )

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
                        <div class="metric-value" style="font-size: 15px; margin-top: 5px;">Optimizado (Progreso en Vivo)</div>
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
                        <div class="metric-value" style="font-size: 15px; margin-top: 5px;">Alta Velocidad</div>
                    </div>
                </div>
            """,
          unsafe_allow_html=True,
      )
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

  st.markdown(
      "<div style='margin-bottom: 10px;'></div>", unsafe_allow_html=True
  )

  st.subheader(
      "🌐 Tabla: Datos de la API de Instalación (Todos los registros)"
  )
  if not df_filtrado.empty:
    st.dataframe(df_filtrado, use_container_width=True, height=350)
  else:
    st.warning("No hay datos cargados desde la API.")
