"""Custodia de delivery sencillo: fondos de terceros, nunca ventas ni gastos."""
import json
from uuid import NAMESPACE_URL, uuid5

from fastapi import HTTPException


def es_sencillo(pedido):
    return pedido.get("entrega", {}).get("circuito") == "sencillo" and bool(pedido.get("envio"))


def existe(db):
    return db.execute("SELECT 1 FROM sqlite_schema WHERE name='pos_delivery_movimientos'").fetchone() is not None


def crear(db):
    db.execute("""
        CREATE TABLE IF NOT EXISTS pos_delivery_movimientos (
            id_evento INTEGER PRIMARY KEY REFERENCES pos_eventos_simulados,
            id_venta INTEGER NOT NULL REFERENCES pos_ventas_simuladas,
            tipo TEXT NOT NULL CHECK(tipo IN ('recepcion','entrega','reembolso')),
            receptor TEXT NOT NULL,
            importe_centavos INTEGER NOT NULL CHECK(importe_centavos <> 0),
            id_movimiento INTEGER UNIQUE REFERENCES pos_movimientos_simulados,
            referencia TEXT,
            id_evento_cobro INTEGER REFERENCES pos_eventos_simulados,
            CHECK ((tipo='recepcion') = (importe_centavos > 0)),
            UNIQUE(receptor, referencia)
        )
    """)
    db.execute("CREATE INDEX IF NOT EXISTS pos_delivery_por_venta ON pos_delivery_movimientos(id_venta)")
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS pos_delivery_entrega_unica ON pos_delivery_movimientos(id_venta) WHERE tipo='entrega'")


def estado_delivery(db, venta, pedido, anulada=False):
    from pos_cobros import unidades_devueltas

    recibido = entregado = directo = 0
    if existe(db):
        recibido, entregado = db.execute("""
            SELECT COALESCE(SUM(CASE WHEN tipo<>'entrega' THEN importe_centavos ELSE 0 END),0),
                   -COALESCE(SUM(CASE WHEN tipo='entrega' THEN importe_centavos ELSE 0 END),0)
            FROM pos_delivery_movimientos WHERE id_venta=?
        """, (venta,)).fetchone()
        directo = db.execute("SELECT COALESCE(SUM(importe_centavos),0) FROM pos_delivery_movimientos WHERE id_venta=? AND receptor='repartidor_directo' AND tipo<>'entrega'", (venta,)).fetchone()[0]
    devueltas = unidades_devueltas(db, venta)
    total_devuelto = all(devueltas.get(i, 0) == item['cantidad']
                         for i, item in enumerate(pedido['items'], 1))
    cargo = pedido['envio']['importe_centavos'] if entregado or not (anulada or total_devuelto) else 0
    return {"cargo_centavos": cargo, "cobrado_centavos": recibido,
            "entregado_centavos": entregado, "saldo_cliente_centavos": cargo - recibido,
            "cobrado_directo_centavos": directo,
            "pendiente_entregar_centavos": cargo - entregado,
            "custodia_centavos": max(0, recibido - max(entregado, directo)),
            "adelanto_pendiente_centavos": max(0, entregado - recibido)}


def mover(db, venta, tipo, receptor, importe, usuario, clave, motivo, referencia=None, evento_cobro=None):
    from pos_cobros import ReversionEntrada, iniciar_evento, registrar_movimiento, terminar_evento

    crear(db)
    datos = ReversionEntrada(id_solicitud=uuid5(NAMESPACE_URL, f'abadion-delivery:{clave}'), motivo=motivo)
    evento, previo = iniciar_evento(db, 'transferencia_interna', usuario, datos,
                                  contexto={"delivery": venta, "tipo": tipo, "receptor": receptor,
                                            "importe": importe, "referencia": referencia})
    if previo is not None:
        return
    if importe < 0 and receptor != 'repartidor_directo' and disponible_receptor(db, receptor) < -importe:
        raise HTTPException(409, 'No hay fondos disponibles en el receptor para la salida de delivery.')
    if referencia and db.execute("SELECT 1 FROM pos_delivery_movimientos WHERE receptor=? AND referencia=?",
                                (receptor, referencia)).fetchone():
        raise HTTPException(409, 'La referencia de delivery ya fue registrada.')
    # vincular_movimiento_pos puede haber insertado un evento de diario: buscar por evento POS.
    movimiento = None
    if receptor != 'repartidor_directo':
        registrar_movimiento(db, evento, None, receptor, None, importe)
        movimiento = db.execute('SELECT id_movimiento FROM pos_movimientos_simulados WHERE id_evento=?', (evento,)).fetchone()[0]
    db.execute('INSERT INTO pos_delivery_movimientos VALUES (?,?,?,?,?,?,?,?)',
               (evento, venta, tipo, receptor, importe, movimiento, referencia, evento_cobro))
    terminar_evento(db, evento, {"id_venta": venta, "tipo": tipo, "receptor": receptor, "importe_centavos": importe})


def registrar_pago_conjunto(db, evento, venta, pedido, pagos, usuario):
    from pos_cobros import estado_cuenta, registrar_pagos

    if not es_sencillo(pedido):
        if any(p.envio_directo for p in pagos):
            raise HTTPException(422, 'La retención de efectivo corresponde al delivery sencillo.')
        return registrar_pagos(db, evento, venta, pagos)
    crear(db)
    cuenta = estado_cuenta(db, venta, pedido)
    pendiente = cuenta['saldo_pendiente_centavos']
    envio = cuenta['delivery']['saldo_cliente_centavos']
    if sum(p.importe_centavos for p in pagos) > pendiente + envio:
        raise HTTPException(409, 'El pago supera el saldo de productos y envío.')
    for i, pago in enumerate(pagos):
        if pago.receptor.endswith('_en_transito') and not pago.envio_directo:
            raise HTTPException(422, 'El delivery sencillo requiere indicar la caja o cuenta que recibe realmente el pago.')
        if pago.referencia and (db.execute(
            'SELECT 1 FROM pos_movimientos_simulados WHERE receptor=? AND referencia=?',
            (pago.receptor, pago.referencia)).fetchone() or db.execute(
            'SELECT 1 FROM pos_delivery_movimientos WHERE receptor=? AND referencia=?',
            (pago.receptor, pago.referencia)).fetchone()):
            raise HTTPException(409, 'La referencia ya fue registrada en esa cuenta.')
        productos = min(pendiente, pago.importe_centavos)
        reparto = pago.importe_centavos - productos
        if pago.envio_directo and (not reparto or reparto != pedido['envio']['importe_centavos']):
            raise HTTPException(422, 'El envío retenido en efectivo debe cubrir el cargo completo del repartidor.')
        if productos:
            registrar_pagos(db, evento, venta, [pago.model_copy(update={'importe_centavos': productos, 'envio_directo': False})])
        if reparto:
            mover(db, venta, 'recepcion', 'repartidor_directo' if pago.envio_directo else pago.receptor, reparto, usuario,
                  f'cobro:{evento}:{i}', 'Cobro conjunto del envío', pago.referencia, evento)
        pendiente -= productos


def entregar_delivery(db, venta, cambio, usuario):
    from pos_cobros import PagoPos

    pedido_json, = db.execute('SELECT pedido FROM pos_ventas_simuladas WHERE id_venta=?', (venta,)).fetchone()
    pedido = json.loads(pedido_json)
    estado = estado_delivery(db, venta, pedido)
    importe = estado['pendiente_entregar_centavos']
    if not importe:
        return
    if estado['cobrado_directo_centavos'] == importe:
        if cambio.receptor_reparto not in (None, 'repartidor_directo'):
            raise HTTPException(422, 'El repartidor ya retuvo el envío; no corresponde otra salida de caja.')
        mover(db, venta, 'entrega', 'repartidor_directo', -importe, usuario,
              f'entrega:{cambio.id_solicitud}', 'Envío retenido directamente en efectivo')
        return
    receptor = cambio.receptor_reparto
    # Validar contra receptores concretos, nunca inferir la caja que paga.
    try:
        PagoPos(receptor=receptor, medio_pago=('efectivo' if (receptor or '').endswith('_efectivo') else
                'mercado_pago' if (receptor or '').endswith('_mercado_pago') else 'transferencia'), importe_centavos=importe)
    except ValueError:
        raise HTTPException(422, 'Elegí la caja o cuenta desde donde se entrega el envío al repartidor.')
    if receptor.endswith('_en_transito'):
        raise HTTPException(422, 'No se puede pagar al repartidor con fondos en tránsito.')
    if disponible_receptor(db, receptor) < importe:
        raise HTTPException(409, 'No hay fondos disponibles en el receptor elegido para entregar el envío.')
    if estado['saldo_cliente_centavos'] and not cambio.motivo:
        raise HTTPException(422, 'Indicá el motivo del adelanto del envío fiado.')
    mover(db, venta, 'entrega', receptor, -importe, usuario, f'entrega:{cambio.id_solicitud}',
          cambio.motivo or 'Entrega inmediata al finalizar el reparto')


def disponible_receptor(db, receptor):
    from pos_caja_diaria import caja_diaria_activa, exigir_jornada_actual, ahora_local, saldo_fisico
    from pos_cobros import caja_receptora

    if receptor.endswith('_efectivo') and caja_diaria_activa(db):
        jornada = exigir_jornada_actual(db, caja_receptora(receptor), ahora_local()[:10])
        disponible = saldo_fisico(db, jornada)['esperado_centavos']
    else:
        disponible = db.execute('SELECT COALESCE(SUM(importe_centavos),0) FROM pos_movimientos_simulados WHERE receptor=?',
                                (receptor,)).fetchone()[0]
        if db.execute("SELECT 1 FROM sqlite_schema WHERE name='pos_compras_caja'").fetchone():
            disponible -= db.execute('SELECT COALESCE(SUM(pagado_centavos),0) FROM pos_compras_caja WHERE pagador=?', (receptor,)).fetchone()[0]
    return disponible


def reembolsar_delivery(db, venta, pedido, usuario, clave):
    if not es_sencillo(pedido) or not existe(db):
        return 0
    estado = estado_delivery(db, venta, pedido)
    if estado['entregado_centavos']:
        return 0  # Servicio prestado: no reembolsar ni pagar otra vez.
    filas = db.execute("""
        SELECT receptor, SUM(importe_centavos) FROM pos_delivery_movimientos
        WHERE id_venta=? GROUP BY receptor HAVING SUM(importe_centavos)>0
    """, (venta,)).fetchall()
    for receptor, importe in filas:
        mover(db, venta, 'reembolso', receptor, -importe, usuario, f'reembolso:{clave}:{receptor}',
              'Reembolso de envío no realizado')
    return sum(importe for _, importe in filas)


def resumen_delivery(db, periodo):
    if not existe(db):
        return []
    return [dict(zip(('receptor', 'movimiento_neto_centavos', 'custodia_centavos', 'recibido_centavos', 'entregado_centavos', 'reembolsado_centavos'), fila))
            for fila in db.execute("""
                SELECT receptor, SUM(importe_centavos),
                       SUM(CASE WHEN receptor<>'repartidor_directo' AND NOT EXISTS (
                           SELECT 1 FROM pos_delivery_movimientos pago
                           JOIN pos_eventos_simulados ep ON ep.id_evento=pago.id_evento
                           WHERE pago.id_venta=d.id_venta AND pago.tipo='entrega' AND ep.periodo<=:periodo
                       ) THEN importe_centavos ELSE 0 END),
                       SUM(CASE WHEN d.tipo='recepcion' THEN importe_centavos ELSE 0 END),
                       -SUM(CASE WHEN d.tipo='entrega' THEN importe_centavos ELSE 0 END),
                       -SUM(CASE WHEN d.tipo='reembolso' THEN importe_centavos ELSE 0 END)
                FROM pos_delivery_movimientos d JOIN pos_eventos_simulados e USING(id_evento)
                WHERE e.periodo<=:periodo GROUP BY receptor ORDER BY receptor
            """, {'periodo': periodo})]


def conciliar_delivery(db):
    if not existe(db):
        return []
    diferencias = []
    for venta, datos, anulada in db.execute('''
        SELECT v.id_venta, v.pedido, a.id_venta IS NOT NULL FROM pos_ventas_simuladas v
        LEFT JOIN pos_anulaciones_simuladas a USING(id_venta)
        WHERE v.id_venta IN (SELECT id_venta FROM pos_delivery_movimientos)
    '''):
        pedido = json.loads(datos)
        estado = estado_delivery(db, venta, pedido, anulada) if es_sencillo(pedido) else None
        if estado is None or not (0 <= estado['cobrado_centavos'] <= estado['cargo_centavos']
                                 and 0 <= estado['entregado_centavos'] <= estado['cargo_centavos']):
            diferencias.append({'codigo': 'DELIVERY_DESCUADRADO', 'id_venta': venta})
    for evento, venta, tipo, receptor, importe, solicitud in db.execute('''
        SELECT d.id_evento, d.id_venta, d.tipo, d.receptor, d.importe_centavos, e.solicitud
        FROM pos_delivery_movimientos d JOIN pos_eventos_simulados e USING(id_evento)
    '''):
        esperado = {'delivery': venta, 'tipo': tipo, 'receptor': receptor, 'importe': importe}
        if any(json.loads(solicitud).get(k) != v for k, v in esperado.items()):
            diferencias.append({'codigo': 'DELIVERY_AUDITORIA_INVALIDA', 'id_evento': evento})
    return diferencias


def historial_delivery(db, venta):
    if not existe(db):
        return []
    return [dict(zip(('id_evento', 'tipo', 'receptor', 'importe_centavos', 'referencia', 'fecha', 'id_usuario', 'motivo'), fila))
            for fila in db.execute('''
                SELECT d.id_evento, d.tipo, d.receptor, d.importe_centavos, d.referencia,
                       e.fecha, e.id_usuario, json_extract(e.solicitud,'$.motivo')
                FROM pos_delivery_movimientos d JOIN pos_eventos_simulados e USING(id_evento)
                WHERE d.id_venta=? ORDER BY d.id_evento
            ''', (venta,))]
