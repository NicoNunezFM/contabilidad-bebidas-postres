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
            fecha TEXT NOT NULL,
            estado_pago TEXT NOT NULL DEFAULT 'Cobrado',
            fecha_hora TEXT,
            canal_origen TEXT,
            usuario_origen TEXT,
            numero_origen TEXT,
            grupo_origen TEXT,
            id_mensaje_origen TEXT,
            anulada INTEGER NOT NULL DEFAULT 0,
            fecha_anulacion TEXT,
            motivo_anulacion TEXT,
            usuario_anulacion TEXT,
            id_mensaje_anulacion TEXT
        )
    """)

    conexion.commit()
    conexion.close()


def actualizar_tabla_operaciones_venta():

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute("PRAGMA table_info(ventas_operaciones)")
    columnas = cursor.fetchall()

    nombres_columnas = [columna[1] for columna in columnas]

    if "estado_pago" not in nombres_columnas:
        cursor.execute("""
            ALTER TABLE ventas_operaciones
            ADD COLUMN estado_pago TEXT NOT NULL DEFAULT 'Cobrado'
        """)

    if "anulada" not in nombres_columnas:
        cursor.execute("""
            ALTER TABLE ventas_operaciones
            ADD COLUMN anulada INTEGER NOT NULL DEFAULT 0
        """)

    if "fecha_anulacion" not in nombres_columnas:
        cursor.execute("""
            ALTER TABLE ventas_operaciones
            ADD COLUMN fecha_anulacion TEXT
        """)

    if "motivo_anulacion" not in nombres_columnas:
        cursor.execute("""
            ALTER TABLE ventas_operaciones
            ADD COLUMN motivo_anulacion TEXT
        """)

    columnas_a_agregar = {
        "fecha_hora": "TEXT",
        "canal_origen": "TEXT",
        "usuario_origen": "TEXT",
        "numero_origen": "TEXT",
        "grupo_origen": "TEXT",
        "id_mensaje_origen": "TEXT",
        "usuario_anulacion": "TEXT",
        "id_mensaje_anulacion": "TEXT",
    }

    for nombre, tipo in columnas_a_agregar.items():
        if nombre not in nombres_columnas:
            cursor.execute(
                f"""
                ALTER TABLE ventas_operaciones
                ADD COLUMN {nombre} {tipo}
                """
            )

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS
        idx_ventas_operaciones_usuario_activa
        ON ventas_operaciones (
            usuario_origen,
            anulada,
            id_operacion
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
        costo_unitario_snapshot REAL,
        fuente_costo_snapshot TEXT,
        id_operacion INTEGER,
        FOREIGN KEY (id_producto)
            REFERENCES productos(id_producto),
        FOREIGN KEY (id_operacion)
            REFERENCES ventas_operaciones(id_operacion)
        )
    """)

    conexion.commit()
    conexion.close()

def crear_tabla_venta_adicionales():
    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS adicionales_catalogo (
            id_adicional_catalogo INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL UNIQUE,
            precio_venta REAL,
            costo_unitario REAL,
            activo INTEGER NOT NULL DEFAULT 1,
            fecha_actualizacion TEXT
        )
    """)

    for nombre in (
        "huevo",
        "cheddar",
        "doble porcion",
        "extra papa",
    ):
        cursor.execute(
            """
            INSERT OR IGNORE INTO adicionales_catalogo (
                nombre,
                activo
            )
            VALUES (?, 1)
            """,
            (nombre,)
        )

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS venta_adicionales (
            id_adicional INTEGER PRIMARY KEY AUTOINCREMENT,
            id_venta INTEGER NOT NULL,
            id_adicional_catalogo INTEGER,
            descripcion TEXT NOT NULL,
            cantidad INTEGER NOT NULL DEFAULT 1,
            precio_total REAL NOT NULL DEFAULT 0,
            costo_unitario_snapshot REAL,
            fuente_costo_snapshot TEXT,
            FOREIGN KEY (id_venta)
                REFERENCES ventas(id_venta),
            FOREIGN KEY (id_adicional_catalogo)
                REFERENCES adicionales_catalogo(id_adicional_catalogo)
        )
    """)

    cursor.execute("PRAGMA table_info(venta_adicionales)")
    columnas = cursor.fetchall()
    nombres_columnas = [
        columna[1]
        for columna in columnas
    ]

    if "id_adicional_catalogo" not in nombres_columnas:
        cursor.execute("""
            ALTER TABLE venta_adicionales
            ADD COLUMN id_adicional_catalogo INTEGER
        """)

    if "costo_unitario_snapshot" not in nombres_columnas:
        cursor.execute("""
            ALTER TABLE venta_adicionales
            ADD COLUMN costo_unitario_snapshot REAL
        """)

    if "fuente_costo_snapshot" not in nombres_columnas:
        cursor.execute("""
            ALTER TABLE venta_adicionales
            ADD COLUMN fuente_costo_snapshot TEXT
        """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS
        idx_venta_adicionales_id_venta
        ON venta_adicionales (id_venta)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS
        idx_venta_adicionales_catalogo
        ON venta_adicionales (id_adicional_catalogo)
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
        valor_final REAL NOT NULL,
        seccion TEXT,
        subseccion TEXT
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


    if "costo_unitario_snapshot" not in nombres_columnas:
        cursor.execute("""
            ALTER TABLE ventas
            ADD COLUMN costo_unitario_snapshot REAL
        """)

    if "fuente_costo_snapshot" not in nombres_columnas:
        cursor.execute("""
            ALTER TABLE ventas
            ADD COLUMN fuente_costo_snapshot TEXT
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

    if "seccion" not in nombres_columnas:
        cursor.execute("""
            ALTER TABLE gastos
            ADD COLUMN seccion TEXT
        """)

    if "subseccion" not in nombres_columnas:
        cursor.execute("""
            ALTER TABLE gastos
            ADD COLUMN subseccion TEXT
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

def crear_tabla_mensajes_procesados():

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS mensajes_procesados (
            id_registro INTEGER PRIMARY KEY AUTOINCREMENT,
            canal TEXT NOT NULL,
            id_externo TEXT NOT NULL,
            fecha_recepcion TEXT NOT NULL,
            fecha_actualizacion TEXT,
            mensaje TEXT NOT NULL,
            estado TEXT NOT NULL DEFAULT 'Procesando',
            respuesta_json TEXT,
            UNIQUE(canal, id_externo)
        )
    """)

    conexion.commit()
    conexion.close()


def actualizar_tabla_mensajes_procesados():

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute("PRAGMA table_info(mensajes_procesados)")
    columnas = cursor.fetchall()

    nombres_columnas = [columna[1] for columna in columnas]

    if "fecha_actualizacion" not in nombres_columnas:
        cursor.execute("""
            ALTER TABLE mensajes_procesados
            ADD COLUMN fecha_actualizacion TEXT
        """)

    conexion.commit()
    conexion.close()


def crear_tabla_contextos_conversacion():

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS contextos_conversacion (
            id_contexto INTEGER PRIMARY KEY AUTOINCREMENT,
            canal TEXT NOT NULL,
            clave_contexto TEXT NOT NULL,
            tipo_contexto TEXT NOT NULL,
            fecha_actualizacion TEXT NOT NULL,
            UNIQUE(canal, clave_contexto)
        )
    """)

    conexion.commit()
    conexion.close()


def crear_tablas_costos_postres():

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS insumos (
            id_insumo INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL UNIQUE,
            unidad_base TEXT NOT NULL,
            seccion TEXT NOT NULL DEFAULT 'bebidas_postres',
            stock_base REAL NOT NULL DEFAULT 0,
            controla_stock INTEGER NOT NULL DEFAULT 1,
            activo INTEGER NOT NULL DEFAULT 1
        )
    """)

    cursor.execute("PRAGMA table_info(insumos)")
    columnas_insumos = cursor.fetchall()
    nombres_columnas_insumos = [
        columna[1]
        for columna in columnas_insumos
    ]

    if "stock_base" not in nombres_columnas_insumos:
        cursor.execute("""
            ALTER TABLE insumos
            ADD COLUMN stock_base REAL NOT NULL DEFAULT 0
        """)

    if "controla_stock" not in nombres_columnas_insumos:
        cursor.execute("""
            ALTER TABLE insumos
            ADD COLUMN controla_stock INTEGER NOT NULL DEFAULT 1
        """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS compras_insumos (
            id_compra_insumo INTEGER PRIMARY KEY AUTOINCREMENT,
            id_insumo INTEGER NOT NULL,
            fecha TEXT NOT NULL,
            cantidad_base REAL NOT NULL,
            costo_total REAL NOT NULL,
            comercio TEXT,
            id_gasto INTEGER,
            observaciones TEXT,
            FOREIGN KEY (id_insumo)
                REFERENCES insumos(id_insumo),
            FOREIGN KEY (id_gasto)
                REFERENCES gastos(id_gasto)
        )
    """)


    cursor.execute("""
        CREATE TABLE IF NOT EXISTS presentaciones_insumos (
            id_presentacion INTEGER PRIMARY KEY AUTOINCREMENT,
            id_insumo INTEGER NOT NULL,
            nombre TEXT NOT NULL,
            contenido_base REAL NOT NULL,
            activa INTEGER NOT NULL DEFAULT 1,
            FOREIGN KEY (id_insumo)
                REFERENCES insumos(id_insumo),
            UNIQUE(id_insumo, nombre)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ajustes_stock_insumos (
            id_ajuste_insumo INTEGER PRIMARY KEY AUTOINCREMENT,
            id_insumo INTEGER NOT NULL,
            fecha_hora TEXT NOT NULL,
            tipo TEXT NOT NULL,
            cantidad_anterior REAL NOT NULL,
            cantidad_nueva REAL NOT NULL,
            diferencia REAL NOT NULL,
            canal_origen TEXT,
            usuario_origen TEXT,
            grupo_origen TEXT,
            id_mensaje_origen TEXT,
            FOREIGN KEY (id_insumo)
                REFERENCES insumos(id_insumo)
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS
        idx_ajustes_stock_insumos_insumo_fecha
        ON ajustes_stock_insumos (
            id_insumo,
            fecha_hora,
            id_ajuste_insumo
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS
        idx_compras_insumos_insumo_fecha
        ON compras_insumos (
            id_insumo,
            fecha,
            id_compra_insumo
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS recetas (
            id_receta INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            producto TEXT NOT NULL,
            version INTEGER NOT NULL DEFAULT 1,
            rendimiento REAL NOT NULL,
            costo_fijo_por_unidad REAL NOT NULL DEFAULT 0,
            activa INTEGER NOT NULL DEFAULT 1,
            notas TEXT,
            UNIQUE(producto, version)
        )
    """)

    cursor.execute("PRAGMA table_info(recetas)")
    columnas_recetas = cursor.fetchall()
    nombres_columnas_recetas = [
        columna[1]
        for columna in columnas_recetas
    ]

    if "notas" not in nombres_columnas_recetas:
        cursor.execute("""
            ALTER TABLE recetas
            ADD COLUMN notas TEXT
        """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS receta_insumos (
            id_receta_insumo INTEGER PRIMARY KEY AUTOINCREMENT,
            id_receta INTEGER NOT NULL,
            id_insumo INTEGER NOT NULL,
            cantidad_base REAL NOT NULL,
            FOREIGN KEY (id_receta)
                REFERENCES recetas(id_receta),
            FOREIGN KEY (id_insumo)
                REFERENCES insumos(id_insumo),
            UNIQUE(id_receta, id_insumo)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS producciones_postres (
            id_produccion INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha_hora TEXT NOT NULL,
            id_producto INTEGER NOT NULL,
            producto TEXT NOT NULL,
            cantidad_producida INTEGER NOT NULL,
            id_receta INTEGER NOT NULL,
            version_receta INTEGER NOT NULL,
            costo_insumos REAL NOT NULL,
            costo_fijo REAL NOT NULL,
            costo_total REAL NOT NULL,
            costo_unitario REAL NOT NULL,
            canal_origen TEXT,
            usuario_origen TEXT,
            grupo_origen TEXT,
            id_mensaje_origen TEXT,
            FOREIGN KEY (id_producto)
                REFERENCES productos(id_producto),
            FOREIGN KEY (id_receta)
                REFERENCES recetas(id_receta)
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS
        idx_producciones_postres_fecha
        ON producciones_postres (
            fecha_hora,
            id_produccion
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS produccion_postres_insumos (
            id_produccion_insumo INTEGER PRIMARY KEY AUTOINCREMENT,
            id_produccion INTEGER NOT NULL,
            id_insumo INTEGER NOT NULL,
            insumo TEXT NOT NULL,
            cantidad_base REAL NOT NULL,
            unidad_base TEXT NOT NULL,
            costo_unitario_base REAL NOT NULL,
            costo_estimado REAL NOT NULL,
            controla_stock INTEGER NOT NULL DEFAULT 1,
            stock_anterior REAL,
            stock_nuevo REAL,
            FOREIGN KEY (id_produccion)
                REFERENCES producciones_postres(id_produccion),
            FOREIGN KEY (id_insumo)
                REFERENCES insumos(id_insumo)
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS
        idx_produccion_postres_insumos_produccion
        ON produccion_postres_insumos (
            id_produccion
        )
    """)

    cursor.execute("PRAGMA table_info(produccion_postres_insumos)")
    columnas_produccion_insumos = cursor.fetchall()
    nombres_columnas_produccion_insumos = [
        columna[1]
        for columna in columnas_produccion_insumos
    ]

    if "controla_stock" not in nombres_columnas_produccion_insumos:
        cursor.execute("""
            ALTER TABLE produccion_postres_insumos
            ADD COLUMN controla_stock INTEGER NOT NULL DEFAULT 1
        """)

    if "stock_anterior" not in nombres_columnas_produccion_insumos:
        cursor.execute("""
            ALTER TABLE produccion_postres_insumos
            ADD COLUMN stock_anterior REAL
        """)

    if "stock_nuevo" not in nombres_columnas_produccion_insumos:
        cursor.execute("""
            ALTER TABLE produccion_postres_insumos
            ADD COLUMN stock_nuevo REAL
        """)

    conexion.commit()
    conexion.close()



def crear_tablas_deudas_negocio():

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cuentas_deuda_negocio (
            id_cuenta INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL UNIQUE,
            tipo TEXT NOT NULL DEFAULT 'Tarjeta',
            moneda TEXT NOT NULL DEFAULT 'ARS',
            proximo_vencimiento TEXT,
            activa INTEGER NOT NULL DEFAULT 1,
            fecha_creacion TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS movimientos_deuda_negocio (
            id_movimiento_deuda INTEGER PRIMARY KEY AUTOINCREMENT,
            id_cuenta INTEGER NOT NULL,
            fecha_hora TEXT NOT NULL,
            tipo TEXT NOT NULL,
            importe REAL NOT NULL,
            descripcion TEXT,
            id_movimiento_caja INTEGER,
            FOREIGN KEY (id_cuenta)
                REFERENCES cuentas_deuda_negocio(id_cuenta),
            FOREIGN KEY (id_movimiento_caja)
                REFERENCES movimientos_caja(id_movimiento)
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS
        idx_movimientos_deuda_cuenta_fecha
        ON movimientos_deuda_negocio (
            id_cuenta,
            fecha_hora,
            id_movimiento_deuda
        )
    """)

    conexion.commit()
    conexion.close()

def inicializar_base_de_datos():
    crear_tabla_productos()
    actualizar_tabla_productos()
    crear_tabla_compras()
    crear_tabla_operaciones_venta()
    actualizar_tabla_operaciones_venta()
    crear_tabla_ventas()
    crear_tabla_venta_adicionales()
    crear_tabla_gastos()
    crear_tablas_costos_postres()
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
    crear_tabla_mensajes_procesados()
    actualizar_tabla_mensajes_procesados()
    crear_tabla_contextos_conversacion()
    crear_tablas_deudas_negocio()



