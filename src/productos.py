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
    unidades_por_pack,
    precio_venta=None,
    controla_stock=True
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

    if isinstance(contenido, bool) or not isinstance(contenido, (int, float)):
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

    if precio_venta is not None:
        if isinstance(precio_venta, bool) or not isinstance(precio_venta, (int, float)):
            return {
                "ok": False,
                "mensaje": "El precio de venta debe ser un número."
            }

        if precio_venta <= 0:
            return {
                "ok": False,
                "mensaje": "El precio de venta debe ser mayor que cero."
            }

    if not isinstance(controla_stock, bool):
        return {
            "ok": False,
            "mensaje": "controla_stock debe ser verdadero o falso."
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
                unidades_por_pack,
                precio_venta,
                controla_stock
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            nombre.strip(),
            categoria.strip(),
            presentacion.strip(),
            contenido,
            unidad_medida.strip(),
            unidades_por_pack,
            precio_venta,
            int(controla_stock)
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
            stock,
            precio_venta,
            controla_stock
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
            "stock": producto[7],
            "precio_venta": producto[8],
            "controla_stock": bool(producto[9])
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

                # Verificar si existen ajustes de stock asociados
        cursor.execute("""
            SELECT COUNT(*)
            FROM ajustes_stock
            WHERE id_producto = ?
        """, (
            id_producto,
        ))

        cantidad_ajustes = cursor.fetchone()[0]

        if (
            cantidad_compras > 0
            or cantidad_ventas > 0
            or cantidad_ajustes > 0
        ):
            return {
                "ok": False,
                "mensaje": (
                    "No se puede eliminar el producto porque tiene "
                    "compras, ventas o ajustes de stock registrados."
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


# ============================================================
# ACTUALIZAR PRECIO DE VENTA
# ============================================================

def actualizar_precio_venta(id_producto, precio_venta):

    producto = buscar_producto_por_id(id_producto)

    if producto is None:
        return {
            "ok": False,
            "codigo": "PRODUCTO_NO_ENCONTRADO",
            "mensaje": "Producto no encontrado."
        }

    if isinstance(precio_venta, bool) or not isinstance(precio_venta, (int, float)):
        return {
            "ok": False,
            "codigo": "DATOS_INVALIDOS",
            "mensaje": "El precio de venta debe ser un número."
        }

    if precio_venta <= 0:
        return {
            "ok": False,
            "codigo": "DATOS_INVALIDOS",
            "mensaje": "El precio de venta debe ser mayor que cero."
        }

    conexion = obtener_conexion()

    try:
        cursor = conexion.cursor()

        cursor.execute("""
            UPDATE productos
            SET precio_venta = ?
            WHERE id_producto = ?
        """, (
            precio_venta,
            id_producto
        ))

        conexion.commit()

        return {
            "ok": True,
            "codigo": "PRECIO_ACTUALIZADO",
            "mensaje": "Precio de venta actualizado correctamente.",
            "id_producto": id_producto,
            "precio_venta": precio_venta
        }

    except sqlite3.Error as error:
        conexion.rollback()

        return {
            "ok": False,
            "codigo": "ERROR_BASE_DATOS",
            "mensaje": f"Error al actualizar el precio: {error}"
        }

    finally:
        conexion.close()
