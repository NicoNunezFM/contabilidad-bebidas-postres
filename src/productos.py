import sqlite3

from database import obtener_conexion


# ============================================================
# AGREGAR PRODUCTO
# ============================================================

def agregar_producto(
    nombre,
    categoria,
    presentacion,
    contenido,
    unidad_medida,
    unidades_por_pack
):
    """
    Registra un producto nuevo.

    No utiliza input(), por lo que puede ser llamada desde
    terminal, WhatsApp, Notion u otra interfaz.
    """

    if not isinstance(nombre, str) or not nombre.strip():
        return {
            "ok": False,
            "mensaje": "El nombre del producto no puede estar vacío."
        }

    if not isinstance(categoria, str) or not categoria.strip():
        return {
            "ok": False,
            "mensaje": "La categoría no puede estar vacía."
        }

    if not isinstance(presentacion, str) or not presentacion.strip():
        return {
            "ok": False,
            "mensaje": "La presentación no puede estar vacía."
        }

    if not isinstance(contenido, (int, float)):
        return {
            "ok": False,
            "mensaje": "El contenido debe ser un número."
        }

    if contenido <= 0:
        return {
            "ok": False,
            "mensaje": "El contenido debe ser mayor que cero."
        }

    if not isinstance(unidad_medida, str) or not unidad_medida.strip():
        return {
            "ok": False,
            "mensaje": "La unidad de medida no puede estar vacía."
        }

    if not isinstance(unidades_por_pack, int):
        return {
            "ok": False,
            "mensaje": "Las unidades por pack deben ser un número entero."
        }

    if unidades_por_pack <= 0:
        return {
            "ok": False,
            "mensaje": "Las unidades por pack deben ser mayores que cero."
        }

    conexion = obtener_conexion()

    try:
        cursor = conexion.cursor()

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
            nombre.strip(),
            categoria.strip(),
            presentacion.strip(),
            contenido,
            unidad_medida.strip(),
            unidades_por_pack
        ))

        conexion.commit()

        return {
            "ok": True,
            "mensaje": "Producto agregado correctamente.",
            "id_producto": cursor.lastrowid
        }

    except sqlite3.Error as error:
        conexion.rollback()

        return {
            "ok": False,
            "mensaje": f"Error al agregar el producto: {error}"
        }

    finally:
        conexion.close()


# ============================================================
# OBTENER PRODUCTOS
# ============================================================

def obtener_productos():
    """
    Devuelve los productos como una lista de diccionarios.
    """

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute("""
        SELECT
            id_producto,
            nombre,
            categoria,
            presentacion,
            contenido,
            unidad_medida,
            unidades_por_pack,
            stock
        FROM productos
        ORDER BY id_producto
    """)

    productos_db = cursor.fetchall()

    conexion.close()

    productos = []

    for producto in productos_db:
        producto_python = {
            "id_producto": producto[0],
            "nombre": producto[1],
            "categoria": producto[2],
            "presentacion": producto[3],
            "contenido": producto[4],
            "unidad_medida": producto[5],
            "unidades_por_pack": producto[6],
            "stock": producto[7]
        }

        productos.append(producto_python)

    return productos


# ============================================================
# LISTAR PRODUCTOS
# ============================================================

def listar_productos():
    """
    Mantiene compatibilidad con el main actual.
    Devuelve las filas como tuplas.
    """

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute("""
        SELECT *
        FROM productos
        ORDER BY id_producto
    """)

    productos = cursor.fetchall()

    conexion.close()

    return productos


# ============================================================
# BUSCAR PRODUCTO POR ID
# ============================================================

def buscar_producto_por_id(id_producto):

    if not isinstance(id_producto, int):
        return None

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute("""
        SELECT *
        FROM productos
        WHERE id_producto = ?
    """, (
        id_producto,
    ))

    producto = cursor.fetchone()

    conexion.close()

    return producto


# ============================================================
# BUSCAR PRODUCTO POR NOMBRE
# ============================================================

def buscar_producto_por_nombre(nombre):
    """
    Busca un producto por nombre ignorando mayúsculas y minúsculas.

    Será especialmente útil para WhatsApp.
    """

    if not isinstance(nombre, str) or not nombre.strip():
        return None

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute("""
        SELECT *
        FROM productos
        WHERE LOWER(nombre) = LOWER(?)
    """, (
        nombre.strip(),
    ))

    producto = cursor.fetchone()

    conexion.close()

    return producto


# ============================================================
# MODIFICAR PRODUCTO
# ============================================================

def modificar_producto(
    id_producto,
    nombre,
    categoria,
    presentacion,
    contenido,
    unidad_medida,
    unidades_por_pack
):

    producto = buscar_producto_por_id(id_producto)

    if producto is None:
        return {
            "ok": False,
            "mensaje": "Producto no encontrado."
        }

    if not isinstance(nombre, str) or not nombre.strip():
        return {
            "ok": False,
            "mensaje": "El nombre no puede estar vacío."
        }

    if not isinstance(categoria, str) or not categoria.strip():
        return {
            "ok": False,
            "mensaje": "La categoría no puede estar vacía."
        }

    if not isinstance(presentacion, str) or not presentacion.strip():
        return {
            "ok": False,
            "mensaje": "La presentación no puede estar vacía."
        }

    if not isinstance(contenido, (int, float)) or contenido <= 0:
        return {
            "ok": False,
            "mensaje": "El contenido debe ser un número mayor que cero."
        }

    if not isinstance(unidad_medida, str) or not unidad_medida.strip():
        return {
            "ok": False,
            "mensaje": "La unidad de medida no puede estar vacía."
        }

    if not isinstance(unidades_por_pack, int) or unidades_por_pack <= 0:
        return {
            "ok": False,
            "mensaje": (
                "Las unidades por pack deben ser "
                "un número entero mayor que cero."
            )
        }

    conexion = obtener_conexion()

    try:
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
            nombre.strip(),
            categoria.strip(),
            presentacion.strip(),
            contenido,
            unidad_medida.strip(),
            unidades_por_pack,
            id_producto
        ))

        conexion.commit()

        return {
            "ok": True,
            "mensaje": "Producto modificado correctamente."
        }

    except sqlite3.Error as error:
        conexion.rollback()

        return {
            "ok": False,
            "mensaje": f"Error al modificar el producto: {error}"
        }

    finally:
        conexion.close()


# ============================================================
# ELIMINAR PRODUCTO
# ============================================================

def eliminar_producto(id_producto):

    producto = buscar_producto_por_id(id_producto)

    if producto is None:
        return {
            "ok": False,
            "mensaje": "Producto no encontrado."
        }

    conexion = obtener_conexion()

    try:
        cursor = conexion.cursor()

        # Verificar si existen compras asociadas
        cursor.execute("""
            SELECT COUNT(*)
            FROM compras
            WHERE id_producto = ?
        """, (
            id_producto,
        ))

        cantidad_compras = cursor.fetchone()[0]

        # Verificar si existen ventas asociadas
        cursor.execute("""
            SELECT COUNT(*)
            FROM ventas
            WHERE id_producto = ?
        """, (
            id_producto,
        ))

        cantidad_ventas = cursor.fetchone()[0]

        if cantidad_compras > 0 or cantidad_ventas > 0:
            return {
                "ok": False,
                "mensaje": (
                    "No se puede eliminar el producto porque tiene "
                    "compras o ventas registradas."
                )
            }

        cursor.execute("""
            DELETE FROM productos
            WHERE id_producto = ?
        """, (
            id_producto,
        ))

        conexion.commit()

        return {
            "ok": True,
            "mensaje": "Producto eliminado correctamente."
        }

    except sqlite3.Error as error:
        conexion.rollback()

        return {
            "ok": False,
            "mensaje": f"Error al eliminar el producto: {error}"
        }

    finally:
        conexion.close()
