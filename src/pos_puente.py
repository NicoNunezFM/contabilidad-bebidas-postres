"""Lectura contable conjunta del legado y del POS, en una copia ficticia."""
import json
import os

from fastapi import HTTPException

from caja import obtener_caja_seccion, obtener_estado_caja
from database import RUTA_ENTRENAMIENTO
from pos_caja_diaria import caja_diaria_activa, conciliar_caja_diaria, estado_cajas
from pos_cobros import SECCIONES, estado_cuenta
from pos_contabilidad import calcular_periodo, corte_contable, etapa_contable_activa, fecha_local
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
            envio = pedido.get("envio")
            if envio and envio["titular"] == "negocio":
                total_original += envio["importe_centavos"]
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

    tablas = {nombre for nombre, in conexion.execute(
        "SELECT name FROM sqlite_schema WHERE type = 'table'"
    )}
    rendiciones = (
        "SELECT id_evento, id_cobro, importe_centavos FROM pos_rendiciones_efectivo"
        if "pos_rendiciones_efectivo" in tablas else "SELECT NULL, NULL, NULL WHERE 0"
    )
    fondos = (
        "SELECT id_evento FROM pos_fondos_reparto"
        if "pos_fondos_reparto" in tablas else "SELECT NULL WHERE 0"
    )
    delivery = ("SELECT id_evento, id_movimiento, receptor, importe_centavos FROM pos_delivery_movimientos"
                if "pos_delivery_movimientos" in tablas else "SELECT NULL, NULL, NULL, NULL WHERE 0")
    for evento, in conexion.execute(f"""
        WITH rendicion(id_evento, id_cobro, importe) AS ({rendiciones}),
             reparto(id_evento) AS ({fondos}),
             delivery(id_evento, id_movimiento, receptor, importe) AS ({delivery})
        SELECT e.id_evento FROM pos_eventos_simulados AS e
        LEFT JOIN pos_movimientos_simulados AS m USING (id_evento)
        LEFT JOIN rendicion AS r ON r.id_evento = e.id_evento
        LEFT JOIN reparto AS f ON f.id_evento = e.id_evento
        LEFT JOIN delivery AS d ON d.id_evento = e.id_evento
        LEFT JOIN pos_movimientos_simulados AS origen ON origen.id_movimiento = r.id_cobro
        GROUP BY e.id_evento
        HAVING e.resultado IS NULL OR e.periodo > ?
            OR COALESCE(SUM(m.importe_centavos), 0) - CASE WHEN d.id_movimiento IS NOT NULL THEN d.importe ELSE 0 END <> e.cobrado_comidas + e.cobrado_bebidas
            OR SUM(m.id_venta IS NOT e.id_venta AND m.id_movimiento IS NOT NULL) > 0
            OR (e.tipo = 'transferencia_interna' AND NOT CASE
                WHEN d.id_evento IS NOT NULL AND d.receptor='repartidor_directo' THEN COUNT(m.id_movimiento)=0 AND d.id_movimiento IS NULL
                    AND r.id_evento IS NULL AND f.id_evento IS NULL
                WHEN d.id_evento IS NOT NULL THEN COUNT(m.id_movimiento)=1 AND COUNT(m.medio_pago)=0
                    AND m.id_movimiento=d.id_movimiento AND m.receptor=d.receptor
                    AND m.importe_centavos=d.importe AND r.id_evento IS NULL AND f.id_evento IS NULL
                WHEN f.id_evento IS NOT NULL THEN COUNT(m.id_movimiento) = 0 AND r.id_evento IS NULL
                WHEN r.id_evento IS NOT NULL THEN
                    origen.id_movimiento IS NOT NULL AND origen.id_evento < e.id_evento
                    AND origen.receptor IN ('comidas_efectivo_en_transito', 'bebidas_postres_efectivo_en_transito')
                    AND COUNT(m.id_movimiento) = 2 AND COUNT(m.medio_pago) = 0
                    AND SUM(m.receptor = origen.receptor AND m.importe_centavos = -r.importe) = 1
                    AND SUM(m.receptor || '_en_transito' = origen.receptor AND m.importe_centavos = r.importe) = 1
                ELSE COUNT(m.id_movimiento) = 2 AND COUNT(DISTINCT m.receptor) = 2 AND COUNT(m.medio_pago) = 0
                    AND SUM(m.receptor=json_extract(e.solicitud,'$.origen')
                        AND m.importe_centavos=-json_extract(e.solicitud,'$.importe_centavos'))=1
                    AND SUM(m.receptor=json_extract(e.solicitud,'$.destino')
                        AND m.importe_centavos=json_extract(e.solicitud,'$.importe_centavos'))=1
            END)
            OR (e.id_venta IS NOT NULL AND COUNT(m.id_movimiento) <> SUM(CASE WHEN m.medio_pago IS NOT NULL OR (m.receptor IN ('comidas_saldo_unificado','bebidas_postres_saldo_unificado') AND m.id_venta IS NOT NULL) THEN 1 ELSE 0 END))
            OR (e.id_venta IS NULL AND (e.devengado_comidas <> 0 OR e.devengado_bebidas <> 0
                OR e.cobrado_comidas <> 0 OR e.cobrado_bebidas <> 0))
            OR (e.tipo = 'cierre' AND (COUNT(m.id_movimiento) <> 0 OR NOT EXISTS (
                SELECT 1 FROM pos_cierres_simulados AS c WHERE c.id_evento = e.id_evento)))
        ORDER BY e.id_evento
    """, (pos["periodo_abierto"],)):
        diferencias.append({"codigo": "EVENTO_POS_DESCUADRADO", "id_evento": evento})
    from pos_delivery import conciliar_delivery
    diferencias.extend(conciliar_delivery(conexion))

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
                OR (original.receptor <> m.receptor AND NOT (
                    m.receptor IN ('comidas_efectivo', 'bebidas_postres_efectivo')
                    AND original.receptor = m.receptor || '_en_transito'
                ))
                OR original.medio_pago IS NOT m.medio_pago
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
    from pos_compras_caja import compras_caja_existe, conciliar_compras_caja

    exigir_copia_puente(conexion)
    pos = consultar_cajas_simuladas(conexion)
    diferencias = conciliar_pos(conexion, pos)
    if compras_caja_existe(conexion):
        diferencias.extend(conciliar_compras_caja(conexion))
    caja_diaria = {}
    if caja_diaria_activa(conexion):
        diferencias.extend(conciliar_caja_diaria(conexion))
        caja_diaria["caja_diaria_centavos"] = estado_cajas(conexion)
    from pos_conciliacion_financiera import informe as informe_financiero
    contrato = informe_financiero(conexion)
    for diferencia in contrato['diferencias']:
        if (diferencia['codigo']=='MOVIMIENTO_FISICO_SIN_CONCILIAR' and any(
                previa.get('codigo')==diferencia['codigo'] and
                previa.get('id_movimiento')==diferencia.get('id_movimiento') for previa in diferencias)):
            continue
        diferencias.append(diferencia)
    corte = corte_contable(conexion)
    integrada = {"contabilidad_centavos": calcular_periodo(conexion, corte[0], fecha_local())} if corte else {}
    return {
        **integrada,
        "ok": True,
        "simulacion": True,
        "cuadrado": not diferencias,
        "diferencias": diferencias,
        "pos_centavos": pos,
        "contrato_financiero": contrato,
        **caja_diaria,
        "legado_pesos": {
            "caja_general": obtener_estado_caja(conexion=conexion),
            "secciones": {s: obtener_caja_seccion(s, conexion=conexion) for s in SECCIONES},
            "cierres_semanales": conexion.execute("SELECT COUNT(*) FROM cierres_semanales").fetchone()[0],
            "cierres_mensuales": conexion.execute("SELECT COUNT(*) FROM cierres_mensuales").fetchone()[0],
        },
    }


def consultar_puente_ficticio():
    if RUTA_ENTRENAMIENTO.get() is None and os.getenv("ABADION_PUENTE_FICTICIO") != "1":
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
    if "contabilidad_centavos" in informe:
        contabilidad = informe["contabilidad_centavos"]
        lineas.append(f"Desde el corte · cobrado neto {formatear_centavos(contabilidad['cobrado_neto_centavos'])}"
                      f" · diezmo estimado {formatear_centavos(contabilidad['diezmo_centavos'])}")
    lineas.append(f"Legado · ventas ${legado['ventas']:.2f} · caja disponible ${legado['saldo_disponible']:.2f}")
    return {"ok": True, "respuesta": "\n".join(lineas), "simulacion": True}


def formatear_centavos(centavos):
    pesos, resto = divmod(abs(centavos), 100)
    signo = "-" if centavos < 0 else ""
    return f"{signo}${pesos},{resto:02d}"



def consultar_caja_operativa(seccion=None):
    from database import lectura_contable

    with lectura_contable() as db:
        db.execute("BEGIN")
        if seccion is None:
            legado = obtener_estado_caja(conexion=db)
        else:
            legado = obtener_caja_seccion(seccion, conexion=db)
        if etapa_contable_activa(db):
            diaria = estado_cajas(db)
            if seccion is not None:
                diaria["cajas"] = {legado["seccion"]: diaria["cajas"][legado["seccion"]]}
            legado["caja_diaria_centavos"] = diaria
        return legado
