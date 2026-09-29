from datetime import datetime
import sqlite3

from database import obtener_conexion
from productos import listar_productos, buscar_producto_por_id


# ============================================================
# REGISTRAR VENTA
# ============================================================

def registrar_venta(id_producto, cantidad, precio_unitario, fecha=None):
    """
    Registra una venta en la base de datos y descuenta el stock.

    Esta función no utiliza input(), por lo que puede ser llamada
    desde la terminal, WhatsApp, Notion u otra interfaz.
    """

    # Validar ID
    if not isinstance(id_producto, int):
        return {
            "ok": False,
            "mensaje": "El ID del producto debe ser un número entero."
        }

    # Buscar producto
    producto = buscar_producto_por_id(id_producto)

    if producto is None:
        return {
            "ok": False,
            "mensaje": "Producto no encontrado."
        }

    # Validar cantidad
    if not isinstance(cantidad, int):
        return {
            "ok": False,
            "mensaje": "La cantidad debe ser un número entero."
        }

    if cantidad <= 0:
        return {
            "ok": False,
            "mensaje": "La cantidad debe ser mayor que cero."
        }

    # Obtener stock actual
    stock_actual = producto[7]

    if cantidad > stock_actual:
        return {
            "ok": False,
            "mensaje": (
                f"Stock insuficiente. "
                f"Stock disponible: {stock_actual}"
            )
        }

    # Validar precio
    if not isinstance(precio_unitario, (int, float)):
        return {
            "ok": False,
            "mensaje": "El precio unitario debe ser un número."
        }

    if precio_unitario <= 0:
        return {
            "ok": False,
            "mensaje": "El precio unitario debe ser mayor que cero."
        }

    # Si no se recibe fecha, usar la fecha actual
    if fecha is None:
        fecha = datetime.now().strftime("%Y-%m-%d")

    conexion = obtener_conexion()

    try:
        cursor = conexion.cursor()

        # Registrar venta
        cursor.execute("""
            INSERT INTO ventas (
                id_producto,
                fecha,
                cantidad,
                precio_unitario
            )
            VALUES (?, ?, ?, ?)
        """, (
            id_producto,
            fecha,
            cantidad,
            precio_unitario
        ))

        # Guardar ID de la nueva venta
        id_venta = cursor.lastrowid

        # Descontar stock
        cursor.execute("""
            UPDATE productos
            SET stock = stock - ?
            WHERE id_producto = ?
        """, (
            cantidad,
            id_producto
        ))

        conexion.commit()

        total = cantidad * precio_unitario

        return {
            "ok": True,
            "mensaje": "Venta registrada correctamente.",
            "id_venta": id_venta,
            "producto": producto[1],
            "cantidad": cantidad,
            "precio_unitario": precio_unitario,
            "total": total,
            "fecha": fecha,
            "stock_restante": stock_actual - cantidad
        }

    except sqlite3.Error as error:
        conexion.rollback()

        return {
            "ok": False,
            "mensaje": f"Error al registrar la venta: {error}"
        }

    finally:
        conexion.close()


# ============================================================
# REGISTRAR VENTA DESDE TERMINAL
# ============================================================

def anular_venta(id_venta, motivo):

    if not isinstance(id_venta, int):
        return {
            "ok": False,
            "mensaje": "El ID de la venta debe ser un número entero."
        }

    if not isinstance(motivo, str) or not motivo.strip():
        return {
            "ok": False,
            "mensaje": "El motivo de anulación no puede estar vacío."
        }

    conexion = obtener_conexion()

    try:
        cursor = conexion.cursor()

        cursor.execute("""
            SELECT
                id_producto,
                cantidad,
                anulada
            FROM ventas
            WHERE id_venta = ?
        """, (id_venta,))

        venta = cursor.fetchone()

        if venta is None:
            return {
                "ok": False,
                "mensaje": "Venta no encontrada."
            }

        id_producto = venta[0]
        cantidad = venta[1]
        anulada = venta[2]

        if anulada == 1:
            return {
                "ok": False,
                "mensaje": "La venta ya se encuentra anulada."
            }

        fecha_anulacion = datetime.now().strftime("%Y-%m-%d")

        cursor.execute("""
            UPDATE productos
            SET stock = stock + ?
            WHERE id_producto = ?
        """, (
            cantidad,
            id_producto
        ))

        cursor.execute("""
            UPDATE ventas
            SET
                anulada = 1,
                fecha_anulacion = ?,
                motivo_anulacion = ?
            WHERE id_venta = ?
        """, (
            fecha_anulacion,
            motivo.strip(),
            id_venta
        ))

        conexion.commit()

        return {
            "ok": True,
            "mensaje": "Venta anulada correctamente.",
            "id_venta": id_venta,
            "cantidad_devuelta_stock": cantidad,
            "fecha_anulacion": fecha_anulacion,
            "motivo": motivo.strip()
        }

    except sqlite3.Error as error:
        conexion.rollback()

        return {
            "ok": False,
            "mensaje": f"Error al anular la venta: {error}"
        }

    finally:
        conexion.close()

def agregar_venta():
    """
    Interfaz de consola para registrar una venta.
    Solicita los datos al usuario y utiliza registrar_venta().
    """

    listar_productos()

    id_texto = input("Ingrese ID del producto: ")

    if not id_texto.isdigit():
        print("El ID debe ser un número.")
        return

    id_producto = int(id_texto)

    cantidad_texto = input("Ingrese cantidad: ")

    if not cantidad_texto.isdigit():
        print("La cantidad debe ser un número entero.")
        return

    cantidad = int(cantidad_texto)

    precio_texto = input("Ingrese el precio unitario: ")

    try:
        precio_unitario = float(precio_texto)

    except ValueError:
        print("El precio debe ser un número.")
        return

    resultado = registrar_venta(
        id_producto=id_producto,
        cantidad=cantidad,
        precio_unitario=precio_unitario
    )

    print(resultado["mensaje"])

    if resultado["ok"]:
        print(f"Producto: {resultado['producto']}")
        print(f"Cantidad: {resultado['cantidad']}")
        print(f"Total: ${resultado['total']:.2f}")
        print(f"Stock restante: {resultado['stock_restante']}")


# ============================================================
# OBTENER VENTAS
# ============================================================

def obtener_ventas():
    """
    Obtiene todas las ventas y las devuelve como una lista
    de diccionarios de Python.
    """

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute("""
        SELECT
            ventas.id_venta,
            productos.nombre,
            ventas.fecha,
            ventas.cantidad,
            ventas.precio_unitario,
            ventas.anulada,
            ventas.fecha_anulacion,
            ventas.motivo_anulacion
        FROM ventas
        INNER JOIN productos
            ON ventas.id_producto = productos.id_producto
        ORDER BY ventas.id_venta
    """)

    ventas_db = cursor.fetchall()

    conexion.close()

    ventas = []

    for venta in ventas_db:

        total = venta[3] * venta[4]

        venta_python = {
            "id_venta": venta[0],
            "producto": venta[1],
            "fecha": venta[2],
            "cantidad": venta[3],
            "precio_unitario": venta[4],
            "total": total,
            "anulada": bool(venta[5]),
            "fecha_anulacion": venta[6],
            "motivo_anulacion": venta[7]
        }   

        ventas.append(venta_python)

    return ventas


# ============================================================
# LISTAR VENTAS EN TERMINAL
# ============================================================

def listar_ventas():
    """
    Muestra las ventas en la terminal.
    """

    ventas = obtener_ventas()

    if not ventas:
        print("No hay ventas registradas.")
        return

    for venta in ventas:
        print(f"Venta N°: {venta['id_venta']}")
        print(f"Producto: {venta['producto']}")
        print(f"Fecha: {venta['fecha']}")
        print(f"Cantidad: {venta['cantidad']}")
        print(
            f"Precio unitario: "
            f"${venta['precio_unitario']:.2f}"
        )
        print(f"Total: ${venta['total']:.2f}")
        print("-----------------------\n")