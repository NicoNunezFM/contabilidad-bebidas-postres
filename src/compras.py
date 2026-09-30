from datetime import datetime
import sqlite3

from database import obtener_conexion
from productos import listar_productos, buscar_producto_por_id


# ============================================================
# REGISTRAR COMPRA
# ============================================================

def registrar_compra(id_producto, cantidad, precio_unitario, fecha=None):
    """
    Registra una compra y aumenta el stock.

    Esta función no utiliza input(), por lo que puede ser llamada
    desde la terminal, WhatsApp, Notion u otra interfaz.
    """

    # Validar ID
    if not isinstance(id_producto, int):
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

    # Validar cantidad
    if not isinstance(cantidad, int):
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

    # Validar precio
    if not isinstance(precio_unitario, (int, float)):
        return {
            "ok": False,
            "codigo": "DATOS_INVALIDOS",
            "mensaje": "El precio debe ser un número."
        }

    if precio_unitario <= 0:
        return {
            "ok": False,
            "codigo": "DATOS_INVALIDOS",
            "mensaje": "El precio debe ser mayor que cero."
        }

    if fecha is None:
        fecha = datetime.now().strftime("%Y-%m-%d")

    stock_actual = producto[7]

    conexion = obtener_conexion()

    try:

        cursor = conexion.cursor()

        cursor.execute("""
            INSERT INTO compras (
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

        id_compra = cursor.lastrowid

        cursor.execute("""
            UPDATE productos
            SET stock = stock + ?
            WHERE id_producto = ?
        """, (
            cantidad,
            id_producto
        ))

        conexion.commit()

        total = cantidad * precio_unitario

        return {
            "ok": True,
            "codigo": "COMPRA_REGISTRADA",
            "mensaje": "Compra registrada correctamente.",
            "id_compra": id_compra,
            "producto": producto[1],
            "cantidad": cantidad,
            "precio_unitario": precio_unitario,
            "total": total,
            "fecha": fecha,
            "stock_actual": stock_actual + cantidad
        }

    except sqlite3.Error as error:

        conexion.rollback()

        return {
            "ok": False,
            "codigo": "ERROR_BASE_DATOS",
            "mensaje": f"Error al registrar la compra: {error}"
        }

    finally:

        conexion.close()


# ============================================================
# REGISTRAR COMPRA DESDE TERMINAL
# ============================================================

def agregar_compra():
    """
    Interfaz de consola para registrar compras.
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

    resultado = registrar_compra(
        id_producto=id_producto,
        cantidad=cantidad,
        precio_unitario=precio_unitario
    )

    print(resultado["mensaje"])

    if resultado["ok"]:
        print(f"Producto: {resultado['producto']}")
        print(f"Cantidad: {resultado['cantidad']}")
        print(f"Total: ${resultado['total']:.2f}")
        print(f"Stock actual: {resultado['stock_actual']}")


# ============================================================
# OBTENER COMPRAS
# ============================================================

def obtener_compras():

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute("""
        SELECT
            compras.id_compra,
            productos.nombre,
            compras.fecha,
            compras.cantidad,
            compras.precio_unitario,
            compras.anulada,
            compras.fecha_anulacion,
            compras.motivo_anulacion
        FROM compras
        INNER JOIN productos
            ON compras.id_producto = productos.id_producto
        ORDER BY compras.id_compra
    """)

    compras_db = cursor.fetchall()

    conexion.close()

    compras = []

    for compra in compras_db:

        total = compra[3] * compra[4]

        compra_python = {
            "id_compra": compra[0],
            "producto": compra[1],
            "fecha": compra[2],
            "cantidad": compra[3],
            "precio_unitario": compra[4],
            "total": total,
            "anulada": bool(compra[5]),
            "fecha_anulacion": compra[6],
            "motivo_anulacion": compra[7]
        }

        compras.append(compra_python)

    return compras


# ============================================================
# LISTAR COMPRAS
# ============================================================

def listar_compras():

    compras = obtener_compras()

    if not compras:
        print("No hay compras registradas.")
        return

    for compra in compras:

        print(f"Compra N°: {compra['id_compra']}")
        print(f"Producto: {compra['producto']}")
        print(f"Fecha: {compra['fecha']}")
        print(f"Cantidad: {compra['cantidad']}")
        print(f"Precio unitario: ${compra['precio_unitario']:.2f}")
        print(f"Total: ${compra['total']:.2f}")
        print("-----------------------\n")

def anular_compra(id_compra, motivo):

    if not isinstance(id_compra, int):
        return {
            "ok": False,
            "codigo": "DATOS_INVALIDOS",
            "mensaje": "El ID de la compra debe ser un número entero."
        }

    if not isinstance(motivo, str) or not motivo.strip():
        return {
            "ok": False,
            "codigo": "DATOS_INVALIDOS",
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
            FROM compras
            WHERE id_compra = ?
        """, (id_compra,))

        compra = cursor.fetchone()

        if compra is None:
            return {
                "ok": False,
                "codigo": "COMPRA_NO_ENCONTRADA",
                "mensaje": "Compra no encontrada."
            }

        id_producto = compra[0]
        cantidad = compra[1]
        anulada = compra[2]

        if anulada == 1:
            return {
                "ok": False,
                "codigo": "COMPRA_YA_ANULADA",
                "mensaje": "La compra ya se encuentra anulada."
            }

        cursor.execute("""
            SELECT stock
            FROM productos
            WHERE id_producto = ?
        """, (id_producto,))

        producto = cursor.fetchone()

        stock_actual = producto[0]

        if stock_actual < cantidad:
            return {
                "ok": False,
                "codigo": "STOCK_INSUFICIENTE_PARA_ANULAR_COMPRA",
                "mensaje": (
                    "No se puede anular la compra porque "
                    "no hay suficiente stock disponible. "
                    f"Stock actual: {stock_actual}. "
                    f"Cantidad de la compra: {cantidad}."
                )
            }

        fecha_anulacion = datetime.now().strftime("%Y-%m-%d")

        cursor.execute("""
            UPDATE productos
            SET stock = stock - ?
            WHERE id_producto = ?
        """, (
            cantidad,
            id_producto
        ))

        cursor.execute("""
            UPDATE compras
            SET
                anulada = 1,
                fecha_anulacion = ?,
                motivo_anulacion = ?
            WHERE id_compra = ?
        """, (
            fecha_anulacion,
            motivo.strip(),
            id_compra
        ))

        conexion.commit()

        return {
            "ok": True,
            "codigo": "COMPRA_ANULADA",
            "mensaje": "Compra anulada correctamente.",
            "id_compra": id_compra,
            "cantidad_retirada_stock": cantidad,
            "fecha_anulacion": fecha_anulacion,
            "motivo": motivo.strip()
        }

    except sqlite3.Error as error:
        conexion.rollback()

        return {
            "ok": False,
            "codigo": "ERROR_BASE_DATOS",
            "mensaje": f"Error al anular la compra: {error}"
        }

    finally:
        conexion.close()