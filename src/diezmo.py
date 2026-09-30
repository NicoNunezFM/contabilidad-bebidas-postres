from datetime import datetime
import sqlite3
import calendar

from database import obtener_conexion
from reportes import resumen_por_periodo


PORCENTAJE_DIEZMO = 0.10

TIPOS_MOVIMIENTO_DIEZMO = (
    "Reserva",
    "Entrega"
)


# ============================================================
# VALIDACIONES
# ============================================================

def validar_fecha(fecha):

    try:
        datetime.strptime(
            fecha,
            "%Y-%m-%d"
        )

        return True

    except (ValueError, TypeError):

        return False


# ============================================================
# REGISTRAR MOVIMIENTO DE DIEZMO
# ============================================================

def registrar_movimiento_diezmo(
    anio,
    mes,
    tipo,
    monto,
    descripcion,
    fecha=None
):

    if not isinstance(anio, int) or anio < 1:
        return {
            "ok": False,
            "codigo": "ANIO_INVALIDO",
            "mensaje": "El año debe ser un número entero mayor que cero."
        }

    if not isinstance(mes, int) or mes < 1 or mes > 12:
        return {
            "ok": False,
            "codigo": "MES_INVALIDO",
            "mensaje": "El mes debe estar entre 1 y 12."
        }

    if tipo not in TIPOS_MOVIMIENTO_DIEZMO:
        return {
            "ok": False,
            "codigo": "TIPO_MOVIMIENTO_INVALIDO",
            "mensaje": "El tipo de movimiento no es válido."
        }

    if not isinstance(monto, (int, float)):
        return {
            "ok": False,
            "codigo": "MONTO_INVALIDO",
            "mensaje": "El monto debe ser un número."
        }

    if monto <= 0:
        return {
            "ok": False,
            "codigo": "MONTO_INVALIDO",
            "mensaje": "El monto debe ser mayor que cero."
        }

    if not isinstance(descripcion, str) or not descripcion.strip():
        return {
            "ok": False,
            "codigo": "DESCRIPCION_INVALIDA",
            "mensaje": "La descripción no puede estar vacía."
        }

    if fecha is None:
        fecha = datetime.now().strftime("%Y-%m-%d")

    elif not validar_fecha(fecha):
        return {
            "ok": False,
            "codigo": "FECHA_INVALIDA",
            "mensaje": "La fecha debe tener formato YYYY-MM-DD."
        }

    conexion = obtener_conexion()

    try:

        cursor = conexion.cursor()

        cursor.execute("""
            INSERT INTO movimientos_diezmo (
                anio,
                mes,
                fecha,
                tipo,
                monto,
                descripcion
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            anio,
            mes,
            fecha,
            tipo,
            monto,
            descripcion.strip()
        ))

        id_movimiento = cursor.lastrowid

        conexion.commit()

        return {
            "ok": True,
            "codigo": "MOVIMIENTO_DIEZMO_REGISTRADO",
            "mensaje": "Movimiento de diezmo registrado correctamente.",
            "id_movimiento": id_movimiento,
            "anio": anio,
            "mes": mes,
            "fecha": fecha,
            "tipo": tipo,
            "monto": monto,
            "descripcion": descripcion.strip()
        }

    except sqlite3.Error as error:

        conexion.rollback()

        return {
            "ok": False,
            "codigo": "ERROR_BASE_DATOS",
            "mensaje": (
                f"Error al registrar movimiento de diezmo: {error}"
            )
        }

    finally:

        conexion.close()


# ============================================================
# REGISTRAR RESERVA
# ============================================================

def registrar_reserva_diezmo(
    anio,
    mes,
    monto,
    descripcion="Reserva para diezmo",
    fecha=None
):

    if not isinstance(monto, (int, float)):
        return {
            "ok": False,
            "codigo": "MONTO_INVALIDO",
            "mensaje": "El monto debe ser un número."
        }

    if monto <= 0:
        return {
            "ok": False,
            "codigo": "MONTO_INVALIDO",
            "mensaje": "El monto debe ser mayor que cero."
        }

    estado = estado_diezmo_mes(
        anio,
        mes
    )

    if not estado["ok"]:
        return estado

    if estado.get("futuro", False):

        return {
            "ok": False,
            "codigo": "MES_FUTURO",
            "mensaje": (
                "No se puede reservar diezmo para "
                "un mes que todavía no comenzó."
            )
        }

    # Si el mes ya está cerrado, no permitimos reservar
    # más de lo que corresponde definitivamente.
    if estado["cerrado"]:

        pendiente = estado["pendiente_reservar"]

        if monto > pendiente:

            return {
                "ok": False,
                "codigo": "RESERVA_EXCEDE_PENDIENTE",
                "mensaje": (
                    f"El monto supera lo pendiente de reservar. "
                    f"Pendiente: ${pendiente:.2f}"
                )
            }

    return registrar_movimiento_diezmo(
        anio=anio,
        mes=mes,
        tipo="Reserva",
        monto=monto,
        descripcion=descripcion,
        fecha=fecha
    )


# ============================================================
# REGISTRAR ENTREGA
# ============================================================

def registrar_entrega_diezmo(
    anio,
    mes,
    monto,
    descripcion="Entrega de diezmo",
    fecha=None
):

    if not isinstance(monto, (int, float)):
        return {
            "ok": False,
            "codigo": "MONTO_INVALIDO",
            "mensaje": "El monto debe ser un número."
        }

    if monto <= 0:
        return {
            "ok": False,
            "codigo": "MONTO_INVALIDO",
            "mensaje": "El monto debe ser mayor que cero."
        }

    estado = estado_diezmo_mes(
        anio,
        mes
    )

    if not estado["ok"]:
        return estado

    if not estado["cerrado"]:

        return {
            "ok": False,
            "codigo": "MES_NO_CERRADO",
            "mensaje": (
                "No se puede registrar una entrega "
                "porque el mes todavía no está cerrado."
            )
        }

    pendiente = estado["pendiente_entregar"]

    if monto > pendiente:

        return {
            "ok": False,
            "codigo": "ENTREGA_EXCEDE_PENDIENTE",
            "mensaje": (
                f"El monto supera lo pendiente de entregar. "
                f"Pendiente: ${pendiente:.2f}"
            )
        }

    return registrar_movimiento_diezmo(
        anio=anio,
        mes=mes,
        tipo="Entrega",
        monto=monto,
        descripcion=descripcion,
        fecha=fecha
    )


# ============================================================
# TOTAL DE MOVIMIENTOS DE DIEZMO
# ============================================================

def total_movimientos_diezmo(
    anio,
    mes,
    tipo
):

    conexion = obtener_conexion()

    try:

        cursor = conexion.cursor()

        cursor.execute("""
            SELECT SUM(monto)
            FROM movimientos_diezmo
            WHERE anio = ?
            AND mes = ?
            AND tipo = ?
            AND anulado = 0
        """, (
            anio,
            mes,
            tipo
        ))

        resultado = cursor.fetchone()

        total = resultado[0]

        if total is None:
            total = 0

        return total

    finally:

        conexion.close()


# ============================================================
# ESTADO DEL DIEZMO DE UN MES
# ============================================================

def estado_diezmo_mes(
    anio,
    mes
):

    if not isinstance(anio, int) or anio < 1:

        return {
            "ok": False,
            "codigo": "ANIO_INVALIDO",
            "mensaje": (
                "El año debe ser un número entero "
                "mayor que cero."
            )
        }

    if not isinstance(mes, int) or mes < 1 or mes > 12:

        return {
            "ok": False,
            "codigo": "MES_INVALIDO",
            "mensaje": "El mes debe estar entre 1 y 12."
        }

    reservado = total_movimientos_diezmo(
        anio,
        mes,
        "Reserva"
    )

    entregado = total_movimientos_diezmo(
        anio,
        mes,
        "Entrega"
    )

    conexion = obtener_conexion()

    try:

        cursor = conexion.cursor()

        cursor.execute("""
            SELECT
                diezmo_correspondiente,
                resultado_negocio
            FROM cierres_mensuales
            WHERE anio = ?
            AND mes = ?
        """, (
            anio,
            mes
        ))

        cierre = cursor.fetchone()

    finally:

        conexion.close()

    # ========================================================
    # MES SIN CIERRE DEFINITIVO
    # ========================================================

    if cierre is None:

        hoy = datetime.now().date()

        mes_consultado = (
            anio,
            mes
        )

        mes_actual = (
            hoy.year,
            hoy.month
        )

        # ----------------------------------------------------
        # MES FUTURO
        # ----------------------------------------------------

        if mes_consultado > mes_actual:

            return {
                "ok": True,
                "cerrado": False,
                "futuro": True,
                "anio": anio,
                "mes": mes,
                "resultado_estimado": None,
                "diezmo_estimado": None,
                "reservado": reservado,
                "entregado": entregado,
                "diezmo_correspondiente": None,
                "pendiente_reservar": None,
                "pendiente_entregar": None,
                "mensaje": (
                    "El mes consultado todavía no comenzó."
                )
            }

        fecha_desde = (
            f"{anio}-{mes:02d}-01"
        )

        # ----------------------------------------------------
        # MES ACTUAL
        # ----------------------------------------------------

        if mes_consultado == mes_actual:

            fecha_hasta = hoy.strftime(
                "%Y-%m-%d"
            )

            estado_mes = "abierto"

        # ----------------------------------------------------
        # MES PASADO SIN CIERRE
        # ----------------------------------------------------

        else:

            ultimo_dia = calendar.monthrange(
                anio,
                mes
            )[1]

            fecha_hasta = (
                f"{anio}-{mes:02d}-{ultimo_dia:02d}"
            )

            estado_mes = "pendiente_cierre"

        resumen = resumen_por_periodo(
            fecha_desde,
            fecha_hasta
        )

        resultado_estimado = (
            resumen["resultado_negocio"]
        )

        if resultado_estimado > 0:

            diezmo_estimado = (
                resultado_estimado *
                PORCENTAJE_DIEZMO
            )

        else:

            diezmo_estimado = 0

        diferencia_estimada = (
            diezmo_estimado - reservado
        )

        if diferencia_estimada < 0:
            diferencia_estimada = 0

        return {
            "ok": True,
            "cerrado": False,
            "futuro": False,
            "estado_mes": estado_mes,
            "anio": anio,
            "mes": mes,
            "fecha_desde": fecha_desde,
            "fecha_hasta": fecha_hasta,
            "resultado_estimado": resultado_estimado,
            "diezmo_estimado": diezmo_estimado,
            "reservado": reservado,
            "diferencia_estimada_reserva": diferencia_estimada,
            "entregado": entregado,
            "diezmo_correspondiente": None,
            "pendiente_reservar": None,
            "pendiente_entregar": None,
            "mensaje": (
                "Los valores son estimativos porque "
                "el mes todavía no tiene un cierre definitivo."
            )
        }

    # ========================================================
    # MES CON CIERRE DEFINITIVO
    # ========================================================

    diezmo_correspondiente = cierre[0]
    resultado_negocio = cierre[1]

    pendiente_reservar = (
        diezmo_correspondiente - reservado
    )

    exceso_reservado = 0

    if pendiente_reservar < 0:

        exceso_reservado = abs(
            pendiente_reservar
        )

        pendiente_reservar = 0

    pendiente_entregar = (
        diezmo_correspondiente - entregado
    )

    if pendiente_entregar < 0:
        pendiente_entregar = 0

    return {
        "ok": True,
        "cerrado": True,
        "anio": anio,
        "mes": mes,
        "resultado_negocio": resultado_negocio,
        "diezmo_correspondiente": diezmo_correspondiente,
        "reservado": reservado,
        "pendiente_reservar": pendiente_reservar,
        "exceso_reservado": exceso_reservado,
        "entregado": entregado,
        "pendiente_entregar": pendiente_entregar
    }


# ============================================================
# ESTADO GENERAL DEL DIEZMO
# ============================================================

def estado_general_diezmo():

    conexion = obtener_conexion()

    try:

        cursor = conexion.cursor()

        cursor.execute("""
            SELECT
                tipo,
                SUM(monto)
            FROM movimientos_diezmo
            WHERE anulado = 0
            GROUP BY tipo
        """)

        resultados = cursor.fetchall()

    finally:

        conexion.close()

    total_reservado = 0
    total_entregado = 0

    for resultado in resultados:

        tipo = resultado[0]
        monto = resultado[1]

        if tipo == "Reserva":
            total_reservado = monto

        elif tipo == "Entrega":
            total_entregado = monto

    reservado_en_caja = (
        total_reservado -
        total_entregado
    )

    if reservado_en_caja < 0:
        reservado_en_caja = 0

    return {
        "reservado_total": total_reservado,
        "entregado_total": total_entregado,
        "reservado_en_caja": reservado_en_caja
    }