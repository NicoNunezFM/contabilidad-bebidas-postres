from database import obtener_conexion


def agregar_producto( #Recibe los datos del producto como parametros
    nombre,
    categoria,
    presentacion,
    contenido,
    unidad_medida,
    unidades_por_pack
):
    conexion = obtener_conexion() #Inicia la conexion y crea el cursor
    cursor = conexion.cursor()
    #Insert into significa insertar un registro nuevo. Los signos ? representan valores que se enviaran despues. 
    cursor.execute(""" 
        INSERT INTO productos ( 
            nombre,
            categoria,
            presentacion,
            contenido,
            unidad_medida,
            unidades_por_pack
        )
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        nombre,
        categoria,
        presentacion,
        contenido,
        unidad_medida,
        unidades_por_pack
    ))

    conexion.commit()
    conexion.close()

def listar_productos():
    
    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute("SELECT * FROM productos")
    
    productos = cursor.fetchall()  
        
    conexion.close()

    return productos

def buscar_producto_por_id(id_producto):

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute(
        """
        SELECT * FROM productos
        WHERE id_producto = ?
        """,
        (id_producto,)
    )

    producto = cursor.fetchone()

    conexion.close()

    return producto

def modificar_producto(
    id_producto,
    nombre,
    categoria,
    presentacion,
    contenido,
    unidad_medida,
    unidades_por_pack
):
    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute("""
        UPDATE productos
        SET
            nombre = ?,
            categoria = ?,
            presentacion = ?,
            contenido = ?,
            unidad_medida = ?,
            unidades_por_pack = ?
        WHERE id_producto = ?
    """, (
        nombre,
        categoria,
        presentacion,
        contenido,
        unidad_medida,
        unidades_por_pack,
        id_producto

    ))

    conexion.commit()
    conexion.close()

def eliminar_producto(id_producto):
    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute("""
        DELETE FROM productos
        WHERE id_producto= ?
    """, (id_producto,))

    conexion.commit()
    conexion.close()    
        
    
    
        
