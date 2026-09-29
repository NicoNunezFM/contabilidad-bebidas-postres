from datetime import datetime
import sqlite3

from database import obtener_conexion

TIPOS_MOVIMIENTO = (
    "Aporte",
    "Retiro"
)

def registrar_movimiento_caja(
    tipo,
    descripcion,
    monto,
    fecha=None
):

    if not isinstance(tipo, str):
        return {
            "ok": False,
            "mensaje": "El tipo de movimiento debe ser texto."
        }

    if tipo not in TIPOS_MOVIMIENTO:
        return {
            "ok": False,
            "mensaje": "El tipo de movimiento no es válido."
        }

    if not isinstance(descripcion, str) or not descripcion.strip():
        return {
            "ok": False,
            "mensaje": "La descripción no puede estar vacía."
        }

    if not isinstance(monto, (int, float)):
        return {
            "ok": False,
            "mensaje": "El monto debe ser un número."
        }

    if monto <= 0:
        return {
            "ok": False,
            "mensaje": "El monto debe ser mayor que cero."
        }

    if fecha is None:
        fecha = datetime.now().strftime("%Y-%m-%d")

    conexion = obtener_conexion()

    try:
        cursor = conexion.cursor()

        cursor.execute("""
            INSERT INTO movimientos_caja (
                fecha,
                tipo,
                descripcion,
                monto
            )
            VALUES (?, ?, ?, ?)
        """, (
            fecha,
            tipo,
            descripcion.strip(),
            monto
        ))

        id_movimiento = cursor.lastrowid

        conexion.commit()

        return {
            "ok": True,
            "mensaje": "Movimiento de caja registrado correctamente.",
            "id_movimiento": id_movimiento,
            "fecha": fecha,
            "tipo": tipo,
            "descripcion": descripcion.strip(),
            "monto": monto
        }

    except sqlite3.Error as error:
        conexion.rollback()

        return {
            "ok": False,
            "mensaje": f"Error al registrar movimiento: {error}"
        }

    finally:
        conexion.close()

def registrar_retiro(descripcion, monto, fecha=None):

    return registrar_movimiento_caja(
        tipo="Retiro",
        descripcion=descripcion,
        monto=monto,
        fecha=fecha
    )


def registrar_aporte(descripcion, monto, fecha=None):

    return registrar_movimiento_caja(
        tipo="Aporte",
        descripcion=descripcion,
        monto=monto,
        fecha=fecha
    )

def obtener_movimientos_caja():

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute("""
    SELECT
        id_movimiento,
        fecha,
        tipo,
        descripcion,
        monto,
        anulado,
        fecha_anulacion,
        motivo_anulacion
    FROM movimientos_caja
    ORDER BY id_movimiento
    """)

    movimientos_db = cursor.fetchall()

    conexion.close()

    movimientos = []

    for movimiento in movimientos_db:

        movimiento_python = {
        "id_movimiento": movimiento[0],
        "fecha": movimiento[1],
        "tipo": movimiento[2],
        "descripcion": movimiento[3],
        "monto": movimiento[4],
        "anulado": bool(movimiento[5]),
        "fecha_anulacion": movimiento[6],
        "motivo_anulacion": movimiento[7]
    }

        movimientos.append(movimiento_python)

    return movimientos

def total_aportes():

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute("""
    SELECT SUM(monto)
    FROM movimientos_caja
    WHERE tipo = 'Aporte'
    AND anulado = 0
    """)

    resultado = cursor.fetchone()
    conexion.close()

    total = resultado[0]

    if total is None:
        total = 0

    return total

def total_retiros():

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute("""
    SELECT SUM(monto)
    FROM movimientos_caja
    WHERE tipo = 'Retiro'
    AND anulado = 0
    """)

    resultado = cursor.fetchone()
    conexion.close()

    total = resultado[0]

    if total is None:
        total = 0

    return total

def total_movimientos_por_periodo(
    tipo,
    fecha_desde,
    fecha_hasta
):

    if tipo not in TIPOS_MOVIMIENTO:
        return 0

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute("""
        SELECT SUM(monto)
        FROM movimientos_caja
        WHERE tipo = ?
        AND fecha BETWEEN ? AND ?
        AND anulado = 0
    """, (
        tipo,
        fecha_desde,
        fecha_hasta
    ))

    resultado = cursor.fetchone()
    conexion.close()

    total = resultado[0]

    if total is None:
        total = 0

    return total

def total_aportes_por_periodo(fecha_desde, fecha_hasta):

    return total_movimientos_por_periodo(
        "Aporte",
        fecha_desde,
        fecha_hasta
    )


def total_retiros_por_periodo(fecha_desde, fecha_hasta):

    return total_movimientos_por_periodo(
        "Retiro",
        fecha_desde,
        fecha_hasta
    )

def anular_movimiento_caja(id_movimiento, motivo):

    if not isinstance(id_movimiento, int):
        return {
            "ok": False,
            "mensaje": "El ID del movimiento debe ser un número entero."
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
                tipo,
                monto,
                anulado
            FROM movimientos_caja
            WHERE id_movimiento = ?
        """, (id_movimiento,))

        movimiento = cursor.fetchone()

        if movimiento is None:
            return {
                "ok": False,
                "mensaje": "Movimiento de caja no encontrado."
            }

        tipo = movimiento[0]
        monto = movimiento[1]
        anulado = movimiento[2]

        if anulado == 1:
            return {
                "ok": False,
                "mensaje": "El movimiento ya se encuentra anulado."
            }

        fecha_anulacion = datetime.now().strftime("%Y-%m-%d")

        cursor.execute("""
            UPDATE movimientos_caja
            SET
                anulado = 1,
                fecha_anulacion = ?,
                motivo_anulacion = ?
            WHERE id_movimiento = ?
        """, (
            fecha_anulacion,
            motivo.strip(),
            id_movimiento
        ))

        conexion.commit()

        return {
            "ok": True,
            "mensaje": "Movimiento de caja anulado correctamente.",
            "id_movimiento": id_movimiento,
            "tipo": tipo,
            "monto": monto,
            "fecha_anulacion": fecha_anulacion,
            "motivo": motivo.strip()
        }

    except sqlite3.Error as error:
        conexion.rollback()

        return {
            "ok": False,
            "mensaje": f"Error al anular movimiento: {error}"
        }

    finally:
        conexion.close()