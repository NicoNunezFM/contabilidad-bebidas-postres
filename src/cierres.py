from datetime import datetime
import calendar
import sqlite3

from database import obtener_conexion
from reportes import resumen_por_periodo


PORCENTAJE_DIEZMO = 0.10


def validar_fechas_periodo(fecha_desde, fecha_hasta):
    """
    Valida que ambas fechas tengan formato YYYY-MM-DD
    y que el período sea válido.
    """

    try:
        desde = datetime.strptime(
            fecha_desde,
            "%Y-%m-%d"
        ).date()

        hasta = datetime.strptime(
            fecha_hasta,
            "%Y-%m-%d"
        ).date()

    except (ValueError, TypeError):
        return False

    if desde > hasta:
        return False

    return True


def registrar_cierre_semanal(fecha_desde, fecha_hasta):

    if not validar_fechas_periodo(
        fecha_desde,
        fecha_hasta
    ):
        return {
            "ok": False,
            "codigo": "FECHAS_INVALIDAS",
            "mensaje": (
                "Las fechas deben tener formato YYYY-MM-DD "
                "y fecha_desde no puede ser posterior a fecha_hasta."
            )
        }

    conexion = obtener_conexion()

    try:
        cursor = conexion.cursor()

        # Evitar cerrar dos veces exactamente el mismo período
        cursor.execute("""
            SELECT id_cierre
            FROM cierres_semanales
            WHERE fecha_desde = ?
            AND fecha_hasta = ?
        """, (
            fecha_desde,
            fecha_hasta
        ))

        cierre_existente = cursor.fetchone()

        if cierre_existente is not None:
            return {
                "ok": False,
                "codigo": "CIERRE_SEMANAL_EXISTENTE",
                "mensaje": "Ese período ya tiene un cierre registrado."
            }

        resumen = resumen_por_periodo(
            fecha_desde,
            fecha_hasta
        )

        resultado_negocio = resumen["resultado_negocio"]

        if resultado_negocio > 0:
            diezmo_estimado = (
                resultado_negocio * PORCENTAJE_DIEZMO
            )
        else:
            diezmo_estimado = 0

        resultado_despues_diezmo = (
            resultado_negocio - diezmo_estimado
        )

        fecha_cierre = datetime.now().strftime(
            "%Y-%m-%d"
        )

        cursor.execute("""
            INSERT INTO cierres_semanales (
                fecha_desde,
                fecha_hasta,
                ventas,
                compras,
                gastos,
                resultado_negocio,
                aportes,
                retiros,
                saldo_caja,
                diezmo,
                resultado_despues_diezmo,
                fecha_cierre
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            fecha_desde,
            fecha_hasta,
            resumen["ventas"],
            resumen["compras"],
            resumen["gastos"],
            resultado_negocio,
            resumen["aportes"],
            resumen["retiros"],
            resumen["saldo_caja"],
            diezmo_estimado,
            resultado_despues_diezmo,
            fecha_cierre
        ))

        id_cierre = cursor.lastrowid

        conexion.commit()

        return {
            "ok": True,
            "codigo": "CIERRE_SEMANAL_REGISTRADO",
            "mensaje": "Cierre semanal registrado correctamente.",
            "id_cierre": id_cierre,
            "fecha_desde": fecha_desde,
            "fecha_hasta": fecha_hasta,
            "ventas": resumen["ventas"],
            "compras": resumen["compras"],
            "gastos": resumen["gastos"],
            "resultado_negocio": resultado_negocio,
            "diezmo_estimado": diezmo_estimado,
            "resultado_despues_diezmo": resultado_despues_diezmo,
            "aportes": resumen["aportes"],
            "retiros": resumen["retiros"],
            "saldo_caja": resumen["saldo_caja"],
            "fecha_cierre": fecha_cierre
        }

    except sqlite3.Error as error:
        conexion.rollback()

        return {
            "ok": False,
            "codigo": "ERROR_BASE_DATOS",
            "mensaje": f"Error al registrar el cierre: {error}"
        }

    finally:
        conexion.close()


def obtener_cierres_semanales():

    conexion = obtener_conexion()

    try:
        cursor = conexion.cursor()

        cursor.execute("""
            SELECT
                id_cierre,
                fecha_desde,
                fecha_hasta,
                ventas,
                compras,
                gastos,
                resultado_negocio,
                aportes,
                retiros,
                saldo_caja,
                diezmo,
                resultado_despues_diezmo,
                fecha_cierre
            FROM cierres_semanales
            ORDER BY fecha_desde DESC
        """)

        cierres_db = cursor.fetchall()

        cierres = []

        for cierre in cierres_db:

            cierre_python = {
                "id_cierre": cierre[0],
                "fecha_desde": cierre[1],
                "fecha_hasta": cierre[2],
                "ventas": cierre[3],
                "compras": cierre[4],
                "gastos": cierre[5],
                "resultado_negocio": cierre[6],
                "aportes": cierre[7],
                "retiros": cierre[8],
                "saldo_caja": cierre[9],
                "diezmo_estimado": cierre[10],
                "resultado_despues_diezmo": cierre[11],
                "fecha_cierre": cierre[12]
            }

            cierres.append(cierre_python)

        return cierres

    finally:
        conexion.close()


def registrar_cierre_mensual(anio, mes):

    if not isinstance(anio, int):
        return {
            "ok": False,
            "codigo": "ANIO_INVALIDO",
            "mensaje": "El año debe ser un número entero."
        }

    if anio < 1:
        return {
            "ok": False,
            "codigo": "ANIO_INVALIDO",
            "mensaje": "El año debe ser mayor que cero."
        }

    if not isinstance(mes, int) or mes < 1 or mes > 12:
        return {
            "ok": False,
            "codigo": "MES_INVALIDO",
            "mensaje": "El mes debe ser un número entre 1 y 12."
        }

    fecha_desde = f"{anio}-{mes:02d}-01"

    ultimo_dia = calendar.monthrange(
        anio,
        mes
    )[1]

    fecha_hasta = (
        f"{anio}-{mes:02d}-{ultimo_dia:02d}"
    )

    hoy = datetime.now().date()

    fecha_fin_mes = datetime.strptime(
        fecha_hasta,
        "%Y-%m-%d"
    ).date()

    if hoy <= fecha_fin_mes:
        return {
            "ok": False,
            "codigo": "MES_NO_TERMINADO",
            "mensaje": "No se puede cerrar un mes que todavía no terminó."
        }

    resumen = resumen_por_periodo(
        fecha_desde,
        fecha_hasta
    )

    resultado_negocio = resumen["resultado_negocio"]

    if resultado_negocio > 0:
        diezmo_correspondiente = (
            resultado_negocio * PORCENTAJE_DIEZMO
        )
    else:
        diezmo_correspondiente = 0

    conexion = obtener_conexion()

    try:
        cursor = conexion.cursor()

        cursor.execute("""
            SELECT id_cierre
            FROM cierres_mensuales
            WHERE anio = ?
            AND mes = ?
        """, (
            anio,
            mes
        ))

        cierre_existente = cursor.fetchone()

        if cierre_existente is not None:
            return {
                "ok": False,
                "codigo": "CIERRE_MENSUAL_EXISTENTE",
                "mensaje": "Ese mes ya tiene un cierre registrado."
            }

        fecha_cierre = datetime.now().strftime(
            "%Y-%m-%d"
        )

        cursor.execute("""
            INSERT INTO cierres_mensuales (
                anio,
                mes,
                fecha_desde,
                fecha_hasta,
                ventas,
                compras,
                gastos,
                resultado_negocio,
                aportes,
                retiros,
                saldo_caja,
                diezmo_correspondiente,
                fecha_cierre
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            anio,
            mes,
            fecha_desde,
            fecha_hasta,
            resumen["ventas"],
            resumen["compras"],
            resumen["gastos"],
            resultado_negocio,
            resumen["aportes"],
            resumen["retiros"],
            resumen["saldo_caja"],
            diezmo_correspondiente,
            fecha_cierre
        ))

        id_cierre = cursor.lastrowid

        conexion.commit()

        return {
            "ok": True,
            "codigo": "CIERRE_MENSUAL_REGISTRADO",
            "mensaje": "Cierre mensual registrado correctamente.",
            "id_cierre": id_cierre,
            "anio": anio,
            "mes": mes,
            "fecha_desde": fecha_desde,
            "fecha_hasta": fecha_hasta,
            "ventas": resumen["ventas"],
            "compras": resumen["compras"],
            "gastos": resumen["gastos"],
            "resultado_negocio": resultado_negocio,
            "aportes": resumen["aportes"],
            "retiros": resumen["retiros"],
            "saldo_caja": resumen["saldo_caja"],
            "diezmo_correspondiente": diezmo_correspondiente,
            "fecha_cierre": fecha_cierre
        }

    except sqlite3.Error as error:
        conexion.rollback()

        return {
            "ok": False,
            "codigo": "ERROR_BASE_DATOS",
            "mensaje": f"Error al registrar cierre mensual: {error}"
        }

    finally:
        conexion.close()


def obtener_cierres_mensuales():

    conexion = obtener_conexion()

    try:
        cursor = conexion.cursor()

        cursor.execute("""
            SELECT
                id_cierre,
                anio,
                mes,
                fecha_desde,
                fecha_hasta,
                ventas,
                compras,
                gastos,
                resultado_negocio,
                aportes,
                retiros,
                saldo_caja,
                diezmo_correspondiente,
                fecha_cierre
            FROM cierres_mensuales
            ORDER BY anio DESC, mes DESC
        """)

        cierres_db = cursor.fetchall()

        cierres = []

        for cierre in cierres_db:

            cierre_python = {
                "id_cierre": cierre[0],
                "anio": cierre[1],
                "mes": cierre[2],
                "fecha_desde": cierre[3],
                "fecha_hasta": cierre[4],
                "ventas": cierre[5],
                "compras": cierre[6],
                "gastos": cierre[7],
                "resultado_negocio": cierre[8],
                "aportes": cierre[9],
                "retiros": cierre[10],
                "saldo_caja": cierre[11],
                "diezmo_correspondiente": cierre[12],
                "fecha_cierre": cierre[13]
            }

            cierres.append(cierre_python)

        return cierres

    finally:
        conexion.close()