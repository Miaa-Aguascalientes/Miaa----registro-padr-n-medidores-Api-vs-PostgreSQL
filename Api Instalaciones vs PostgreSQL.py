from datetime import datetime, timedelta
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
            height: 200px;
            overflow-y: scroll;
            font-size: 13px;
            line-height: 1.4;
        }
    </style>
""",
    unsafe_allow_html=True,
)

# ==========================================
# 2. GESTIÓN DE LOGS (CONSOLA - HORA MÉXICO)
# ==========================================
ZONA_MEXICO = ZoneInfo("America/Mexico_City")

if "logs" not in st.session_state:
  hora_actual_mx = datetime.now(ZONA_MEXICO).strftime("%H:%M:%S")
  st.session_state.logs = [
      f"[{hora_actual_mx}] Sistema inicializado correctamente. Esperando ciclo de ejecución..."
  ]


def agregar_log(mensaje):
  timestamp = datetime.now(ZONA_MEXICO).strftime("%H:%M:%S")
  st.session_state.logs.insert(0, f"[{timestamp}] {mensaje}")
  if len(st.session_state.logs) > 100:
    st.session_state.logs.pop()


# ==========================================
# 3. CONEXIONES Y CONSULTAS OPTIMIZADAS (SQL)
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
  except Exception as e:
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

          return df
    return pd.DataFrame()
  except Exception as e:
    return pd.DataFrame()


# ==========================================
# 4. CRUCE Y ACTUALIZACIÓN ULTRA RÁPIDA (VÍA SQL NATIVO)
# ==========================================
def ejecutar_sincronizacion_automatica():
  agregar_log(
      "🔄 Iniciando ciclo: Conectando y autenticando con la API de MIAA..."
  )
  df_api = cargar_datos_api()

  if df_api.empty:
    agregar_log(
        "❌ Error: No se pudo conectar de manera correcta a la API o no devolvió"
        " datos."
    )
    return False

  agregar_log(
      f"✅ API consultada con éxito. Registros obtenidos: {len(df_api):,}. "
      "Actualizando base de datos mediante SQL optimizado..."
  )

  try:
    engine_pg = obtener_motor_postgres()

    # Preparamos el DataFrame de la API con los nombres normalizados para el SQL
    df_staging = pd.DataFrame()

    # Extraer columnas clave de la API de forma flexible
    col_predio = next(
        (
            c
            for c in ["Predio_Viv", "predioViv", "predio_viv", "predio"]
            if c in df_api.columns
        ),
        None,
    )
    col_cliente = next(
        (
            c
            for c in ["numeroCliente", "numero_cliente", "cliente", "Cliente"]
            if c in df_api.columns
        ),
        None,
    )
    col_serie = next(
        (c for c in ["serie", "Serie", "numeroSerie"] if c in df_api.columns),
        None,
    )
    col_colonia = next((c for c in ["colonia", "Colonia"] if c in df_api.columns), None)
    col_domicilio = next(
        (c for c in ["domicilio", "Domicilio", "direccion"] if c in df_api.columns),
        None,
    )
    col_instalador = next(
        (c for c in ["usuarioNombre", "instalador"] if c in df_api.columns), None
    )
    col_ext = next(
        (c for c in ["usuarioExterno"] if c in df_api.columns), None
    )
    col_lec = next(
        (c for c in ["lecturaActual", "lectura"] if c in df_api.columns), None
    )
    col_freg = next(
        (c for c in ["fechaRegistro"] if c in df_api.columns), None
    )
    col_finst = next(
        (c for c in ["fechaInstalacion"] if c in df_api.columns), None
    )

    df_staging["api_predio"] = (
        df_api[col_predio].astype(str).str.strip()
        if col_predio
        else ""
    )
    df_staging["api_cliente"] = (
        df_api[col_cliente].astype(str).str.strip()
        if col_cliente
        else ""
    )
    df_staging["api_serie"] = (
        df_api[col_serie].astype(str).str.strip() if col_serie else None
    )
    df_staging["api_colonia"] = (
        df_api[col_colonia].astype(str).str.strip() if col_colonia else None
    )
    df_staging["api_domicilio"] = (
        df_api[col_domicilio].astype(str).str.strip() if col_domicilio else None
    )
    df_staging["api_instalador"] = (
        df_api[col_instalador].astype(str).str.strip()
        if col_instalador
        else None
    )
    df_staging["api_lectura"] = (
        pd.to_numeric(df_api[col_lec], errors="coerce") if col_lec else None
    )
    df_staging["api_freg"] = (
        pd.to_datetime(df_api[col_freg], errors="coerce") if col_freg else None
    )
    df_staging["api_finst"] = (
        pd.to_datetime(df_api[col_finst], errors="coerce") if col_finst else None
    )

    if col_ext:

      def map_ext(val):
        if val in [True, 1, "1", "true", "True", "YES", "yes", "S", "s"]:
          return "Externo"
        return "MIAA"

      df_staging["api_tipo"] = df_api[col_ext].apply(map_ext)
    else:
      df_staging["api_tipo"] = "MIAA"

    with engine_pg.begin() as conn:
      # 1. Volcar datos limpios a una tabla temporal en PostgreSQL (Staging)
      df_staging.to_sql(
          "temp_api_staging",
          con=conn,
          if_exists="replace",
          index=False,
          method="multi",
          chunksize=5000,
      )

      # 2. Ejecutar actualización masiva ultrarrápida en SQL (Actualiza por Predio_Viv o por Cliente)
      # Nota: Solo actualiza si el campo destino está vacío o nulo, ahorrando procesamiento innecesario.
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

      result = conn.execute(query_update)
      agregar_log(
          f"✅ ¡Sincronización SQL completada con éxito! Registros"
          f" actualizados en la base de datos."
      )
    return True

  except Exception as ex:
    agregar_log(f"❌ Error durante la actualización SQL en PostgreSQL: {ex}")
    return False


# ==========================================
# 5. GESTIÓN DE ESTADO PARA EL TEMPORIZADOR
# ==========================================
if "is_running" not in st.session_state:
  st.session_state.is_running = False
if "next_run_time" not in st.session_state:
  st.session_state.next_run_time = None
if "total_seconds_interval" not in st.session_state:
  st.session_state.total_seconds_interval = 300

# ==========================================
# 6. CONFIGURACIÓN EN BARRA LATERAL (SIDEBAR)
# ==========================================
with st.sidebar:
  st.markdown("<h2>⚙️ Configuración</h2>", unsafe_allow_html=True)
  st.markdown("---")

  st.markdown("#### Ejecución Manual")
  if st.button("🚀 Ejecutar Ahora", type="primary", use_container_width=True):
    with st.spinner("Ejecutando proceso de sincronización rápida..."):
      exito = ejecutar_sincronizacion_automatica()
    if exito:
      st.success("¡Proceso ejecutado con éxito!")
    else:
      st.error("Hubo un error en el proceso. Revisa la consola.")
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
  total_segundos = opciones_intervalo[intervalo_sel]

  col_sb1, col_sb2 = st.columns(2)
  with col_sb1:
    btn_iniciar = st.button("INICIAR", type="primary", use_container_width=True)
  with col_sb2:
    btn_parar = st.button("PARAR", type="secondary", use_container_width=True)

  if btn_iniciar:
    st.session_state.is_running = True
    st.session_state.total_seconds_interval = total_segundos
    st.session_state.next_run_time = datetime.now(ZONA_MEXICO) + timedelta(
        seconds=total_segundos
    )
    agregar_log(
        f"Temporizador iniciado. Próxima ejecución en {intervalo_sel.lower()}."
    )
    st.success("¡Temporizador iniciado!")
    st.rerun()

  if btn_parar:
    st.session_state.is_running = False
    st.session_state.next_run_time = None
    agregar_log("Temporizador detenido manualmente por el usuario.")
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
# 8. FRAGMENTO AISLADO CON BARRA DE PROGRESO, CONTADOR Y CONSOLA
# ==========================================
@st.fragment(run_every=1)
def renderizar_progreso_y_consola():
  if st.session_state.is_running and st.session_state.next_run_time:
    ahora_mx = datetime.now(ZONA_MEXICO)
    if ahora_mx >= st.session_state.next_run_time:
      ejecutar_sincronizacion_automatica()
      st.session_state.next_run_time = datetime.now(ZONA_MEXICO) + timedelta(
          seconds=st.session_state.total_seconds_interval
      )

  if st.session_state.is_running and st.session_state.next_run_time:
    ahora_mx = datetime.now(ZONA_MEXICO)
    restante = (st.session_state.next_run_time - ahora_mx).total_seconds()
    restante = max(0, int(restante))

    total_intervalo = st.session_state.total_seconds_interval
    transcurrido = total_intervalo - restante
    progreso = min(1.0, max(0.0, transcurrido / total_intervalo))

    mins, secs = divmod(restante, 60)
    tiempo_formateado = f"{mins:02d}:{secs:02d}"

    st.markdown(
        f"<p style='font-size: 13px; color: #38bdf8; font-weight: bold;"
        f" margin-bottom: 4px;'>⏱️ Próxima actualización automática en:"
        f" {tiempo_formateado}</p>",
        unsafe_allow_html=True,
    )
    st.progress(progreso)
  else:
    st.markdown(
        "<p style='font-size: 13px; color: #94a3b8; font-style: italic;"
        " margin-bottom: 4px;'>⏸️ Temporizador inactivo. Haz clic en INICIAR"
        " en la barra lateral para activar el ciclo automático.</p>",
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

# ==========================================
# 9. OBTENCIÓN DE DATOS PARA INDICADORES
# ==========================================
total_registros_db = obtener_total_registros()
total_con_serie = obtener_total_con_serie()
df_filtrado = cargar_datos_api()
total_registros_api = len(df_filtrado) if not df_filtrado.empty else 0

# ==========================================
# 10. TARJETAS DE INDICADORES (A MERO ARRIBA)
# ==========================================
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

# ==========================================
# 11. ESTRUCTURA DE PESTAÑAS CON PAGINACIÓN SQL EFICIENTE
# ==========================================
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
    # ==========================================
    # LIMPIEZA MASIVA DE CAMPOS (SIN BORRAR FILAS)
    # ==========================================
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
                f"Limpieza masiva ejecutada. Campos vaciados en toda la tabla:"
                f" {campos_a_limpiar_masivo}"
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
