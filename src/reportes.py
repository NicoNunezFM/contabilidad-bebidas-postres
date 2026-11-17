from datetime import datetime, timedelta
from database import lectura_contable, obtener_conexion
from pos_contabilidad import calcular_periodo, corte_contable, etapa_contable_activa, fecha_local
from movimientos_caja import (
    total_aportes_por_periodo,
    total_retiros_por_periodo
)


def ventas_del_dia(fecha=None):

    if fecha is None:
        fecha = datetime.now().strftime("%Y-%m-%d")

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute("""
        SELECT SUM(
            cantidad * precio_unitario
            + COALESCE(
                (
                    SELECT SUM(precio_total)
                    FROM venta_adicionales
                    WHERE venta_adicionales.id_venta = ventas.id_venta
                ),
                0
            )
        )
        FROM ventas
        WHERE fecha = ?
        AND anulada = 0
    """, (fecha,))

    resultado = cursor.fetchone()
    conexion.close()

    total = resultado[0]

    if total is None:
        total = 0 

    return total

def compras_del_dia(fecha=None):

    if fecha is None:
        fecha = datetime.now().strftime("%Y-%m-%d")

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute("""
        SELECT SUM(cantidad * precio_unitario)
        FROM compras
        WHERE fecha = ?
        AND anulada = 0
    """, (fecha,))
    
    resultado = cursor.fetchone()
    conexion.close()

    total = resultado[0]

    if total is None:
        total = 0

    return total

def gastos_del_dia(fecha=None):

    if fecha is None:
        fecha = datetime.now().strftime("%Y-%m-%d")

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute("""
    SELECT SUM(valor_final)
    FROM gastos
    WHERE fecha = ?
    AND anulado = 0
    """, (fecha,))

    resultado = cursor.fetchone()
    conexion.close()

    total = resultado [0]

    if total is None:
        total = 0

    return total

def resumen_del_dia(fecha=None):

    ventas = ventas_del_dia(fecha)
    compras = compras_del_dia(fecha)
    gastos = gastos_del_dia(fecha)

    resultado = ventas - compras - gastos

    return {
        "ventas" : ventas,
        "compras" : compras,
        "gastos" : gastos,
        "resultado" : resultado
    }

def ventas_por_periodo(fecha_desde, fecha_hasta):

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute("""
        SELECT SUM(
            cantidad * precio_unitario
            + COALESCE(
                (
                    SELECT SUM(precio_total)
                    FROM venta_adicionales
                    WHERE venta_adicionales.id_venta = ventas.id_venta
                ),
                0
            )
        )
        FROM ventas
        WHERE fecha BETWEEN ? AND ?
        AND anulada = 0
    """, (fecha_desde, fecha_hasta))

    resultado = cursor.fetchone()
    conexion.close()

    total = resultado[0]

    if total is None:
        total = 0

    return total

def compras_por_periodo(fecha_desde, fecha_hasta):

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute("""
        SELECT SUM(cantidad * precio_unitario)
        FROM compras
        WHERE fecha BETWEEN ? AND ?
        AND anulada = 0
    """, (fecha_desde, fecha_hasta))

    resultado = cursor.fetchone()
    conexion.close()
    
    total = resultado[0]
    
    if total is None:
        total = 0
    
    return total

def gastos_por_periodo(fecha_desde, fecha_hasta):

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute("""
    SELECT SUM(valor_final)
    FROM gastos
    WHERE fecha BETWEEN ? AND ?
    AND anulado = 0
    """, (fecha_desde, fecha_hasta))

    resultado = cursor.fetchone()
    conexion.close()
    
    total = resultado[0]
    
    if total is None:
        total = 0
    
    return total

def resumen_pos_periodo(fecha_desde, fecha_hasta, *, conexion=None):
    with lectura_contable(conexion) as db:
        if conexion is None:
            db.execute("BEGIN")
        if not etapa_contable_activa(db) or fecha_hasta < corte_contable(db)[0]:
            return None
        return calcular_periodo(db, fecha_desde, fecha_hasta)


def resumen_por_periodo(fecha_desde, fecha_hasta, *, conexion=None):
    informe = resumen_pos_periodo(fecha_desde, fecha_hasta, conexion=conexion)
    if informe is not None:
        def pesos(campo):
            return informe[campo + "_centavos"] / 100

        aportes = pesos("aportes_fisicos")
        retiros = pesos("retiros_fisicos")
        cobrado_fisico = sum(
            fila["neto_centavos"] for fila in informe["cobros_por_receptor"]
            if fila["medio_pago"] == "efectivo"
        )
        movimiento_fisico = (
            cobrado_fisico - informe["gastos_con_receptor_centavos"]
            + informe["aportes_fisicos_centavos"] - informe["retiros_fisicos_centavos"]
        )
        return {
            "fecha_desde": fecha_desde, "fecha_hasta": fecha_hasta,
            "ventas": pesos("devengado"), "compras": pesos("compras"), "gastos": pesos("gastos"),
            "resultado_negocio": pesos("resultado_devengado"),
            "resultado_base_diezmo": pesos("resultado_base_diezmo"), "diezmo_estimado": pesos("diezmo"),
            "aportes": aportes, "retiros": retiros,
            "saldo_caja": movimiento_fisico / 100,
            "contabilidad_centavos": informe,
        }


    ventas = ventas_por_periodo(fecha_desde, fecha_hasta)
    compras = compras_por_periodo(fecha_desde, fecha_hasta)
    gastos = gastos_por_periodo(fecha_desde, fecha_hasta)

    aportes = total_aportes_por_periodo(
        fecha_desde,
        fecha_hasta
    )

    retiros = total_retiros_por_periodo(
        fecha_desde,
        fecha_hasta
    )

    resultado_negocio = ventas - compras - gastos

    saldo_caja = (
        resultado_negocio
        + aportes
        - retiros
    )

    return {
        "fecha_desde": fecha_desde,
        "fecha_hasta": fecha_hasta,
        "ventas": ventas,
        "compras": compras,
        "gastos": gastos,
        "resultado_negocio": resultado_negocio,
        "aportes": aportes,
        "retiros": retiros,
        "saldo_caja": saldo_caja
    }
def resumen_semana_actual():

    hoy = datetime.fromisoformat(fecha_reporte_hoy())

    inicio_semana = hoy - timedelta(days=hoy.weekday())

    fecha_desde = inicio_semana.strftime("%Y-%m-%d")
    fecha_hasta = hoy.strftime("%Y-%m-%d")

    return resumen_por_periodo(fecha_desde, fecha_hasta)

def resumen_mes_actual():

    hoy = datetime.fromisoformat(fecha_reporte_hoy())

    inicio_mes = hoy.replace(day=1)

    fecha_desde = inicio_mes.strftime("%Y-%m-%d")
    fecha_hasta = hoy.strftime("%Y-%m-%d")

    return resumen_por_periodo(fecha_desde, fecha_hasta)

def fecha_reporte_hoy():
    with lectura_contable() as db:
        if etapa_contable_activa(db):
            return fecha_local()
    return datetime.now().date().isoformat()
