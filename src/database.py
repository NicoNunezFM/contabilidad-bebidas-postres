import sqlite3 #Importa el modulo que permite trabajar con bases 

def obtener_conexion():  
    conexion = sqlite3.connect("negocio.db") # busca un archivo llamado negocio.db, si no existe sqlite lo crea automaticamente. 
    return conexion #retorna la conexion para poder utilizarla en otros archivos. 

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
            stock INTEGER NOT NULL DEFAULT 0
        )
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
        FOREIGN KEY (id_producto)
            REFERENCES productos(id_producto)
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

def inicializar_base_de_datos():
    crear_tabla_productos()
    crear_tabla_compras()
    crear_tabla_ventas()
    crear_tabla_gastos()



