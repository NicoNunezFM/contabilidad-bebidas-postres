from datetime import datetime
import sqlite3

from database import obtener_conexion


TIPOS_MOVIMIENTO = (
    "Aporte",
    "Retiro"
)


# ============================================================
# REGISTRAR MOVIMIENTO DE CAJA
# ============================================================

def registrar_movimiento_caja(
    tipo,
    descripcion,
    monto,
    fecha=None,
    seccion=None,
):
    """
    Registra un aporte o retiro de caja.

    No utiliza input(), por lo que puede ser llamada desde
    terminal, FastAPI, WhatsApp, Notion u otra interfaz.
    """

    # Validar tipo
    if not isinstance(tipo, str):
        return {
            "ok": False,
            "codigo": "DATOS_INVALIDOS",
            "mensaje": "El tipo de movimiento debe ser texto."
        }

    if tipo not in TIPOS_MOVIMIENTO:
        return {
            "ok": False,
            "codigo": "DATOS_INVALIDOS",
            "mensaje": "El tipo de movimiento no es válido."
        }

    # Validar descripción
    if not isinstance(descripcion, str) or not descripcion.strip():
        return {
            "ok": False,
            "codigo": "DATOS_INVALIDOS",
            "mensaje": "La descripción no puede estar vacía."
        }

    # Validar monto
    if isinstance(monto, bool) or not isinstance(
    monto,
    (int, float)
    ):
        return {
            "ok": False,
            "codigo": "DATOS_INVALIDOS",
            "mensaje": "El monto debe ser un número."
        }

    if monto <= 0:
        return {
            "ok": False,
            "codigo": "DATOS_INVALIDOS",
            "mensaje": "El monto debe ser mayor que cero."
        }

    # Fecha automática
    if fecha is None:
        fecha = datetime.now().strftime("%Y-%m-%d")

    conexion = obtener_conexion()

    try:
        cursor = conexion.cursor()

        cursor.execute(
            """
            INSERT INTO movimientos_caja (
                fecha,
                tipo,
                descripcion,
                monto,
                seccion
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                fecha,
                tipo,
                descripcion.strip(),
                monto,
                seccion,
            )
        )

        id_movimiento = cursor.lastrowid

        conexion.commit()

        return {
            "ok": True,
            "codigo": "MOVIMIENTO_CAJA_REGISTRADO",
            "mensaje": "Movimiento de caja registrado correctamente.",
            "id_movimiento": id_movimiento,
            "fecha": fecha,
            "tipo": tipo,
            "descripcion": descripcion.strip(),
            "monto": monto,
            "seccion": seccion,
        }

    except sqlite3.Error as error:
        conexion.rollback()

        return {
            "ok": False,
            "codigo": "ERROR_BASE_DATOS",
            "mensaje": (
                f"Error al registrar movimiento de caja: {error}"
            )
        }

    finally:
        conexion.close()


# ============================================================
# REGISTRAR RETIRO
# ============================================================

def registrar_retiro(
    descripcion,
    monto,
    fecha=None,
    seccion=None,
):
    """
    Registra un retiro de dinero de la caja.
    """

    return registrar_movimiento_caja(
        tipo="Retiro",
        descripcion=descripcion,
        monto=monto,
        fecha=fecha,
        seccion=seccion,
    )


# ============================================================
# REGISTRAR APORTE
# ============================================================

def registrar_aporte(
    descripcion,
    monto,
    fecha=None,
    seccion=None,
):
    """
    Registra un aporte de dinero a la caja.
    """

    return registrar_movimiento_caja(
        tipo="Aporte",
        descripcion=descripcion,
        monto=monto,
        fecha=fecha,
        seccion=seccion,
    )


# ============================================================
# OBTENER MOVIMIENTOS DE CAJA
# ============================================================

def obtener_movimientos_caja():
    """
    Devuelve todos los movimientos de caja como una lista
    de diccionarios.
    """

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute(
        """
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
        """
    )

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


# ============================================================
# TOTAL DE APORTES
# ============================================================

def total_aportes():
    """
    Devuelve el total de aportes activos.
    """

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute(
        """
        SELECT SUM(monto)
        FROM movimientos_caja
        WHERE tipo = 'Aporte'
        AND anulado = 0
        """
    )

    resultado = cursor.fetchone()

    conexion.close()

    total = resultado[0]

    if total is None:
        total = 0

    return total


# ============================================================
# TOTAL DE RETIROS
# ============================================================

def total_retiros():
    """
    Devuelve el total de retiros activos.
    """

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute(
        """
        SELECT SUM(monto)
        FROM movimientos_caja
        WHERE tipo = 'Retiro'
        AND anulado = 0
        """
    )

    resultado = cursor.fetchone()

    conexion.close()

    total = resultado[0]

    if total is None:
        total = 0

    return total


# ============================================================
# TOTAL DE MOVIMIENTOS POR PERÍODO
# ============================================================

def total_movimientos_por_periodo(
    tipo,
    fecha_desde,
    fecha_hasta
):
    """
    Calcula el total de aportes o retiros activos
    dentro de un período.
    """

    if tipo not in TIPOS_MOVIMIENTO:
        return 0

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute(
        """
        SELECT SUM(monto)
        FROM movimientos_caja
        WHERE tipo = ?
        AND fecha BETWEEN ? AND ?
        AND anulado = 0
        """,
        (
            tipo,
            fecha_desde,
            fecha_hasta
        )
    )

    resultado = cursor.fetchone()

    conexion.close()

    total = resultado[0]

    if total is None:
        total = 0

    return total


# ============================================================
# TOTAL DE APORTES POR PERÍODO
# ============================================================

def total_aportes_por_periodo(
    fecha_desde,
    fecha_hasta
):

    return total_movimientos_por_periodo(
        "Aporte",
        fecha_desde,
        fecha_hasta
    )


# ============================================================
# TOTAL DE RETIROS POR PERÍODO
# ============================================================

def total_retiros_por_periodo(
    fecha_desde,
    fecha_hasta
):

    return total_movimientos_por_periodo(
        "Retiro",
        fecha_desde,
        fecha_hasta
    )


# ============================================================
# ANULAR MOVIMIENTO DE CAJA
# ============================================================

def anular_movimiento_caja(
    id_movimiento,
    motivo
):
    """
    Anula un aporte o retiro sin eliminarlo de la base de datos.
    """

    # Validar ID
    if isinstance(id_movimiento, bool) or not isinstance(
    id_movimiento,
    int
    ):
        return {
            "ok": False,
            "codigo": "DATOS_INVALIDOS",
            "mensaje": (
                "El ID del movimiento debe ser un número entero."
            )
        }

    # Validar motivo
    if not isinstance(motivo, str) or not motivo.strip():
        return {
            "ok": False,
            "codigo": "DATOS_INVALIDOS",
            "mensaje": (
                "El motivo de anulación no puede estar vacío."
            )
        }

    conexion = obtener_conexion()

    try:
        cursor = conexion.cursor()

        cursor.execute(
            """
            SELECT
                tipo,
                monto,
                anulado
            FROM movimientos_caja
            WHERE id_movimiento = ?
            """,
            (id_movimiento,)
        )

        movimiento = cursor.fetchone()

        # Movimiento inexistente
        if movimiento is None:
            return {
                "ok": False,
                "codigo": "MOVIMIENTO_CAJA_NO_ENCONTRADO",
                "mensaje": "Movimiento de caja no encontrado."
            }

        tipo = movimiento[0]
        monto = movimiento[1]
        anulado = movimiento[2]

        # Movimiento ya anulado
        if anulado == 1:
            return {
                "ok": False,
                "codigo": "MOVIMIENTO_CAJA_YA_ANULADO",
                "mensaje": (
                    "El movimiento de caja ya se encuentra anulado."
                )
            }

        fecha_anulacion = datetime.now().strftime("%Y-%m-%d")

        cursor.execute(
            """
            UPDATE movimientos_caja
            SET
                anulado = 1,
                fecha_anulacion = ?,
                motivo_anulacion = ?
            WHERE id_movimiento = ?
            """,
            (
                fecha_anulacion,
                motivo.strip(),
                id_movimiento
            )
        )

        conexion.commit()

        return {
            "ok": True,
            "codigo": "MOVIMIENTO_CAJA_ANULADO",
            "mensaje": (
                "Movimiento de caja anulado correctamente."
            ),
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
            "codigo": "ERROR_BASE_DATOS",
            "mensaje": (
                f"Error al anular movimiento de caja: {error}"
            )
        }

    finally:
        conexion.close()


def total_movimientos_seccion(
    seccion,
    tipo,
    id_movimiento_corte=0,
):
    if tipo not in TIPOS_MOVIMIENTO:
        return 0

    conexion = obtener_conexion()

    try:
        total = conexion.execute(
            """
            SELECT COALESCE(SUM(monto), 0)
            FROM movimientos_caja
            WHERE tipo = ?
              AND anulado = 0
              AND seccion = ?
              AND id_movimiento > ?
            """,
            (
                tipo,
                seccion,
                int(id_movimiento_corte or 0),
            )
        ).fetchone()[0]

        return total or 0

    finally:
        conexion.close()
