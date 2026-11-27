"""Contrato de fuentes: lectura consistente, sin ajustes, importaciones ni DDL."""
import json

SECCIONES = ('comidas', 'bebidas_postres')


def tablas(db):
    return {r[0] for r in db.execute("SELECT name FROM sqlite_schema WHERE type='table'")}


def pagos_netos_compras(db, receptor):
    if 'pos_compras_caja' not in tablas(db):
        return 0
    return db.execute("""SELECT COALESCE(SUM(CASE WHEN evento='alta' THEN pagado_centavos
        ELSE -pagado_centavos END),0) FROM pos_compras_caja WHERE pagador=?""", (receptor,)).fetchone()[0]


def saldos_receptores(db):
    from pos_caja_diaria import caja_diaria_activa, saldo_fisico
    from pos_cobros import periodo_abierto
    from pos_delivery import resumen_delivery
    from pos_envios import resumen_fondos_reparto
    from pos_saldo_unificado import existe, resumen

    if existe(db):
        return [{'receptor': s + '_saldo_unificado', 'seccion': s,
                 'fuente': 'saldo_unificado_agregado', 'saldo_registrado_centavos': f['saldo_centavos'],
                 'custodia_delivery_centavos': f['custodia_reparto_centavos'],
                 'saldo_con_custodia_centavos': f['saldo_centavos'] + f['custodia_reparto_centavos'],
                 'efectivo_identificable': False, 'digital_identificable': False}
                for s, f in resumen(db)['cajas'].items()]
    custodia = {f['receptor']: f['custodia_centavos'] for f in resumen_delivery(db, periodo_abierto(db))}
    anterior = {f['receptor']: f['obligacion_centavos'] for f in resumen_fondos_reparto(db)}
    filas = []
    for seccion in SECCIONES:
        for sufijo in ('efectivo', 'banco', 'mercado_pago', 'efectivo_en_transito'):
            receptor = seccion + '_' + sufijo
            neto = db.execute('SELECT COALESCE(SUM(importe_centavos),0) FROM pos_movimientos_simulados WHERE receptor=?', (receptor,)).fetchone()[0]
            fuente = 'movimientos_pos_menos_pagos_netos_compras'
            contado = None
            if sufijo == 'efectivo' and caja_diaria_activa(db):
                jornada = db.execute('SELECT id_jornada FROM pos_jornadas_caja WHERE caja=? ORDER BY fecha DESC,id_jornada DESC LIMIT 1', (seccion,)).fetchone()
                neto = saldo_fisico(db, jornada[0])['esperado_centavos'] if jornada else 0
                fuente = 'diario_ultima_jornada_sin_sumar_espejos_pos'
                if jornada:
                    from pos_caja_diaria import ultimo_evento
                    arqueo = ultimo_evento(db, jornada[0], 'arqueo')
                    contado = arqueo['resultado']['contado_centavos'] if arqueo else None
            elif sufijo in ('banco', 'mercado_pago'):
                neto -= pagos_netos_compras(db, receptor)
            tercero = custodia.get(receptor, 0)
            # Fondos del modelo anterior no están incluidos en movimientos POS.
            externo = anterior.get(receptor, 0)
            filas.append({'receptor': receptor, 'seccion': seccion, 'fuente': fuente,
                          'saldo_registrado_centavos': neto - tercero,
                          'custodia_delivery_centavos': tercero,
                          'custodia_reparto_anterior_centavos': externo,
                          'saldo_con_custodia_centavos': neto + externo,
                          'ultimo_contado_centavos': contado,
                          'es_transito': sufijo.endswith('en_transito'),
                          'alcance': 'Saldo del libro indicado; no acredita saldo bancario ni arqueo actual.'})
    return filas


def disponibilidad(db, receptor, *, incluir_custodia_delivery=False):
    from pos_caja_diaria import caja_diaria_activa, exigir_jornada_actual, ahora_local
    from pos_cobros import caja_receptora
    if receptor.endswith('_efectivo') and caja_diaria_activa(db):
        exigir_jornada_actual(db, caja_receptora(receptor), ahora_local()[:10])
    fila = next((r for r in saldos_receptores(db) if r['receptor'] == receptor), None)
    if fila is None:
        return 0
    return fila['saldo_registrado_centavos'] + (fila['custodia_delivery_centavos'] if incluir_custodia_delivery else 0)


def proteger_custodia(db, receptor, egreso):
    from fastapi import HTTPException
    fila = next((r for r in saldos_receptores(db) if r['receptor'] == receptor), None)
    if fila and fila['custodia_delivery_centavos'] > 0 and egreso > max(0, fila['saldo_registrado_centavos']):
        raise HTTPException(409, 'Los fondos de delivery en custodia no pagan compras propias.')


def compatibilidad_legada(db):
    nombres = tablas(db)
    if 'saldos_iniciales_caja' not in nombres:
        return {'detectado': False, 'integracion_habilitada': False, 'motivos': ['No hay registros laterales para importar.']}
    aperturas = db.execute('SELECT COUNT(*) FROM saldos_iniciales_caja').fetchone()[0]
    columnas = {r[1] for r in db.execute('PRAGMA table_info(movimientos_caja)')}
    sin_seccion = db.execute("SELECT COUNT(*) FROM movimientos_caja WHERE seccion IS NULL OR trim(seccion)='' ").fetchone()[0] if 'seccion' in columnas else db.execute('SELECT COUNT(*) FROM movimientos_caja').fetchone()[0]
    return {'detectado': True, 'integracion_habilitada': False, 'aperturas': aperturas,
            'movimientos_sin_seccion': sin_seccion,
            'motivos': ['Sin correspondencia de receptor/medio, jornada, UUID y corte POS.',
                        'Los máximos de ID legados no equivalen a un corte de efectivo POS.',
                        'Se requiere conciliación individual y autorización; no se importa ni reconstruye.']}


def diagnosticar_diario(db):
    from pos_caja_diaria import caja_diaria_activa, ahora_local
    if not caja_diaria_activa(db):
        return [], []
    diferencias = []
    pendientes = []
    for jornada, caja, fecha, cerrada in db.execute('SELECT id_jornada,caja,fecha,cerrada FROM pos_jornadas_caja'):
        apertura = db.execute("SELECT COUNT(*) FROM pos_diario_caja WHERE id_jornada=? AND tipo='apertura'", (jornada,)).fetchone()[0]
        cierre = db.execute("SELECT COUNT(*) FROM pos_diario_caja WHERE id_jornada=? AND tipo='cierre'", (jornada,)).fetchone()[0]
        if apertura != 1 or cierre != cerrada:
            diferencias.append({'codigo': 'JORNADA_ESTADO_INCOMPATIBLE', 'id_jornada': jornada})
        if not cerrada and fecha < ahora_local()[:10]:
            pendientes.append({'codigo': 'JORNADA_PENDIENTE_CIERRE', 'id_jornada': jornada, 'caja': caja, 'fecha': fecha})
    for evento, movimiento, receptor in db.execute("""SELECT d.id_evento,m.id_movimiento,m.receptor FROM pos_diario_caja d
        JOIN pos_jornadas_caja j USING(id_jornada)
        LEFT JOIN pos_movimientos_simulados m ON m.id_movimiento=d.id_movimiento_pos
        WHERE d.id_movimiento_pos IS NOT NULL AND (m.id_movimiento IS NULL
          OR m.receptor IS NOT j.caja || '_efectivo' OR m.importe_centavos IS NOT d.importe_centavos)
        OR d.tipo IN ('cobro','reembolso','transferencia') AND d.id_movimiento_pos IS NULL"""):
        if movimiento is not None and receptor in ('comidas_efectivo','bebidas_postres_efectivo'):
            # Conservar el contrato histórico del diagnóstico movimiento -> diario.
            diferencias.append({'codigo':'MOVIMIENTO_FISICO_SIN_CONCILIAR',
                                'id_movimiento':movimiento,'id_evento_diario':evento})
        else:
            diferencias.append({'codigo': 'ESPEJO_DIARIO_INCOMPATIBLE', 'id_evento_diario': evento})
    return diferencias, pendientes


def diagnosticar_custodia(db):
    nombres = tablas(db)
    diferencias = []
    if 'pos_delivery_movimientos' not in nombres:
        return diferencias
    for evento, in db.execute("""SELECT d.id_evento FROM pos_delivery_movimientos d
        LEFT JOIN pos_movimientos_simulados m ON m.id_movimiento=d.id_movimiento
        WHERE (d.receptor='repartidor_directo' AND d.id_movimiento IS NOT NULL)
          OR (d.receptor<>'repartidor_directo' AND (m.id_movimiento IS NULL
            OR m.id_evento IS NOT d.id_evento OR m.id_venta IS NOT NULL
            OR m.receptor IS NOT d.receptor OR m.importe_centavos IS NOT d.importe_centavos))"""):
        diferencias.append({'codigo': 'ESPEJO_DELIVERY_INCOMPATIBLE', 'id_evento': evento})
    if 'pos_fondos_reparto' in nombres:
        for venta, in db.execute('SELECT DISTINCT id_venta FROM pos_delivery_movimientos INTERSECT SELECT id_venta FROM pos_fondos_reparto'):
            diferencias.append({'codigo': 'DOS_MODELOS_CUSTODIA_MISMA_VENTA', 'id_venta': venta})
    return diferencias


def informe(db):
    """El llamador aporta la transacción de lectura; no altera fuentes ni corrige saldos."""
    from pos_cobros import resumen_libro
    diferencias, pendientes = diagnosticar_diario(db)
    diferencias.extend(diagnosticar_custodia(db))
    from fastapi import HTTPException
    try:
        receptores = saldos_receptores(db)
    except HTTPException as error:
        if error.status_code != 409:
            raise
        receptores = []
        diferencias.append({'codigo': 'SALDO_UNIFICADO_PENDIENTE_VALIDACION', 'detalle': error.detail})
    libro = resumen_libro(db)
    nombres = tablas(db)
    alertas = []
    if 'pos_diario_caja' in nombres:
        for evento, caja, datos in db.execute("""SELECT d.id_evento,j.caja,d.resultado FROM pos_diario_caja d
            JOIN pos_jornadas_caja j USING(id_jornada) WHERE d.tipo='cierre'
            AND json_extract(d.resultado,'$.alerta_administracion')=1"""):
            cierre = json.loads(datos)
            alertas.append({'codigo': 'CIERRE_CON_DIFERENCIA', 'fuente': 'pos_diario_caja',
                            'id_evento': evento, 'caja': caja, 'resultado': cierre})
    if 'pos_cierres_unificados' in nombres:
        for cierre, datos in db.execute('SELECT id_cierre,resultado FROM pos_cierres_unificados'):
            resultado = json.loads(datos)
            if resultado['diferencia_centavos'] or resultado['diferencia_custodia_centavos']:
                alertas.append({'codigo': 'CIERRE_UNIFICADO_CON_DIFERENCIA', 'fuente': 'pos_cierres_unificados',
                                'id_cierre': cierre, 'caja': resultado['caja'], 'resultado': resultado})
    cobertura = {}
    if 'pos_costos_contables' in nombres:
        gastos = db.execute("SELECT COUNT(*),COALESCE(SUM(importe_centavos),0) FROM pos_costos_contables WHERE tipo='gasto'").fetchone()
        cobertura['gastos_legados_sin_receptor'] = {'eventos': gastos[0], 'neto_centavos': gastos[1]}
        compras = db.execute("""SELECT COUNT(*),COALESCE(SUM(importe_centavos),0) FROM pos_costos_contables c
            WHERE tipo='compra' AND NOT EXISTS(SELECT 1 FROM pos_compras_caja p WHERE p.id_compra=c.id_origen)""").fetchone() if 'pos_compras_caja' in nombres else db.execute("SELECT COUNT(*),COALESCE(SUM(importe_centavos),0) FROM pos_costos_contables WHERE tipo='compra'").fetchone()
        cobertura['compras_sin_pago_identificado'] = {'eventos': compras[0], 'neto_centavos': compras[1]}
    advertencias = list(pendientes)
    deudas = []
    if 'cuentas_deuda_negocio' in nombres:
        deudas = [dict(zip(('id_cuenta','nombre','moneda','saldo_moneda_origen','reserva_moneda_origen'), f))
            for f in db.execute('''SELECT c.id_cuenta,c.nombre,c.moneda,
                COALESCE((SELECT SUM(importe) FROM movimientos_deuda_negocio m WHERE m.id_cuenta=c.id_cuenta),0),
                COALESCE((SELECT SUM(importe) FROM movimientos_reserva_deuda_negocio r WHERE r.id_cuenta=c.id_cuenta),0)
                FROM cuentas_deuda_negocio c ORDER BY c.id_cuenta''')]
    deudas_apertura = []
    if 'pos_deudas_apertura' in nombres:
        deudas_apertura = [dict(zip(('id_deuda','seccion','pendiente_centavos'), f)) for f in db.execute('''
            SELECT d.id_deuda,d.caja,d.importe_centavos-COALESCE((SELECT SUM(p.importe_centavos)
            FROM pos_pagos_deuda_apertura p WHERE p.id_deuda=d.id_deuda AND NOT EXISTS(
                SELECT 1 FROM pos_reversos_deuda_apertura r WHERE r.id_pago=p.id_pago)),0)
            FROM pos_deudas_apertura d ORDER BY d.id_deuda''')]
    if deudas and deudas_apertura:
        advertencias.append({'codigo':'DEUDAS_DE_MODELOS_DISTINTOS_NO_SUMABLES'})
    if 'pos_delivery_movimientos' in nombres:
        for venta, in db.execute('''SELECT DISTINCT a.id_venta FROM pos_delivery_movimientos a
            JOIN pos_delivery_movimientos b ON a.id_venta=b.id_venta
            WHERE a.tipo='recepcion' AND b.tipo='entrega'
              AND a.receptor<>'repartidor_directo' AND b.receptor<>'repartidor_directo'
              AND (a.receptor LIKE 'comidas_%')<>(b.receptor LIKE 'comidas_%')'''):
            advertencias.append({'codigo':'DELIVERY_PAGADO_DESDE_OTRA_SECCION','id_venta':venta})
    for fila in receptores:
        if fila['saldo_registrado_centavos'] < 0:
            advertencias.append({'codigo': 'SALDO_REGISTRADO_NEGATIVO', 'receptor': fila['receptor'], 'importe_centavos': fila['saldo_registrado_centavos']})
    for concepto, datos in cobertura.items():
        if datos['eventos']:
            advertencias.append({'codigo': 'PAGADOR_NO_IDENTIFICADO', 'concepto': concepto, **datos})
    return {'version_contrato': 1, 'receptores': receptores, 'diferencias': diferencias,
            'advertencias': advertencias, 'jornadas_pendientes': pendientes,
            'alertas_administrativas': alertas,
            'deudas_negocio_por_cuenta': deudas, 'deudas_apertura_separadas': deudas_apertura,
            'asignacion_pagos': cobertura, 'compatibilidad_legada': compatibilidad_legada(db),
            'secciones_economicas': libro['secciones'],
            'saldo_global_certificado': False,
            'criterio': 'Fuentes distintas y no aditivas. Arqueo, custodia, margen y cobros no son ingresos adicionales.'}
