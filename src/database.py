import os
import sqlite3
from pathlib import Path


RUTA_BASE_PREDETERMINADA = (
    Path(__file__).resolve().parent.parent / "negocio.db"
)


def obtener_ruta_base():

    ruta_personalizada = os.getenv("NEGOCIO_DB_PATH")

    if ruta_personalizada:
        return Path(ruta_personalizada)

    return RUTA_BASE_PREDETERMINADA


def obtener_conexion():

    conexion = sqlite3.connect(
        obtener_ruta_base()
    )

    conexion.execute("PRAGMA foreign_keys = ON")

    return conexion

def crear_tabla_productos():
    conexion = obtener_conexion()

    cursor = conexion.cursor() #crea un cursor. ##Cursor es el objeto que usamos para enviar instruciones SQL a la base de datos

    cursor.execute("""  
        CREATE TABLE IF NOT EXISTS productos (  
            id_producto INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            categoria TEXT NOT NULL,
            presentacion TEXT,
            contenido REAL,
            unidad_medida TEXT,
            unidades_por_pack INTEGER,
            stock INTEGER NOT NULL DEFAULT 0,
            precio_venta REAL,
            controla_stock INTEGER NOT NULL DEFAULT 1
        )
    """)

    conexion.commit()
    conexion.close()

def actualizar_tabla_productos():

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute("PRAGMA table_info(productos)")
    columnas = cursor.fetchall()

    nombres_columnas = [columna[1] for columna in columnas]

    if "precio_venta" not in nombres_columnas:
        cursor.execute("""
            ALTER TABLE productos
            ADD COLUMN precio_venta REAL
        """)

    if "controla_stock" not in nombres_columnas:
        cursor.execute("""
            ALTER TABLE productos
            ADD COLUMN controla_stock INTEGER NOT NULL DEFAULT 1
        """)

    conexion.commit()
    conexion.close()


def crear_tabla_compras():
    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS compras(
        id_compra INTEGER PRIMARY KEY AUTOINCREMENT,
        id_producto INTEGER NOT NULL,
        fecha TEXT NOT NULL,
        cantidad INTEGER NOT NULL,
        precio_unitario REAL NOT NULL,
        FOREIGN KEY (id_producto)
            REFERENCES productos(id_producto)
        )
    """)

    conexion.commit()
    conexion.close()

def crear_tabla_operaciones_venta():
    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ventas_operaciones (
            id_operacion INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT NOT NULL
        )
    """)

    conexion.commit()
    conexion.close()


def crear_tabla_ventas():
    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ventas(
        id_venta INTEGER PRIMARY KEY AUTOINCREMENT,
        id_producto INTEGER NOT NULL,
        fecha TEXT NOT NULL,
        cantidad INTEGER NOT NULL,
        precio_unitario REAL NOT NULL,
        id_operacion INTEGER,
        FOREIGN KEY (id_producto)
            REFERENCES productos(id_producto),
        FOREIGN KEY (id_operacion)
            REFERENCES ventas_operaciones(id_operacion)
        )
    """)

    conexion.commit()
    conexion.close()

def crear_tabla_gastos():
    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS gastos(
        id_gasto INTEGER PRIMARY KEY AUTOINCREMENT,
        fecha TEXT NOT NULL,
        categoria TEXT NOT NULL,
        descripcion_gasto TEXT NOT NULL,
        valor_final REAL NOT NULL
        )
    """)

    conexion.commit()
    conexion.close()

def crear_tabla_ajustes_stock():

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ajustes_stock (
            id_ajuste INTEGER PRIMARY KEY AUTOINCREMENT,
            id_producto INTEGER NOT NULL,
            fecha TEXT NOT NULL,
            cantidad_ajuste INTEGER NOT NULL,
            motivo TEXT NOT NULL,
            tipo TEXT NOT NULL DEFAULT 'Ajuste',
            stock_anterior INTEGER NOT NULL,
            stock_nuevo INTEGER NOT NULL,
            FOREIGN KEY (id_producto)
                REFERENCES productos(id_producto)
        )
    """)

    conexion.commit()
    conexion.close()

def actualizar_tabla_ajustes_stock():

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute("PRAGMA table_info(ajustes_stock)")
    columnas = cursor.fetchall()

    nombres_columnas = [columna[1] for columna in columnas]

    if "tipo" not in nombres_columnas:
        cursor.execute("""
            ALTER TABLE ajustes_stock
            ADD COLUMN tipo TEXT NOT NULL DEFAULT 'Ajuste'
        """)

    conexion.commit()
    conexion.close()


def actualizar_tabla_ventas():

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute("PRAGMA table_info(ventas)")
    columnas = cursor.fetchall()

    nombres_columnas = []

    for columna in columnas:
        nombres_columnas.append(columna[1])

    if "anulada" not in nombres_columnas:
        cursor.execute("""
            ALTER TABLE ventas
            ADD COLUMN anulada INTEGER NOT NULL DEFAULT 0
        """)

    if "fecha_anulacion" not in nombres_columnas:
        cursor.execute("""
            ALTER TABLE ventas
            ADD COLUMN fecha_anulacion TEXT
        """)

    if "motivo_anulacion" not in nombres_columnas:
        cursor.execute("""
            ALTER TABLE ventas
            ADD COLUMN motivo_anulacion TEXT
        """)

    if "id_operacion" not in nombres_columnas:
        cursor.execute("""
            ALTER TABLE ventas
            ADD COLUMN id_operacion INTEGER
            REFERENCES ventas_operaciones(id_operacion)
        """)

    conexion.commit()
    conexion.close()

def actualizar_tabla_compras():

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute("PRAGMA table_info(compras)")
    columnas = cursor.fetchall()

    nombres_columnas = []

    for columna in columnas:
        nombres_columnas.append(columna[1])

    if "anulada" not in nombres_columnas:
        cursor.execute("""
            ALTER TABLE compras
            ADD COLUMN anulada INTEGER NOT NULL DEFAULT 0
        """)

    if "fecha_anulacion" not in nombres_columnas:
        cursor.execute("""
            ALTER TABLE compras
            ADD COLUMN fecha_anulacion TEXT
        """)

    if "motivo_anulacion" not in nombres_columnas:
        cursor.execute("""
            ALTER TABLE compras
            ADD COLUMN motivo_anulacion TEXT
        """)

    conexion.commit()
    conexion.close()

def actualizar_tabla_gastos():

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute("PRAGMA table_info(gastos)")
    columnas = cursor.fetchall()

    nombres_columnas = []

    for columna in columnas:
        nombres_columnas.append(columna[1])

    if "anulado" not in nombres_columnas:
        cursor.execute("""
            ALTER TABLE gastos
            ADD COLUMN anulado INTEGER NOT NULL DEFAULT 0
        """)

    if "fecha_anulacion" not in nombres_columnas:
        cursor.execute("""
            ALTER TABLE gastos
            ADD COLUMN fecha_anulacion TEXT
        """)

    if "motivo_anulacion" not in nombres_columnas:
        cursor.execute("""
            ALTER TABLE gastos
            ADD COLUMN motivo_anulacion TEXT
        """)

    conexion.commit()
    conexion.close()

def crear_tabla_movimientos_caja():

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS movimientos_caja (
            id_movimiento INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT NOT NULL,
            tipo TEXT NOT NULL,
            descripcion TEXT NOT NULL,
            monto REAL NOT NULL
        )
    """)

    conexion.commit()
    conexion.close()

def actualizar_tabla_movimientos_caja():

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute("PRAGMA table_info(movimientos_caja)")
    columnas = cursor.fetchall()

    nombres_columnas = []

    for columna in columnas:
        nombres_columnas.append(columna[1])

    if "anulado" not in nombres_columnas:
        cursor.execute("""
            ALTER TABLE movimientos_caja
            ADD COLUMN anulado INTEGER NOT NULL DEFAULT 0
        """)

    if "fecha_anulacion" not in nombres_columnas:
        cursor.execute("""
            ALTER TABLE movimientos_caja
            ADD COLUMN fecha_anulacion TEXT
        """)

    if "motivo_anulacion" not in nombres_columnas:
        cursor.execute("""
            ALTER TABLE movimientos_caja
            ADD COLUMN motivo_anulacion TEXT
        """)

    conexion.commit()
    conexion.close()

def crear_tabla_cierres_semanales():

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cierres_semanales (
            id_cierre INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha_desde TEXT NOT NULL,
            fecha_hasta TEXT NOT NULL,
            ventas REAL NOT NULL,
            compras REAL NOT NULL,
            gastos REAL NOT NULL,
            resultado_negocio REAL NOT NULL,
            aportes REAL NOT NULL,
            retiros REAL NOT NULL,
            saldo_caja REAL NOT NULL,
            fecha_cierre TEXT NOT NULL
        )
    """)

    conexion.commit()
    conexion.close()

def actualizar_tabla_cierres_semanales():

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute("PRAGMA table_info(cierres_semanales)")
    columnas = cursor.fetchall()

    nombres_columnas = []

    for columna in columnas:
        nombres_columnas.append(columna[1])

    if "diezmo" not in nombres_columnas:
        cursor.execute("""
            ALTER TABLE cierres_semanales
            ADD COLUMN diezmo REAL NOT NULL DEFAULT 0
        """)

    if "resultado_despues_diezmo" not in nombres_columnas:
        cursor.execute("""
            ALTER TABLE cierres_semanales
            ADD COLUMN resultado_despues_diezmo REAL NOT NULL DEFAULT 0
        """)

    conexion.commit()
    conexion.close()

def crear_tabla_cierres_mensuales():

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cierres_mensuales (
            id_cierre INTEGER PRIMARY KEY AUTOINCREMENT,
            anio INTEGER NOT NULL,
            mes INTEGER NOT NULL,

            fecha_desde TEXT NOT NULL,
            fecha_hasta TEXT NOT NULL,

            ventas REAL NOT NULL,
            compras REAL NOT NULL,
            gastos REAL NOT NULL,

            resultado_negocio REAL NOT NULL,

            aportes REAL NOT NULL,
            retiros REAL NOT NULL,
            saldo_caja REAL NOT NULL,

            diezmo_correspondiente REAL NOT NULL,

            fecha_cierre TEXT NOT NULL,

            UNIQUE(anio, mes)
        )
    """)

    conexion.commit()
    conexion.close()

def crear_tabla_movimientos_diezmo():

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS movimientos_diezmo (
            id_movimiento INTEGER PRIMARY KEY AUTOINCREMENT,

            anio INTEGER NOT NULL,
            mes INTEGER NOT NULL,

            fecha TEXT NOT NULL,
            tipo TEXT NOT NULL,

            monto REAL NOT NULL,
            descripcion TEXT NOT NULL,

            anulado INTEGER NOT NULL DEFAULT 0,
            fecha_anulacion TEXT,
            motivo_anulacion TEXT
        )
    """)

    conexion.commit()
    conexion.close()

def inicializar_base_de_datos():
    crear_tabla_productos()
    actualizar_tabla_productos()
    crear_tabla_compras()
    crear_tabla_operaciones_venta()
    crear_tabla_ventas()
    crear_tabla_gastos()
    crear_tabla_ajustes_stock()
    actualizar_tabla_ajustes_stock()
    actualizar_tabla_ventas()
    actualizar_tabla_compras()
    actualizar_tabla_gastos()
    crear_tabla_movimientos_caja()
    actualizar_tabla_movimientos_caja()
    crear_tabla_cierres_semanales()
    actualizar_tabla_cierres_semanales()
    crear_tabla_cierres_mensuales()
    crear_tabla_movimientos_diezmo()



