import streamlit as st
import sqlite3
import re
import pandas as pd
import urllib.parse
import base64
from datetime import datetime, date
from sqlalchemy import create_engine, text

# Conexión centralizada a Supabase
DATABASE_URL = "postgresql://postgres.hgukbkxetzxlxossfvif:Laboratorio135Lis@aws-1-us-west-2.pooler.supabase.com:5432/postgres?sslmode=require"
engine = create_engine(DATABASE_URL)

@st.dialog("🖨️ Preparando Impresión")

# ==========================================
# FUNCIONES MATEMÁTICAS / DE CÁLCULO GLOBAL
# ==========================================

def calcular_fge_ckd_epi(creatinina, edad, sexo):
    """
    Calcula el Filtrado Glomerular Estimado (FGe) usando la fórmula CKD-EPI (2021).
    Solo aplica para pacientes de 18 años o más.
    """
    try:
        edad_paciente = int(edad)
        if edad_paciente < 18:
            return "No aplica (<18 años)"

        cr = float(creatinina)
        sexo_limpio = str(sexo).strip().lower()
        
        # Parámetros CKD-EPI 2021
        if sexo_limpio in ['femenino', 'f', 'mujer']:
            kappa = 0.7
            alfa = -0.241
            multiplicador_sexo = 1.012
        else:  # Masculino / M
            kappa = 0.9
            alfa = -0.302
            multiplicador_sexo = 1.0
            
        termino_cr = min(cr / kappa, 1) ** alfa
        termino_cr_max = max(cr / kappa, 1) ** -1.200
        termino_edad = 0.9938 ** edad_paciente
        
        fge = 142 * termino_cr * termino_cr_max * termino_edad * multiplicador_sexo
        return str(round(fge, 1))
    except (ValueError, TypeError):
        return ""

def calcular_ldl_johns_hopkins(col_total, hdl_c, trigliceridos):
    """
    Calcula el LDL-C usando la matriz de Johns Hopkins de forma autónoma.
    Garantiza retornar (valor, factor) o (None, error)
    """
    try:
        ct = float(col_total)
        hdl = float(hdl_c)
        tg = float(trigliceridos)
        
        if ct <= 0 or hdl <= 0 or tg <= 0:
            return None, "Valores menores o iguales a cero"
            
        non_hdl = ct - hdl
        if non_hdl <= 0:
            return None, "No-HDL menor o igual a cero"
            
        # Restricción de rango clínico de Johns Hopkins
        if tg < 9 or tg > 400:
            return None, "Triglicéridos fuera del rango (9-400 mg/dL)"

        # 1. Rangos de Non-HDL (Columnas)
        # Columnas representan los límites superiores de Non-HDL: <100, 100-129, 130-159, 160-189, 190-218, >=219
        col_idx = 0
        if non_hdl < 100:
            col_idx = 0
        elif non_hdl <= 129:
            col_idx = 1
        elif non_hdl <= 159:
            col_idx = 2
        elif non_hdl <= 189:
            col_idx = 3
        elif non_hdl <= 218:
            col_idx = 4
        else:
            col_idx = 5

        # 2. Rangos de Triglicéridos (Filas)
        intervalos_tg = [
            (9, 49), (50, 56), (57, 63), (64, 70), (71, 77), (78, 84), (85, 91),
            (92, 98), (99, 105), (106, 112), (113, 120), (121, 128), (129, 137),
            (138, 147), (148, 158), (159, 170), (171, 184), (185, 201), (202, 222),
            (223, 252), (253, 298), (299, 400)
        ]
        
        # 3. Matriz de factores de Johns Hopkins (22 filas x 6 columnas principales)
        matriz_factores = [
            [3.3, 3.1, 3.1, 3.1, 3.1, 3.1], # TG 9-49
            [3.9, 3.7, 3.5, 3.5, 3.5, 3.5], # TG 50-56
            [4.2, 4.0, 3.9, 3.8, 3.8, 3.8], # TG 57-63
            [4.5, 4.3, 4.1, 4.0, 4.0, 4.0], # TG 64-70
            [4.8, 4.5, 4.4, 4.3, 4.2, 4.2], # TG 71-77
            [5.1, 4.8, 4.6, 4.5, 4.4, 4.4], # TG 78-84
            [5.3, 5.0, 4.8, 4.7, 4.6, 4.6], # TG 85-91
            [5.6, 5.3, 5.0, 4.9, 4.8, 4.8], # TG 92-98
            [5.8, 5.5, 5.2, 5.1, 5.0, 5.0], # TG 99-105
            [6.2, 5.7, 5.5, 5.3, 5.2, 5.2], # TG 106-112
            [6.4, 6.0, 5.7, 5.5, 5.4, 5.4], # TG 113-120
            [6.7, 6.2, 5.9, 5.8, 5.6, 5.6], # TG 121-128
            [7.0, 6.5, 6.2, 6.0, 5.8, 5.8], # TG 129-137
            [7.3, 6.8, 6.4, 6.2, 6.1, 6.1], # TG 138-147
            [7.7, 7.1, 6.8, 6.5, 6.4, 6.4], # TG 148-158
            [8.1, 7.5, 7.1, 6.9, 6.7, 6.7], # TG 159-170
            [8.6, 7.9, 7.5, 7.2, 7.0, 7.0], # TG 171-184
            [9.1, 8.4, 7.9, 7.6, 7.4, 7.4], # TG 185-201
            [9.7, 9.0, 8.5, 8.1, 7.9, 7.9], # TG 202-222
            [10.5, 9.6, 9.1, 8.7, 8.5, 8.5], # TG 223-252
            [11.7, 10.6, 9.9, 9.5, 9.2, 9.2], # TG 253-298
            [11.9, 11.9, 11.3, 10.8, 10.4, 10.4] # TG 299-400
        ]
        
        fila_idx = None
        for i, (min_tg, max_tg) in enumerate(intervalos_tg):
            if min_tg <= tg <= max_tg:
                fila_idx = i
                break
                
        if fila_idx is None:
            return None, "Triglicéridos fuera de los intervalos de la matriz"
            
        factor = matriz_factores[fila_idx][col_idx]
        ldl_c = non_hdl - (tg / factor)
        
        return round(ldl_c, 0), factor

    except Exception as e:
        return None, f"Error: {str(e)}"
        
def obtener_factor_johns_hopkins(trigliceridos, non_hdl):
               
        """
        Retorna el factor de conversión dinámico para el cálculo de LDL
        basado en la matriz oficial de la Universidad Johns Hopkins.
        """
        try:
            tg = float(trigliceridos)
            nhdl = float(non_hdl)
        except (ValueError, TypeError):
            # Si los datos no son numéricos, devolvemos un factor por defecto seguro
            return 5.0

        # 1. Definimos los rangos para Colesterol No-HDL (Filas de la matriz)
        if nhdl < 100:
            idx_nhdl = 0
        elif 100 <= nhdl < 130:
            idx_nhdl = 1
        elif 130 <= nhdl < 160:
            idx_nhdl = 2
        elif 160 <= nhdl < 190:
            idx_nhdl = 3
        else: # >= 190
            idx_nhdl = 4

        # 2. Definimos los rangos para Triglicéridos (Columnas de la matriz)
        if tg < 50:
            idx_tg = 0
        elif 50 <= tg < 100:
            idx_tg = 1
        elif 100 <= tg < 150:
            idx_tg = 2
        elif 150 <= tg < 200:
            idx_tg = 3
        elif 200 <= tg < 400:
            idx_tg = 4
        else: # >= 400
            idx_tg = 5

        # 3. Matriz de factores oficial de Johns Hopkins (Filas: Non-HDL | Columnas: TG)
        # [ TG <50 | 50-99 | 100-149 | 150-199 | 200-399 | >=400 ]
        matriz_factores = [
            [5.7, 4.9, 4.3, 3.9, 3.4, 3.1],  # Non-HDL < 100
            [6.4, 5.6, 4.9, 4.5, 3.9, 3.4],  # Non-HDL 100-129
            [7.2, 6.2, 5.4, 4.9, 4.3, 3.7],  # Non-HDL 130-159
            [8.1, 6.9, 6.0, 5.4, 4.7, 4.0],  # Non-HDL 160-189
            [9.5, 8.0, 6.9, 6.1, 5.2, 4.3]   # Non-HDL >= 190
        ]

        return matriz_factores[idx_nhdl][idx_tg]

def calcular_fge_ckd_epi(creatinina, edad, sexo):
    """
    Calcula el Filtrado Glomerular Estimado (FGe) usando la fórmula CKD-EPI (2021).
    Solo aplica para pacientes de 18 años o más.
    """
    try:
        # Validar edad mínima
        edad_paciente = int(edad)
        if edad_paciente < 18:
            return "No aplica (<18 años)"  # CKD-EPI no está validada para pediátricos

        cr = float(creatinina)
        sexo_limpio = str(sexo).strip().lower()
        
        # Definición de variables según Sexo (Fórmula CKD-EPI 2021 sin factor de raza)
        if sexo_limpio in ['femenino', 'f', 'mujer']:
            kappa = 0.7
            alfa = -0.241
            multiplicador_sexo = 1.012
        else:  # Masculino / Hombre
            kappa = 0.9
            alfa = -0.302
            multiplicador_sexo = 1.0
            
        # Cálculo de los términos de la fórmula
        termino_cr = min(cr / kappa, 1) ** alfa
        termino_cr_max = max(cr / kappa, 1) ** -1.200
        termino_edad = 0.9938 ** edad_paciente
        
        fge = 142 * termino_cr * termino_cr_max * termino_edad * multiplicador_sexo
        
        return round(fge, 1)  # Retorna el valor redondeado a un decimal (ej: 89.4)
    except (ValueError, TypeError):
        # Si la creatinina no es un número o falta la edad/sexo, devuelve vacío
        return ""       

def disparar_impresion():
    st.write("Se abrirá una pestaña limpia con el informe listo para imprimir o guardar en PDF.")
    
    # Este script mágico clona solo el informe, lo abre en una pestaña limpia y dispara la impresión original
    st.components.v1.html(r"""
        <script>
            setTimeout(function() {
                var contenidoInforme = window.parent.document.getElementById("print-area").innerHTML;
                var ventanaImpresion = window.open('', '_blank');
                ventanaImpresion.document.write('<html><head><title>Informe de Laboratorio</title>');
                ventanaImpresion.document.write('<style>body { font-family: Arial, sans-serif; background: white; color: black; padding: 20px; }</style>');
                ventanaImpresion.document.write('</head><body>');
                ventanaImpresion.document.write(contenidoInforme);
                ventanaImpresion.document.write('</body></html>');
                ventanaImpresion.document.write('<script>window.addEventListener("load", function() { window.print(); window.close(); });<\/script>');
                ventanaImpresion.document.close();
            }, 500);
        </script>
    """, height=0)
    
    if st.button("❌ Cerrar Ventana"):
        st.rerun()
        
        

    
        
# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(page_title="LIS - Laboratorio Fernández Farfán", page_icon="🔬", layout="wide")

# --- TRUCO ANTI-TRADUCTOR Y ESTILOS DE IMPRESIÓN ---
st.markdown("""
    <style>
        /* Bloqueo de traductor */
        html, body, div, span, p, td, th, input {
            translate: no !important;
        }
        
        /* Ocultar elementos de Streamlit en el papel */
        @media print {
            header, [data-testid="stSidebar"], .stButton, [data-testid="stDecoration"], footer {
                display: none !important;
            }
            .not-printable {
                display: none !important;
            }
            #print-area {
                border: none !important;
                padding: 0 !important;
                margin: 0 !important;
            }
            body {
                background-color: white !important;
                color: black !important;
            }
        }
    </style>
    <script>
        document.documentElement.setAttribute('lang', 'es');
        document.documentElement.classList.add('notranslate');
    </script>
""", unsafe_allow_html=True)
# --- CONTROL DE ACCESO (LOGIN) ---
if "autenticado" not in st.session_state:
    st.session_state.autenticado = False
    st.session_state.usuario = ""
    st.session_state.rol = ""

# Diccionario de usuarios (Cambiá las contraseñas acá según tu laboratorio)
USUARIOS = {
    "admin": {"clave": "admin135", "rol": "administrador"},
    "tecnico": {"clave": "tec456", "rol": "tecnico"}
}

def login_pantalla():
    st.sidebar.markdown("### 🔒 Control de Acceso")
    usuario_input = st.sidebar.text_input("Usuario:", key="input_user_login")
    clave_input = st.sidebar.text_input("Contraseña:", type="password", key="input_pass_login")
    
    if st.sidebar.button("Ingresar", key="btn_login_submit"):
        if usuario_input in USUARIOS and USUARIOS[usuario_input]["clave"] == clave_input:
            st.session_state.autenticado = True
            st.session_state.usuario = usuario_input
            st.session_state.rol = USUARIOS[usuario_input]["rol"]
            st.sidebar.success(f"Bienvenido/a {usuario_input}")
            st.rerun()
        else:
            st.sidebar.error("Usuario o contraseña incorrectos.")

def logout():
    st.session_state.autenticado = False
    st.session_state.usuario = ""
    st.session_state.rol = ""
    st.rerun()

# Si no está autenticado, frena la ejecución acá
if not st.session_state.autenticado:
    st.header("🔬 LIS - Laboratorio Fernández Farfán")
    st.info("Por favor, ingrese sus credenciales en la barra lateral para continuar.")
    login_pantalla()
    st.stop()

st.sidebar.write(f"👤 **Usuario:** {st.session_state.usuario} ({st.session_state.rol.upper()})")
if st.sidebar.button("Cerrar Sesión", key="btn_logout"):
    logout()

# --- CONEXIÓN Y CREACIÓN DE TABLAS ---
import os
import sqlite3

from supabase import create_client, Client

import psycopg2

def conectar_db():
    return psycopg2.connect(
        host="aws-1-us-west-2.pooler.supabase.com",
        port=5432,
        user="postgres.hgukbkxetzxlxossfvif", # <-- ¡Asegúrate de que tenga zxlx!
        password="Laboratorio135Lis",
        dbname="postgres",
        sslmode="require"
    )
def crear_tablas():
    conn = conectar_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS obras_sociales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE NOT NULL,
            valor_ub REAL NOT NULL
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS medicos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE NOT NULL,
            matricula TEXT DEFAULT ''
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS respuestas_predefinidas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            texto TEXT UNIQUE NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bioquimicos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE NOT NULL,
            matricula TEXT NOT NULL,
            cargo TEXT DEFAULT 'Dirección Técnico',
            firma_blob BLOB
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS configuracion_general (
            id INTEGER PRIMARY KEY,
            institucion_nombre TEXT DEFAULT 'Lab. Fernández - Farfán',
            institucion_subtitulo TEXT DEFAULT 'Laboratorio de Análisis Clínicos',
            direccion TEXT DEFAULT 'San Martín 441',
            telefono TEXT DEFAULT '3534772594',
            email TEXT DEFAULT 'lab.fernandezfarfan@gmail.com',
            localidad TEXT DEFAULT 'Villa María - Córdoba',
            whatsapp_leyenda TEXT DEFAULT 'Estimado/a paciente, le informamos desde el Laboratorio Fernández-Farfán que sus resultados ya se encuentran validados de forma correcta.',
            whatsapp_codigo_area TEXT DEFAULT '54',
            leyenda_colegio TEXT DEFAULT 'Laboratorio autorizado por el Colegio de Bioquímico de la Provincia de Córdoba según Resolución N° A 21594/2025',
            logo_blob BLOB
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS nomenclador (
            codigo TEXT PRIMARY KEY,
            nombre TEXT NOT NULL,
            unidades_bioquimicas REAL DEFAULT 0.0
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS determinaciones (
            codigo_item TEXT PRIMARY KEY,
            sub_item TEXT NOT NULL,
            text_unidad TEXT DEFAULT '',
            valores_referencia TEXT DEFAULT '',
            es_titulo TEXT DEFAULT 'No',
            ub_facturacion REAL DEFAULT 0.0
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS perfil_detalles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo_perfil TEXT,
            codigo_item TEXT,
            formula TEXT DEFAULT '',
            orden_visual INTEGER DEFAULT 0,
            metodo TEXT DEFAULT '',
            en_negrita TEXT DEFAULT 'No',
            FOREIGN KEY (codigo_perfil) REFERENCES nomenclador(codigo),
            FOREIGN KEY (codigo_item) REFERENCES determinaciones(codigo_item),
            UNIQUE(codigo_perfil, codigo_item)
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pacientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            dni TEXT UNIQUE NOT NULL,
            fecha_nacimiento TEXT DEFAULT '',
            edad INTEGER,
            sexo TEXT,
            telefono TEXT DEFAULT '',
            nro_afiliado TEXT DEFAULT ''
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ordenes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nro_protocolo INTEGER UNIQUE,
            paciente_id INTEGER,
            fecha TEXT,
            medico_id INTEGER,
            obra_social_id INTEGER,
            total_pesos REAL,
            estado TEXT DEFAULT 'Pendiente', 
            bioquimico_firma_id INTEGER,
            tipo_paciente TEXT DEFAULT 'Externo',
            nro_orden_internacion TEXT DEFAULT '',
            FOREIGN KEY (paciente_id) REFERENCES pacientes(id),
            FOREIGN KEY (obra_social_id) REFERENCES obras_sociales(id)
        )
    """)
    
    # 🔗 REFUERZO DE PARCHES: Forzamos la creación de columnas por si la BD vino muy vieja
    try:
        cursor.execute("ALTER TABLE ordenes ADD COLUMN total_pesos REAL DEFAULT 0.0")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE ordenes ADD COLUMN nro_protocolo INTEGER UNIQUE")
    except sqlite3.OperationalError:
        pass

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS resultados_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            orden_id INTEGER,
            codigo_perfil TEXT,
            codigo_item TEXT,
            sub_item TEXT,
            resultado TEXT DEFAULT '',
            unidad TEXT DEFAULT '',
            valores_referencia TEXT DEFAULT '',
            es_titulo TEXT DEFAULT 'No',
            formula TEXT DEFAULT '',
            orden_visual INTEGER DEFAULT 0,
            metodo TEXT DEFAULT '',
            en_negrita TEXT DEFAULT 'No',
            ub_facturacion REAL DEFAULT 0.0,
            FOREIGN KEY (orden_id) REFERENCES ordenes(id)
        )
    """)
    
    # Precargas controladas
    cursor.execute("SELECT COUNT(*) FROM obras_sociales")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO obras_sociales (nombre, valor_ub) VALUES ('PARTICULAR', 1260.0)")
        cursor.execute("INSERT INTO obras_sociales (nombre, valor_ub) VALUES ('UOM', 1104.0)")
        
    cursor.execute("SELECT COUNT(*) FROM medicos")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO medicos (nombre, matricula) VALUES ('SIN MEDICO ACUDIENTE', '0000')")
        
    cursor.execute("INSERT OR IGNORE INTO configuracion_general (id) VALUES (1)")
    
    cursor.execute("SELECT COUNT(*) FROM bioquimicos")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO bioquimicos (id, nombre, matricula, cargo) VALUES (1, 'Fernández María de los Ángeles', '3774', 'Dirección Técnica')")
        cursor.execute("INSERT INTO bioquimicos (id, nombre, matricula, cargo) VALUES (2, 'Farfán Luis A.', '5092', 'Dirección Técnica')")

    conn.commit()
    conn.close()

# --- AUXILIARES ---
def calcular_edad_por_texto(fecha_str):
    try:
        partes = fecha_str.split("/")
        dia, mes, ano = int(partes[0]), int(partes[1]), int(partes[2])
        hoy = date.today()
        return hoy.year - ano - ((hoy.month, hoy.day) < (mes, dia))
    except:
        return 0

def listar_obras_sociales():
    # 🛠️ MIGRACIÓN SEGURA con rollback para limpiar transacciones abortadas
    conn = conectar_db(); c = conn.cursor()
    try:
        c.execute("ALTER TABLE obras_sociales ADD COLUMN incluye_acto INTEGER DEFAULT 0;")
        c.execute("ALTER TABLE obras_sociales ADD COLUMN valor_acto REAL DEFAULT 0.0;")
        c.execute("ALTER TABLE obras_sociales ADD COLUMN incluye_gbi INTEGER DEFAULT 0;")
        c.execute("ALTER TABLE obras_sociales ADD COLUMN valor_gbi REAL DEFAULT 0.0;")
        conn.commit()
    except Exception:
        conn.rollback()  # 👈 ESTO ES LO QUE FALTABA: Limpia el estado de error de PostgreSQL
    
    # Ahora la consulta se ejecutará de forma totalmente limpia y segura
    c.execute("""
        SELECT id, nombre, valor_ub, incluye_acto, valor_acto, incluye_gbi, valor_gbi 
        FROM obras_sociales 
        ORDER BY nombre ASC
    """)
    res = c.fetchall(); conn.close(); return res

def listar_medicos():
    conn = conectar_db(); c = conn.cursor()
    c.execute("SELECT id, nombre, matricula FROM medicos ORDER BY nombre ASC")
    res = c.fetchall(); conn.close(); return res

def listar_respuestas():
    conn = conectar_db(); c = conn.cursor()
    c.execute("SELECT id, texto FROM respuestas_predefinidas ORDER BY texto ASC")
    res = c.fetchall(); conn.close(); return res

def listar_bioquimicos():
    conn = conectar_db(); c = conn.cursor()
    try:
        c.execute("ALTER TABLE bioquimicos ADD COLUMN IF NOT EXISTS cargo TEXT;")
        conn.commit()
    except Exception:
        conn.rollback()
        
    try:
        c.execute("SELECT id, nombre, matricula, cargo FROM bioquimicos ORDER BY id ASC")
        res = c.fetchall()
        conn.close()
        return res
    except Exception:
        conn.rollback()
        conn.close()
        return []

def obtener_firma_base64(bq_id):
    conn = conectar_db()
    c = conn.cursor()
    try:
        # Aseguramos que la columna exista por seguridad
        c.execute("ALTER TABLE bioquimicos ADD COLUMN IF NOT EXISTS firma_blob TEXT;")
        conn.commit()
        
        # ⚠️ CAMBIO CLAVE: Usar %s en lugar de ? para PostgreSQL
        c.execute("SELECT firma_blob FROM bioquimicos WHERE id = %s", (bq_id,))
        res = c.fetchone()
        conn.close()
        
        if res and res[0]:
            return res[0]
        return None
    except Exception:
        conn.rollback()
        conn.close()
        return None

def obtener_logo_base64():
    conn = conectar_db(); c = conn.cursor()
    c.execute("SELECT logo_blob FROM configuracion_general WHERE id = 1")
    res = c.fetchone()
    conn.close()
    if res and res[0]:
        return f"data:image/png;base64,{base64.b64encode(res[0]).decode('utf-8')}"
    return ""

def obtener_configuracion_general():
    conn = conectar_db()
    c = conn.cursor()
    try:
        c.execute("SELECT institucion_nombre, institucion_subtitulo, direccion, telefono, email, localidad, whatsapp_leyenda, whatsapp_codigo_area, leyenda_colegio FROM configuracion_general WHERE id = 1")
        res = c.fetchone()
        conn.close()
        
        # Si no hay configuración guardada, devolvemos valores por defecto vacíos
        if res is None:
            return ("", "", "", "", "", "", "", "", "")
            
        return res
    except Exception:
        conn.rollback()
        conn.close()
        return ("", "", "", "", "", "", "", "", "")

def listar_nomenclador():
    conn = conectar_db(); c = conn.cursor()
    c.execute("SELECT codigo, nombre, unidades_bioquimicas FROM nomenclador ORDER BY codigo ASC")
    res = c.fetchall(); conn.close(); return res

def listar_todas_determinaciones():
    conn = conectar_db(); c = conn.cursor()
    c.execute("SELECT codigo_item, sub_item, text_unidad, valores_referencia, es_titulo, ub_facturacion, formula_calculo FROM determinaciones ORDER BY codigo_item ASC")
    res = c.fetchall(); conn.close(); return res

def obtener_sub_items_de_practica(codigo_perfil):
    conn = conectar_db(); c = conn.cursor()
    c.execute("""
        SELECT pd.id, d.codigo_item, d.sub_item, d.text_unidad, d.valores_referencia, d.es_titulo, pd.formula, pd.orden_visual, pd.metodo, pd.en_negrita, d.ub_facturacion 
        FROM perfil_detalles pd JOIN determinaciones d ON pd.codigo_item = d.codigo_item
        WHERE pd.codigo_perfil = %s ORDER BY pd.orden_visual ASC, pd.id ASC
    """, (codigo_perfil,))
    res = c.fetchall(); conn.close(); return res

def buscar_pacientes_filtro(termino):
    conn = conectar_db()
    c = conn.cursor()
    try:
        # ⚠️ CAMBIO CLAVE: Usar %s en lugar de ? para PostgreSQL y asegurarnos de manejar transacciones
        query = """
            SELECT id, nombre, dni, fecha_nacimiento, edad, sexo, telefono, nro_afiliado 
            FROM pacientes 
            WHERE nombre LIKE %s OR dni LIKE %s 
            ORDER BY nombre ASC
        """
        c.execute(query, (f"%{termino}%", f"%{termino}%"))
        res = c.fetchall()
        conn.close()
        return res
    except Exception as e:
        conn.rollback()
        conn.close()
        print(f"Error al buscar pacientes: {e}")
        return []

def guardar_paciente(nombre, dni, f_nac, edad, sexo, telefono, nro_afiliado):
    conn = conectar_db(); c = conn.cursor()
    try:
        c.execute("INSERT INTO pacientes (nombre, dni, fecha_nacimiento, edad, sexo, telefono, nro_afiliado) VALUES (%s, %s, %s, %s, %s, %s, %s)", (nombre.upper(), dni, f_nac, edad, sexo, telefono, nro_afiliado))
        conn.commit(); exito = True
    except sqlite3.IntegrityError: exito = False
    conn.close(); return exito

def actualizar_orden_datos(orden_id, nro_proto, fecha, medico_id, os_id, b_id, tipo_p, nro_ord_int):
    """Actualiza los datos principales de la orden en la tabla ordenes."""
    conn = conectar_db(); c = conn.cursor()
    try:
        c.execute("""
            UPDATE ordenes 
            SET nro_protocolo = %s, fecha = %s, medico_id = %s, obra_social_id = %s, 
                bioquimico_firma_id = %s, tipo_paciente = %s, nro_orden_internacion = %s
            WHERE id = %s
        """, (nro_proto, fecha, medico_id, os_id, b_id, tipo_p, nro_ord_int, orden_id))
        conn.commit(); exito = True
    except sqlite3.IntegrityError:
        exito = False
    conn.close(); return exito

def eliminar_item_de_orden(orden_id, codigo_item):
    """Elimina una determinación específica de un protocolo."""
    conn = conectar_db(); c = conn.cursor()
    c.execute("DELETE FROM resultados_items WHERE orden_id = %s AND codigo_item = %s", (orden_id, codigo_item))
    conn.commit(); conn.close()

def agregar_perfil_a_orden_existente(orden_id, cod_p):
    """Agrega todas las determinaciones de un perfil a una orden ya creada sin duplicar."""
    conn = conectar_db(); c = conn.cursor()
    sub_items = obtener_sub_items_de_practica(cod_p)
    for _, c_item, s_nombre, s_uni, s_ref, s_tit, s_form, s_ord, s_met, s_neg, s_ub_fac in sub_items:
        c.execute("SELECT id FROM resultados_items WHERE orden_id = %s AND codigo_item = %s", (orden_id, c_item))
        if not c.fetchone():
            c.execute("""
                INSERT INTO resultados_items (orden_id, codigo_perfil, codigo_item, sub_item, resultado, unidad, valores_referencia, es_titulo, formula, orden_visual, metodo, en_negrita, ub_facturacion) 
                VALUES (%s, %s, %s, %s, '', %s, %s, %s, %s, %s, %s, %s, %s)
            """, (orden_id, cod_p, c_item, s_nombre, s_uni, s_ref, s_tit, s_form, s_ord, s_met, s_neg, s_ub_fac))
    conn.commit(); conn.close()

def actualizar_orden_datos(orden_id, nro_proto, fecha, medico_id, os_id, b_id, tipo_p, nro_ord_int):
    """Actualiza los datos principales de la orden en la tabla ordenes."""
    conn = conectar_db()
    c = conn.cursor()
    try:
        c.execute("""
            UPDATE ordenes 
            SET nro_protocolo = %s, fecha = %s, medico_id = %s, obra_social_id = %s, 
                bioquimico_firma_id = %s, tipo_paciente = %s, nro_orden_internacion = %s
            WHERE id = ?
        """, (nro_proto, fecha, medico_id, os_id, b_id, tipo_p, nro_ord_int, orden_id))
        conn.commit()
        exito = True
    except sqlite3.IntegrityError:
        exito = False
    conn.close()
    return exito

def eliminar_item_de_orden(orden_id, codigo_item):
    """Elimina una determinación específica de un protocolo."""
    conn = conectar_db()
    c = conn.cursor()
    c.execute("DELETE FROM resultados_items WHERE orden_id = %s AND codigo_item = %s", (orden_id, codigo_item))
    conn.commit()
    conn.close()

def eliminar_protocolo_completo(orden_id):
    """Borra de forma definitiva un protocolo y todos sus resultados asociados."""
    conn = conectar_db()
    c = conn.cursor()
    c.execute("DELETE FROM resultados_items WHERE orden_id = %s", (orden_id,))
    c.execute("DELETE FROM ordenes WHERE id = %s", (orden_id,))
    conn.commit()
    conn.close()

def agregar_perfil_a_orden_existente(orden_id, cod_p):
    """Agrega todas las determinaciones de un perfil a una orden ya creada sin duplicar."""
    conn = conectar_db()
    c = conn.cursor()
    sub_items = obtener_sub_items_de_practica(cod_p)
    for _, c_item, s_nombre, s_uni, s_ref, s_tit, s_form, s_ord, s_met, s_neg, s_ub_fac in sub_items:
        c.execute("SELECT id FROM resultados_items WHERE orden_id = %s AND codigo_item = %s", (orden_id, c_item))
        if not c.fetchone():
            c.execute("""
                INSERT INTO resultados_items (orden_id, codigo_perfil, codigo_item, sub_item, resultado, unidad, valores_referencia, es_titulo, formula, orden_visual, metodo, en_negrita, ub_facturacion) 
                VALUES (%s, %s, %s, %s, '', %s, %s, %s, %s, %s, %s, %s, %s)
            """, (orden_id, cod_p, c_item, s_nombre, s_uni, s_ref, s_tit, s_form, s_ord, s_met, s_neg, s_ub_fac))
    conn.commit()
    conn.close()

def registrar_orden(proto_manual, paciente_id, medico_id, os_id, b_id, tipo_p, nro_ord_int, lista_perfiles, fecha_manual=None):
    conn = conectar_db(); c = conn.cursor()
    
    # Si viene una fecha manual la usa, de lo contrario cae en la de hoy por defecto
    if fecha_manual:
        fecha_actual = fecha_manual
    else:
        fecha_actual = datetime.now().strftime("%d/%m/%Y")
        
    if proto_manual:
        nro_proto = proto_manual
    else:
        c.execute("SELECT MAX(nro_protocolo) FROM ordenes")
        max_proto = c.fetchone()[0]
        nro_proto = 1001 if not max_proto else max_proto + 1
        
    try:
        c.execute("""
            INSERT INTO ordenes (nro_protocolo, paciente_id, fecha, medico_id, obra_social_id, total_pesos, estado, bioquimico_firma_id, tipo_paciente, nro_orden_internacion) 
            VALUES (%s, %s, %s, %s, %s, 0.0, 'Pendiente', %s, %s, %s)
        """, (nro_proto, paciente_id, fecha_actual, medico_id, os_id, b_id, tipo_p, nro_ord_int))
        orden_id = c.lastrowid
    except sqlite3.IntegrityError:
        conn.close(); return None
        
    for cod_p in lista_perfiles:
        sub_items = obtener_sub_items_de_practica(cod_p)
        for _, c_item, s_nombre, s_uni, s_ref, s_tit, s_form, s_ord, s_met, s_neg, s_ub_fac in sub_items:
            # CORREGIDO: Dejamos el '?' para el resultado y pasamos el '' abajo en la tupla
            c.execute("""
                INSERT INTO resultados_items (orden_id, codigo_perfil, codigo_item, sub_item, resultado, unidad, valores_referencia, es_titulo, formula, orden_visual, metodo, en_negrita, ub_facturacion) 
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (orden_id, cod_p, c_item, s_nombre, '', s_uni, s_ref, s_tit, s_form, s_ord, s_met, s_neg, s_ub_fac))
            
    conn.commit(); conn.close(); return orden_id

def buscar_ordenes_todas():
    conn = conectar_db(); c = conn.cursor()
    c.execute("""
        SELECT o.id, o.fecha, p.nombre, p.dni, o.estado, o.total_pesos, p.sexo, m.nombre, os.nombre, p.telefono, o.nro_protocolo, b.nombre, b.matricula, p.nro_afiliado, o.tipo_paciente, o.nro_orden_internacion, os.valor_ub, p.fecha_nacimiento
        FROM ordenes o 
        JOIN pacientes p ON o.paciente_id = p.id 
        JOIN medicos m ON o.medico_id = m.id
        JOIN obras_sociales os ON o.obra_social_id = os.id 
        LEFT JOIN bioquimicos b ON o.bioquimico_firma_id = b.id
        ORDER BY o.id DESC
    """)
    res = c.fetchall(); conn.close(); return res
def obtener_historial_paciente_item(paciente_id, nombre_paciente, codigo_item, orden_id_actual, limite=10):
    """
    Recupera TODOS los antecedentes de análisis anteriores para este ítem y paciente.
    """
    if not codigo_item:
        return []

    conn = conectar_db()
    cur = conn.cursor()
    historial = []

    # Consulta que busca TODOS los resultados de órdenes anteriores a la actual
    query = """
        SELECT 
            o.fecha, 
            ri.resultado, 
            ri.unidad, 
            o.id AS nro_protocolo
        FROM resultados_items ri
        JOIN ordenes o ON ri.orden_id = o.id
        LEFT JOIN pacientes p ON o.paciente_id = p.id
        WHERE (o.paciente_id = ? OR (p.nombre IS NOT NULL AND LOWER(TRIM(p.nombre)) = LOWER(TRIM(?))))
          AND (TRIM(UPPER(ri.codigo_item)) = TRIM(UPPER(?)) OR TRIM(UPPER(ri.sub_item)) = TRIM(UPPER(?)))
          AND CAST(o.id AS INT) < CAST(? AS INT)
          AND ri.resultado IS NOT NULL 
          AND TRIM(CAST(ri.resultado AS TEXT)) != ''
        ORDER BY CAST(o.id AS INT) DESC
        LIMIT ?
    """

    try:
        cur.execute(query, (
            paciente_id, 
            str(nombre_paciente).strip(), 
            str(codigo_item).strip(), 
            str(codigo_item).strip(), 
            orden_id_actual, 
            limite
        ))
        historial = cur.fetchall()
    except Exception as e:
        print(f"Error al obtener historial: {e}")
        historial = []
    finally:
        conn.close()

    return historial
def obtener_items_para_cargar(orden_id):
    conn = conectar_db(); c = conn.cursor()
    # 🚀 Traemos la fórmula en tiempo real y agregamos 'es_particular'
    c.execute("""
        SELECT 
            ri.id, 
            ri.codigo_perfil, 
            ri.codigo_item, 
            ri.sub_item, 
            ri.unidad, 
            ri.valores_referencia, 
            ri.resultado, 
            ri.es_titulo, 
            COALESCE(d.formula_calculo, ri.formula) AS formula, -- 👈 Si no hay en d, usa ri
            ri.metodo, 
            ri.en_negrita, 
            ri.ub_facturacion, 
            ri.orden_visual,
            COALESCE(ri.es_particular, 0) AS es_particular -- 👈 Agregado clave (posición 13 / índice 13 o -1)
        FROM resultados_items ri
        LEFT JOIN determinaciones d ON ri.codigo_item = d.codigo_item
        WHERE ri.orden_id = %s 
        ORDER BY ri.codigo_perfil ASC, CAST(ri.orden_visual AS INTEGER) ASC, ri.id ASC
    """, (orden_id,))
    res = c.fetchall(); conn.close(); return res

# Comenta o borra esta línea donde inicia tu app:
# crear_tablas()

# --- MENÚ DEL SISTEMA (UNIFICADO) ---
# --- MENÚ DEL SISTEMA (UNIFICADO) ---
opciones_menu = [
    "📋 Recepción de Pacientes", 
    "👥 Gestión de Pacientes",  
    "🛒 Carga de Protocolos", 
    "✏️ Modificar Protocolos", 
    "🧪 Área Analítica (Carga)", 
    "🖨️ Validación e Informes",
    "📊 Estadísticas e Historial"
]

if st.session_state.rol == "administrador":
    opciones_menu.extend([
        "💵 Facturación Obras Sociales", 
        "💵 Facturación Particulares",  # 👈 NUEVA OPCIÓN AGREGADA AQUÍ
        "⚙️ Configuración de Análisis"
    ])

with st.sidebar:
    st.markdown("### 🖥️ Módulos del LIS")
    
    # Este es el ÚNICO selectbox que debe quedar en toda la barra lateral
    menu = st.selectbox("Seleccione un módulo:", opciones_menu)
    
    st.markdown("---")
    st.markdown("### 💾 Copia de Seguridad")
    
    # Obtenemos la ruta exacta a "laboratorio.db" usando la misma lógica
    base_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(base_dir, "laboratorio.db")
    
    if os.path.exists(db_path):
        with open(db_path, "rb") as f:
            bytes_db = f.read()
        
        from datetime import datetime
        fecha_backup = datetime.now().strftime("%Y-%m-%d_%H-%M")
        
        st.download_button(
            label="📥 Descargar Backup (.db)",
            data=bytes_db,
            file_name=f"backup_laboratorio_{fecha_backup}.db",
            mime="application/x-sqlite3",
            use_container_width=True,
            help="Haz clic para descargar una copia de seguridad local de la base de datos."
        )
        st.markdown("---")
        st.subheader("🔄 Restaurar Copia de Seguridad")
        st.write("Sube tu archivo de respaldo (`.db`) para reemplazar la base de datos actual.")
        
        # Componente para subir el archivo .db
        archivo_subido = st.file_uploader("Selecciona el archivo de backup (.db)", type=["db"], key="uploader_backup_db")
        
        if archivo_subido is not None:
            # Botón de confirmación para evitar reemplazos accidentales
            if st.button("⚠️ Confirmar y Restaurar Base de Datos", type="primary"):
                try:
                    # Usamos la misma variable 'db_path' que ya tienes definida en tu sistema
                    with open(db_path, "wb") as f:
                        f.write(archivo_subido.getbuffer())
                        
                    st.success("¡Base de datos restaurada con éxito! Recargando el sistema...")
                    import time
                    time.sleep(1.5)
                    st.rerun()
                except Exception as e:
                    st.error(f"Error al restaurar la base de datos: {e}")    
    else:
        st.warning("⚠️ No se encontró la base de datos activa.")

    st.markdown("---")
    if st.button("🚪 Cerrar Sesión", type="secondary", use_container_width=True):
        st.session_state.clear()
        st.rerun()

# [MÓDULOS 1 AL 5 QUEDAN CON SU LÓGICA ESTABLE Y COMPLETA]
if menu == "📋 Recepción de Pacientes":
    st.header("📋 Ficha de Admisión de Pacientes")
    with st.form("alta_p", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            # Ahora pedimos apellido y nombre por separado
            apellido_input = st.text_input("Apellido(s): (ej: FARFAN)")
            nombre_input = st.text_input("Nombre(s): (ej: MARIA VICTORIA)")
            
            # Los unificamos automáticamente en el formato estándar: "APELLIDO, NOMBRE"
            nom = ""
            if apellido_input and nombre_input:
                nom = f"{apellido_input.strip().upper()}, {nombre_input.strip().upper()}"
            elif apellido_input:
                nom = apellido_input.strip().upper()

            dni = st.text_input("Documento (DNI)")
            nro_afi = st.text_input("N° de Afiliado Cobertura")
        with col2:
            f_nac_manual = st.text_input("Fecha de Nacimiento (Formato: DD/MM/AAAA)", value="01/01/2000")
            box_edad = calcular_edad_por_texto(f_nac_manual)
            st.info(f"💡 Edad estimada según texto: **{box_edad} años**")
            sexo_visual = st.selectbox("Sexo", ["Masculino", "Femenino"])
            sexo_final = "M" if sexo_visual == "Masculino" else "F"
            tel = st.text_input("Teléfono Celular (ej: 3534772594)")
            
        if st.form_submit_button("Guardar Paciente"):
            if nom and dni:
                if guardar_paciente(nom, dni, f_nac_manual, box_edad, sexo_final, tel, nro_afi): 
                    st.success(f"¡Paciente '{nom}' guardado de forma exitosa!")
                else: 
                    st.error("Error: El DNI ya se encuentra registrado.")
            else:
                st.error("Por favor, complete Apellido, Nombre y DNI.")
                
elif menu == "👥 Gestión de Pacientes":
        st.header("👥 Gestión de Pacientes y Carga de Protocolos")
        st.markdown("Utilizá este módulo para dar de alta protocolos con autocompletado por DNI, corregir errores o eliminar fichas duplicadas.")

        # --- PESTAÑAS PRINCIPALES DEL MÓDULO ---
        tab_principal_carga, tab_principal_gestion = st.tabs(["🆕 Nueva Orden / Protocolo", "🗂️ Modificar / Eliminar Fichas"])

        # =================================================================
        # 👑 PESTAÑA A: NUEVA ORDEN / PROTOCOLO (CON AUTOCOMPLETADO POR DNI)
        # =================================================================
        with tab_principal_carga:
            st.subheader("Cargar Nueva Orden de Trabajo")
            
            dni_input = st.text_input("Ingrese DNI del Paciente:", key="dni_recepcion_nueva_orden").strip()
            
            paciente_existente = False
            nombre_def = ""
            apellido_def = ""
            fnac_def = "01/01/2000"
            sexo_def = "Masculino"
            id_paciente_bd = None
            actual_afi = ""
            actual_tel = ""
            
            if dni_input:
                conn = conectar_db(); cur = conn.cursor()
                cur.execute("SELECT * FROM pacientes WHERE dni = ?", (dni_input,))
                col_names = [description[0] for description in cur.description]
                paciente_data = cur.fetchone()
                conn.close()
                
                if paciente_data:
                    st.success("✨ Paciente encontrado en el sistema. Datos demográficos autocompletados.")
                    paciente_existente = True
                    datos_dict_c = dict(zip(col_names, paciente_data))
                    
                    id_paciente_bd = datos_dict_c.get('id')
                    p_nom_full = datos_dict_c.get('nombre', '')
                    
                    if "," in p_nom_full:
                        partes = p_nom_full.split(",", 1)
                        apellido_def = partes[0].strip()
                        nombre_def = partes[1].strip()
                    else:
                        apellido_def = p_nom_full.strip()
                        
                    fnac_def = datos_dict_c.get('f_nac', datos_dict_c.get('fecha_nacimiento', '01/01/2000'))
                    sexo_bd = datos_dict_c.get('sexo', 'M')
                    sexo_def = "Masculino" if sexo_bd == "M" else "Femenino"
                    actual_tel = datos_dict_c.get('telefono', datos_dict_c.get('tel', ''))
                    actual_afi = datos_dict_c.get('nro_afi', datos_dict_c.get('nro_afiliado', ''))
                else:
                    st.info("🆕 El DNI no está registrado. Ingrese los datos demográficos para dar de alta al paciente.")

            st.markdown("### 📋 Datos Demográficos")
            col1_c, col2_c = st.columns(2)
            with col1_c:
                edit_ape_c = st.text_input("Apellido(s):", value=apellido_def, disabled=paciente_existente, key="ape_c")
                edit_nom_c = st.text_input("Nombre(s):", value=nombre_def, disabled=paciente_existente, key="nom_c")
                edit_afi_c = st.text_input("N° de Afiliado Cobertura:", value=actual_afi, disabled=paciente_existente, key="afi_c")
            with col2_c:
                edit_f_nac_c = st.text_input("Fecha de Nacimiento (DD/MM/AAAA):", value=fnac_def, disabled=paciente_existente, key="fnac_c")
                edit_sexo_c = st.selectbox("Sexo:", ["Masculino", "Femenino"], index=0 if sexo_def == "Masculino" else 1, disabled=paciente_existente, key="sexo_c")
                edit_tel_c = st.text_input("Teléfono Celular:", value=actual_tel, disabled=paciente_existente, key="tel_c")

            st.markdown("### 📝 Datos del Protocolo")
            col3_c, col4_c, col5_c = st.columns(3)
            with col3_c:
                nro_protocolo = st.text_input("Número de Protocolo / Interno:", key="proto_c")
            with col4_c:
                conn = conectar_db(); cur = conn.cursor()
                try:
                    cur.execute("SELECT id, nombre FROM obras_sociales ORDER BY nombre")
                    lista_os = cur.fetchall()
                except Exception:
                    lista_os = []
                conn.close()
                dict_os = {os[0]: os[1] for os in lista_os} if lista_os else {}
                os_seleccionada = st.selectbox("Obra Social:", options=list(dict_os.keys()), format_func=lambda x: dict_os[x] if dict_os else "No hay OS", key="os_c")
            with col5_c:
                ambito_orden = st.selectbox("Ámbito de Atención:", options=["Externo", "Internado"], key="ambito_c")

            col6_c, col7_c = st.columns(2)
            with col6_c:
                fecha_orden = st.date_input("Fecha del Protocolo:", value=date.today(), key="fecha_o_c")
            with col7_c:
                medico_solicitante = st.text_input("Médico Solicitante:", key="medico_c")

            if st.button("💾 Guardar Protocolo y Registrar", use_container_width=True, key="btn_guardar_proto"):
                if not dni_input or not edit_ape_c or not edit_nom_c or not nro_protocolo:
                    st.error("⚠️ Falta completar campos obligatorios: DNI, Apellido, Nombre y Nro de Protocolo.")
                else:
                    try:
                        conn = conectar_db(); cur = conn.cursor()
                        
                        # 1. Si es paciente nuevo, se guarda primero
                        if not paciente_existente:
                            nombre_completo_c = f"{edit_ape_c.strip().upper()}, {edit_nom_c.strip().upper()}"
                            sexo_guardar = "M" if edit_sexo_c == "Masculino" else "F"
                            edad_calculada = calcular_edad_por_texto(edit_f_nac_c)
                            
                            # Mapeo dinámico según las columnas que maneje tu base de datos
                            cur.execute("PRAGMA table_info(pacientes)")
                            cols_pacientes = [c[1] for c in cur.fetchall()]
                            
                            campos_p = ['dni', 'nombre', 'sexo']
                            valores_p = [dni_input, nombre_completo_c, sexo_guardar]
                            
                            if 'f_nac' in cols_pacientes: campos_p.append('f_nac'); valores_p.append(edit_f_nac_c)
                            elif 'fecha_nacimiento' in cols_pacientes: campos_p.append('fecha_nacimiento'); valores_p.append(edit_f_nac_c)
                            if 'edad' in cols_pacientes: campos_p.append('edad'); valores_p.append(edad_calculada)
                            if 'telefono' in cols_pacientes: campos_p.append('telefono'); valores_p.append(edit_tel_c)
                            elif 'tel' in cols_pacientes: campos_p.append('tel'); valores_p.append(edit_tel_c)
                            if 'nro_afi' in cols_pacientes: campos_p.append('nro_afi'); valores_p.append(edit_afi_c)
                            elif 'nro_afiliado' in cols_pacientes: campos_p.append('nro_afiliado'); valores_p.append(edit_afi_c)
                            
                            query_p = f"INSERT INTO pacientes ({', '.join(campos_p)}) VALUES ({', '.join(['?']*len(valores_p))})"
                            cur.execute(query_p, tuple(valores_p))
                            id_paciente_bd = cur.lastrowid
                        
                        # 2. Guardar el protocolo en la tabla de órdenes
                        cur.execute("PRAGMA table_info(ordenes)")
                        cols_ordenes = [c[1] for c in cur.fetchall()]
                        
                        # Detectar nombres de columnas de filiación en la tabla ordenes
                        col_id_p_ord = 'paciente_id' if 'paciente_id' in cols_ordenes else ('id_paciente' if 'id_paciente' in cols_ordenes else 'dni')
                        col_os_ord = 'obra_social_id' if 'obra_social_id' in cols_ordenes else ('id_obra_social' if 'id_obra_social' in cols_ordenes else 'obra_social')
                        
                        campos_o = ['protocolo', col_id_p_ord, col_os_ord, 'fecha', 'ambito', 'medico', 'estado']
                        valores_o = [nro_protocolo, id_paciente_bd if 'dni' not in col_id_p_ord else dni_input, os_seleccionada, str(fecha_orden), ambito_orden.lower(), medico_solicitante.upper(), 'Abierta']
                        
                        query_o = f"INSERT INTO ordenes ({', '.join(campos_o)}) VALUES ({', '.join(['?']*len(valores_o))})"
                        cur.execute(query_o, tuple(valores_o))
                        
                        conn.commit()
                        conn.close()
                        st.success(f"🎉 ¡Protocolo N° {nro_protocolo} registrado con éxito para {edit_ape_c.upper()}, {edit_nom_c.upper()}!")
                        st.balloons()
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error al registrar la orden/paciente: {e}")

        # =================================================================
        # 🗂️ PESTAÑA B: MODIFICAR / ELIMINAR FICHAS (TU CÓDIGO ORIGINAL)
        # =================================================================
        with tab_principal_gestion:
            # 1. Buscador rápido
            busqueda = st.text_input("🔍 Buscar paciente por DNI o Apellido/Nombre:", "").strip().upper()
            
            conn = conectar_db()
            cur = conn.cursor()
            
            if busqueda:
                cur.execute("""
                    SELECT id, nombre, dni 
                    FROM pacientes 
                    WHERE dni LIKE ? OR nombre LIKE ?
                    LIMIT 10
                """, (f"%{busqueda}%", f"%{busqueda}%"))
            else:
                cur.execute("""
                    SELECT id, nombre, dni 
                    FROM pacientes 
                    ORDER BY id DESC 
                    LIMIT 10
                """)
                
            lista_pacientes = cur.fetchall()
            conn.close()
            
            if not lista_pacientes:
                st.info("No se encontraron pacientes registrados con ese criterio.")
            else:
                # 2. Selector del paciente a editar/eliminar
                opciones = {f"{p[1]} (DNI: {p[2]})": p for p in lista_pacientes}
                seleccion = st.selectbox("Seleccioná el paciente que deseás modificar o eliminar:", list(opciones.keys()))
                
                if seleccion:
                    p_id, p_nom, p_dni = opciones[seleccion]
                    
                    # Consultamos de forma segura el resto de los campos
                    conn = conectar_db(); cur = conn.cursor()
                    cur.execute("SELECT * FROM pacientes WHERE id = ?", (p_id,))
                    col_names = [description[0] for description in cur.description]
                    datos_completos = cur.fetchone()
                    conn.close()
                    
                    datos_dict = dict(zip(col_names, datos_completos))
                    
                    actual_f_nac = datos_dict.get('f_nac', datos_dict.get('fecha_nacimiento', '01/01/2000'))
                    actual_sexo = datos_dict.get('sexo', 'M')
                    actual_tel = datos_dict.get('telefono', datos_dict.get('tel', ''))
                    actual_afi = datos_dict.get('nro_afi', datos_dict.get('nro_afiliado', ''))
                    
                    # Separamos Apellido y Nombre
                    apellido_inicial = ""
                    nombre_inicial = ""
                    if "," in p_nom:
                        partes = p_nom.split(",", 1)
                        apellido_inicial = partes[0].strip()
                        nombre_inicial = partes[1].strip()
                    else:
                        apellido_inicial = p_nom.strip()

                    st.markdown("---")
                    
                    # Creamos dos pestañas internas: una para Modificar y otra para Eliminar de forma ordenada
                    tab_editar, tab_eliminar = st.tabs(["📝 Modificar Datos", "🚨 Eliminar Ficha"])
                    
                    # ----------------------------------------------------
                    # PESTAÑA DE EDICIÓN
                    # ----------------------------------------------------
                    with tab_editar:
                        with st.form("form_editar_paciente"):
                            col1, col2 = st.columns(2)
                            
                            with col1:
                                edit_ape_input = st.text_input("Apellido(s):", value=str(apellido_inicial))
                                edit_nom_input = st.text_input("Nombre(s):", value=str(nombre_inicial))
                                
                                edit_nom = ""
                                if edit_ape_input and edit_nom_input:
                                    edit_nom = f"{edit_ape_input.strip().upper()}, {edit_nom_input.strip().upper()}"
                                elif edit_ape_input:
                                    edit_nom = edit_ape_input.strip().upper()

                                edit_dni = st.text_input("Documento (DNI):", value=str(p_dni))
                                edit_afi = st.text_input("N° de Afiliado Cobertura:", value=str(actual_afi if actual_afi else ""))
                            
                            with col2:
                                edit_f_nac = st.text_input("Fecha de Nacimiento (Formato: DD/MM/AAAA):", value=str(actual_f_nac))
                                edit_edad = calcular_edad_por_texto(edit_f_nac)
                                st.info(f"💡 Edad estimada automáticamente: **{edit_edad} años**")
                                
                                sexo_index = 0 if actual_sexo == "M" else 1
                                edit_sexo_visual = st.selectbox("Sexo:", ["Masculino", "Femenino"], index=sexo_index)
                                edit_sexo = "M" if edit_sexo_visual == "Masculino" else "F"
                                
                                edit_tel = st.text_input("Teléfono Celular:", value=str(actual_tel if actual_tel else ""))
                            
                            if st.form_submit_button("💾 Guardar Cambios"):
                                if not edit_nom or not edit_dni:
                                    st.error("Error: El Apellido y el DNI son campos obligatorios.")
                                else:
                                    try:
                                        conn = conectar_db(); cur = conn.cursor()
                                        campos_update = []
                                        valores_update = []
                                        
                                        mapeo_columnas = {
                                            'nombre': edit_nom,
                                            'dni': edit_dni,
                                            'sexo': edit_sexo
                                        }
                                        
                                        if 'f_nac' in datos_dict: mapeo_columnas['f_nac'] = edit_f_nac
                                        elif 'fecha_nacimiento' in datos_dict: mapeo_columnas['fecha_nacimiento'] = edit_f_nac
                                            
                                        if 'edad' in datos_dict: mapeo_columnas['edad'] = edit_edad
                                        
                                        if 'telefono' in datos_dict: mapeo_columnas['telefono'] = edit_tel
                                        elif 'tel' in datos_dict: mapeo_columnas['tel'] = edit_tel
                                            
                                        if 'nro_afi' in datos_dict: mapeo_columnas['nro_afi'] = edit_afi
                                        elif 'nro_afiliado' in datos_dict: mapeo_columnas['nro_afiliado'] = edit_afi

                                        for col, val in mapeo_columnas.items():
                                            campos_update.append(f"{col} = ?")
                                            valores_update.append(val)
                                        
                                        valores_update.append(p_id)
                                        query_sql = f"UPDATE pacientes SET {', '.join(campos_update)} WHERE id = ?"
                                        
                                        cur.execute(query_sql, tuple(valores_update))
                                        conn.commit()
                                        conn.close()
                                        
                                        st.success(f"¡Paciente '{edit_nom}' actualizado con éxito!")
                                        st.rerun()
                                        
                                    except Exception as e:
                                        if "UNIQUE" in str(e) or "constraint" in str(e).lower():
                                            st.error(f"❌ Error: El DNI '{edit_dni}' ya pertenece a otro paciente en el sistema. No se pueden duplicar DNIs.")
                                        else:
                                            st.error(f"Ocurrió un error al intentar actualizar el paciente: {str(e)}")

                    # ----------------------------------------------------
                    # PESTAÑA DE ELIMINACIÓN SEGURA
                    # ----------------------------------------------------
                    with tab_eliminar:
                        st.warning(f"⚠️ **Atención:** Está a punto de eliminar permanentemente la ficha de **{p_nom}** (DNI: {p_dni}) del sistema.")
                        st.write("Para evitar pérdidas accidentales de datos, el sistema verificará primero si el paciente posee protocolos médicos cargados.")
                        
                        confirmar_borrado = st.checkbox("Confirmo que deseo borrar a este paciente y asumo la responsabilidad.", value=False, key=f"check_del_{p_id}")
                        
                        if st.button("🗑️ Eliminar Paciente del Sistema", type="primary", disabled=not confirmar_borrado, key=f"btn_del_{p_id}"):
                            try:
                                conn = conectar_db(); cur = conn.cursor()
                                
                                tablas_sistema = []
                                cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
                                tablas = [t[0] for t in cur.fetchall()]
                                
                                tiene_ordenes = False
                                for t in ['protocolos', 'ordenes', 'resultados_cabecera', 'turnos']:
                                    if t in tablas:
                                        cur.execute(f"PRAGMA table_info({t})")
                                        columnas = [c[1] for c in cur.fetchall()]
                                        col_id_pac = next((col for col in columnas if col in ['paciente_id', 'id_paciente', 'dni_paciente', 'dni']), None)
                                        
                                        if col_id_pac:
                                            if 'dni' in col_id_pac:
                                                cur.execute(f"SELECT COUNT(*) FROM {t} WHERE {col_id_pac} = ?", (p_dni,))
                                            else:
                                                cur.execute(f"SELECT COUNT(*) FROM {t} WHERE {col_id_pac} = ?", (p_id,))
                                            
                                            if cur.fetchone()[0] > 0:
                                                tiene_ordenes = True
                                                break
                                
                                if tiene_ordenes:
                                    st.error("❌ No es posible eliminar este paciente porque cuenta con órdenes médicas o resultados asociados en el sistema. Eliminarlo causaría inconsistencias graves.")
                                    conn.close()
                                else:
                                    cur.execute("DELETE FROM pacientes WHERE id = ?", (p_id,))
                                    conn.commit()
                                    conn.close()
                                    st.success(f"¡La ficha del paciente '{p_nom}' ha sido eliminada con éxito del sistema!")
                                    st.rerun()
                                    
                            except Exception as e:
                                st.error(f"Error al intentar eliminar el paciente: {str(e)}")             

elif menu == "🛒 Carga de Protocolos":
    st.header("🛒 Generación de Órdenes de Trabajo")
    buscar = st.text_input("Buscar Paciente por DNI o Nombre:")
    
    if buscar:
        lista_p = buscar_pacientes_filtro(buscar)
        if lista_p:
            dict_p = {p[0]: f"{p[1]} (DNI: {p[2]} - Nacimiento: {p[3]})" for p in lista_p}
            p_sel = st.selectbox("Confirmar Paciente:", options=dict_p.keys(), format_func=lambda x: dict_p[x])
            
            # Dividimos en 4 columnas equilibradas para agregar la fecha manual
            col_proto1, col_proto2, col_proto3, col_proto4 = st.columns([3, 3, 3, 3])
            with col_proto1: 
                tipo_ingreso_proto = st.radio("N° Protocolo:", ["Manual / Personalizado", "Automático del Sistema"])
            with col_proto2: 
                proto_man = st.number_input("Ingresar N° Protocolo Manual:", min_value=1, value=1) if tipo_ingreso_proto == "Manual / Personalizado" else None
            with col_proto3:
                tipo_p_sel = st.selectbox("Ámbito del Paciente:", ["Externo", "Internado"])
                nro_ord_int = st.text_input("N° Orden Internación (Si aplica):", value="")
            with col_proto4:
                fecha_manual = st.date_input("Fecha de Carga:", value=date.today())
                fecha_para_guardar = fecha_manual.strftime('%d/%m/%Y')

            medicos_db = listar_medicos(); dict_m = {m[0]: f"{m[1]} (MP: {m[2]})" for m in medicos_db}
            m_sel = st.selectbox("Médico Remitente:", options=dict_m.keys(), format_func=lambda x: dict_m[x])
            obras = listar_obras_sociales(); dict_o = {o[0]: f"{o[1]} (UB: ${o[2]})" for o in obras}
            o_sel = st.selectbox("Seguro / Cobertura:", options=dict_o.keys(), format_func=lambda x: dict_o[x])
            bq = listar_bioquimicos(); dict_bq = {b[0]: f"{b[1]} ({b[2]})" for b in bq}
            bq_sel = st.selectbox("Bioquímico que da el Ingreso:", options=dict_bq.keys(), format_func=lambda x: dict_bq[x])
            
            st.markdown("---")
            
            # ==========================================
            # DETECTAR O INICIALIZAR LA LISTA EN MEMORIA
            # ==========================================
            if "perfiles_seleccionados" not in st.session_state:
                st.session_state.perfiles_seleccionados = []  # Guardará diccionarios: {'perfil': p, 'es_particular': False}

            st.subheader("🔬 Selección de Prácticas y Perfiles")

            # Búsqueda interactiva de perfiles
            perf_lista = listar_nomenclador()
            
            perfil_buscado = st.selectbox(
                "Buscar y Agregar los Perfiles de Análisis en la Orden:", 
                options=perf_lista, 
                format_func=lambda x: f"({x[0]}) — {x[1]}",
                key="buscador_perfiles_input"
            )

            # Botón para añadir el perfil elegido a la lista
            if st.button("➕ Añadir Perfil al Protocolo", use_container_width=True):
                # Validamos que no se duplique buscando por el código (perfil_buscado[0])
                codigos_actuales = [p['perfil'][0] for p in st.session_state.perfiles_seleccionados]
                if perfil_buscado[0] not in codigos_actuales:
                    # Guardamos la práctica en formato Diccionario junto con la bandera 'es_particular'
                    st.session_state.perfiles_seleccionados.append({
                        'perfil': perfil_buscado,
                        'es_particular': False  # Por defecto no es particular (lo cubre OS)
                    })
                    st.rerun()

            st.markdown("---")

            # ===================================================
            # INTERFAZ CON REORDENAMIENTO Y TILDE PARTICULAR
            # ===================================================
            if st.session_state.perfiles_seleccionados:
                col_lista, col_botones = st.columns([0.75, 0.25])
                
                with col_lista:
                    st.write("📋 **Perfiles incluidos en la orden actual:**")
                    
                    # Recorremos los perfiles agregados para dibujarlos con su checkbox individual
                    for idx, item in enumerate(st.session_state.perfiles_seleccionados):
                        c_codigo = item['perfil'][0]
                        c_nombre = item['perfil'][1]
                        
                        col_txt, col_chk = st.columns([0.65, 0.35])
                        with col_txt:
                            st.markdown(f"**{idx + 1}. ({c_codigo}) — {c_nombre}**")
                        with col_chk:
                            # 🟡 CHECKBOX CLAVE: Tilde para marcar como Particular / Cobro Paciente
                            item['es_particular'] = st.checkbox(
                                "💵 Paga Paciente (Particular)", 
                                value=item['es_particular'], 
                                key=f"particular_chk_{c_codigo}_{idx}"
                            )
                        st.markdown("<hr style='margin: 3px 0;'>", unsafe_allow_html=True)

                    opciones_radio = range(len(st.session_state.perfiles_seleccionados))
                    perfil_index_sel = st.radio(
                        "Seleccione un perfil si desea moverlo de lugar o quitarlo:", 
                        options=opciones_radio,
                        format_func=lambda i: f"({st.session_state.perfiles_seleccionados[i]['perfil'][0]}) — {st.session_state.perfiles_seleccionados[i]['perfil'][1]}"
                    )

                with col_botones:
                    st.write("### Ordenar")
                    
                    # ⬆️ BOTÓN SUBIR PERFIL
                    if st.button("🔼 Subir", use_container_width=True, key="btn_subir_perfil"):
                        if perfil_index_sel > 0:
                            idx = perfil_index_sel
                            st.session_state.perfiles_seleccionados[idx], st.session_state.perfiles_seleccionados[idx-1] = \
                                st.session_state.perfiles_seleccionados[idx-1], st.session_state.perfiles_seleccionados[idx]
                            st.rerun()
                            
                    # ⬇️ BOTÓN BAJAR PERFIL
                    if st.button("🔽 Bajar", use_container_width=True, key="btn_bajar_perfil"):
                        if perfil_index_sel < len(st.session_state.perfiles_seleccionados) - 1:
                            idx = perfil_index_sel
                            st.session_state.perfiles_seleccionados[idx], st.session_state.perfiles_seleccionados[idx+1] = \
                                st.session_state.perfiles_seleccionados[idx+1], st.session_state.perfiles_seleccionados[idx]
                            st.rerun()
                            
                    st.write("---")
                    # ❌ BOTÓN QUITAR PERFIL
                    if st.button("🗑️ Quitar Práctica", use_container_width=True, key="btn_quitar_perfil", type="secondary"):
                        st.session_state.perfiles_seleccionados.pop(perfil_index_sel)
                        st.rerun()

            st.markdown("---")

                        # ===================================================
            # BOTÓN DE GUARDADO CORREGIDO
            # ===================================================
            if st.button("🚀 Crear Protocolo Médico", type="primary", use_container_width=True):
                if not st.session_state.perfiles_seleccionados:
                    st.error("❌ Error: Debe agregar al menos un perfil de análisis a la lista interactiva antes de guardar.")
                else:
                    lista_ids_ordenados = [item['perfil'][0] for item in st.session_state.perfiles_seleccionados]
                    
                    # 1. Registramos la orden base
                    orden_id = registrar_orden(proto_man, p_sel, m_sel, o_sel, bq_sel, tipo_p_sel, nro_ord_int, lista_ids_ordenados, fecha_para_guardar)
                    
                    if orden_id:
                        # 1. Obtenemos primero los datos de los perfiles antes de tocar la BD
                        datos_perfiles = []
                        for item in st.session_state.perfiles_seleccionados:
                            cod_p = item['perfil'][0]
                            p_particular = 1 if item['es_particular'] else 0
                            sub_items = obtener_sub_items_de_practica(cod_p) # Esta función suele cerrar conn
                            datos_perfiles.append((cod_p, p_particular, sub_items))

                        # 2. Abrimos UNA SOLA CONEXIÓN LIMPIA para todas las actualizaciones y lecturas
                        conn = conectar_db()
                        c = conn.cursor()
                        
                        try:
                            c.execute("ALTER TABLE resultados_items ADD COLUMN es_particular INTEGER DEFAULT 0")
                        except Exception:
                            pass 
                        
                        orden_del_perfil = 1
                        
                        # 3. Actualizamos orden_visual y es_particular
                        for cod_p, p_particular, sub_items in datos_perfiles:
                            for sub in sub_items:
                                c_item = sub[1]
                                s_ord = sub[8] if len(sub) > 8 else 0
                                
                                try:
                                    num_orden_interno = int(s_ord) if s_ord is not None and str(s_ord).strip() != "" else 0
                                except Exception:
                                    num_orden_interno = 0
                                
                                orden_visual_calculado = (orden_del_perfil * 100) + num_orden_interno
                                
                                c.execute("""
                                    UPDATE resultados_items 
                                    SET orden_visual = ?, es_particular = ? 
                                    WHERE orden_id = ? AND codigo_perfil = ? AND codigo_item = ?
                                """, (orden_visual_calculado, p_particular, orden_id, cod_p, c_item))
                                
                            orden_del_perfil += 1
                        
                        # 4. Guardamos los cambios
                        conn.commit()

                        # 5. Consultamos el número real de protocolo antes de cerrar la BD
                        num_protocolo_real = orden_id
                        try:
                            c.execute("SELECT nro_protocolo FROM ordenes WHERE id = ?", (orden_id,))
                            fila_proto = c.fetchone()
                            if fila_proto and fila_proto[0]:
                                num_protocolo_real = fila_proto[0]
                        except Exception as e:
                            print(f"Nota consulta protocolo: {e}")
                            num_protocolo_real = orden_id

                        # 1. Abrimos conexión y cursor de forma segura para obtener el ID real
                        conn_temp = conectar_db()
                        cur_temp = conn_temp.cursor()
                        
                        # 2. Obtenemos el ID máximo (la última orden recién creada)
                        cur_temp.execute("SELECT MAX(id) FROM ordenes")
                        fila_proto = cur_temp.fetchone()
                        num_protocolo_real = fila_proto[0] if fila_proto and fila_proto[0] is not None else orden_id

                        # 3. Cerramos la conexión temporal correctamente
                        conn_temp.close()
                        
                        # 4. Limpiamos estados y mostramos el mensaje de éxito con el número exacto
                        st.session_state.perfiles_seleccionados = []
                        st.toast("🎉 ¡Protocolo creado con éxito!", icon="✅")
                        st.success(f"💾 ¡El Protocolo N° **{num_protocolo_real}** se ha guardado correctamente!")
                        
                        import time
                        time.sleep(1.5)
                        st.rerun()
                    else:
                        st.error("⚠️ Error crítico: El número de protocolo ingresado ya existe en el sistema. Verifique e intente con otro.")

                        
elif menu == "✏️ Modificar Protocolos":
    st.header("✏️ Edición y Modificación de Protocolos Existentes")
    
    # 1. TRAEMOS TODAS LAS ÓRDENES PARA EL SELECTOR MAESTRO
    ordenes_todas = buscar_ordenes_todas()
    if not ordenes_todas:
        st.warning("No hay protocolos registrados en el sistema.")
    else:
        # Creamos el diccionario para el selectbox usando el ID real como clave
        dict_ord_mod = {o[0]: f"Protocolo Nº {o[10]} — Paciente: {o[2]} ({o[1]})" for o in ordenes_todas}
        
        # 🌟 AQUÍ SE DEFINE 'orden_id_mod' (La variable que nos faltaba)
        orden_id_mod = st.selectbox("Seleccione el Protocolo a Modificar:", options=dict_ord_mod.keys(), format_func=lambda x: dict_ord_mod[x])
        
        # Extraemos los datos actuales de la orden seleccionada
        ord_sel = [o for o in ordenes_todas if o[0] == orden_id_mod][0]
        
        # Desempaquetamos los datos de la orden (Asegurándonos de capturar el estado, ej: o[4])
        _, o_fecha, o_paciente, _, o_estado, _, _, o_medico, o_obra, _, o_proto, _, _, _, t_pac, n_ord_i, b_firma_id, _ = ord_sel
        
        st.markdown(f"### Modificando Datos de: **{o_paciente}**")
        
        # 🔐 CONTROL DE SEGURIDAD: BOTÓN PARA DESVALIDAR SI ESTÁ VALIDADO
        estado_actual = str(o_estado).strip().lower()
        es_validado = "validad" in estado_actual or "firmad" in estado_actual
        
        # 1. Obtenemos el último ID de orden creado de forma segura si no está definido
        if 'orden_id' not in locals() and 'orden_id' not in globals():
            conn_id = conectar_db()
            c_id = conn_id.cursor()
            c_id.execute("SELECT MAX(id) FROM ordenes")
            res_id = c_id.fetchone()
            conn_id.close()
            orden_id = res_id[0] if res_id and res_id[0] is not None else 1

        # 2. Consultamos el estado real del protocolo usando ese ID
        conn_est = conectar_db()
        c_est = conn_est.cursor()
        c_est.execute("SELECT estado FROM ordenes WHERE id = ?", (orden_id,))
        res_estado = c_est.fetchone()
        conn_est.close()
        
        # 3. Determinamos si está validado
        estado_actual = res_estado[0] if res_estado and res_estado[0] else "Pendiente"
        es_validado_aa = estado_actual.strip().lower() in ["validado", "cerrado", "firmado"]

        # 4. Evaluamos la validación correctamente
        if es_validado_aa:
            st.error("🛑 **Resultados Bloqueados:** Este protocolo ya se encuentra **VALIDADO**.")
            if st.button("🔓 Desvalidar Protocolo para Modificar", type="secondary", use_container_width=True, key=f"btn_desvalidar_{orden_id}"):
                conn = conectar_db(); c = conn.cursor()
                c.execute("UPDATE ordenes SET estado = 'Pendiente' WHERE id = ?", (orden_id,))
                conn.commit(); conn.close()
                st.toast("🔓 Protocolo liberado. Ya puede modificarlo.", icon="🔓")
                st.rerun()
        else:
            st.success("🟢 **Protocolo Abierto:** Este protocolo está en proceso de carga. Las modificaciones están permitidas.")
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        # 1. Obtenemos los ítems o determinaciones asociados a este protocolo de forma segura
        try:
            items = obtener_sub_items_de_practica(orden_id) # O la función que utilices para listar los ítems del protocolo
        except:
            items = []

        # 2. Validamos correctamente si la lista está vacía
        if not items:
            st.info("Este protocolo se creó vacío.")
        else:
            # 🚨 BLOQUE TEMPORAL DE DEPURACIÓN EN PANTALLA
            st.write(f"🔍 **Debug Paciente ID:** `{pac_id_sel}` | **Orden Actual ID:** `{orden_id}`")

            try:
                conn_debug = conectar_db()
                cur_debug = conn_debug.cursor()
                cur_debug.execute("SELECT id, fecha, paciente_id FROM ordenes WHERE paciente_id = ?", (pac_id_sel,))
                ordenes_paciente = cur_debug.fetchall()
                conn_debug.close()
                st.write(f"📋 **Órdenes encontradas para este paciente:** {ordenes_paciente}")
            except Exception as e_dbg:
                st.write(f"⚠️ Error al depurar: {e_dbg}")

            st.markdown("---")

        # --- SECCIÓN 1: DATOS MAESTROS DEL PROTOCOLO ---
        st.subheader("1. Datos Generales del Protocolo")
        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        
        # Si está validado, desactivamos todos los inputs usando disabled=es_validado
        with col_m1:
            proto_editado = st.number_input("N° Protocolo:", min_value=1, value=int(o_proto), disabled=es_validado)
        
        with col_m2:
            try:
                fecha_defecto = datetime.strptime(str(o_fecha).strip(), '%d/%m/%Y').date()
            except:
                fecha_defecto = date.today()
            fecha_editada = st.date_input("Fecha del Protocolo:", value=fecha_defecto, disabled=es_validado)
            fecha_guardar_editada = fecha_editada.strftime('%d/%m/%Y')
            
        with col_m3:
            tipo_p_editado = st.selectbox("Ámbito:", ["Externo", "Internado"], index=0 if t_pac == "Externo" else 1, disabled=es_validado)
            
        with col_m4:
            nro_ord_int_editado = st.text_input("N° Orden Internación:", value=str(n_ord_i) if n_ord_i else "", disabled=es_validado)
            
        # Selectores maestros de la orden
        medicos_db = listar_medicos(); dict_m = {m[0]: f"{m[1]} (MP: {m[2]})" for m in medicos_db}
        id_medico_defecto = list(dict_m.keys())[0] if dict_m else None
        for k, v in dict_m.items():
            if str(o_medico).strip().lower() in v.lower(): id_medico_defecto = k; break
        m_sel_editado = st.selectbox("Médico Remitente:", options=dict_m.keys(), format_func=lambda x: dict_m[x], index=list(dict_m.keys()).index(id_medico_defecto) if id_medico_defecto in dict_m else 0, disabled=es_validado)
        
        obras = listar_obras_sociales(); dict_o = {o[0]: f"{o[1]}" for o in obras}
        id_obra_defecto = list(dict_o.keys())[0] if dict_o else None
        for k, v in dict_o.items():
            if str(o_obra).strip().lower() in v.lower(): id_obra_defecto = k; break
        o_sel_editado = st.selectbox("Seguro / Cobertura:", options=dict_o.keys(), format_func=lambda x: dict_o[x], index=list(dict_o.keys()).index(id_obra_defecto) if id_obra_defecto in dict_o else 0, disabled=es_validado)
        
        bq = listar_bioquimicos(); dict_bq = {b[0]: f"{b[1]}" for b in bq}
        bq_index = list(dict_bq.keys()).index(b_firma_id) if b_firma_id in dict_bq else 0
        bq_sel_editado = st.selectbox("Bioquímico a cargo:", options=dict_bq.keys(), format_func=lambda x: dict_bq[x], index=bq_index, disabled=es_validado)
        
        # Ocultamos o deshabilitamos el botón de guardar datos generales si está validado
        if st.button("💾 Guardar Cambios Generales", type="primary", disabled=es_validado):
            ok = actualizar_orden_datos(orden_id_mod, proto_editado, fecha_guardar_editada, m_sel_editado, o_sel_editado, bq_sel_editado, tipo_p_editado, nro_ord_int_editado)
            if ok:
                st.success("¡Datos generales del protocolo actualizados con éxito!")
                st.rerun()
            else:
                st.error("Error: El número de protocolo ingresado ya está asignado a otra orden.")
                
        st.markdown("---")
        
        # --- SECCIÓN 2: INTERFAZ INTERACTIVA DE PRÁCTICAS CON FLECHAS ---
        st.subheader("2. Prácticas y Determinaciones del Protocolo")
        
        # 1. SINCRONIZACIÓN CON EL SESSION_STATE:
        if "perfiles_editar" not in st.session_state:
            st.session_state.perfiles_editar = []
            
        # 🚀 UNA SOLA VEZ: Este es el bloque correcto y unificado
        if "ultimo_orden_id_mod" not in st.session_state or st.session_state.ultimo_orden_id_mod != orden_id_mod or not st.session_state.perfiles_editar:
            st.session_state.ultimo_orden_id_mod = orden_id_mod
            items_actuales = obtener_items_para_cargar(orden_id_mod)
            
            # Traemos el nomenclador maestro para rescatar los nombres reales por su código
            perf_lista = listar_nomenclador()
            nombres_nomenclador = {str(p[0]).strip(): str(p[1]).upper() for p in perf_lista}
            
            perfiles_cargados = []
            vistos_perfiles = set()
            
            for item in items_actuales:
                try:
                    perf_c_m = str(item[1]).strip() # Código del perfil (ej: '412')
                    sub_i_m  = item[3]             # Nombre en la orden
                    es_tit_m = str(item[7]).strip().lower() # Título ('si' / 'no')
                    
                    # Verificamos si la columna de particular existe en la tupla (índice 13 aprox, o por seguridad)
                    es_part_m = item[13] if len(item) > 13 else 0 
                    
                    if perf_c_m not in vistos_perfiles:
                        vistos_perfiles.add(perf_c_m)
                        
                        if es_tit_m == 'si' or es_tit_m == 'sí':
                            nombre_perfil = sub_i_m
                        elif perf_c_m in nombres_nomenclador:
                            nombre_perfil = nombres_nomenclador[perf_c_m]
                        else:
                            nombre_perfil = f"Práctica Código {perf_c_m}"
                            
                        perfiles_cargados.append((item[1], nombre_perfil, bool(es_part_m)))
                except Exception:
                    continue
            
            st.session_state.perfiles_editar = perfiles_cargados

        st.write("➕ **Agregar Nueva Práctica al Protocolo:**")
        perf_lista = listar_nomenclador()
        
        perfil_a_agregar = st.selectbox(
            "Buscar perfil en el nomenclador:", 
            options=perf_lista, 
            format_func=lambda x: f"({x[0]}) {x[1]}",
            key=f"add_perf_combo_{orden_id_mod}"
        )
        
        if st.button("➕ Añadir Práctica a la Lista", key=f"btn_add_mod_{orden_id_mod}", disabled=es_validado):
            if perfil_a_agregar:
                codigos_en_lista = [p[0] for p in st.session_state.perfiles_editar]
                if perfil_a_agregar[0] not in codigos_en_lista:
                    st.session_state.perfiles_editar.append((perfil_a_agregar[0], perfil_a_agregar[1], False))
                    st.rerun()

        st.markdown("<br>", unsafe_allow_html=True)

        if st.session_state.perfiles_editar:
            col_lista_m, col_botones_m = st.columns([0.75, 0.25])
            
            with col_lista_m:
                st.write("📋 **Estructura y Orden del Protocolo:**")
                # Mostramos cada práctica con su checkbox de "Paga Paciente (Particular)" al lado
                nuevos_estados_particulares = []
                for i, (p_id, p_nom, p_part) in enumerate(st.session_state.perfiles_editar):
                    col_item_txt, col_item_chk = st.columns([0.65, 0.35])
                    with col_item_txt:
                        st.markdown(f"**{i+1}.** `({p_id})` — {p_nom.upper()}")
                    with col_item_chk:
                        chk_val = st.checkbox("💵 Paga Paciente (Particular)", value=p_part, key=f"chk_part_mod_{orden_id_mod}_{p_id}_{i}")
                        nuevos_estados_particulares.append((p_id, p_nom, chk_val))
                
                # Actualizamos los valores de particular en el session state si cambian
                if nuevos_estados_particulares != st.session_state.perfiles_editar:
                    st.session_state.perfiles_editar = nuevos_estados_particulares

                # Radio invisible o selector para elegir cuál mover con los botones
                opciones_radio_m = range(len(st.session_state.perfiles_editar))
                perfil_index_sel_m = st.radio(
                    "Seleccione el índice de la práctica a mover o quitar:", 
                    options=opciones_radio_m,
                    format_func=lambda i: f"Mover/Quitar ítem N° {i+1}: ({st.session_state.perfiles_editar[i][0]})"
                )

            with col_botones_m:
                st.write("### Ordenar")
                
                if st.button("🔼 Subir", use_container_width=True, key=f"btn_subir_mod_{orden_id_mod}"):
                    if perfil_index_sel_m > 0:
                        idx = perfil_index_sel_m
                        st.session_state.perfiles_editar[idx], st.session_state.perfiles_editar[idx-1] = \
                            st.session_state.perfiles_editar[idx-1], st.session_state.perfiles_editar[idx]
                        st.rerun()
                        
                if st.button("🔽 Bajar", use_container_width=True, key=f"btn_bajar_mod_{orden_id_mod}"):
                    if perfil_index_sel_m < len(st.session_state.perfiles_editar) - 1:
                        idx = perfil_index_sel_m
                        st.session_state.perfiles_editar[idx], st.session_state.perfiles_editar[idx+1] = \
                            st.session_state.perfiles_editar[idx+1], st.session_state.perfiles_editar[idx]
                        st.rerun()
                        
                st.write("---")
                if st.button("🗑️ Quitar", use_container_width=True, key=f"btn_quitar_mod_{orden_id_mod}", type="secondary"):
                    st.session_state.perfiles_editar.pop(perfil_index_sel_m)
                    st.rerun()
        else:
            st.info("Este protocolo no tiene prácticas asignadas en este momento.")

        st.markdown("<br>", unsafe_allow_html=True)
            
        # 4. BOTÓN DE GUARDADO FINAL Y RECALCULO DE ORDEN VISUAL (ESTABLE)
        if st.button("💾 Guardar Estructura y Orden de Prácticas", type="primary", use_container_width=True, key=f"btn_save_practicas_{orden_id_mod}", disabled=es_validado):
            if not st.session_state.perfiles_editar:
                st.error("Error: El protocolo no puede quedar vacío. Asigne al menos una práctica antes de guardar.")
            else:
                conn = conectar_db(); c = conn.cursor()
                
                # 1. Conservamos de forma segura ABSOLUTAMENTE TODO lo que ya esté escrito en la pantalla
                c.execute("SELECT codigo_item, resultado FROM resultados_items WHERE orden_id = ?", (orden_id_mod,))
                valores_cargados_previamente = {str(row[0]).strip(): row[1] for row in c.fetchall()}
                
                # 2. Limpiamos las filas para reacomodar el orden visual
                c.execute("DELETE FROM resultados_items WHERE orden_id = ?", (orden_id_mod,))
                
                # 3. Reinyectamos las prácticas en el nuevo orden estricto de la lista y guardando el flag particular
                orden_del_perfil = 1
                for perf_id, _, es_particular_bool in st.session_state.perfiles_editar:
                    sub_items = obtener_sub_items_de_practica(perf_id)
                    val_part_int = 1 if es_particular_bool else 0
                    
                    for _, c_item, s_nombre, s_uni, s_ref, s_tit, s_form, s_ord, s_met, s_neg, s_ub_fac in sub_items:
                        codigo_limpio = str(c_item).strip()
                        
                        try:
                            num_orden_interno = int(s_ord) if s_ord is not None and str(s_ord).strip() != "" else 0
                        except:
                            num_orden_interno = 0
                            
                        orden_visual_calculado = (orden_del_perfil * 100) + num_orden_interno
                        
                        # Recuperamos el resultado exacto que ya estaba guardado
                        resultado_a_preservar = valores_cargados_previamente.get(codigo_limpio, '')
                        
                        c.execute("""
                            INSERT INTO resultados_items (
                                orden_id, codigo_perfil, codigo_item, sub_item, resultado, 
                                unidad, valores_referencia, es_titulo, formula, orden_visual, 
                                metodo, en_negrita, ub_facturacion, es_particular
                            ) 
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            orden_id_mod, perf_id, c_item, s_nombre, resultado_a_preservar, s_uni, 
                            s_ref, s_tit, s_form, orden_visual_calculado, s_met, s_neg, s_ub_fac, val_part_int
                        ))
                    
                    orden_del_perfil += 1
                
                conn.commit(); conn.close()
                
                st.toast("🎉 ¡Estructura modificada y ordenada con éxito!", icon="✅")
                st.success("💾 ¡El orden personalizado de las determinaciones ha sido actualizado correctamente!")
                import time
                time.sleep(1.5)
                st.rerun()
                
        st.markdown("---")        

        st.subheader("🚨 Zona de Peligro")
        st.write("Si necesitás anular por completo este protocolo del sistema, utilizá esta opción. Esta acción no se puede deshacer.")
        
        confirmar_bloqueo = st.checkbox(f"Habilitar botón para eliminar el Protocolo N° {o_proto}", key=f"chk_del_{orden_id_mod}")
        
        if confirmar_bloqueo:
            if st.button(f"💥 ELIMINAR PROTOCOLO N° {o_proto} DE FORMA DEFINITIVA", type="primary", use_container_width=True, key=f"btn_del_def_{orden_id_mod}"):
                eliminar_protocolo_completo(orden_id_mod)
                st.success(f"El Protocolo N° {o_proto} ha sido eliminado por completo del sistema.")
                st.rerun()

elif menu == "🧪 Área Analítica (Carga)":
    st.header("🧪 Carga Técnica de Resultados Analíticos")
    todas_ordenes = buscar_ordenes_todas()
    
    if not todas_ordenes:
        st.warning("No se registran protocolos en el sistema.")
    else:
        dict_ord = {
            o[0]: f"Protocolo Nº {o[10]} — Paciente: {o[2]} [{o[4].upper()}]" 
            for o in todas_ordenes
        }
        
        orden_id = st.selectbox("Seleccionar Orden de Trabajo:", options=dict_ord.keys(), format_func=lambda x: dict_ord[x])
        
        nombre_paciente_sel = None
        estado_orden_sel = None 
        pac_id_sel = None  # Variable para guardar el ID real del paciente

        for o in todas_ordenes:
            if o[0] == orden_id:
                nombre_paciente_sel = o[2]
                estado_orden_sel = o[4]
                break

        # 🚀 EXTRAEMOS PACIENTE_ID, EDAD Y SEXO DESDE LA BASE DE DATOS
        p_edad = 18   # Por defecto
        p_sexo = "m"  # Por defecto
        try:
            conn_pac = conectar_db(); cur_pac = conn_pac.cursor()
            cur_pac.execute("""
                SELECT p.id, p.edad, p.sexo 
                FROM pacientes p 
                JOIN ordenes o ON o.paciente_id = p.id 
                WHERE o.id = ?
            """, (orden_id,))
            pac_data = cur_pac.fetchone()
            if pac_data:
                pac_id_sel = pac_data[0]
                p_edad = int(pac_data[1]) if pac_data[1] is not None else 18
                p_sexo = str(pac_data[2]).strip().lower()
            conn_pac.close()
        except Exception:
            pass

        # Obtenemos y ordenamos de forma estricta los ítems analíticos de la base de datos
        try:
            conn_items = conectar_db()
            cur_items = conn_items.cursor()
            cur_items.execute("""
                SELECT id, perfil_codigo, codigo_item, sub_item, unidad, valores_referencia, 
                       resultado, es_titulo, formula, metodo, en_negrita, ub_facturacion, orden_visual, es_particular
                FROM resultados_items 
                WHERE orden_id = ?
                ORDER BY orden_visual ASC, id ASC
            """, (orden_id,))
            items = cur_items.fetchall()
            conn_items.close()
        except Exception:
            items = obtener_items_para_cargar(orden_id)
        
        try:
            items = sorted(items, key=lambda x: (int(x[12]) if x[12] is not None else 9999, x[0]))
        except Exception:
            items = sorted(items, key=lambda x: (x[1], x[0]))

        resp_list = [r[1] for r in listar_respuestas()]
        
        st.markdown("---")
        
        # 🔐 CONTROL DE SEGURIDAD GENERAL
        estado_actual_aa = str(estado_orden_sel).strip().lower()
        es_validado_aa = "validad" in estado_actual_aa or "firmad" in estado_actual_aa or "cerrad" in estado_actual_aa
        
        if es_validado_aa:
            st.error("🛑 **Resultados Bloqueados:** Este protocolo ya se encuentra **VALIDADO**.")
            if st.button("🔓 Desvalidar Protocolo para Editar Resultados", type="secondary", use_container_width=True, key=f"btn_desval_aa_{orden_id}"):
                conn = conectar_db(); c = conn.cursor()
                c.execute("UPDATE ordenes SET estado = 'Pendiente' WHERE id = ?", (orden_id,))
                conn.commit(); conn.close()
                st.toast("🔓 Protocolo liberado. Ya puede editar los resultados.", icon="🔓")
                st.rerun()
        else:
            st.success("🟢 **Protocolo Abierto:** Los resultados pueden ser modificados libremente.")
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        if not items: 
            st.info("Este protocolo se creó vacío.")
        else:
            # -----------------------------------------------------------------
            # FASE 1: CAPTURA DE VALORES E INTERFAZ GRÁFICA DE RENDERIZADO
            # -----------------------------------------------------------------
            valores_temporales = {}
            mapa_codigos = {}
            
            # Función auxiliar interna para traer antecedentes de manera segura
            def obtener_historial_paciente_item(paciente_id, nombre_paciente, codigo_item, orden_id_actual, limite=15):
                if not codigo_item:
                    return []

                conn = conectar_db()
                cur = conn.cursor()
                historial = []

                # Ampliamos la consulta para buscar tanto por el código exacto como por coincidencias de sub_item
                query = """
                    SELECT 
                        o.fecha, 
                        ri.resultado, 
                        ri.unidad, 
                        o.id AS nro_protocolo
                    FROM resultados_items ri
                    JOIN ordenes o ON ri.orden_id = o.id
                    LEFT JOIN pacientes p ON o.paciente_id = p.id
                    WHERE (o.paciente_id = ? OR LOWER(TRIM(p.nombre)) = LOWER(TRIM(?)))
                      AND (
                          TRIM(UPPER(ri.codigo_item)) = TRIM(UPPER(?)) 
                          OR TRIM(UPPER(ri.sub_item)) = TRIM(UPPER(?))
                      )
                      AND o.id < ?
                      AND ri.resultado IS NOT NULL 
                      AND TRIM(CAST(ri.resultado AS TEXT)) != ''
                    ORDER BY o.id DESC
                    LIMIT ?
                """

                try:
                    cur.execute(query, (
                        paciente_id, 
                        str(nombre_paciente).strip(), 
                        str(codigo_item).strip(), 
                        str(codigo_item).strip(), 
                        orden_id_actual, # Usamos menor (<) que el protocolo actual para garantizar que sean estrictamente históricos hacia atrás
                        limite
                    ))
                    historial = cur.fetchall()
                except Exception as e:
                    print(f"Error al consultar historial: {e}")
                    historial = []
                finally:
                    conn.close()

                return historial

            # Bucle principal que dibuja cada ítem en pantalla de forma ordenada
            for r_id, perf_c, item_c, sub_item, unidad, ref, resultado, es_tit, formula, metodo, en_negrita, ub_f, orden_v, es_part in items:

                if es_tit == 'Si' or str(item_c).strip().upper() == 'T_FORM': 
                    st.markdown(f"### 📊 {sub_item.upper()}")
                    st.markdown("---")
                    continue
                
                # BÚSQUEDA DE ANTECEDENTES HISTÓRICOS
                historial = obtener_historial_paciente_item(pac_id_sel, nombre_paciente_sel, item_c, orden_id, 10)
                

                # Proporciones equilibradas para mantener todo perfectamente horizontal
                col_n, col_v, col_u, col_h = st.columns([3, 5, 2, 2])

                with col_n:
                    st.markdown(f"**{sub_item}**" if en_negrita == 'Si' else f"{sub_item}")
                    if metodo: 
                        st.caption(f"🧪 {metodo}")

                with col_v:
                    col_sub_manual, col_sub_combo = st.columns([1, 1])
                    
                    opciones_combo = ["-- Manual --"] + resp_list
                    
                    index_def = 0
                    if str(resultado).strip() in resp_list:
                        index_def = resp_list.index(str(resultado).strip()) + 1
                        
                    with col_sub_combo:
                        seleccion_resp = st.selectbox(
                            "Prediseñado", 
                            options=opciones_combo, 
                            index=index_def,
                            key=f"sel_{r_id}", 
                            disabled=es_validado_aa,
                            label_visibility="collapsed"
                        )
                    
                    with col_sub_manual:
                        if seleccion_resp == "-- Manual --":
                            val_actual_str = str(resultado) if resultado is not None else ""
                            val_input = st.text_input(
                                "Resultado", 
                                value=val_actual_str, 
                                key=f"raw_{r_id}", 
                                disabled=es_validado_aa,
                                label_visibility="collapsed"
                            )
                            valores_temporales[r_id] = val_input
                        else:
                            st.text_input("Resultado", value=seleccion_resp, key=f"raw_dis_{r_id}", disabled=True, label_visibility="collapsed")
                            valores_temporales[r_id] = seleccion_resp

                with col_u:
                    if unidad:
                        st.write(unidad)

                with col_h:
                    if historial:
                        html_historial = ""

                        for idx, item_h in enumerate(historial):
                            f_hist = item_h[0] if len(item_h) > 0 else ""
                            r_hist = item_h[1] if len(item_h) > 1 else ""
                            u_hist = item_h[2] if len(item_h) > 2 else ""
                            prot_h = item_h[3] if len(item_h) > 3 else ""

                            fondo = "#eff6ff" if idx == 0 else ("#ffffff" if idx % 2 == 0 else "#f8fafc")
                            borde = "#60a5fa" if idx == 0 else "#e2e8f0"

                            html_historial += f"""
                            <div style="
                                background-color: {fondo};
                                border: 1px solid {borde};
                                border-radius: 6px;
                                padding: 4px 6px;
                                margin-bottom: 4px;
                                line-height: 1.1;
                                font-size: 10px;
                                color: #0f172a;
                                white-space: nowrap;
                                overflow: hidden;
                                text-overflow: ellipsis;
                            ">
                                <span style="font-size: 8.5px; color: #64748b;">{f_hist} · #{prot_h}</span>
                                <span style="font-weight: 700; color: #16a34a;"> — {r_hist}</span>
                                <span style="font-size: 8.5px; color: #475569;"> {u_hist}</span>
                            </div>
                            """

                        st.markdown(
                            f"""
                            <div style="
                                border: 1px solid #cbd5e1;
                                background-color: #f8fafc;
                                border-radius: 10px;
                                padding: 5px;
                                height: 180px;
                                overflow-y: auto;
                                box-shadow: 0 1px 2px rgba(0,0,0,0.04);
                            ">
                                {html_historial}
                            </div>
                            """,
                            unsafe_allow_html=True
                        )
                    else:
                        st.caption("Sin historial")









                # Alimentamos el mapa de códigos en tiempo real para cada ítem procesado
                codigo_str = str(item_c).strip().upper()
                mapa_codigos[codigo_str] = {
                    'r_id': r_id,
                    'valor': str(valores_temporales.get(r_id, "")).strip()
                }
            
            st.markdown("<br>", unsafe_allow_html=True)

            # -----------------------------------------------------------------
            # FASE 2: MOTOR DE PROCESAMIENTO MATEMÁTICO (FÓRMULAS)
            # -----------------------------------------------------------------
            hubo_error_ldl = False
            
            # Hemograma
            gr_val = mapa_codigos.get("GR_01", {}).get("valor", "")
            ht_val = mapa_codigos.get("HT_02", {}).get("valor", "")
            hb_val = mapa_codigos.get("HB_03", {}).get("valor", "")
            try:
                gr = float(gr_val.replace(',', '.')) if gr_val else 0
                ht = float(ht_val.replace(',', '.')) if ht_val else 0
                hb = float(hb_val.replace(',', '.')) if hb_val else 0
                
                if gr > 0 and ht > 0 and "VCM_04" in mapa_codigos:
                    valores_temporales[mapa_codigos["VCM_04"]['r_id']] = str(round((ht * 10) / gr, 1))
                if gr > 0 and hb > 0 and "HCM_05" in mapa_codigos:
                    valores_temporales[mapa_codigos["HCM_05"]['r_id']] = str(round((hb * 10) / gr, 1))
                if ht > 0 and hb > 0 and "CHCM_06" in mapa_codigos:
                    valores_temporales[mapa_codigos["CHCM_06"]['r_id']] = str(round((hb * 100) / ht, 1))
            except ValueError:
                pass

            # Perfil Lipídico
            col_val = mapa_codigos.get("174", {}).get("valor", "")
            hdl_val = mapa_codigos.get("1035", {}).get("valor", "")
            tg_val = mapa_codigos.get("876", {}).get("valor", "")
            try:
                ct = float(col_val.replace(',', '.')) if col_val else 0
                hdl = float(hdl_val.replace(',', '.')) if hdl_val else 0
                tg = float(tg_val.replace(',', '.')) if tg_val else 0

                if ct > 0 and hdl > 0:
                    non_hdl = round(ct - hdl, 0)
                    if "CNOH" in mapa_codigos: valores_temporales[mapa_codigos["CNOH"]['r_id']] = str(int(non_hdl))
                    relacion_ch = round(ct / hdl, 1)
                    if "C/H" in mapa_codigos: valores_temporales[mapa_codigos["C/H"]['r_id']] = str(relacion_ch)
                    if "IA" in mapa_codigos: valores_temporales[mapa_codigos["IA"]['r_id']] = str(relacion_ch)

                    if tg > 0:
                        if non_hdl <= 0:
                            st.error("⚠️ Cálculo de LDL falló: El colesterol No-HDL da un valor menor o igual a cero.")
                            hubo_error_ldl = True
                        elif tg < 9 or tg > 400:
                            st.error("⚠️ Cálculo de LDL falló: Los triglicéridos deben estar entre 9 y 400 mg/dL para Johns Hopkins.")
                            hubo_error_ldl = True
                        else:
                            col_idx = 0
                            if non_hdl < 100: col_idx = 0
                            elif non_hdl <= 129: col_idx = 1
                            elif non_hdl <= 159: col_idx = 2
                            elif non_hdl <= 189: col_idx = 3
                            elif non_hdl <= 218: col_idx = 4
                            else: col_idx = 5

                            intervalos_tg = [
                                (9, 49), (50, 56), (57, 63), (64, 70), (71, 77), (78, 84), (85, 91),
                                (92, 98), (99, 105), (106, 112), (113, 120), (121, 128), (129, 137),
                                (138, 147), (148, 158), (159, 170), (171, 184), (185, 201), (202, 222),
                                (223, 252), (253, 298), (299, 400)
                            ]
                            matriz_factores = [
                                [3.3, 3.1, 3.1, 3.1, 3.1, 3.1], [3.9, 3.7, 3.5, 3.5, 3.5, 3.5],
                                [4.2, 4.0, 3.9, 3.8, 3.8, 3.8], [4.5, 4.3, 4.1, 4.0, 4.0, 4.0],
                                [4.8, 4.5, 4.4, 4.3, 4.2, 4.2], [5.1, 4.8, 4.6, 4.5, 4.4, 4.4],
                                [5.3, 5.0, 4.8, 4.7, 4.6, 4.6], [5.6, 5.3, 5.0, 4.9, 4.8, 4.8],
                                [5.8, 5.5, 5.2, 5.1, 5.0, 5.0], [6.2, 5.7, 5.5, 5.3, 5.2, 5.2],
                                [6.4, 6.0, 5.7, 5.5, 5.4, 5.4], [6.7, 6.2, 5.9, 5.8, 5.6, 5.6],
                                [7.0, 6.5, 6.2, 6.0, 5.8, 5.8], [7.3, 6.8, 6.4, 6.2, 6.1, 6.1],
                                [7.7, 7.1, 6.8, 6.5, 6.4, 6.4], [8.1, 7.5, 7.1, 6.9, 6.7, 6.7],
                                [8.6, 7.9, 7.5, 7.2, 7.0, 7.0], [9.1, 8.4, 7.9, 7.6, 7.4, 7.4],
                                [9.7, 9.0, 8.5, 8.1, 7.9, 7.9], [10.5, 9.6, 9.1, 8.7, 8.5, 8.5],
                                [11.7, 10.6, 9.9, 9.5, 9.2, 9.2], [11.9, 11.9, 11.3, 10.8, 10.4, 10.4]
                            ]
                            fila_idx = None
                            for i, (min_tg, max_tg) in enumerate(intervalos_tg):
                                if min_tg <= tg <= max_tg:
                                    fila_idx = i
                                    break
                            if fila_idx is not None:
                                factor = matriz_factores[fila_idx][col_idx]
                                ldl_calc = round(non_hdl - (tg / factor), 0)
                                if "1040" in mapa_codigos:
                                    valores_temporales[mapa_codigos["1040"]['r_id']] = str(int(ldl_calc))
            except Exception as e:
                hubo_error_ldl = True

            # FGe CKD-EPI
            crea_val = mapa_codigos.get("192", {}).get("valor", "")
            if crea_val:
                fge_val = calcular_fge_ckd_epi(crea_val.replace(',', '.'), p_edad, p_sexo)
                if "FGE" in mapa_codigos: valores_temporales[mapa_codigos["FGE"]['r_id']] = fge_val

            # Fórmulas Dinámicas Personalizadas
            for r_id_f, _, item_c_f, _, _, _, _, _, formula_f, _, _, _, _, _ in items:
                if formula_f and str(formula_f).strip():
                    expr_evaluable = str(formula_f).strip().upper()
                    codigos_db = sorted(mapa_codigos.keys(), key=len, reverse=True)
                    hubo_reemplazo = False
                    error_conversion = False
                    
                    for cod in codigos_db:
                        if cod in expr_evaluable:
                            valor_crudo = mapa_codigos[cod]['valor']
                            try:
                                valor_num = float(valor_crudo.replace(',', '.')) if valor_crudo else 0.0
                                expr_evaluable = expr_evaluable.replace(cod, f"({valor_num})")
                                hubo_reemplazo = True
                            except ValueError:
                                error_conversion = True
                                break
                    
                    if hubo_reemplazo and not error_conversion:
                        try:
                            safe_dict = {"__builtins__": None, "abs": abs, "round": round, "min": min, "max": max}
                            calculo_final = round(eval(expr_evaluable, safe_dict), 2)
                            if isinstance(calculo_final, float) and calculo_final.is_integer():
                                calculo_final = int(calculo_final)
                            valores_temporales[r_id_f] = str(calculo_final)
                        except ZeroDivisionError:
                            valores_temporales[r_id_f] = ""
                        except Exception:
                            pass

            # -----------------------------------------------------------------
            # FASE 3: INTERFAZ DE IMAGEN (PROTEINOGRAMA) Y BOTÓN GUARDAR
            # -----------------------------------------------------------------
            tiene_pxe = any(str(item[2]).strip() == "764" for item in items)
            archivo_grafico = None
            eliminar_img = False
            r_id_pxe = None

            if tiene_pxe:
                st.markdown("---")
                st.markdown("### 📈 Gráfico de Corrida Electroforética (Código 764)")
                imagen_guardada = None
                
                for item in items:
                    if str(item[2]).strip() == "764":
                        r_id_pxe = item[0]
                        break
                
                if r_id_pxe:
                    try:
                        conn_img = conectar_db(); cur_img = conn_img.cursor()
                        cur_img.execute("SELECT pxe_grafico FROM resultados_items WHERE id = ? AND pxe_grafico IS NOT NULL", (r_id_pxe,))
                        row = cur_img.fetchone()
                        if row: imagen_guardada = row[0]
                        conn_img.close()
                    except Exception:
                        pass
                
                if imagen_guardada:
                    st.image(imagen_guardada, caption="Corrida electroforética actual guardada", width=350)
                    eliminar_img = st.checkbox("🗑️ Marcar para eliminar o reemplazar la imagen actual", key="del_pxe_actual")
                else:
                    st.info("ℹ️ Aún no se ha subido el gráfico de la corrida para este paciente.")
                
                archivo_grafico = st.file_uploader("Subir imagen de la corrida (.png, .jpg, .jpeg):", type=["png", "jpg", "jpeg"], key="uploader_pxe_corrida")
                if archivo_grafico is not None:
                    st.image(archivo_grafico, caption="Vista previa del nuevo gráfico a guardar", width=350)
                st.markdown("---")

            # Botón de Guardar Persistente
            if st.button("💾 Guardar Resultados", type="primary", disabled=es_validado_aa):
                conn = conectar_db(); cur = conn.cursor()
                
                for r_id, val in valores_temporales.items():
                    cur.execute("UPDATE resultados_items SET resultado = ? WHERE id = ?", (str(val), r_id))
                
                if tiene_pxe and r_id_pxe:
                    if archivo_grafico is not None:
                        bytes_imagen = archivo_grafico.getvalue()
                        cur.execute("UPDATE resultados_items SET pxe_grafico = ? WHERE id = ?", (sqlite3.Binary(bytes_imagen), r_id_pxe))
                    elif eliminar_img:
                        cur.execute("UPDATE resultados_items SET pxe_grafico = NULL WHERE id = ?", (r_id_pxe,))
                
                conn.commit(); conn.close()
                
                if not hubo_error_ldl:
                    st.success("Resultados guardados con éxito.")
                    st.rerun()
                else:
                    st.warning("Se guardaron los demás resultados, pero el LDL no pudo procesarse. Revisa el error rojo de arriba.")
elif menu == "🖨️ Validación e Informes":
    st.header("🖨️ Impresión y Validación de Informes Bioquímicos")
    ordenes = buscar_ordenes_todas()
    cfg_g = obtener_configuracion_general()
    
    img_logo = obtener_logo_base64()
    img_f1 = obtener_firma_base64(1)
    img_f2 = obtener_firma_base64(2)
    
    html_logo = f'<img src="{img_logo}" style="max-height: 75px; max-width: 220px; display: block; margin-bottom: 5px;">' if img_logo else f'<span style="font-size: 24px; font-weight: bold; color: black;">{cfg_g[0]}</span>'
    html_f1 = f'<img src="{img_f1}" style="max-height: 55px; max-width: 150px; display: block; margin: 0 auto 5px auto;">' if img_f1 else '<div style="height:55px;"></div>'
    html_f2 = f'<img src="{img_f2}" style="max-height: 55px; max-width: 150px; display: block; margin: 0 auto 5px auto;">' if img_f2 else '<div style="height:55px;"></div>'
    
    if ordenes:
        dict_o = {o[0]: f"Protocolo N&deg; {o[10]} — Paciente: {o[2]}" for o in ordenes}
        id_sel = st.selectbox("Seleccione el Examen:", options=dict_o.keys(), format_func=lambda x: dict_o[x])
        ord_sel = [o for o in ordenes if o[0] == id_sel][0]
        _, o_fecha, o_paciente, o_dni, o_estado, _, p_sexo, o_medico, o_obra, p_tel, o_proto, _, _, p_afiliado, t_pac, n_ord_i, _, p_f_nac = ord_sel
        p_edad = calcular_edad_por_texto(p_f_nac)
        
        # 🔒 CONTROL DE ESTADO
        es_ya_cerrado = str(o_estado).strip().lower() == "cerrada"
        
        if es_ya_cerrado:
            st.warning(f"🔒 Este examen (Protocolo N° {o_proto}) ya se encuentra **VALIDADO Y CERRADO**. No se permiten modificaciones.")
        
        items_proto = obtener_items_para_cargar(id_sel)
        try:
            items_proto = sorted(items_proto, key=lambda x: (int(x[12]) if x[12] is not None else 9999, x[0]))
        except Exception:
            items_proto = sorted(items_proto, key=lambda x: (x[1], x[0]))
        
        st.markdown("---")
        try:
            for formato in ('%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y'):
                try:
                    fecha_defecto = datetime.strptime(str(o_fecha).strip(), formato).date()
                    break
                except ValueError:
                    continue
        except:
            fecha_defecto = date.today()
            
        fecha_custom = st.date_input("📆 Modificar fecha (Solo afecta a la impresión de este reporte):", value=fecha_defecto, key=f"f_cust_{id_sel}", disabled=es_ya_cerrado)
        fecha_informe_final = fecha_custom.strftime('%d/%m/%Y')
        st.markdown("---")
        
        # ==========================================
        # 📊 PROCESAMIENTO DEL GRÁFICO (PROTEINOGRAMA)
        # ==========================================
        html_grafico_pantalla = ""
        try:
            import base64
            conn_rep = conectar_db()
            cur_rep = conn_rep.cursor()
            
            cur_rep.execute("PRAGMA table_info(resultados_items)")
            columnas = [col[1] for col in cur_rep.fetchall()]
            col_orden = "orden_id" if "orden_id" in columnas else ("protocolo_id" if "protocolo_id" in columnas else None)
            
            if col_orden:
                cur_rep.execute(f"SELECT pxe_grafico FROM resultados_items WHERE {col_orden} = ? AND pxe_grafico IS NOT NULL LIMIT 1", (id_sel,))
                row = cur_rep.fetchone()
                if row and row[0]:
                    img_b64 = base64.b64encode(row[0]).decode('utf-8')
                    html_grafico_pantalla = f"""
                    <div style="text-align: center; margin-top: 15px; margin-bottom: 15px; page-break-inside: avoid;">
                        <span style="font-size: 11px; font-weight: bold; color: #444; text-transform: uppercase; display:block; margin-bottom:5px;">Curva Electroforética (Proteinograma)</span>
                        <img src="data:image/png;base64,{img_b64}" style="max-height: 120px; border: 1px solid #ddd; padding:5px; background:white;" />
                    </div>
                    """
            conn_rep.close()
        except Exception as e_graph:
            print(f"❌ Error al procesar gráfico: {str(e_graph)}")

        # ==========================================
        # 🖥️ CONSTRUCCIÓN DEL CUERPO DE RESULTADOS
        # ==========================================
        html_filas_resultados = ""
        for _, perf_c, item_c, sub_item, unidad, ref, resultado, es_tit, _, metodo, en_negrita, *resto in items_proto:
            resultado_limpio = str(resultado).strip() if resultado is not None else ""
            if es_tit != 'Si' and str(item_c).strip().upper() != 'T_FORM' and (resultado_limpio == "" or resultado_limpio.lower() == "none"):
                continue

            if es_tit == 'Si' or str(item_c).strip().upper() == 'T_FORM': 
                html_filas_resultados += f"""
                <tr style="page-break-inside: avoid;">
                    <td colspan='3' style='font-weight: bold; font-size: 14px; padding-top: 12px; padding-bottom: 4px; text-transform: uppercase; border-bottom: 1px solid #eee;'>{sub_item}</td>
                </tr>"""
            else:
                # 🛠️ Formateo inteligente según los decimales de la Referencia
                res_fmt = resultado
                if resultado is not None and str(resultado).strip() != "":
                    try:
                        val_float = float(str(resultado).replace(',', '.'))
                        ref_str = str(ref) if ref else ""
                        
                        if "," in ref_str or "." in ref_str:
                            import re
                            # Si en la referencia hay números con 2 decimales (ej: 2,00 o 14.50)
                            if re.search(r'[\.,]\d{2}\b', ref_str):
                                res_fmt = f"{val_float:.2f}"
                            else:
                                # Si tiene 1 decimal (ej: 4,5)
                                res_fmt = f"{val_float:.1f}"
                        else:
                            # Si la referencia no tiene comas ni puntos (ej: 37 a 48)
                            res_fmt = f"{int(round(val_float))}"
                            
                    except ValueError:
                        # Si es texto (ej: "Positivo"), se mantiene igual
                        res_fmt = resultado

                res_display = f"{res_fmt} {unidad}" if res_fmt else ""
                estilo_texto = "font-weight: bold;" if en_negrita == 'Si' else "font-weight: normal;"
                html_filas_resultados += f"""
                <tr style="page-break-inside: avoid;">
                    <td style="padding-left: 15px; padding-top: 4px; padding-bottom: 4px; {estilo_texto}">{sub_item}:"""
                if metodo: 
                    html_filas_resultados += f'<br><span style="font-size:11px; font-weight:normal; color:#555; padding-left:10px;">(Método: {metodo})</span>'
                html_filas_resultados += f"""</td>
                    <td><b>{res_display}</b></td>
                    <td style="font-size: 12px; white-space: pre-line; padding-top: 4px; padding-bottom: 4px;">{ref}</td>
                </tr>"""
        # ==========================================
        # 📑 HTML COMPLETO DE TABLA ORIGINAL
        # ==========================================
        cfg = obtener_configuracion_general()
        leyenda_colegio = cfg[8] if len(cfg) > 8 else ""

        html_cuerpo_resultados = f"<tbody><tr><td colspan='3'><style>table tr td:nth-child(1), table tr th:nth-child(1) {{ width: 40% !important; text-align: left !important; }} table tr td:nth-child(2), table tr th:nth-child(2) {{ width: 30% !important; text-align: center !important; }} table tr td:nth-child(3), table tr th:nth-child(3) {{ width: 30% !important; text-align: left !important; }}</style><table style='width: 100%; border-collapse: collapse; color: black;'>{html_filas_resultados}</table>{html_grafico_pantalla}</td></tr></tbody>"
        
        html_encabezado = f"""
        <thead>
        <tr>
          <td colspan="3" style="padding-bottom: 10px;">
            <table style="width: 100%; border-collapse: collapse;">
              <tr>
                <td style="width: 25%; vertical-align: middle;">{html_logo}</td>
                <td style="width: 45%; text-align: center; vertical-align: middle; padding: 10px 0;">
                  <span style="font-size: 22px; font-weight: bold; color: black; text-transform: uppercase;">
                    LABORATORIO DE ANÁLISIS CLÍNICOS
                  </span>
                </td>
                <td style="width: 30%; text-align: center; vertical-align: middle; font-size: 12px; line-height: 1.3;">
                  <b>Bioq.: Fernández María de los Ángeles</b><br>M.P.: 3774<br><br>
                  <b>Bioq.: Farfán Luis A.</b><br>M.P.: 5092
                </td>
              </tr>
            </table>
            <hr style="border-top: 2px solid black; margin: 8px 0 10px 0;">
            <table style="width: 100%; font-size: 13px; color: black; line-height: 1.4;">
              <tr>
                <td style="width: 60%;"><b>Paciente:</b> {o_paciente}</td>
                <td style="width: 40%;"><b>Fecha:</b> {fecha_informe_final}</td>
              </tr>
              <tr>
                <td><b>D.N.I.:</b> {o_dni} &nbsp;&nbsp;&nbsp;&nbsp; <b>Sexo:</b> {p_sexo} &nbsp;&nbsp;&nbsp;&nbsp; <b>Edad:</b> {p_edad} años</td>
                <td><b>N&deg; Protocolo:</b> {o_proto}</td>
              </tr>
              <tr>
                <td><b>Obra Social:</b> {o_obra} &nbsp;&nbsp;&nbsp;&nbsp; <b>N&deg; Afiliado:</b> {p_afiliado}</td>
                <td><b>Dr./a:</b> {o_medico}</td>
              </tr>
            </table>
            <table style="width: 100%; border-collapse: collapse; margin-top: 10px; border-bottom: 2px solid black;">
              <tr>
                <th style="text-align: center; font-size: 13px; padding: 4px; width: 40%;">DETERMINACIÓN</th>
                <th style="text-align: center; font-size: 13px; padding: 4px; width: 30%;">RESULTADO</th>
                <th style="text-align: center; font-size: 13px; padding: 4px; width: 30%;">VALORES DE REFERENCIA</th>
              </tr>
            </table>
          </td>
        </tr>
        </thead>
        """

        # Construcción del cuerpo de resultados
        html_cuerpo_resultados = f"""
        <tbody>
          {html_filas_resultados}
          <tr><td colspan="3">{html_grafico_pantalla}</td></tr>
        </tbody>
        """

        # Construcción del informe completo
        html_informe_estructurado = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    margin: 0;
                    padding: 0;
                    background-color: white;
                    color: black;
                }}
                .tabla-global {{
                    width: 100%;
                    border-collapse: collapse;
                }}
                thead {{
                    display: table-header-group;
                }}
                tbody {{
                    display: table-row-group;
                }}
                tfoot {{
                    display: table-footer-group;
                }}
                tr {{
                    page-break-inside: avoid;
                }}
                /* Estilos para centrar columnas de resultados */
                table tr td:nth-child(1), table tr th:nth-child(1) {{
                    width: 40% !important;
                    text-align: center !important;
                }}
                table tr td:nth-child(2), table tr th:nth-child(2) {{
                    width: 30% !important;
                    text-align: center !important;
                }}
                table tr td:nth-child(3), table tr th:nth-child(3) {{
                    width: 30% !important;
                    text-align: center !important;
                }}
                @media print {{
                    @page {{
                        size: A4 portrait;
                        margin: 1cm;
                    }}
                }}
            </style>
        </head>
        <body>
            <div style="padding: 10px; border: 1px solid #111;">
                <table class="tabla-global">
                    {html_encabezado}
                    {html_cuerpo_resultados}
                    <tfoot>
                        <tr>
                            <td colspan="3" style="padding-top: 20px;">
                                <table style="width: 100%; font-size: 12px; text-align: center;">
                                    <tr>
                                        <td style="width: 50%; vertical-align: bottom; text-align: center;">
                                            {html_f1}
                                            <div style="border-top: 1px dotted black; width: 180px; margin: 5px auto 0 auto;"></div>
                                            <b>Bioq. Fernández María de los Ángeles</b><br>Bioquímica - M.P. 3774
                                        </td>
                                        <td style="width: 50%; vertical-align: bottom; text-align: center;">
                                            {html_f2}
                                            <div style="border-top: 1px dotted black; width: 180px; margin: 5px auto 0 auto;"></div>
                                            <b>Bioq. Farfán Luis A.</b><br>Bioquímico - M.P. 5092
                                        </td>
                                    </tr>
                                </table>
                                <div style="margin-top: 8px; text-align: center; font-size: 10px; color: #444; line-height: 1.2;">
                                    {leyenda_colegio}
                                </div>
                            </td>
                        </tr>
                    </tfoot>
                </table>
            </div>
        </body>
        </html>
        """

        
        # 💡 CAMBIO CLAVE: Conversión de HTML a Data URL limpia
        import urllib.parse
        encoded_html = urllib.parse.quote(html_informe_estructurado)
        src_preview = f"data:text/html;charset=utf-8,{encoded_html}"
        
        # Muestra la vista previa con st.iframe sin parámetros incompatibles
        st.iframe(src=src_preview, height=800)

        # ==========================================
        # 🔘 BOTONES DE ACCIÓN
        # ==========================================
        st.markdown("---")
        col_btn1, col_btn2, col_btn3 = st.columns(3)

        with col_btn1:
            if st.button("🖨️ Imprimir Informe", key="btn_lis_imprimir", type="primary", use_container_width=True):
                cfg = obtener_configuracion_general()
                leyenda_colegio = cfg[8] if len(cfg) > 8 else ""

                html_impresion_crudo = f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <meta charset="utf-8">
                    <title>Informe Bioquímico - Protocolo {o_proto}</title>
                    <style>
                        @page {{
                            size: A4;
                            margin: 15mm;
                        }}
                        body {{
                            font-family: Arial, sans-serif;
                            position: relative;
                            min-height: 100vh;
                        }}
                        .footer {{
                            position: fixed;
                            bottom: 8mm;
                            left: 0;
                            right: 0;
                            text-align: center;
                            font-size: 10px;
                            color: #444;
                        }}
                    </style>
                </head>
                <body>
                    {html_informe_estructurado}

                    

                    <script>
                        window.onload = function() {{ window.print(); }};
                    </script>
                </body>
                </html>
                """
                encoded_print = urllib.parse.quote(html_impresion_crudo)
                src_print = f"data:text/html;charset=utf-8,{encoded_print}"
                st.iframe(src=src_print, height=1)

        with col_btn2:
            tel_wsp = str(p_tel).strip() if p_tel else ""
            texto_wsp = f"Hola! Te enviamos el informe de Laboratorio del Protocolo N° {o_proto} ({o_paciente})."
            tel_wsp_filtrado = "".join(c for c in tel_wsp if c.isdigit())
            st.link_button("💬 Enviar WhatsApp", url=f"https://wa.me/{tel_wsp_filtrado}?text={texto_wsp}", use_container_width=True)

        with col_btn3:
            texto_boton_cerrar = "🔒 Ya está Cerrado" if es_ya_cerrado else "✅ Validar y Cerrar"
            if st.button(texto_boton_cerrar, key="btn_lis_cerrar", use_container_width=True, disabled=es_ya_cerrado):
                conn = conectar_db()
                cur = conn.cursor()
                cur.execute("UPDATE ordenes SET estado = 'Cerrada' WHERE id = ?", (id_sel,))
                conn.commit()
                conn.close()
                st.success(f"🚀 Examen Protocolo N° {o_proto} cerrado con éxito.")
                st.rerun()
    else:
        st.info("No hay órdenes registradas para validar o imprimir.")
  
  
# -----------------------------------------------------------------------------
# 💵 MÓDULO 1: FACTURACIÓN OBRAS SOCIALES (RESTAURADO CON SUS 2 VISTAS)
# -----------------------------------------------------------------------------
elif menu == "💵 Facturación Obras Sociales":
    st.header("💵 Liquidación y Facturación de Obras Sociales")
    lista_os_f = listar_obras_sociales()
    if not lista_os_f:
        st.warning("No hay obras sociales registradas.")
        st.stop()
        
    dict_os_f = {os[0]: os[1] for os in lista_os_f}
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        os_f_sel = st.selectbox("Seleccione Obra Social:", options=dict_os_f.keys(), format_func=lambda x: dict_os_f[x], key="sb_os_f")
    with col2:
        f_desde = st.date_input("Fecha Desde:", value=date(date.today().year, date.today().month, 1), key="fact_fecha_desde")
    with col3:
        f_hasta = st.date_input("Fecha Hasta:", value=date.today(), key="fact_fecha_hasta")
    with col4:
        ambito_f = st.selectbox("Ámbito:", options=["Ambos", "Externo", "Internado"], key="fact_ambito")
    
    valor_ub_os_actual = 0.0
    incluye_acto = 0
    valor_acto = 0.0
    incluye_gbi = 0
    valor_gbi = 0.0

    for os_item in lista_os_f:
        if os_item[0] == os_f_sel:
            valor_ub_os_actual = os_item[2] if os_item[2] is not None else 0.0
            incluye_acto = os_item[3] if len(os_item) > 3 and os_item[3] is not None else 0
            valor_acto = os_item[4] if len(os_item) > 4 and os_item[4] is not None else 0.0
            incluye_gbi = os_item[5] if len(os_item) > 5 and os_item[5] is not None else 0
            valor_gbi = os_item[6] if len(os_item) > 6 and os_item[6] is not None else 0.0
            break
            
    st.info(f"💡 Valor de la U.B. actual para esta Obra Social: **$ {valor_ub_os_actual:,.2f}**")
    
    todas_las_ordenes = buscar_ordenes_todas()
    ordenes_filtradas = []
    
    for o in todas_las_ordenes:
        estado_o = str(o[4]).strip().lower() 
        nombre_os_buscada = str(dict_os_f[os_f_sel]).strip().lower()
        os_en_bd = str(o[8]).strip().lower() if o[8] is not None else ""
        fecha_orden_str = str(o[1]).strip() if o[1] is not None else ""
        ambito_o = str(o[14]).strip().lower() if o[14] is not None else ""
        
        # EXCLUSIÓN 1: Si la orden entera fue pasada a PARTICULAR, saltar
        if os_en_bd == "particular":
            continue

        if estado_o in ['validada', 'cerrada'] and os_en_bd == nombre_os_buscada:
            fecha_objeto = None
            for formato in ('%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y'):
                try:
                    fecha_objeto = datetime.strptime(fecha_orden_str, formato).date()
                    break
                except ValueError:
                    continue
            
            if fecha_objeto is not None:
                if f_desde <= fecha_objeto <= f_hasta:
                    if ambito_f == "Ambos" or (ambito_f == "Externo" and ambito_o == "externo") or (ambito_f == "Internado" and ambito_o == "internado"):
                        ordenes_filtradas.append(o)
                        
    if not ordenes_filtradas:
        st.info("No se encontraron órdenes validadas o cerradas para los filtros seleccionados.")
    else:
        st.success(f"📋 Se encontraron **{len(ordenes_filtradas)}** órdenes listas para liquidar en el período seleccionado.")
        t_vista = st.radio("Tipo de Reporte / Vista:", options=["1. Detalle por Pacientes", "2. Resumen Consolidado (Agrupado por Código)"], horizontal=True, key="fact_tipo_vista")
        st.markdown("---")
        
        codigos_hemograma = ['GR_01', 'HB_02', 'HT_03', 'VCM_04', 'HCM_05', 'CHCM_06', 'GB_07', 'NEU_08', 'EOS_09', 'BAS_10', 'LIN_11', 'MON_12', 'PLAQ_13']
        codigos_no_facturables = ['C/H', 'CNOH', 'IA', 'FGE']

        clave_contenedor = f"cont_fact_{os_f_sel}_{f_desde}_{f_hasta}_{ambito_f}_{t_vista.replace(' ', '_')}"
        
        with st.container(key=clave_contenedor):
            # -----------------------------------------------------------------
            # OPCIÓN 1: VISTA DETALLADA POR PACIENTES
            # -----------------------------------------------------------------
            if t_vista == "1. Detalle por Pacientes":
                filas_vouchers = []
                gran_total = 0.0
                for o in ordenes_filtradas:
                    items_o = obtener_items_para_cargar(o[0])
                    hemograma_procesado_en_orden = False
                    tiene_analisis_facturables = False
                    
                    for item in items_o:
                        perf_c = str(item[1]).strip() if item[1] is not None else ""
                        cod_i = str(item[2]).strip() if item[2] is not None else ""
                        sub_i = str(item[3]).strip() if item[3] is not None else ""
                        ub_f = item[11]
                        
                        # EXCLUSIÓN 2: Verificar si el ítem individual está marcado como es_particular
                        val_particular = item[-1] if len(item) > 13 else 0
                        if val_particular in [1, '1', True, 'true', 'True']:
                            continue

                        codigo_limpio = cod_i.upper()

                        if codigo_limpio in codigos_no_facturables: 
                            continue
                        
                        try:
                            if ub_f is None or str(ub_f).strip() == "" or float(str(ub_f).replace(',', '.')) == 0:
                                continue
                        except ValueError:
                            continue
                        
                        tiene_analisis_facturables = True
                        
                        if perf_c == '475' or codigo_limpio in codigos_hemograma:
                            if not hemograma_procesado_en_orden:
                                precio_final = 5.0 * valor_ub_os_actual
                                gran_total += precio_final
                                filas_vouchers.append({
                                    "Protocolo": o[10], "Paciente": o[2], "DNI": o[3],
                                    "Código": "475", "Práctica": "HEMOGRAMA COMPLETO",
                                    "U.B.": 5.0, "Precio ($)": f"$ {precio_final:,.2f}"
                                })
                                hemograma_procesado_en_orden = True
                        else:
                            ub_numerica = float(str(ub_f).replace(',', '.'))
                            precio_final = ub_numerica * valor_ub_os_actual
                            gran_total += precio_final
                            filas_vouchers.append({
                                "Protocolo": o[10], "Paciente": o[2], "DNI": o[3],
                                "Código": cod_i, "Práctica": sub_i.upper(),
                                "U.B.": ub_numerica, "Precio ($)": f"$ {precio_final:,.2f}"
                            })
                    
                    if tiene_analisis_facturables:
                        if incluye_acto == 1:
                            gran_total += valor_acto
                            filas_vouchers.append({
                                "Protocolo": o[10], "Paciente": o[2], "DNI": o[3],
                                "Código": "1", "Práctica": "ACTO BIOQUIMICO",
                                "U.B.": 6.0, "Precio ($)": f"$ {valor_acto:,.2f}"
                            })
                        if incluye_gbi == 1:
                            gran_total += valor_gbi
                            filas_vouchers.append({
                                "Protocolo": o[10], "Paciente": o[2], "DNI": o[3],
                                "Código": "1002", "Práctica": "GBI - GESTION BIOQUIMICA INTEGRAL",
                                "U.B.": 0.0, "Precio ($)": f"$ {valor_gbi:,.2f}"
                            })
                
                df_detalle = pd.DataFrame(filas_vouchers) if filas_vouchers else pd.DataFrame(columns=["Protocolo", "Paciente", "DNI", "Código", "Práctica", "U.B.", "Precio ($)"])
                html_tabla_detalle = df_detalle.to_html(index=False, classes='tabla-facturacion', border=1)

                st.html(f"""
                <div id="print-area">
                    <style>
                        .tabla-facturacion {{ width: 100%; border-collapse: collapse; font-family: Arial, sans-serif; margin-top: 15px; margin-bottom: 15px; }}
                        .tabla-facturacion th, .tabla-facturacion td {{ padding: 8px; text-align: left; border: 1px solid #ddd; color: black !important; }}
                        .tabla-facturacion th {{ background-color: #f2f2f2; font-weight: bold; }}
                        .btn-imprimir-html {{
                            background-color: #0066cc; color: white; border: none; padding: 10px 20px;
                            font-size: 16px; border-radius: 5px; cursor: pointer; width: 100%; margin-top: 10px;
                        }}
                        @media print {{
                            .btn-imprimir-html {{ display: none; }}
                        }}
                    </style>
                    <h3 style='text-align: center; color: black; margin-bottom:0;'>LIQUIDACIÓN DE OBRA SOCIAL: {dict_os_f[os_f_sel]}</h3>
                    <p style='text-align: center; color: #333; margin-top:5px; margin-bottom:20px;'>Período: {f_desde.strftime('%d/%m/%Y')} al {f_hasta.strftime('%d/%m/%Y')} | Ámbito: {ambito_f}</p>
                    {html_tabla_detalle}
                    <h3 style='color: black; margin-top: 20px;'>TOTAL COMPROBANTES: $ {gran_total:,.2f}</h3>
                    <button class="btn-imprimir-html" onclick="window.print()">🖨️ Imprimir Detalle por Pacientes</button>
                </div>
                """)

            # -----------------------------------------------------------------
            # OPCIÓN 2: RESUMEN CONSOLIDADO (AGRUPADO POR CÓDIGO)
            # -----------------------------------------------------------------
            elif t_vista == "2. Resumen Consolidado (Agrupado por Código)":
                mapa_consolidado = {}
                gran_total_consolidado = 0.0
                cant_actos = 0
                cant_gbis = 0

                for o in ordenes_filtradas:
                    items_o = obtener_items_para_cargar(o[0])
                    hemograma_procesado_en_orden = False
                    tiene_analisis_facturables = False
                    
                    for item in items_o:
                        perf_c = str(item[1]).strip() if item[1] is not None else ""
                        cod_i = str(item[2]).strip() if item[2] is not None else ""
                        sub_i = str(item[3]).strip() if item[3] is not None else ""
                        ub_f = item[11]
                        
                        val_particular = item[-1] if len(item) > 13 else 0
                        if val_particular in [1, '1', True, 'true', 'True']:
                            continue

                        codigo_limpio = cod_i.upper()

                        if codigo_limpio in codigos_no_facturables: 
                            continue
                        
                        try:
                            if ub_f is None or str(ub_f).strip() == "" or float(str(ub_f).replace(',', '.')) == 0:
                                continue
                        except ValueError:
                            continue
                            
                        tiene_analisis_facturables = True

                        if perf_c == '475' or codigo_limpio in codigos_hemograma:
                            if not hemograma_procesado_en_orden:
                                cod_resumen = "475"
                                nom_resumen = "HEMOGRAMA COMPLETO"
                                ub_resumen = 5.0
                                hemograma_procesado_en_orden = True
                            else:
                                continue
                        else:
                            cod_resumen = cod_i
                            nom_resumen = sub_i.upper()
                            ub_resumen = float(str(ub_f).replace(',', '.'))

                        if cod_resumen not in mapa_consolidado:
                            mapa_consolidado[cod_resumen] = {
                                "Código": cod_resumen, "Práctica": nom_resumen,
                                "U.B. Unit": ub_resumen, "Cantidad": 0, "Total U.B.": 0.0
                            }
                        
                        mapa_consolidado[cod_resumen]["Cantidad"] += 1
                        mapa_consolidado[cod_resumen]["Total U.B."] += ub_resumen

                    if tiene_analisis_facturables:
                        if incluye_acto == 1: cant_actos += 1
                        if incluye_gbi == 1: cant_gbis += 1

                filas_consolidadas = []
                for c_key, c_val in mapa_consolidado.items():
                    precio_acumulado = c_val["Total U.B."] * valor_ub_os_actual
                    gran_total_consolidado += precio_acumulado
                    filas_consolidadas.append({
                        "Código": c_val["Código"], "Práctica": c_val["Práctica"],
                        "U.B. Unit": c_val["U.B. Unit"], "Cantidad": c_val["Cantidad"],
                        "Total U.B.": c_val["Total U.B."], "Subtotal ($)": f"$ {precio_acumulado:,.2f}"
                    })

                if cant_actos > 0:
                    tot_acto_f = cant_actos * valor_acto
                    gran_total_consolidado += tot_acto_f
                    filas_consolidadas.append({
                        "Código": "1", "Práctica": "ACTO BIOQUIMICO", "U.B. Unit": 6.0,
                        "Cantidad": cant_actos, "Total U.B.": 6.0 * cant_actos, "Subtotal ($)": f"$ {tot_acto_f:,.2f}"
                    })
                if cant_gbis > 0:
                    tot_gbi_f = cant_gbis * valor_gbi
                    gran_total_consolidado += tot_gbi_f
                    filas_consolidadas.append({
                        "Código": "1002", "Práctica": "GBI - GESTION BIOQUIMICA INTEGRAL", "U.B. Unit": 0.0,
                        "Cantidad": cant_gbis, "Total U.B.": 0.0, "Subtotal ($)": f"$ {tot_gbi_f:,.2f}"
                    })

                df_consolidado = pd.DataFrame(filas_consolidadas) if filas_consolidadas else pd.DataFrame(columns=["Código", "Práctica", "U.B. Unit", "Cantidad", "Total U.B.", "Subtotal ($)"])
                html_tabla_consolidado = df_consolidado.to_html(index=False, classes='tabla-facturacion', border=1)

                st.html(f"""
                <div id="print-area">
                    <style>
                        .tabla-facturacion {{ width: 100%; border-collapse: collapse; font-family: Arial, sans-serif; margin-top: 15px; margin-bottom: 15px; }}
                        .tabla-facturacion th, .tabla-facturacion td {{ padding: 8px; text-align: left; border: 1px solid #ddd; color: black !important; }}
                        .tabla-facturacion th {{ background-color: #e6f2ff; font-weight: bold; }}
                        .btn-imprimir-html {{
                            background-color: #0066cc; color: white; border: none; padding: 10px 20px;
                            font-size: 16px; border-radius: 5px; cursor: pointer; width: 100%; margin-top: 10px;
                        }}
                        @media print {{
                            .btn-imprimir-html {{ display: none; }}
                        }}
                    </style>
                    <h3 style='text-align: center; color: black; margin-bottom:0;'>RESUMEN CONSOLIDADO DE LIQUIDACIÓN: {dict_os_f[os_f_sel]}</h3>
                    <p style='text-align: center; color: #333; margin-top:5px; margin-bottom:20px;'>Período: {f_desde.strftime('%d/%m/%Y')} al {f_hasta.strftime('%d/%m/%Y')} | Ámbito: {ambito_f}</p>
                    {html_tabla_consolidado}
                    <h3 style='color: black; margin-top: 20px;'>TOTAL GENERAL DE LIQUIDACIÓN: $ {gran_total_consolidado:,.2f}</h3>
                    <button class="btn-imprimir-html" onclick="window.print()">🖨️ Resumen Consolidado (Agrupado por Código)</button>
                </div>
                """)

# -----------------------------------------------------------------------------
# 💵 MÓDULO 2: FACTURACIÓN PARTICULARES (NUEVO)
# -----------------------------------------------------------------------------
elif menu == "💵 Facturación Particulares":
    st.header("💵 Liquidación y Facturación de Particulares")
    
    col1, col2 = st.columns(2)
    with col1:
        f_desde_p = st.date_input("Fecha Desde:", value=date(date.today().year, date.today().month, 1), key="part_fecha_desde")
    with col2:
        f_hasta_p = st.date_input("Fecha Hasta:", value=date.today(), key="part_fecha_hasta")

    todas_las_ordenes = buscar_ordenes_todas()
    filas_particulares = []
    gran_total_particular = 0.0

    codigos_no_facturables = ['C/H', 'CNOH', 'IA', 'FGE']
    codigos_hemograma = ['GR_01', 'HB_02', 'HT_03', 'VCM_04', 'HCM_05', 'CHCM_06', 'GB_07', 'NEU_08', 'EOS_09', 'BAS_10', 'LIN_11', 'MON_12', 'PLAQ_13']

    for o in todas_las_ordenes:
        estado_o = str(o[4]).strip().lower()
        os_en_bd = str(o[8]).strip().lower() if o[8] is not None else ""
        fecha_orden_str = str(o[1]).strip() if o[1] is not None else ""
        
        fecha_objeto = None
        for formato in ('%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y'):
            try:
                fecha_objeto = datetime.strptime(fecha_orden_str, formato).date()
                break
            except ValueError:
                continue
        
        if fecha_objeto is None or not (f_desde_p <= fecha_objeto <= f_hasta_p):
            continue

        if estado_o in ['validada', 'cerrada']:
            items_o = obtener_items_para_cargar(o[0])
            hemograma_procesado = False
            
            es_orden_particular = (os_en_bd == "particular")
            
            for item in items_o:
                perf_c = str(item[1]).strip() if item[1] is not None else ""
                cod_i = str(item[2]).strip() if item[2] is not None else ""
                sub_i = str(item[3]).strip() if item[3] is not None else ""
                ub_f = item[11]
                val_particular = item[-1] if len(item) > 13 else 0
                es_item_particular = val_particular in [1, '1', True, 'true', 'True']

                codigo_limpio = cod_i.upper()
                if codigo_limpio in codigos_no_facturables:
                    continue

                if es_orden_particular or es_item_particular:
                    if perf_c == '475' or codigo_limpio in codigos_hemograma:
                        if not hemograma_procesado:
                            precio_item = 5.0 * 1000.0  # Ajustar multiplicador según tu valor de UB Particular
                            gran_total_particular += precio_item
                            filas_particulares.append({
                                "Protocolo": o[10],
                                "Paciente": o[2],
                                "DNI": o[3],
                                "Origen": "Orden Particular" if es_orden_particular else "Ítem Modificado",
                                "Código": "475",
                                "Práctica": "HEMOGRAMA COMPLETO",
                                "Monto ($)": f"$ {precio_item:,.2f}"
                            })
                            hemograma_procesado = True
                    else:
                        try:
                            ub_num = float(str(ub_f).replace(',', '.')) if ub_f else 1.0
                        except ValueError:
                            ub_num = 1.0
                        
                        precio_item = ub_num * 1000.0  # Ajustar multiplicador según tu valor de UB Particular
                        gran_total_particular += precio_item
                        
                        filas_particulares.append({
                            "Protocolo": o[10],
                            "Paciente": o[2],
                            "DNI": o[3],
                            "Origen": "Orden Particular" if es_orden_particular else "Ítem Modificado",
                            "Código": cod_i,
                            "Práctica": sub_i.upper(),
                            "Monto ($)": f"$ {precio_item:,.2f}"
                        })

    if not filas_particulares:
        st.info("No se encontraron prácticas o ítems particulares en el período seleccionado.")
    else:
        st.success(f"📋 Se encontraron **{len(filas_particulares)}** ítems particulares para liquidar.")
        
        df_part = pd.DataFrame(filas_particulares)
        html_tabla_part = df_part.to_html(index=False, classes='tabla-facturacion', border=1)

        clave_cont_part = f"cont_fact_part_{f_desde_p}_{f_hasta_p}"
        
        with st.container(key=clave_cont_part):
            st.html(f"""
            <div id="print-area">
                <style>
                    .tabla-facturacion {{ width: 100%; border-collapse: collapse; font-family: Arial, sans-serif; margin-top: 15px; margin-bottom: 15px; }}
                    .tabla-facturacion th, .tabla-facturacion td {{ padding: 8px; text-align: left; border: 1px solid #ddd; color: black !important; }}
                    .tabla-facturacion th {{ background-color: #fff3cd; font-weight: bold; }}
                    .btn-imprimir-html {{
                        background-color: #d39e00; color: white; border: none; padding: 10px 20px;
                        font-size: 16px; border-radius: 5px; cursor: pointer; width: 100%; margin-top: 10px;
                    }}
                    @media print {{
                        .btn-imprimir-html {{ display: none; }}
                    }}
                </style>
                <h3 style='text-align: center; color: black; margin-bottom:0;'>LIQUIDACIÓN DE PACIENTES PARTICULARES</h3>
                <p style='text-align: center; color: #333; margin-top:5px; margin-bottom:20px;'>Período: {f_desde_p.strftime('%d/%m/%Y')} al {f_hasta_p.strftime('%d/%m/%Y')}</p>
                {html_tabla_part}
                <h3 style='color: black; margin-top: 20px;'>TOTAL PARTICULAR A COBRAR: $ {gran_total_particular:,.2f}</h3>
                <button class="btn-imprimir-html" onclick="window.print()">🖨️ Imprimir Liquidación Particulares</button>
            </div>
            """)
elif menu == "⚙️ Configuración de Análisis":
    st.header("⚙️ Panel de Gestión de Archivos de Configuración")
    t_det, t_perf, t_os, t_med, t_resp, t_firmas = st.tabs(["🔬 Determinaciones", "🧬 Perfiles (Combos)", "💵 Seguros (UB)", "👨‍⚕️ Médicos", "✍ Respuestas Predefinidas", "✍️ Logos y Firmas"])
    
    with t_det:
        st.subheader("Crear / Modificar Renglón de Análisis")
        if "det_state" not in st.session_state: 
            st.session_state.det_state = {"cod": "", "nom": "", "uni": "", "ref": "", "tit": "No", "ub_f": 0.0, "form": "", "es_edicion": False}
        
        with st.form("form_determinacion", clear_on_submit=True):
            col1, col2, col3, col3_ub = st.columns([2,4,2,2])
            with col1: c_i = st.text_input("Código Ítem Único", value=st.session_state.det_state["cod"])
            with col2: s_n = st.text_input("Nombre de Determinación", value=st.session_state.det_state["nom"])
            with col3: es_t = st.selectbox("¿Es solo un Título?", ["No", "Si"], index=0 if st.session_state.det_state["tit"]=="No" else 1)
            with col3_ub: ub_fac_input = st.number_input("U.B. Facturación:", min_value=0.0, value=st.session_state.det_state["ub_f"])
            
            col4, col_formula, col5 = st.columns([2,4,4])
            with col4: u_m = st.text_input("Unidad", value=st.session_state.det_state["uni"])
            with col_formula: f_m = st.text_input("Fórmula Matemática (Opcional)", value=st.session_state.det_state["form"], placeholder="Ej: (HT_02 * 10) / GR_01")
            with col5: r_f = st.text_area("Límites de Referencia", value=st.session_state.det_state["ref"])
            
            if st.form_submit_button("💾 Guardar Renglón"):
                if c_i and s_n:
                    conn = conectar_db(); cur = conn.cursor()
                    es_edicion_actual = st.session_state.det_state.get("es_edicion", False)
                    if not es_edicion_actual:
                        cur.execute("SELECT 1 FROM determinaciones WHERE codigo_item = %s", (c_i,))
                        existe = cur.fetchone()
                        if existe:
                            st.error(f"⚠️ El código **'{c_i}'** ya existe en la base de datos. Utiliza otro código o edita el existente desde la lista.")
                            conn.close()
                            st.stop()

                    try: cur.execute("ALTER TABLE determinaciones ADD COLUMN formula_calculo TEXT")
                    except: pass 

                    cur.execute("""
                        INSERT OR REPLACE INTO determinaciones 
                        (codigo_item, sub_item, text_unidad, valores_referencia, es_titulo, ub_facturacion, formula_calculo) 
                        VALUES (%s, %s, %s, %s, %s, $s, %s)
                    """, (c_i, s_n, u_m, r_f, es_t, ub_fac_input, f_m))
                    
                    conn.commit(); conn.close()
                    st.session_state.det_state = {"cod": "", "nom": "", "uni": "", "ref": "", "tit": "No", "ub_f": 0.0, "form": "", "es_edicion": False}
                    st.success("Guardado correctamente."); st.rerun()
                else:
                    st.warning("⚠️ Por favor completa el Código Ítem y el Nombre.")
                    
        for fila_det in listar_todas_determinaciones():
            cod = fila_det[0]
            nom = fila_det[1]
            uni = fila_det[2]
            ref = fila_det[3]
            tit = fila_det[4]
            ub_f = fila_det[5]
            form = fila_det[6] if len(fila_det) > 6 else ""
            
            col_a, col_b, col_c, col_d = st.columns([4, 4, 1, 1])
            with col_a: st.write(f"**`{cod}`** — {nom}")
            with col_c:
                if st.button("✏️", key=f"ed_det_{cod}"): 
                    st.session_state.det_state = {"cod": cod, "nom": nom, "uni": uni, "ref": ref, "tit": tit, "ub_f": ub_f, "form": form, "es_edicion": True}
                    st.rerun()
            with col_d:
                if st.button("🗑️", key=f"del_det_{cod}"): 
                    conn = conectar_db(); cur = conn.cursor()
                    cur.execute("DELETE FROM determinaciones WHERE codigo_item = ?", (cod,))
                    conn.commit(); conn.close(); st.rerun() 
         
    with t_perf:
        st.subheader("🧬 Gestión de Combos / Perfiles de Análisis")
        
        if "perfil_edit_state" not in st.session_state:
            st.session_state.perfil_edit_state = {"codigo": "", "nombre": "", "modo_edicion": False}
        
        label_form = "✏️ Modificar Código de Perfil Base" if st.session_state.perfil_edit_state["modo_edicion"] else "➕ Crear Nuevo Código Base de Perfil"
        
        with st.expander(label_form, expanded=st.session_state.perfil_edit_state["modo_edicion"]):
            with st.form("form_perfil_base"):
                cod_p_input = st.text_input("Código de Perfil:", value=st.session_state.perfil_edit_state["codigo"], disabled=st.session_state.perfil_edit_state["modo_edicion"])
                nom_p_input = st.text_input("Nombre de Perfil:", value=st.session_state.perfil_edit_state["nombre"])
                
                ub_p_guardada = st.session_state.perfil_edit_state.get("ub_f", 0.0)
                ub_p_input = st.number_input("U.B. de Facturación del Perfil:", min_value=0.0, value=ub_p_guardada, step=0.5)
                
                c_btn_p1, c_btn_p2 = st.columns(2)
                with c_btn_p1:
                    submit_p = st.form_submit_button("💾 Guardar Cambios" if st.session_state.perfil_edit_state["modo_edicion"] else "💾 Crear Perfil")
                with c_btn_p2:
                    cancelar_p = st.form_submit_button("Cancelar")
                    
                if submit_p and cod_p_input and nom_p_input:
                    conn = conectar_db(); cur = conn.cursor()
                    cur.execute("INSERT OR REPLACE INTO nomenclador (codigo, nombre, unidades_bioquimicas) VALUES (?, ?, ?)", (cod_p_input, nom_p_input.upper(), ub_p_input))
                    conn.commit(); conn.close()
                    st.session_state.perfil_edit_state = {"codigo": "", "nombre": "", "modo_edicion": False, "ub_f": 0.0}
                    st.success("Perfil Base guardado con éxito."); st.rerun()
                    
                if cancelar_p:
                    st.session_state.perfil_edit_state = {"codigo": "", "nombre": "", "modo_edicion": False, "ub_f": 0.0}; st.rerun()

        st.markdown("#### Lista de Perfiles Base Registrados:")
        perfiles_lista = listar_nomenclador()
        for i, (p_cod, p_nom, _) in enumerate(perfiles_lista):
            col_p_info, col_p_ed, col_p_del = st.columns([7, 1, 1])
            with col_p_info: st.write(f"• **`{p_cod}`** — {p_nom}")
            with col_p_ed:
                # Añadimos _{i} al key para garantizar que jamás se repita
                if st.button("✏️", key=f"ed_perf_base_{p_cod}_{i}"):
                    try:
                        p_ub = p[2] if len(p) > 2 else 0.0
                    except NameError:
                        p_ub = 0.0 
                    
                    st.session_state.perfil_edit_state = {
                        "codigo": p_cod, 
                        "nombre": p_nom, 
                        "ub_f": float(p_ub) if p_ub is not None else 0.0,
                        "modo_edicion": True
                    }
                    st.rerun()
                    
            with col_p_del:
                # Aquí faltaba agregar el _{i} en la clave
                if st.button("🗑️", key=f"del_perf_base_{p_cod}_{i}"):
                    conn = conectar_db(); cur = conn.cursor()
                    cur.execute("DELETE FROM nomenclador WHERE codigo = ?", (p_cod,))
                    cur.execute("DELETE FROM perfil_detalles WHERE codigo_perfil = ?", (p_cod,))
                    conn.commit(); conn.close(); st.success("Perfil eliminado."); st.rerun()
        
        st.markdown("---")
        st.subheader("🔗 Vincular Determinaciones a un Perfil")
        if perfiles_lista:
            dict_p = {p[0]: f"[{p[0]}] {p[1]}" for p in perfiles_lista}
            p_sel = st.selectbox("Seleccionar Perfil de Trabajo:", options=dict_p.keys(), format_func=lambda x: dict_p[x])
            todas_dets = listar_todas_determinaciones(); dict_dets = {d[0]: f"({d[0]}) {d[1]}" for d in todas_dets}
            if dict_dets:
                if "modo_edicion_enlace" not in st.session_state:
                    st.session_state.modo_edicion_enlace = False
                    st.session_state.enlace_id_a_editar = None

                tecnica_defecto = ""
                negrita_defecto = "No"
                orden_defecto = 1
                det_index_defecto = 0

                if st.session_state.modo_edicion_enlace:
                    conn = conectar_db(); cursor = conn.cursor()
                    cursor.execute("SELECT codigo_item, metodo, en_negrita, orden_visual FROM perfil_detalles WHERE id = ?", (st.session_state.enlace_id_a_editar,))
                    reg = cursor.fetchone()
                    cursor.close(); conn.close()
                    
                    if reg:
                        cod_item_viejo, m_txt_viejo, neg_viejo, ord_viejo = reg
                        tecnica_defecto = str(m_txt_viejo) if m_txt_viejo else ""
                        negrita_defecto = "Si" if str(neg_viejo).strip().lower() in ["si", "sí"] else "No"
                        try: orden_defecto = int(ord_viejo)
                        except: orden_defecto = 1
                        
                        lista_claves = list(dict_dets.keys())
                        if cod_item_viejo in lista_claves:
                            det_index_defecto = lista_claves.index(cod_item_viejo)
                    
                    st.warning("📝 **Modo Edición Activo:** Modifique los campos del análisis seleccionado abajo.")

                with st.container(border=True):
                    det_sel = st.selectbox(
                        "Elegir Análisis a incorporar:", 
                        options=dict_dets.keys(), 
                        format_func=lambda x: dict_dets[x],
                        index=det_index_defecto,
                        disabled=st.session_state.modo_edicion_enlace
                    )
                    
                    col_met, col_neg, col_ord = st.columns([4, 2, 2])
                    with col_met: 
                        m_text = st.text_input("Método / Técnica", value=tecnica_defecto, key="txt_metodo_din")
                    with col_neg: 
                        idx_neg = 1 if negrita_defecto == "Si" else 0
                        neg_sel = st.selectbox("¿Negrita en Informe?", ["No", "Si"], index=idx_neg, key="sel_negrita_din")
                    with col_ord: 
                        ord_v = st.number_input("Orden de aparición", min_value=1, value=orden_defecto, key="num_orden_din")
                    
                    if st.session_state.modo_edicion_enlace:
                        col_up1, col_up2 = st.columns(2)
                        with col_up1:
                            if st.button("🔄 Actualizar Vinculación", type="primary", use_container_width=True):
                                conn = conectar_db(); cursor = conn.cursor()
                                cursor.execute("""
                                    UPDATE perfil_detalles 
                                    SET orden_visual = ?, metodo = ?, en_negrita = ? 
                                    WHERE id = ?
                                """, (ord_v, m_text, neg_sel, st.session_state.enlace_id_a_editar))
                                conn.commit(); conn.close()
                                
                                st.session_state.modo_edicion_enlace = False
                                st.session_state.enlace_id_a_editar = None
                                st.toast("¡Vinculación actualizada!", icon="🔄")
                                st.rerun()
                        with col_up2:
                            if st.button("❌ Cancelar Edición", use_container_width=True):
                                st.session_state.modo_edicion_enlace = False
                                st.session_state.enlace_id_a_editar = None
                                st.rerun()
                    else:
                        if st.button("💾 Enlazar Práctica", type="primary", use_container_width=True):
                            conn = conectar_db(); cursor = conn.cursor()
                            cursor.execute("INSERT OR REPLACE INTO perfil_detalles (codigo_perfil, codigo_item, formula, orden_visual, metodo, en_negrita) VALUES (?, ?, '', ?, ?, ?)", (p_sel, det_sel, ord_v, m_text, neg_sel))
                            conn.commit(); conn.close()
                            st.rerun()

                actuales = obtener_sub_items_de_practica(p_sel)
                for v_id, c_i, s_n, _, _, _, _, o, met, neg, _ in actuales:
                    col_x, col_z = st.columns([8, 1])
                    
                    with col_x: 
                        st.write(f"**Posición {o}** | `{c_i}` — **{s_n}** " + (f"*(Técnica: {met})*" if met else ""))
                    
                    with col_z:
                        col_edit, col_del = st.columns(2)
                        
                        with col_edit:
                            if st.button("✏️", key=f"edit_v_{v_id}", help="Editar esta vinculación"):
                                st.session_state.enlace_id_a_editar = v_id
                                st.session_state.modo_edicion_enlace = True
                                st.rerun()
                                
                        with col_del:
                            if st.button("❌", key=f"del_v_{v_id}", help="Eliminar esta vinculación"): 
                                conn = conectar_db()
                                cur = conn.cursor()
                                cur.execute("DELETE FROM perfil_detalles WHERE id = ?", (v_id,))
                                conn.commit()
                                conn.close()
                                st.rerun()

    with t_os:
        st.subheader("💵 Registro y Ajuste de Obras Sociales (UB)")
        
        if "os_state" not in st.session_state: 
            st.session_state.os_state = {
                "id": None, "nom": "", "val": 1260.0,
                "incluye_acto": 0, "valor_acto": 0.0,
                "incluye_gbi": 0, "valor_gbi": 0.0
            }
        else:
            if "incluye_acto" not in st.session_state.os_state: st.session_state.os_state["incluye_acto"] = 0
            if "valor_acto" not in st.session_state.os_state: st.session_state.os_state["valor_acto"] = 0.0
            if "incluye_gbi" not in st.session_state.os_state: st.session_state.os_state["incluye_gbi"] = 0
            if "valor_gbi" not in st.session_state.os_state: st.session_state.os_state["valor_gbi"] = 0.0
            
        with st.form("form_alta_os", clear_on_submit=True):
            col_o1, col_o2 = st.columns(2)
            with col_o1: 
                name_os = st.text_input("Nombre:", value=st.session_state.os_state["nom"])
            with col_o2: 
                val_ub = st.number_input("Valor UB ($):", min_value=0.0, value=st.session_state.os_state["val"])
            
            st.markdown("---")
            st.markdown("##### 📑 Módulos Automáticos por Protocolo")
            col_mod1, col_mod2 = st.columns(2)
            
            with col_mod1:
                st.markdown("**Acto Bioquímico (Código 1)**")
                inc_acto = st.checkbox("Incluir Acto Bioquímico (6 U.B.)", value=bool(st.session_state.os_state["incluye_acto"]), key="chk_os_acto")
                val_acto = st.number_input("Precio en $ del Acto Bioquímico:", min_value=0.0, value=float(st.session_state.os_state["valor_acto"]), key="val_os_acto")
                
            with col_mod2:
                st.markdown("**Gestión Bioquímica Integral (Código 1002)**")
                inc_gbi = st.checkbox("Incluir GBI en Liquidaciones", value=bool(st.session_state.os_state["incluye_gbi"]), key="chk_os_gbi")
                val_gbi = st.number_input("Precio en $ del GBI:", min_value=0.0, value=float(st.session_state.os_state["valor_gbi"]), key="val_os_gbi")
            
            submit_os = st.form_submit_button("💾 Guardar Obra Social")
            
        if submit_os and name_os:
            val_inc_acto = 1 if inc_acto else 0
            val_inc_gbi = 1 if inc_gbi else 0
            
            conn = conectar_db(); cur = conn.cursor()
            if st.session_state.os_state["id"]: 
                cur.execute("""
                    UPDATE obras_sociales 
                    SET nombre = ?, valor_ub = ?, incluye_acto = ?, valor_acto = ?, incluye_gbi = ?, valor_gbi = ? 
                    WHERE id = ?
                """, (name_os.upper(), val_ub, val_inc_acto, val_acto, val_inc_gbi, val_gbi, st.session_state.os_state["id"]))
            else: 
                cur.execute("""
                    INSERT OR REPLACE INTO obras_sociales 
                    (nombre, valor_ub, incluye_acto, valor_acto, incluye_gbi, valor_gbi) 
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (name_os.upper(), val_ub, val_inc_acto, val_acto, val_inc_gbi, val_gbi))
            
            conn.commit(); conn.close()
            
            st.session_state.os_state = {
                "id": None, "nom": "", "val": 1260.0,
                "incluye_acto": 0, "valor_acto": 0.0,
                "incluye_gbi": 0, "valor_gbi": 0.0
            }
            st.rerun()
                    
        st.markdown("---")
        st.markdown("##### Obras Sociales Registradas")
        for fila_os in listar_obras_sociales():
            os_id = fila_os[0]
            os_nom = fila_os[1]
            os_val = fila_os[2]
            os_inc_acto = fila_os[3] if len(fila_os) > 3 else 0
            os_val_acto = fila_os[4] if len(fila_os) > 4 else 0.0
            os_inc_gbi = fila_os[5] if len(fila_os) > 5 else 0
            os_val_gbi = fila_os[6] if len(fila_os) > 6 else 0.0
            
            col_no, col_va, col_ed, col_ba = st.columns([5, 2, 1, 1])
            with col_no: 
                info_modulos = ""
                if os_inc_acto or os_inc_gbi:
                    info_modulos = " ➔ 📝 [Módulos Activos]"
                st.write(f"• **{os_nom}** — ${os_val}{info_modulos}")
            with col_va:
                st.write("")
            with col_ed:
                if st.button("✏️", key=f"ed_os_{os_id}"): 
                    st.session_state.os_state = {
                        "id": os_id, "nom": os_nom, "val": os_val,
                        "incluye_acto": os_inc_acto, "valor_acto": os_val_acto,
                        "incluye_gbi": os_inc_gbi, "valor_gbi": os_val_gbi
                    }
                    st.rerun()
            with col_ba:
                if st.button("🗑️", key=f"del_os_{os_id}"): 
                    conn = conectar_db(); cur = conn.cursor()
                    cur.execute("DELETE FROM obras_sociales WHERE id = ?", (os_id,))
                    conn.commit(); conn.close()
                    st.rerun()
        with t_med:
            st.subheader("👨‍⚕️ Gestión de Médicos Solicitantes")
            with st.form("form_gestion_medicos_registro_unico_v2"):

                nuevo_nom = st.text_input("Nombre y Apellido del Dr./a:")
                nuevo_mat = st.text_input("Matrícula Profesional (Opcional):")
                btn_crear = st.form_submit_button("💾 Agregar Nuevo Médico")
                
                if btn_crear:
                    if nuevo_nom:
                        try:
                            with engine.begin() as connection:
                                connection.execute(
                                    text("INSERT INTO medicos (nombre, matricula) VALUES (:nombre, :matricula)"),
                                    {"nombre": nuevo_nom.upper(), "matricula": nuevo_mat}
                                )
                            st.success("¡Médico agregado con éxito!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error al guardar: {e}")
                    else:
                        st.warning("⚠️ Debes ingresar el nombre del médico.")
                
            st.markdown("---")
            st.markdown("##### Listado de Médicos Registrados")
            
            try:
                query = "SELECT id, nombre, matricula FROM medicos ORDER BY nombre ASC"
                medicos_df = pd.read_sql(query, engine)
                medicos_db = medicos_df.values.tolist()
            except Exception as e:
                medicos_db = []
                
            for i, (m_id, m_nombre, m_matricula) in enumerate(medicos_db):
                col_m1, col_m2 = st.columns([8, 2])
                with col_m1:
                    mat_txt = f" (Mat: {m_matricula})" if m_matricula else ""
                    st.write(f"• **{m_nombre}**{mat_txt}")
                with col_m2:
                    if st.button("🗑️ Eliminar", key=f"btn_del_med_seguro_{m_id}_{i}"):
                        try:
                            with engine.begin() as connection:
                                connection.execute(text("DELETE FROM medicos WHERE id = :id"), {"id": m_id})
                            st.success("Médico eliminado.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error al eliminar: {e}")
    with t_firmas:
        st.subheader("🖼️ Gestión de Identidad Visual (Logos y Firmas)")
        
        cfg_actual = obtener_configuracion_general()
        with st.form("form_leyenda_col"):
            st.markdown("##### Textos del Informe:")
            nueva_leyenda = st.text_area("Leyenda Colegio / Matrícula de Autorización (Pie de página):", value=cfg_actual[8])
            if st.form_submit_button("⚙️ Actualizar Texto"):
                conn = conectar_db(); cur = conn.cursor(); cur.execute("UPDATE configuracion_general SET leyenda_colegio = ? WHERE id = 1", (nueva_leyenda,)); conn.commit(); conn.close(); st.success("Texto pie de página actualizado correctamente."); st.rerun()
        
        st.markdown("---")
        
        st.markdown("##### 🏢 Logo del Laboratorio")
        logo_vista = obtener_logo_base64()
        if logo_vista: 
            st.image(logo_vista, caption="Logo Actual Cargado en Sistema", width=250)
        uploaded_logo = st.file_uploader("Seleccionar imagen para el Logo institucional (Recomendado PNG transparente):", type=["png", "jpg", "jpeg"], key="upload_logo_institucional")
        if uploaded_logo is not None:
            if st.button("💾 Guardar y Aplicar Logo"):
                conn = conectar_db(); cur = conn.cursor()
                cur.execute("UPDATE configuracion_general SET logo_blob = ? WHERE id = 1", (sqlite3.Binary(uploaded_logo.getvalue()),))
                conn.commit(); conn.close(); st.success("Logo actualizado exitosamente."); st.rerun()
                
        st.markdown("---")
        
        st.markdown("##### ✍️ Firmas Digitales de Profesionales")
        bioquimicos_lista = listar_bioquimicos()
        dict_bq_f = {b[0]: f"{b[1]} (M.P. {b[2]} - {b[3]})" for b in bioquimicos_lista}
        
        bq_firma_sel = st.selectbox("Seleccione el profesional para asignarle/cambiarle la firma digital:", options=dict_bq_f.keys(), format_func=lambda x: dict_bq_f[x])
        
        firma_vista = obtener_firma_base64(bq_firma_sel)
        # Verificamos que firma_vista tenga contenido válido y no esté vacía o nula
        if firma_vista:
            try:
                st.image(firma_vista, caption=f"Firma actual de: {dict_bq_f.get(bq_firma_sel, '')}", width=200)
            except Exception:
                st.info("No se pudo cargar la imagen de la firma o el archivo no existe.")
        else:
            st.info("Este bioquímico aún no tiene una firma registrada.")
            
        uploaded_firma = st.file_uploader(f"Seleccionar imagen de la firma escaneada (Recomendado trazo negro con fondo transparente PNG):", type=["png", "jpg", "jpeg"], key="upload_firma_profesional")
        if uploaded_firma is not None:
            if st.button("💾 Guardar y Vincular Firma"):
                conn = conectar_db(); cur = conn.cursor()
                cur.execute("UPDATE bioquimicos SET firma_blob = ? WHERE id = ?", (sqlite3.Binary(uploaded_firma.getvalue()), bq_firma_sel))
                conn.commit(); conn.close(); st.success("Firma vinculada de manera exitosa."); st.rerun()
elif menu == "📊 Estadísticas e Historial":
    import sqlite3
    import pandas as pd
    st.header("📊 Estadísticas, Historial y Planillas de Trabajo")
    
    DB_PATH = "laboratorio.bd"

    # --- PESTAÑAS DEL MÓDULO ---
    tab_dash, tab_historial, tab_planillas = st.tabs([
        "📈 Volumen de Órdenes", 
        "🧬 Ficha Histórica del Paciente", 
        "📋 Planillas de Trabajo Impresibles"
    ])

    # =================================================================
    # 1️⃣ PESTAÑA: VOLUMEN DE ÓRDENES (DASHBOARD) - PARSEO DE FECHAS INTELIGENTE
    # =================================================================
    with tab_dash:
        st.subheader("Auditoría de Volumen Mensual")
        try:
            conn = conectar_db()
            cur = conn.cursor()
            
            cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tablas_existentes = [t[0] for t in cur.fetchall()]
            tabla_real_ordenes = next((t for t in tablas_existentes if t in ['ordenes', 'protocolos', 'protocolo', 'orden', 'items_orden']), None)
            
            if tabla_real_ordenes:
                # 1. Buscamos el nombre exacto de la columna de fecha
                cur.execute(f"PRAGMA table_info({tabla_real_ordenes})")
                columnas = [c[1] for c in cur.fetchall()]
                col_fecha = next((c for c in columnas if c in ['fecha', 'fecha_orden', 'f_orden', 'fecha_registro']), None)
                
                if col_fecha:
                    # Traemos todas las filas de esa columna para procesarlas con Python
                    query = f"SELECT {col_fecha} FROM {tabla_real_ordenes}"
                    df_fechas = pd.read_sql_query(query, conn)
                    conn.close()
                    
                    if not df_fechas.empty:
                        # Convertimos a formato fecha de manera flexible (detecta DD/MM/AAAA o AAAA-MM-DD)
                        df_fechas['fecha_limpia'] = pd.to_datetime(df_fechas[col_fecha], errors='coerce', dayfirst=True)
                        
                        # Creamos la columna Año-Mes
                        df_fechas['Mes'] = df_fechas['fecha_limpia'].dt.strftime('%Y-%m')
                        
                        # Si alguna fecha no se pudo parsear, le asignamos el mes actual para no perder el dato
                        df_fechas['Mes'] = df_fechas['Mes'].fillna(date.today().strftime('%Y-%m'))
                        
                        # Agrupamos y contamos
                        df_final = df_fechas.groupby('Mes').size().reset_index(name='Total Órdenes')
                        df_final = df_final.sort_values(by="Mes")
                        
                        # Dibujamos el gráfico y la tabla
                        st.bar_chart(data=df_final, x="Mes", y="Total Órdenes", use_container_width=True)
                        st.dataframe(df_final, use_container_width=True, hide_index=True)
                    else:
                        st.info("No hay registros de fechas en la tabla para computar estadísticas.")
                else:
                    conn.close()
                    st.error(f"❌ No se encontró la columna de fecha en la tabla '{tabla_real_ordenes}'. Columnas existentes: {columnas}")
            else:
                conn.close()
                st.error(f"❌ No se encontró la tabla de órdenes.")
        except Exception as e:
            st.error(f"Error al cargar el dashboard: {e}")

    # =================================================================
    # 2️⃣ PESTAÑA: FICHA HISTÓRICA DEL PACIENTE - DETECCIÓN DE COLUMNAS TOTAL
    # =================================================================
    with tab_historial:
        st.subheader("Evolución Temporal de Resultados")
        dni_historial = st.text_input("Ingrese el DNI del paciente para consultar historial:", key="dni_hist").strip()
        
        if dni_historial:
            try:
                conn = conectar_db()
                cur = conn.cursor()
                
                # 1. Buscamos datos del paciente
                cur.execute("SELECT id, nombre FROM pacientes WHERE dni = ?", (dni_historial,))
                pac = cur.fetchone()
                
                if pac:
                    pac_id, pac_nom = pac
                    st.markdown(f"🔬 **Paciente:** {pac_nom} (DNI: {dni_historial})")
                    
                    # 2. Detectamos columnas de 'ordenes'
                    cur.execute("PRAGMA table_info(ordenes)")
                    cols_ordenes = [c[1] for c in cur.fetchall()]
                    col_protocolo = next((c for c in cols_ordenes if c in ['protocolo', 'nro_protocolo', 'numero', 'id']), 'id')
                    col_pac_id = next((c for c in cols_ordenes if c in ['paciente_id', 'id_paciente', 'dni']), 'paciente_id')
                    
                    # 3. Detectamos columnas de 'resultados_items'
                    cur.execute("PRAGMA table_info(resultados_items)")
                    cols_items = [c[1] for c in cur.fetchall()]
                    
                    # Buscamos los mejores nombres para Código, Práctica y Resultado
                    col_codigo = next((c for c in cols_items if c in ['codigo', 'codigo_item', 'determinacion_id', 'codigo_practica', 'id_determinacion']), None)
                    col_practica = next((c for c in cols_items if c in ['practica', 'nombre', 'determinacion', 'descripcion', 'analisis']), None)
                    col_resultado = next((c for c in cols_items if c in ['resultado', 'valor', 'resultado_valor']), None)
                    col_ord_id = next((c for c in cols_items if c in ['orden_id', 'id_orden', 'protocolo_id']), 'orden_id')
                    
                    # Si no encuentra alguna columna clave, usamos la primera disponible para que no rompa
                    if not col_codigo: col_codigo = cols_items[0]
                    if not col_practica: col_practica = cols_items[1] if len(cols_items) > 1 else cols_items[0]
                    if not col_resultado: col_resultado = cols_items[2] if len(cols_items) > 2 else cols_items[0]
                    
                    # 4. Armamos la consulta dinámica con los nombres reales descubiertos
                    query_hist = f"""
                        SELECT o.fecha as Fecha, o.{col_protocolo} as Protocolo, 
                               i.{col_codigo} as Código, i.{col_practica} as Práctica, i.{col_resultado} as Resultado
                        FROM ordenes o
                        JOIN resultados_items i ON o.id = i.{col_ord_id}
                        WHERE o.{col_pac_id} = ?
                        ORDER BY o.fecha DESC
                    """
                    
                    if col_pac_id == 'dni':
                        df_hist = pd.read_sql_query(query_hist, conn, params=(dni_historial,))
                    else:
                        df_hist = pd.read_sql_query(query_hist, conn, params=(pac_id,))
                    
                    conn.close()
                    
                    if not df_hist.empty:
                        # Filtro interactivo por determinación
                        practicas_disponibles = sorted(df_hist["Práctica"].dropna().unique())
                        filtro_practica = st.multiselect("Filtrar por determinación específica para ver evolución:", options=practicas_disponibles)
                        
                        if filtro_practica:
                            df_hist = df_hist[df_hist["Práctica"].isin(filtro_practica)]
                            
                        st.dataframe(df_hist, use_container_width=True, hide_index=True)
                    else:
                        st.info("El paciente está registrado pero no posee análisis cargados con resultados todavía.")
                else:
                    conn.close()
                    st.warning("No se encontró ningún paciente registrado con ese DNI.")
            except Exception as e:
                st.error(f"Error al consultar el historial médico: {e}")

    # =================================================================
    # 3️⃣ PESTAÑA: PLANILLAS DE TRABAJO IMPRESIBLES - ¡CORREGIDA CON JOIN!
    # =================================================================
    with tab_planillas:
        st.subheader("Configuración y Generación de Planillas Diarias")
        
        # Guardamos las plantillas de trabajo en tu base de datos real
        try:
            conn = conectar_db()
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS plantillas_planillas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nombre TEXT UNIQUE,
                    codigos TEXT
                )
            """)
            conn.commit()
            conn.close()
        except Exception:
            pass

        modo_planilla = st.radio("Acción:", ["🖨️ Generar e Imprimir Planilla del Día", "⚙️ Crear / Editar Plantilla de Códigos"], horizontal=True)
        st.markdown("---")

        if modo_planilla == "⚙️ Crear / Editar Plantilla de Códigos":
            st.markdown("### Configurar Grupos de Determinaciones")
            nombre_plantilla = st.text_input("Nombre de la Planilla (Ej: Hematología, Química, Orinas):").strip().upper()
            codigos_plantilla = st.text_area("Códigos de análisis incluidos (separados por coma. Ej: 475, pt, 764, 174):").strip()
            
            if st.button("💾 Guardar Configuración de Plantilla", use_container_width=True):
                if not nombre_plantilla or not codigos_plantilla:
                    st.error("Por favor complete el nombre y añada al menos un código.")
                else:
                    try:
                        conn = conectar_db()
                        cur = conn.cursor()
                        cur.execute("""
                            INSERT INTO plantillas_planillas (nombre, codigos) VALUES (?, ?)
                            ON CONFLICT(nombre) DO UPDATE SET codigos = excluded.codigos
                        """, (nombre_plantilla, codigos_plantilla))
                        conn.commit()
                        conn.close()
                        st.success(f"¡Plantilla '{nombre_plantilla}' guardada con éxito!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error al guardar plantilla: {e}")

        elif modo_planilla == "🖨️ Generar e Imprimir Planilla del Día":
            col_p1, col_p2 = st.columns(2)
            with col_p1:
                from datetime import date
                fecha_planilla = st.date_input("Fecha de Trabajo:", value=date.today())
            with col_p2:
                try:
                    conn = conectar_db()
                    cur = conn.cursor()
                    cur.execute("SELECT nombre, codigos FROM plantillas_planillas ORDER BY nombre")
                    opciones_plantillas = cur.fetchall()
                    conn.close()
                except Exception:
                    opciones_plantillas = []
                
                dict_plantillas = {p[0]: p[1] for p in opciones_plantillas} if opciones_plantillas else {}
                planilla_sel = st.selectbox("Seleccione la Planilla a generar:", options=list(dict_plantillas.keys()))

            if planilla_sel:
                codigos_string = dict_plantillas[planilla_sel]
                lista_codigos_buscar = [c.strip().upper() for c in codigos_string.split(",") if c.strip()]
                
                if lista_codigos_buscar:
                    try:
                        conn = conectar_db()
                        cur = conn.cursor()
                        
                        # 1. Escaneamos la tabla 'determinaciones' para saber si usa 'descripcion', 'nombre' o 'practica'
                        try:
                            cur.execute("PRAGMA table_info(determinaciones)")
                            cols_det = [c[1] for c in cur.fetchall()]
                            col_det_nombre = next((c for c in cols_det if c in ['sub_item', 'descripcion', 'nombre', 'practica']), cols_det[1] if len(cols_det) > 1 else cols_det[0])
                            col_det_codigo = next((c for c in cols_det if c in ['codigo', 'id', 'codigo_practica', 'determinacion_id']), cols_det[0])
                        except Exception:
                            col_det_nombre = 'nombre'
                            col_det_codigo = 'codigo'
                        
                        # 2. Escaneamos 'resultados_items' para el código
                        cur.execute("PRAGMA table_info(resultados_items)")
                        cols_items = [c[1] for c in cur.fetchall()]
                        col_items_codigo = next((c for c in cols_items if c in ['codigo_item', 'codigo', 'determinacion_id']), 'codigo_item')

                        # 3. Armamos la Query Inteligente con Plan B incorporado
                        f_str1 = fecha_planilla.strftime('%Y-%m-%d')
                        f_str2 = fecha_planilla.strftime('%d/%m/%Y')
                        parametros = [f_str1, f_str2] + lista_codigos_buscar
                        comas = ','.join(['?'] * len(lista_codigos_buscar))

                        try:
                            query_planilla = f"""
                                SELECT o.id as [N° Protocolo], 
                                       p.nombre as [Paciente (Apellido, Nombre)], 
                                       i.{col_items_codigo} as [Código], 
                                       d.{col_det_nombre} as [Práctica]
                                FROM ordenes o
                                JOIN pacientes p ON o.paciente_id = p.id
                                JOIN resultados_items i ON o.id = i.orden_id
                                LEFT JOIN determinaciones d ON UPPER(i.{col_items_codigo}) = UPPER(d.{col_det_codigo})
                                WHERE (o.fecha = ? OR o.fecha = ?) AND UPPER(i.{col_items_codigo}) IN ({comas})
                                ORDER BY CAST(o.id AS INTEGER) ASC, p.nombre ASC
                            """
                            df_resultado_p = pd.read_sql_query(query_planilla, conn, params=parametros)
                        
                        except Exception:
                            # 🛡️ PLAN B: Si el JOIN falla por nombres de columnas, usa el código puro
                            query_planilla_fallback = f"""
                                SELECT o.id as [N° Protocolo], 
                                       p.nombre as [Paciente (Apellido, Nombre)], 
                                       i.{col_items_codigo} as [Código], 
                                       i.{col_items_codigo} as [Práctica]
                                FROM ordenes o
                                JOIN pacientes p ON o.paciente_id = p.id
                                JOIN resultados_items i ON o.id = i.orden_id
                                WHERE (o.fecha = ? OR o.fecha = ?) AND UPPER(i.{col_items_codigo}) IN ({comas})
                                ORDER BY CAST(o.id AS INTEGER) ASC, p.nombre ASC
                            """
                            df_resultado_p = pd.read_sql_query(query_planilla_fallback, conn, params=parametros)
                        
                        conn.close()
                        
                        if not df_resultado_p.empty:
                            st.success(f"📋 Se encontraron **{len(df_resultado_p)}** registros para la planilla de **{planilla_sel}**.")
                            
                            html_planilla = df_resultado_p.to_html(index=False, classes='tabla-planilla', border=1)
                            
                            st.html(f"""
                            <div id="print-area-planilla">
                                <style>
                                    .tabla-planilla {{ width: 100%; border-collapse: collapse; font-family: Arial, sans-serif; }}
                                    .tabla-planilla th, .tabla-planilla td {{ padding: 10px; text-align: left; border: 1px solid #333; color: black !important; font-size: 14px; }}
                                    .tabla-planilla th {{ background-color: #f2f2f2; font-weight: bold; }}
                                    .planilla-header {{ text-align: center; color: black; font-family: Arial, sans-serif; margin-bottom: 25px; }}
                                </style>
                                <div class="planilla-header">
                                    <h2 style="margin: 0;">PLANILLA DE TRABAJO: {planilla_sel}</h2>
                                    <p style="margin: 5px 0 0 0; font-size: 16px;">Fecha de Proceso: {fecha_planilla.strftime('%d/%m/%Y')}</p>
                                </div>
                                {html_planilla}
                            </div>
                            """)
                            
                            st.button("🖨️ Imprimir Planilla de Trabajo", key="btn_print_planillas_work", use_container_width=True)
                            st.components.v1.html("""
                                <script>
                                    const buttons = window.parent.document.querySelectorAll('button');
                                    const printButton = Array.from(buttons).find(el => el.innerText.includes('Imprimir Planilla de Trabajo'));
                                    if (printButton) {
                                        printButton.onclick = function() {
                                            const printContents = window.parent.document.getElementById('print-area-planilla').innerHTML;
                                            window.parent.print();
                                        };
                                    }
                                </script>
                            """, height=0)
                        else:
                            st.info(f"No hay pacientes cargados para la fecha {fecha_planilla.strftime('%d/%m/%Y')} con los códigos: {codigos_string}")
                    except Exception as e:
                        st.error(f"Error al compilar la planilla de trabajo: {e}")
