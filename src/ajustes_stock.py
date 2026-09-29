from datetime import datetime
import sqlite3

from database import obtener_conexion
from productos import buscar_producto_por_id

def registrar_ajuste_stock(
    id_producto,
    cantidad_ajuste,
    motivo,
    fecha=None
):

    if not isinstance(id_producto, int):
        return {
            "ok": False,
            "mensaje": "El ID del producto debe ser un número entero."
        }

    producto = buscar_producto_por_id(id_producto)

    if producto is None:
        return {
            "ok": False,
            "mensaje": "Producto no encontrado."
        }

    if not isinstance(cantidad_ajuste, int):
        return {
            "ok": False,
            "mensaje": "El ajuste debe ser un número entero."
        }

    if cantidad_ajuste == 0:
        return {
            "ok": False,
            "mensaje": "El ajuste no puede ser cero."
        }

    if not isinstance(motivo, str) or not motivo.strip():
        return {
            "ok": False,
            "mensaje": "El motivo no puede estar vacío."
        }

    if fecha is None:
        fecha = datetime.now().strftime("%Y-%m-%d")

    stock_anterior = producto[7]
    stock_nuevo = stock_anterior + cantidad_ajuste

    if stock_nuevo < 0:
        return {
            "ok": False,
            "mensaje": (
                f"El ajuste dejaría el stock en negativo. "
                f"Stock actual: {stock_anterior}"
            )
        }

    conexion = obtener_conexion()

    try:
        cursor = conexion.cursor()

        cursor.execute("""
            INSERT INTO ajustes_stock (
                id_producto,
                fecha,
                cantidad_ajuste,
                motivo,
                stock_anterior,
                stock_nuevo
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            id_producto,
            fecha,
            cantidad_ajuste,
            motivo.strip(),
            stock_anterior,
            stock_nuevo
        ))

        id_ajuste = cursor.lastrowid

        cursor.execute("""
            UPDATE productos
            SET stock = ?
            WHERE id_producto = ?
        """, (
            stock_nuevo,
            id_producto
        ))

        conexion.commit()

        return {
            "ok": True,
            "mensaje": "Stock ajustado correctamente.",
            "id_ajuste": id_ajuste,
            "producto": producto[1],
            "stock_anterior": stock_anterior,
            "ajuste": cantidad_ajuste,
            "stock_nuevo": stock_nuevo,
            "motivo": motivo.strip(),
            "fecha": fecha
        }

    except sqlite3.Error as error:
        conexion.rollback()

        return {
            "ok": False,
            "mensaje": f"Error al ajustar el stock: {error}"
        }

    finally:
        conexion.close()

def registrar_inventario_fisico(
    id_producto,
    cantidad_real,
    fecha=None
):

    if not isinstance(id_producto, int):
        return {
            "ok": False,
            "mensaje": "El ID del producto debe ser un número entero."
        }

    producto = buscar_producto_por_id(id_producto)

    if producto is None:
        return {
            "ok": False,
            "mensaje": "Producto no encontrado."
        }

    if not isinstance(cantidad_real, int):
        return {
            "ok": False,
            "mensaje": "La cantidad contada debe ser un número entero."
        }

    if cantidad_real < 0:
        return {
            "ok": False,
            "mensaje": "La cantidad contada no puede ser negativa."
        }

    stock_actual = producto[7]

    diferencia = cantidad_real - stock_actual

    if diferencia == 0:
        return {
            "ok": True,
            "mensaje": "El inventario coincide con el stock del sistema.",
            "producto": producto[1],
            "stock_sistema": stock_actual,
            "stock_contado": cantidad_real,
            "ajuste": 0
        }

    resultado = registrar_ajuste_stock(
        id_producto=id_producto,
        cantidad_ajuste=diferencia,
        motivo="Inventario físico",
        fecha=fecha
    )

    return resultado

def obtener_ajustes_stock(id_producto=None):

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    if id_producto is None:

        cursor.execute("""
            SELECT
                ajustes_stock.id_ajuste,
                productos.nombre,
                ajustes_stock.fecha,
                ajustes_stock.cantidad_ajuste,
                ajustes_stock.motivo,
                ajustes_stock.stock_anterior,
                ajustes_stock.stock_nuevo
            FROM ajustes_stock
            INNER JOIN productos
                ON ajustes_stock.id_producto = productos.id_producto
            ORDER BY ajustes_stock.id_ajuste DESC
        """)

    else:

        cursor.execute("""
            SELECT
                ajustes_stock.id_ajuste,
                productos.nombre,
                ajustes_stock.fecha,
                ajustes_stock.cantidad_ajuste,
                ajustes_stock.motivo,
                ajustes_stock.stock_anterior,
                ajustes_stock.stock_nuevo
            FROM ajustes_stock
            INNER JOIN productos
                ON ajustes_stock.id_producto = productos.id_producto
            WHERE ajustes_stock.id_producto = ?
            ORDER BY ajustes_stock.id_ajuste DESC
        """, (id_producto,))

    ajustes_db = cursor.fetchall()

    conexion.close()

    ajustes = []

    for ajuste in ajustes_db:

        ajuste_python = {
            "id_ajuste": ajuste[0],
            "producto": ajuste[1],
            "fecha": ajuste[2],
            "cantidad_ajuste": ajuste[3],
            "motivo": ajuste[4],
            "stock_anterior": ajuste[5],
            "stock_nuevo": ajuste[6]
        }

        ajustes.append(ajuste_python)

    return ajustes