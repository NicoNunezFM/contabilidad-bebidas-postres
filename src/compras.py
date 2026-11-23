from datetime import datetime
import math
import sqlite3

from database import obtener_conexion
from pos_contabilidad import corte_contable, fecha_local, validar_fecha_costo, validar_reversion_costo
from deudas_negocio import registrar_compra_deuda_en_cursor
from productos import listar_productos


# ============================================================
# REGISTRAR COMPRA
# ============================================================

def registrar_compra(
    id_producto,
    cantidad,
    precio_unitario,
    fecha=None,
    cuenta_deuda=None,
    *,
    _conexion=None,
    _financiado=None,
):
    """
    Registra una compra y aumenta el stock.

    Si cuenta_deuda se informa, la compra aumenta esa deuda y no
    representa una salida inmediata de caja.
    """

    if isinstance(id_producto, bool) or not isinstance(id_producto, int):
        return {
            "ok": False,
            "codigo": "DATOS_INVALIDOS",
            "mensaje": "El ID del producto debe ser un número entero."
        }

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

    if isinstance(precio_unitario, bool) or not isinstance(
        precio_unitario,
        (int, float)
    ):
        return {
            "ok": False,
            "codigo": "DATOS_INVALIDOS",
            "mensaje": "El precio debe ser un número."
        }

    if not math.isfinite(precio_unitario) or precio_unitario <= 0:
        return {
            "ok": False,
            "codigo": "DATOS_INVALIDOS",
            "mensaje": "El precio debe ser mayor que cero."
        }

    cuenta_deuda_limpia = (
        str(cuenta_deuda).strip()
        if cuenta_deuda is not None
        and str(cuenta_deuda).strip()
        else None
    )

    total = cantidad * precio_unitario
    propia = _conexion is None
    conexion = obtener_conexion() if propia else _conexion

    try:
        if propia:
            conexion.execute("BEGIN IMMEDIATE")
        producto = conexion.execute(
            "SELECT nombre, stock FROM productos WHERE id_producto = ?", (id_producto,)
        ).fetchone()
        if producto is None:
            return {
                "ok": False, "codigo": "PRODUCTO_NO_ENCONTRADO",
                "mensaje": "Producto no encontrado.",
            }
        nombre_producto, stock_actual = producto
        integrada = corte_contable(conexion) is not None
        fecha = fecha if fecha is not None else (fecha_local() if integrada else datetime.now().date().isoformat())
        rechazo = validar_fecha_costo(fecha) if integrada else None
        if rechazo:
            return rechazo
        cursor = conexion.cursor()

        medio_pago = ("Deuda" if cuenta_deuda_limpia else "Caja") if propia else "POS"
        id_cuenta_deuda = None
        id_movimiento_deuda = None
        saldo_deuda = None
        nombre_cuenta_deuda = None

        if cuenta_deuda_limpia:
            deuda = registrar_compra_deuda_en_cursor(
                cursor=cursor,
                nombre=cuenta_deuda_limpia,
                monto=total if propia else _financiado,
                descripcion=(
                    f"Compra financiada: "
                    f"{cantidad} x {nombre_producto}"
                ),
            )
            if not propia and deuda["moneda"] != "ARS":
                raise ValueError("La cuenta del proveedor debe estar en pesos.")
            id_cuenta_deuda = deuda[
                "id_cuenta"
            ]
            id_movimiento_deuda = deuda[
                "id_movimiento_deuda"
            ]
            saldo_deuda = deuda[
                "saldo"
            ]
            nombre_cuenta_deuda = deuda[
                "cuenta"
            ]

        cursor.execute(
            """
            INSERT INTO compras (
                id_producto,
                fecha,
                cantidad,
                precio_unitario,
                medio_pago,
                id_cuenta_deuda,
                id_movimiento_deuda
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                id_producto,
                fecha,
                cantidad,
                precio_unitario,
                medio_pago,
                id_cuenta_deuda,
                id_movimiento_deuda,
            )
        )

        id_compra = cursor.lastrowid

        cursor.execute(
            """
            UPDATE productos
            SET stock = stock + ?
            WHERE id_producto = ?
            """,
            (
                cantidad,
                id_producto
            )
        )

        if propia:
            conexion.commit()

        return {
            "ok": True,
            "codigo": "COMPRA_REGISTRADA",
            "mensaje": "Compra registrada correctamente.",
            "id_compra": id_compra,
            "producto": nombre_producto,
            "cantidad": cantidad,
            "precio_unitario": precio_unitario,
            "total": total,
            "fecha": fecha,
            "stock_actual": stock_actual + cantidad,
            "medio_pago": medio_pago,
            "id_cuenta_deuda": id_cuenta_deuda,
            "cuenta_deuda": nombre_cuenta_deuda,
            "id_movimiento_deuda": id_movimiento_deuda,
            "saldo_deuda": saldo_deuda,
        }

    except (sqlite3.Error, ValueError) as error:
        if propia:
            conexion.rollback()

        return {
            "ok": False,
            "codigo": "ERROR_BASE_DATOS",
            "mensaje": f"Error al registrar la compra: {error}"
        }

    finally:
        if propia:
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

def anular_compra(id_compra, motivo, *, _conexion=None):

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

    propia = _conexion is None
    conexion = obtener_conexion() if propia else _conexion

    try:
        if propia:
            conexion.execute("BEGIN IMMEDIATE")
        cursor = conexion.cursor()

        cursor.execute("""
            SELECT
                id_producto,
                cantidad,
                anulada,
                precio_unitario,
                id_cuenta_deuda,
                id_movimiento_deuda,
                medio_pago
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
        precio_unitario = compra[3]
        id_cuenta_deuda = compra[4]
        id_movimiento_deuda = compra[5]

        if propia and compra[6] == "POS":
            return {
                "ok": False, "codigo": "COMPRA_REQUIERE_REVERSO_POS",
                "mensaje": "Revertí esta compra desde el POS para registrar el reintegro.",
            }

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

        integrada = corte_contable(conexion) is not None
        if integrada:
            rechazo = validar_reversion_costo(conexion, "compra", id_compra)
            if rechazo:
                return rechazo
        fecha_anulacion = fecha_local() if integrada else datetime.now().date().isoformat()

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

        deuda_revertida = 0

        if (
            id_cuenta_deuda is not None
            and id_movimiento_deuda is not None
        ):
            deuda_revertida = cantidad * precio_unitario
            if not propia:
                deuda_revertida = cursor.execute("""
                    SELECT importe FROM movimientos_deuda_negocio WHERE id_movimiento_deuda = ?
                """, (id_movimiento_deuda,)).fetchone()[0]

            cursor.execute(
                """
                INSERT INTO movimientos_deuda_negocio (
                    id_cuenta,
                    fecha_hora,
                    tipo,
                    importe,
                    descripcion
                )
                VALUES (?, ?, 'Anulación compra', ?, ?)
                """,
                (
                    id_cuenta_deuda,
                    datetime.now().isoformat(
                        timespec="seconds"
                    ),
                    -float(deuda_revertida),
                    (
                        "Anulación compra #"
                        f"{id_compra}: {motivo.strip()}"
                    ),
                )
            )

        if propia:
            conexion.commit()

        return {
            "ok": True,
            "codigo": "COMPRA_ANULADA",
            "mensaje": "Compra anulada correctamente.",
            "id_compra": id_compra,
            "cantidad_retirada_stock": cantidad,
            "fecha_anulacion": fecha_anulacion,
            "motivo": motivo.strip(),
            "deuda_revertida": deuda_revertida
        }

    except sqlite3.Error as error:
        if propia:
            conexion.rollback()

        return {
            "ok": False,
            "codigo": "ERROR_BASE_DATOS",
            "mensaje": f"Error al anular la compra: {error}"
        }

    finally:
        if propia:
            conexion.close()
