"""Lectura contable conjunta del legado y del POS, en una copia ficticia."""
import json
import os

from fastapi import HTTPException

from caja import obtener_caja_seccion, obtener_estado_caja
from pos_caja_diaria import caja_diaria_activa, conciliar_caja_diaria, estado_cajas
from pos_cobros import SECCIONES, estado_cuenta
from pos_simulacion import consultar_cajas_simuladas, transaccion_simulacion


COMANDO_PUENTE_POS = "conciliacion pos"


def exigir_copia_puente(conexion):
    marcada = conexion.execute("""
        SELECT 1 FROM sqlite_schema
        WHERE type = 'table' AND name = 'pos_puente_ficticio'
    """).fetchone()
    if not marcada or conexion.execute("SELECT version FROM pos_puente_ficticio").fetchall() != [(1,)]:
        raise HTTPException(404, "Prepará una copia ficticia para la etapa 5.")


def conciliar_pos(conexion, pos):
    diferencias = []
    for venta, pedido_json, anulada, altas, dev_c, dev_b, cob_c, cob_b in conexion.execute("""
        WITH libro AS (
            SELECT id_venta, SUM(tipo = 'venta') AS altas,
                   SUM(devengado_comidas) AS dev_c, SUM(devengado_bebidas) AS dev_b,
                   SUM(cobrado_comidas) AS cob_c, SUM(cobrado_bebidas) AS cob_b
            FROM pos_eventos_simulados WHERE id_venta IS NOT NULL GROUP BY id_venta
        )
        SELECT v.id_venta, v.pedido, a.id_venta IS NOT NULL, altas, dev_c, dev_b, cob_c, cob_b
        FROM pos_ventas_simuladas AS v
        LEFT JOIN pos_anulaciones_simuladas AS a USING (id_venta)
        LEFT JOIN libro USING (id_venta)
        ORDER BY v.id_venta
    """):
        try:
            pedido = json.loads(pedido_json)
            cuenta = estado_cuenta(conexion, venta, pedido, anulada)
            cantidades = {n: item["cantidad"] for n, item in enumerate(pedido["items"], start=1)}
            total_original = sum(item["cantidad"] * item["precio_unitario_centavos"] for item in pedido["items"])
        except (ValueError, TypeError, KeyError):
            diferencias.append({"codigo": "SNAPSHOT_POS_INVALIDO", "id_venta": venta})
            continue
        esperado = tuple(cuenta[campo][seccion]
                         for campo in ("devengado_centavos", "cobrado_atribuido_centavos")
                         for seccion in SECCIONES)
        devueltas = cuenta["unidades_devueltas"]
        if (altas != 1 or esperado != (dev_c, dev_b, cob_c, cob_b)
                or total_original != cuenta["importe_original_centavos"]
                or not 0 <= cuenta["cobrado_centavos"] <= cuenta["importe_vigente_centavos"]
                or any(cantidad > cantidades.get(linea, 0) for linea, cantidad in devueltas.items())
                or (anulada and devueltas != cantidades)):
            diferencias.append({"codigo": "VENTA_POS_DESCUADRADA", "id_venta": venta})

    for evento, in conexion.execute("""
        SELECT e.id_evento FROM pos_eventos_simulados AS e
        LEFT JOIN pos_movimientos_simulados AS m USING (id_evento)
        GROUP BY e.id_evento
        HAVING e.resultado IS NULL OR e.periodo > ?
            OR COALESCE(SUM(m.importe_centavos), 0) <> e.cobrado_comidas + e.cobrado_bebidas
            OR SUM(m.id_venta IS NOT e.id_venta AND m.id_movimiento IS NOT NULL) > 0
            OR (e.tipo = 'transferencia_interna' AND (
                COUNT(m.id_movimiento) <> 2 OR COUNT(DISTINCT m.caja) <> 2 OR COUNT(m.medio_pago) <> 0))
            OR (e.id_venta IS NOT NULL AND COUNT(m.id_movimiento) <> COUNT(m.medio_pago))
            OR (e.id_venta IS NULL AND (e.devengado_comidas <> 0 OR e.devengado_bebidas <> 0
                OR e.cobrado_comidas <> 0 OR e.cobrado_bebidas <> 0))
            OR (e.tipo = 'cierre' AND (COUNT(m.id_movimiento) <> 0 OR NOT EXISTS (
                SELECT 1 FROM pos_cierres_simulados AS c WHERE c.id_evento = e.id_evento)))
        ORDER BY e.id_evento
    """, (pos["periodo_abierto"],)):
        diferencias.append({"codigo": "EVENTO_POS_DESCUADRADO", "id_evento": evento})

    for movimiento, in conexion.execute("""
        SELECT m.id_movimiento
        FROM pos_movimientos_simulados AS m
        LEFT JOIN pos_movimientos_simulados AS original ON original.id_movimiento = m.revierte
        WHERE m.id_venta IS NOT NULL AND (
            (m.importe_centavos > 0 AND (m.revierte IS NOT NULL OR m.importe_centavos <
                -COALESCE((SELECT SUM(importe_centavos) FROM pos_movimientos_simulados
                           WHERE revierte = m.id_movimiento), 0)))
            OR (m.importe_centavos < 0 AND (
                original.id_movimiento IS NULL OR original.importe_centavos <= 0
                OR original.id_evento >= m.id_evento OR original.id_venta IS NOT m.id_venta
                OR original.receptor <> m.receptor OR original.medio_pago IS NOT m.medio_pago
            ))
        )
        ORDER BY m.id_movimiento
    """):
        diferencias.append({"codigo": "REVERSO_POS_INCONSISTENTE", "id_movimiento": movimiento})

    cierres = conexion.execute("""
        SELECT c.periodo, c.resumen, e.periodo, e.tipo, e.resultado
        FROM pos_cierres_simulados AS c
        LEFT JOIN pos_eventos_simulados AS e USING (id_evento)
        ORDER BY c.periodo
    """)
    for esperado, (periodo, resumen, periodo_evento, tipo, resultado) in enumerate(cierres, start=1):
        try:
            guardado = json.loads(resumen)["resumen"]
        except (ValueError, TypeError, KeyError):
            guardado = None
        if (periodo != esperado or periodo_evento != periodo or tipo != "cierre" or resumen != resultado
                or guardado != consultar_cajas_simuladas(conexion, hasta_periodo=periodo)):
            diferencias.append({"codigo": "CIERRE_POS_DESCUADRADO", "periodo": periodo})
    return diferencias


def leer_conciliacion(conexion):
    exigir_copia_puente(conexion)
    pos = consultar_cajas_simuladas(conexion)
    diferencias = conciliar_pos(conexion, pos)
    caja_diaria = {}
    if caja_diaria_activa(conexion):
        diferencias.extend(conciliar_caja_diaria(conexion))
        caja_diaria["caja_diaria_centavos"] = estado_cajas(conexion)
    return {
        "ok": True,
        "simulacion": True,
        "cuadrado": not diferencias,
        "diferencias": diferencias,
        "pos_centavos": pos,
        **caja_diaria,
        "legado_pesos": {
            "caja_general": obtener_estado_caja(conexion=conexion),
            "secciones": {s: obtener_caja_seccion(s, conexion=conexion) for s in SECCIONES},
            "cierres_semanales": conexion.execute("SELECT COUNT(*) FROM cierres_semanales").fetchone()[0],
            "cierres_mensuales": conexion.execute("SELECT COUNT(*) FROM cierres_mensuales").fetchone()[0],
        },
    }


def consultar_puente_ficticio():
    if os.getenv("ABADION_PUENTE_FICTICIO") != "1":
        raise HTTPException(404, "Puente contable ficticio deshabilitado.")
    with transaccion_simulacion() as conexion:
        return leer_conciliacion(conexion)


def respuesta_puente_bot():
    informe = consultar_puente_ficticio()
    pos = informe["pos_centavos"]
    legado = informe["legado_pesos"]["caja_general"]
    estado = "cuadrado" if informe["cuadrado"] else "con diferencias para revisar"
    lineas = [f"Conciliación ficticia · período POS {pos['periodo_abierto']} · {estado}"]
    for clave, nombre in (("comidas", "Rotisería / Comidas"), ("bebidas_postres", "Bebidas y Postres")):
        seccion = pos["secciones"][clave]
        importes = [formatear_centavos(seccion[campo]) for campo in (
            "devengado_centavos", "cobrado_atribuido_centavos", "por_cobrar_centavos",
        )]
        lineas.append(f"{nombre} · venta {importes[0]} · cobrado atribuido {importes[1]} · fiado {importes[2]}")
    lineas.append(f"Legado · ventas ${legado['ventas']:.2f} · caja disponible ${legado['saldo_disponible']:.2f}")
    return {"ok": True, "respuesta": "\n".join(lineas), "simulacion": True}


def formatear_centavos(centavos):
    pesos, resto = divmod(abs(centavos), 100)
    signo = "-" if centavos < 0 else ""
    return f"{signo}${pesos},{resto:02d}"
