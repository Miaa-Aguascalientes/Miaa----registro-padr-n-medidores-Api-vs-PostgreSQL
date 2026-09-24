# ==========================================
# 1. CONFIGURACIÓN DE PÁGINA Y ESTILOS
# ==========================================
from datetime import datetime, timedelta
import pandas as pd
import requests
from sqlalchemy import create_engine, text
import streamlit as st

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
# 2. GESTIÓN DE LOGS (CONSOLA)
# ==========================================
if "logs" not in st.session_state:
  st.session_state.logs = [
      f"[{datetime.now().strftime('%H:%M:%S')}] Sistema inicializado correctamente. Esperando ciclo de ejecución..."
  ]


def agregar_log(mensaje):
  timestamp = datetime.now().strftime("%H:%M:%S")
  st.session_state.logs.insert(0, f"[{timestamp}] {mensaje}")
  if len(st.session_state.logs) > 100:
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
            # 1. Renombrar explícitamente numeroCliente de la API a Cliente
            if "numeroCliente" in df.columns:
              df["Cliente"] = df["numeroCliente"]
            elif "numero_cliente" in df.columns:
              df["Cliente"] = df["numero_cliente"]
            elif "numCliente" in df.columns:
              df["Cliente"] = df["numCliente"]

            # 2. Remover fotos/imágenes
            cols_a_remover = [
                c
                for c in df.columns
                if any(
                    term in c.lower()
                    for term in ["foto", "imagen", "img", "fotografia"]
                )
            ]
            df = df.drop(columns=cols_a_remover, errors="ignore")

            # 3. Detectar columnas para construir Predio_Viv
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

            # 4. Eliminar campos solicitados (predio, unidad, uuid, numeroCliente y variantes)
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

            # 5. Reordenar columnas para poner 'Cliente' y 'Predio_Viv' al principio
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
# 4. FUNCIÓN DE CRUCE SECUENCIAL (DIRECTO)
# ==========================================
def procesar_cruce_datos(df_conmedidor_pg, df_filtrado):
  df_api_merge = df_filtrado.copy()

  if df_api_merge.empty or df_conmedidor_pg.empty:
    agregar_log(
        "⚠️ Advertencia: El DataFrame de la API o de PostgreSQL está vacío."
    )
    return df_conmedidor_pg

  # Preparar llaves de búsqueda limpias usando directamente Predio_Viv y Cliente
  df_api_merge["key_predio"] = (
      df_api_merge["Predio_Viv"].astype(str).str.strip()
      if "Predio_Viv" in df_api_merge.columns
      else ""
  )
  df_api_merge["key_cliente"] = (
      df_api_merge["Cliente"].astype(str).str.strip()
      if "Cliente" in df_api_merge.columns
      else ""
  )

  # Diccionarios de mapeo rápido basados en Predio_Viv y Cliente
  dict_api_serie_p = dict(
      zip(df_api_merge["key_predio"], df_api_merge.get("serie", ""))
  )
  dict_api_colonia_p = dict(
      zip(df_api_merge["key_predio"], df_api_merge.get("colonia", ""))
  )
  dict_api_domicilio_p = dict(
      zip(df_api_merge["key_predio"], df_api_merge.get("domicilio", ""))
  )
  dict_api_instalador_p = dict(
      zip(df_api_merge["key_predio"], df_api_merge.get("usuarioNombre", ""))
  )
  dict_api_lectura_p = dict(
      zip(df_api_merge["key_predio"], df_api_merge.get("lecturaActual", 0))
  )
  dict_api_f_reg_p = dict(
      zip(df_api_merge["key_predio"], df_api_merge.get("fechaRegistro", ""))
  )
  dict_api_f_inst_p = dict(
      zip(df_api_merge["key_predio"], df_api_merge.get("fechaInstalacion", ""))
  )

  dict_api_serie_c = dict(
      zip(df_api_merge["key_cliente"], df_api_merge.get("serie", ""))
  )
  dict_api_colonia_c = dict(
      zip(df_api_merge["key_cliente"], df_api_merge.get("colonia", ""))
  )
  dict_api_domicilio_c = dict(
      zip(df_api_merge["key_cliente"], df_api_merge.get("domicilio", ""))
  )
  dict_api_instalador_c = dict(
      zip(df_api_merge["key_cliente"], df_api_merge.get("usuarioNombre", ""))
  )
  dict_api_lectura_c = dict(
      zip(df_api_merge["key_cliente"], df_api_merge.get("lecturaActual", 0))
  )
  dict_api_f_reg_c = dict(
      zip(df_api_merge["key_cliente"], df_api_merge.get("fechaRegistro", ""))
  )
  dict_api_f_inst_c = dict(
      zip(df_api_merge["key_cliente"], df_api_merge.get("fechaInstalacion", ""))
  )


  def mapear_tipo_externo(val):
    if val in [True, 1, "1", "true", "True", "YES", "yes", "S", "s"]:
      return "Externo"
    elif val in [False, 0, "0", "false", "False", "NO", "no", "N", "n"]:
      return "MIAA"
    return "MIAA"


  if "usuarioExterno" in df_api_merge.columns:
    df_api_merge["tipo_calculado"] = df_api_merge["usuarioExterno"].apply(
        mapear_tipo_externo
    )
    dict_api_tipo_p = dict(
        zip(df_api_merge["key_predio"], df_api_merge["tipo_calculado"])
    )
    dict_api_tipo_c = dict(
        zip(df_api_merge["key_cliente"], df_api_merge["tipo_calculado"])
    )
  else:
    dict_api_tipo_p, dict_api_tipo_c = {}, {}

  # PostgreSQL usa directamente las columnas Predio_Viv y Cliente estandarizadas
  df_conmedidor_pg["key_predio"] = (
      df_conmedidor_pg["Predio_Viv"].astype(str).str.strip()
      if "Predio_Viv" in df_conmedidor_pg.columns
      else ""
  )
  df_conmedidor_pg["key_cliente"] = (
      df_conmedidor_pg["Cliente"].astype(str).str.strip()
      if "Cliente" in df_conmedidor_pg.columns
      else ""
  )

  contador_predio = 0
  contador_cliente = 0

  def aplicar_cruce_secuencial(row, dict_p, dict_c, default_val):
    nonlocal contador_predio, contador_cliente
    kp = row["key_predio"]
    kc = row["key_cliente"]

    # 1. Join principal por Predio_Viv contra Predio_Viv
    if kp and kp.lower() not in ["none", "nan", "", "nat", "0"]:
      if kp in dict_p:
        val = dict_p[kp]
        if pd.notna(val) and str(val).strip() not in ["", "None", "nan", "NaT"]:
          return val, "predio"

    # 2. Join secundario por Cliente contra Cliente
    if kc and kc.lower() not in ["none", "nan", "", "nat", "0"]:
      if kc in dict_c:
        val = dict_c[kc]
        if pd.notna(val) and str(val).strip() not in ["", "None", "nan", "NaT"]:
          return val, "cliente"

    return default_val, None

  nuevas_series, nuevas_colonias, nuevos_domicilios, nuevos_instaladores, nuevos_tipos, nuevas_lecturas, nuevas_f_reg, nuevas_f_inst = (
      [],
      [],
      [],
      [],
      [],
      [],
      [],
      [],
  )

  for _, r in df_conmedidor_pg.iterrows():
    # Serie
    val, match_tipo = aplicar_cruce_secuencial(
        r, dict_api_serie_p, dict_api_serie_c, r.get("_Serie", "")
    )
    nuevas_series.append(val)
    if match_tipo == "predio":
      contador_predio += 1
    elif match_tipo == "cliente":
      contador_cliente += 1

    # Colonia
    val, _ = aplicar_cruce_secuencial(
        r, dict_api_colonia_p, dict_api_colonia_c, r.get("_Colonia", "")
    )
    nuevas_colonias.append(val)

    # Domicilio
    val, _ = aplicar_cruce_secuencial(
        r, dict_api_domicilio_p, dict_api_domicilio_c, r.get("_Domicilio", "")
    )
    nuevos_domicilios.append(val)

    # Instalador
    val, _ = aplicar_cruce_secuencial(
        r, dict_api_instalador_p, dict_api_instalador_c, r.get("_Instalador", "")
    )
    nuevos_instaladores.append(val)

    # Tipo instalador
    val, _ = aplicar_cruce_secuencial(
        r,
        dict_api_tipo_p,
        dict_api_tipo_c,
        r.get("_Tipo_instalador", "MIAA"),
    )
    nuevos_tipos.append(val)

    # Lectura actual
    val, _ = aplicar_cruce_secuencial(
        r, dict_api_lectura_p, dict_api_lectura_c, r.get("_Lectura_actual", 0)
    )
    if isinstance(val, (list, dict)):
      val = 0
    nuevas_lecturas.append(val)

    # Fecha registro
    val, _ = aplicar_cruce_secuencial(
        r,
        dict_api_f_reg_p,
        dict_api_f_reg_c,
        r.get("_Fecha_registro", pd.NaT),
    )
    nuevas_f_reg.append(val)

    # Fecha instalacion
    val, _ = aplicar_cruce_secuencial(
        r,
        dict_api_f_inst_p,
        dict_api_f_inst_c,
        r.get("_Fecha_instalacion", pd.NaT),
    )
    nuevas_f_inst.append(val)

  df_conmedidor_pg["_Serie"] = nuevas_series
  df_conmedidor_pg["_Colonia"] = nuevas_colonias
  df_conmedidor_pg["_Domicilio"] = nuevos_domicilios
  df_conmedidor_pg["_Instalador"] = nuevos_instaladores
  df_conmedidor_pg["_Tipo_instalador"] = nuevos_tipos

  # Limpieza y conversión segura para Lectura actual
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
  df_conmedidor_pg["_Fecha_registro"] = pd.to_datetime(
      nuevas_f_reg, errors="coerce"
  )
  df_conmedidor_pg["_Fecha_instalacion"] = pd.to_datetime(
      nuevas_f_inst, errors="coerce"
  )

  agregar_log(
      f"📊 Cruce secuencial finalizado: {contador_predio:,} registros"
      f" actualizados por Predio_Viv y {contador_cliente:,} registros"
      " actualizados por Cliente."
  )

  df_conmedidor_pg = df_conmedidor_pg.drop(
      columns=["key_predio", "key_cliente"], errors="ignore"
  )
  return df_conmedidor_pg


def ejecutar_sincronizacion_automatica():
  status_container = st.status(
      "🔄 Iniciando sincronización...", expanded=True
  )
  progress_bar = status_container.progress(0)

  status_container.update(
      label="🌐 [1/4] Descargando registros de la API...", state="running"
  )
  progress_bar.progress(15)
  agregar_log(
      "🔄 [CICLO INICIADO] Conectando a la API de MIAA para descarga de"
      " instalaciones..."
  )

  df_filtrado = cargar_datos_api()

  if df_filtrado.empty:
    status_container.update(
        label="❌ Error al obtener datos de la API", state="error"
    )
    agregar_log(
        "❌ [ERROR API] No se pudo obtener respuesta o datos válidos de la API."
    )
    return False

  agregar_log(
      f"✅ [API OK] Se descargaron {len(df_filtrado):,} registros de la API"
      " correctamente."
  )

  status_container.update(
      label="📥 [2/4] Extrayendo registros de PostgreSQL...", state="running"
  )
  progress_bar.progress(40)
  agregar_log(
      "🔄 [PG CONEXIÓN] Extrayendo registros de PostgreSQL para realizar el"
      " cruce..."
  )

  try:
    engine_pg = obtener_motor_postgres()
    df_conmedidor_pg = pd.read_sql(
        'SELECT * FROM "Usuarios"."usuarios_miaa_conmedidor"', con=engine_pg
    )
  except Exception as ex:
    status_container.update(
        label="❌ Error al leer la base de datos", state="error"
    )
    agregar_log(f"❌ [ERROR PG] Falló la lectura de PostgreSQL: {ex}")
    return False

  if not df_conmedidor_pg.empty:
    total_registros = len(df_conmedidor_pg)

    status_container.update(
        label=(
            "⚙️ [3/4] Procesando cruce (Predio_Viv -> Cliente) para"
            f" {total_registros:,} registros..."
        ),
        state="running",
    )
    progress_bar.progress(70)
    agregar_log(
        f"⚙️ Procesando actualización masiva para {total_registros:,}"
        " registros locales..."
    )

    df_actualizado = procesar_cruce_datos(df_conmedidor_pg, df_filtrado)

    status_container.update(
        label="💾 [4/4] Guardando cambios en PostgreSQL...", state="running"
    )
    progress_bar.progress(90)
    agregar_log("💾 [PG ESCRITURA] Guardando cambios actualizados en la tabla...")

    try:
      df_actualizado.to_sql(
          "usuarios_miaa_conmedidor",
          con=engine_pg,
          schema="Usuarios",
          if_exists="replace",
          index=False,
      )
      progress_bar.progress(100)
      status_container.update(
          label=(
              "🎉 ¡Sincronización completada con éxito! Se actualizaron"
              f" {total_registros:,} registros."
          ),
          state="complete",
      )
      agregar_log(
          f"🎉 [CICLO EXITOSO] Se actualizaron {total_registros:,} registros en"
          " la base de datos."
      )
      return True
    except Exception as ex:
      status_container.update(
          label="❌ Error al guardar en la base de datos", state="error"
      )
      agregar_log(f"❌ [ERROR ESCRITURA PG] No se pudo guardar en SQL: {ex}")
      return False
  else:
    status_container.update(label="⚠️ La tabla en PG está vacía", state="error")
    agregar_log("⚠️ [AVISO] La tabla en PostgreSQL está vacía actualmente.")
    return False


# ==========================================
# 5. TEMPORIZADOR Y RELOJ
# ==========================================
def calcular_siguiente_tiempo_reloj(minutos_intervalo):
  ahora = datetime.now()
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
if not df_filtrado.empty and "serie" in df_filtrado.columns:
  total_serie_api = df_filtrado["serie"].dropna().astype(str).str.strip()
  total_serie_api = (
      total_serie_api[
          ~total_serie_api.str.lower().isin(["", "none", "nan", "null"])
      ]
      .count()
  )

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
# 7. BARRA LATERAL IZQUIERDA (SIDEBAR)
# ==========================================
with st.sidebar:
  st.markdown("### 🚰 Panel de Control MIAA")
  st.markdown("---")
  st.markdown("#### 📊 Indicadores de Cobertura")

  st.metric(
      label="Registros API con Serie",
      value=f"{total_serie_api:,}",
      help="Total de registros de la API que poseen una serie válida.",
  )

  st.metric(
      label="PostgreSQL (_Serie lleno)",
      value=f"{total_serie_pg_lleno:,}",
      help=(
          "Registros en la base de datos local que ya tienen el campo _Serie"
          " poblado."
      ),
  )

  if total_serie_api > 0:
    porcentaje_cobertura = min(
        100.0, (total_serie_pg_lleno / total_serie_api) * 100
    )
    st.markdown(f"**Sincronización:** {porcentaje_cobertura:.1f}%")
    st.progress(porcentaje_cobertura / 100.0)
  else:
    st.markdown("**Sincronización:** 0.0%")
    st.progress(0.0)

  st.markdown("---")
  st.markdown("💡 *Todos los registros de la API deben reflejarse en PG.*")

# ==========================================
# 8. INTERFAZ PRINCIPAL VISUAL
# ==========================================
st.markdown(
    "<h2>MIAA - Sistema de Registros e Instalaciones</h2>", unsafe_allow_html=True
)
st.markdown("---")

st.markdown("#### Configuración")

with st.container(border=True):
  c1, c2, c3, c4 = st.columns([2, 2, 1, 1])
  with c1:
    modo = st.selectbox(
        "Modo", ["Periódico"], label_visibility="collapsed"
    )
  with c2:
    opciones_intervalo = {
        "Cada 1 minuto": 1,
        "Cada 5 minutos": 5,
        "Cada 10 minutos": 10,
        "Cada 15 minutos": 15,
        "Cada 30 minutos": 30,
        "Cada hora": 60,
    }
    intervalo_sel = st.selectbox(
        "Intervalo", list(opciones_intervalo.keys()), label_visibility="collapsed"
    )
    minutos_seleccionados = opciones_intervalo[intervalo_sel]
  with c3:
    btn_iniciar = st.button("INICIAR", type="primary", use_container_width=True)
  with c4:
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

st.markdown("---")


@st.fragment(run_every=1)
def renderizar_progreso_y_consola():
  if st.session_state.is_running and st.session_state.next_run_time:
    ahora = datetime.now()
    if ahora >= st.session_state.next_run_time:
      ejecutar_sincronizacion_automatica()
      sig_tiempo, _ = calcular_siguiente_tiempo_reloj(
          st.session_state.intervalo_minutos_sel
      )
      st.session_state.next_run_time = sig_tiempo

  if st.session_state.is_running and st.session_state.next_run_time:
    ahora = datetime.now()
    restante = (st.session_state.next_run_time - ahora).total_seconds()
    restante = max(0, int(restante))

    min_sel = st.session_state.intervalo_minutos_sel
    total_intervalo_secs = min_sel * 60
    transcurrido = total_intervalo_secs - restante
    progreso = min(1.0, max(0.0, transcurrido / total_intervalo_secs))

    mins, secs = divmod(restante, 60)
    tiempo_formateado = f"{mins:02d}:{secs:02d}"

    st.markdown(
        f"<p style='font-size: 13px; color: #38bdf8; font-weight: bold;"
        f" margin-bottom: 4px;'>⏱️ Próxima actualización automática en:"
        f" {tiempo_formateado} (Alineado al reloj a las"
        f" {st.session_state.next_run_time.strftime('%H:%M:%S')})</p>",
        unsafe_allow_html=True,
    )
    st.progress(progreso)
  else:
    st.markdown(
        "<p style='font-size: 13px; color: #94a3b8; font-style: italic;"
        " margin-bottom: 4px;'>⏸️ Temporizador inactivo. Haz clic en INICIAR"
        " para activar el ciclo automático alineado al reloj.</p>",
        unsafe_allow_html=True,
    )
    st.progress(0.0)

  st.markdown("#### 🖥️ Consola de Registros del Sistema")
  logs_html = "<br>".join(st.session_state.logs)
  st.markdown(
      f'<div class="terminal-box">{logs_html}</div>', unsafe_allow_html=True
  )


renderizar_progreso_y_consola()

st.markdown("---")

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
                        <div class="metric-value" style="font-size: 15px; margin-top: 5px;">Optimizado (SQL Paginado)</div>
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

    st.markdown("<div style='margin-bottom: 15px;'></div>", unsafe_allow_html=True)

    with st.container(border=True):
      st.markdown(
          "#### 🧹 Limpieza Masiva de Campos (Sin eliminar registros)"
      )
      st.markdown(
          "Selecciona las columnas cuyos datos deseas **vaciar por completo"
          " en toda la tabla** a la vez. Las filas se mantendrán intactas."
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
                f"🧹 Limpieza masiva ejecutada. Campos vaciados en toda la"
                f" tabla: {campos_a_limpiar_masivo}"
            )
            st.success(
                "¡Los campos seleccionados han sido vaciados en todos los"
                " registros exitosamente!"
            )
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
            f" {pagina_actual} de {total_paginas} (Mostrando bloques de 50"
            " registros)</p>",
            unsafe_allow_html=True,
        )

      offset_val = (pagina_actual - 1) * filas_por_pagina
      df_pagina_pg = cargar_pagina_usuarios_db(
          limit=filas_por_pagina, offset=offset_val
      )

      if not df_pagina_pg.empty and not df_filtrado.empty:
        df_pagina_pg = procesar_cruce_datos(df_pagina_pg, df_filtrado)

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
    if not df_t2.empty and not df_filtrado.empty:
      df_t2 = procesar_cruce_datos(df_t2, df_filtrado)

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
