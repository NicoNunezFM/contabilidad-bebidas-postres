from datetime import datetime
import sqlite3

from database import obtener_conexion
from productos import buscar_producto_por_id


TIPOS_AJUSTE_STOCK = (
    "Ajuste",
    "Inventario",
    "Merma",
    "Consumo interno",
)


def registrar_ajuste_stock(
    id_producto,
    cantidad_ajuste,
    motivo,
    fecha=None,
    tipo="Ajuste"
):
    if isinstance(id_producto, bool) or not isinstance(id_producto, int):
        return {
            "ok": False,
            "codigo": "DATOS_INVALIDOS",
            "mensaje": "El ID del producto debe ser un número entero."
        }

    producto = buscar_producto_por_id(id_producto)

    if producto is None:
        return {
            "ok": False,
            "codigo": "PRODUCTO_NO_ENCONTRADO",
            "mensaje": "Producto no encontrado."
        }

    controla_stock = bool(producto[9])

    if not controla_stock:
        return {
            "ok": False,
            "codigo": "PRODUCTO_SIN_CONTROL_STOCK",
            "mensaje": (
                f"{producto[1]} no utiliza control de stock por unidades."
            )
        }

    if isinstance(cantidad_ajuste, bool) or not isinstance(
        cantidad_ajuste,
        int
    ):
        return {
            "ok": False,
            "codigo": "DATOS_INVALIDOS",
            "mensaje": "El ajuste debe ser un número entero."
        }

    if cantidad_ajuste == 0:
        return {
            "ok": False,
            "codigo": "DATOS_INVALIDOS",
            "mensaje": "El ajuste no puede ser cero."
        }

    if not isinstance(motivo, str) or not motivo.strip():
        return {
            "ok": False,
            "codigo": "DATOS_INVALIDOS",
            "mensaje": "El motivo no puede estar vacío."
        }

    if tipo not in TIPOS_AJUSTE_STOCK:
        return {
            "ok": False,
            "codigo": "TIPO_AJUSTE_INVALIDO",
            "mensaje": "El tipo de ajuste de stock no es válido."
        }

    if fecha is None:
        fecha = datetime.now().strftime("%Y-%m-%d")

    stock_anterior = producto[7]
    stock_nuevo = stock_anterior + cantidad_ajuste

    if stock_nuevo < 0:
        return {
            "ok": False,
            "codigo": "STOCK_INSUFICIENTE",
            "mensaje": (
                "El movimiento dejaría el stock en negativo. "
                f"Stock actual: {stock_anterior}"
            )
        }

    conexion = obtener_conexion()

    try:
        cursor = conexion.cursor()

        cursor.execute(
            """
            INSERT INTO ajustes_stock (
                id_producto,
                fecha,
                cantidad_ajuste,
                motivo,
                tipo,
                stock_anterior,
                stock_nuevo
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                id_producto,
                fecha,
                cantidad_ajuste,
                motivo.strip(),
                tipo,
                stock_anterior,
                stock_nuevo
            )
        )

        id_ajuste = cursor.lastrowid

        cursor.execute(
            """
            UPDATE productos
            SET stock = ?
            WHERE id_producto = ?
            """,
            (
                stock_nuevo,
                id_producto
            )
        )

        conexion.commit()

        return {
            "ok": True,
            "codigo": "AJUSTE_STOCK_REGISTRADO",
            "mensaje": "Stock ajustado correctamente.",
            "id_ajuste": id_ajuste,
            "id_producto": id_producto,
            "producto": producto[1],
            "tipo": tipo,
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
            "codigo": "ERROR_BASE_DATOS",
            "mensaje": f"Error al ajustar el stock: {error}"
        }

    finally:
        conexion.close()


def registrar_inventario_fisico(
    id_producto,
    cantidad_real,
    fecha=None
):
    if isinstance(id_producto, bool) or not isinstance(id_producto, int):
        return {
            "ok": False,
            "codigo": "DATOS_INVALIDOS",
            "mensaje": "El ID del producto debe ser un número entero."
        }

    producto = buscar_producto_por_id(id_producto)

    if producto is None:
        return {
            "ok": False,
            "codigo": "PRODUCTO_NO_ENCONTRADO",
            "mensaje": "Producto no encontrado."
        }

    if not bool(producto[9]):
        return {
            "ok": False,
            "codigo": "PRODUCTO_SIN_CONTROL_STOCK",
            "mensaje": (
                f"{producto[1]} no utiliza control de stock por unidades."
            )
        }

    if isinstance(cantidad_real, bool) or not isinstance(
        cantidad_real,
        int
    ):
        return {
            "ok": False,
            "codigo": "DATOS_INVALIDOS",
            "mensaje": "La cantidad contada debe ser un número entero."
        }

    if cantidad_real < 0:
        return {
            "ok": False,
            "codigo": "DATOS_INVALIDOS",
            "mensaje": "La cantidad contada no puede ser negativa."
        }

    stock_actual = producto[7]
    diferencia = cantidad_real - stock_actual

    if diferencia == 0:
        return {
            "ok": True,
            "codigo": "INVENTARIO_SIN_DIFERENCIAS",
            "mensaje": "El inventario coincide con el stock del sistema.",
            "id_producto": id_producto,
            "producto": producto[1],
            "stock_sistema": stock_actual,
            "stock_contado": cantidad_real,
            "ajuste": 0
        }

    resultado = registrar_ajuste_stock(
        id_producto=id_producto,
        cantidad_ajuste=diferencia,
        motivo="Inventario físico",
        fecha=fecha,
        tipo="Inventario"
    )

    return resultado


def registrar_merma(
    id_producto,
    cantidad,
    motivo="Merma",
    fecha=None
):
    if isinstance(cantidad, bool) or not isinstance(cantidad, int):
        return {
            "ok": False,
            "codigo": "DATOS_INVALIDOS",
            "mensaje": "La cantidad debe ser un número entero."
        }

    if cantidad <= 0:
        return {
            "ok": False,
            "codigo": "DATOS_INVALIDOS",
            "mensaje": "La cantidad debe ser mayor que cero."
        }

    return registrar_ajuste_stock(
        id_producto=id_producto,
        cantidad_ajuste=-cantidad,
        motivo=motivo,
        fecha=fecha,
        tipo="Merma"
    )


def registrar_consumo_interno(
    id_producto,
    cantidad,
    motivo="Consumo interno",
    fecha=None
):
    if isinstance(cantidad, bool) or not isinstance(cantidad, int):
        return {
            "ok": False,
            "codigo": "DATOS_INVALIDOS",
            "mensaje": "La cantidad debe ser un número entero."
        }

    if cantidad <= 0:
        return {
            "ok": False,
            "codigo": "DATOS_INVALIDOS",
            "mensaje": "La cantidad debe ser mayor que cero."
        }

    return registrar_ajuste_stock(
        id_producto=id_producto,
        cantidad_ajuste=-cantidad,
        motivo=motivo,
        fecha=fecha,
        tipo="Consumo interno"
    )


def obtener_ajustes_stock(
    id_producto=None,
    tipo=None
):
    conexion = obtener_conexion()
    cursor = conexion.cursor()

    condiciones = []
    parametros = []

    if id_producto is not None:
        condiciones.append("ajustes_stock.id_producto = ?")
        parametros.append(id_producto)

    if tipo is not None:
        condiciones.append("ajustes_stock.tipo = ?")
        parametros.append(tipo)

    where = ""

    if condiciones:
        where = "WHERE " + " AND ".join(condiciones)

    cursor.execute(
        f"""
        SELECT
            ajustes_stock.id_ajuste,
            productos.nombre,
            ajustes_stock.fecha,
            ajustes_stock.cantidad_ajuste,
            ajustes_stock.motivo,
            ajustes_stock.tipo,
            ajustes_stock.stock_anterior,
            ajustes_stock.stock_nuevo
        FROM ajustes_stock
        INNER JOIN productos
            ON ajustes_stock.id_producto = productos.id_producto
        {where}
        ORDER BY ajustes_stock.id_ajuste DESC
        """,
        tuple(parametros)
    )

    ajustes_db = cursor.fetchall()

    conexion.close()

    ajustes = []

    for ajuste in ajustes_db:
        ajustes.append({
            "id_ajuste": ajuste[0],
            "producto": ajuste[1],
            "fecha": ajuste[2],
            "cantidad_ajuste": ajuste[3],
            "motivo": ajuste[4],
            "tipo": ajuste[5],
            "stock_anterior": ajuste[6],
            "stock_nuevo": ajuste[7]
        })

    return ajustes
