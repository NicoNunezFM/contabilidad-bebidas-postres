"""Costos de mercadería, sin asientos financieros. La transacción pertenece al POS."""
import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


VERSION = 1


def _importe(valor):
    if valor is None or isinstance(valor, bool):
        return None
    try:
        numero = Decimal(str(valor))
    except (InvalidOperation, ValueError):
        return None
    return numero if numero.is_finite() and 0 <= numero <= Decimal('1e16') else None


def _centavos(valor):
    return int((valor * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def existe(db):
    return db.execute("SELECT 1 FROM sqlite_schema WHERE type='table' AND name='pos_costos_lineas'").fetchone() is not None


def crear_esquema(db):
    """Aditivo, sin UPDATE ni reconstrucción de ventas previas; no confirma."""
    db.execute("""
        CREATE TABLE IF NOT EXISTS pos_costos_lineas (
            id_venta INTEGER NOT NULL REFERENCES pos_ventas_simuladas,
            linea INTEGER NOT NULL CHECK (linea > 0),
            cantidad INTEGER NOT NULL CHECK (cantidad > 0),
            estado TEXT NOT NULL CHECK (estado IN ('conocido','estimado','parcial','desconocido')),
            costo_unitario TEXT,
            costo_total_centavos INTEGER CHECK (costo_total_centavos >= 0),
            costo_parcial_centavos INTEGER NOT NULL CHECK (costo_parcial_centavos >= 0),
            fuente TEXT NOT NULL,
            metodo TEXT NOT NULL,
            version_receta INTEGER,
            version_modelo INTEGER NOT NULL CHECK (version_modelo = 1),
            detalle TEXT NOT NULL,
            PRIMARY KEY (id_venta, linea),
            CHECK ((estado IN ('conocido','estimado')) =
                   (costo_unitario IS NOT NULL AND costo_total_centavos IS NOT NULL)),
            CHECK (estado IN ('conocido','estimado') OR
                   (costo_unitario IS NULL AND costo_total_centavos IS NULL))
        )
    """)
    for accion in ('UPDATE', 'DELETE'):
        db.execute(f"""CREATE TRIGGER IF NOT EXISTS pos_costos_inmutables_{accion.lower()}
            BEFORE {accion} ON pos_costos_lineas BEGIN
                SELECT RAISE(ABORT, 'El costo histórico POS es inmutable.');
            END""")


def capturar(db, id_venta, pedido):
    from rentabilidad import costo_unitario_para_venta
    from costos_postres import estimar_costo_receta, obtener_receta

    if not db.in_transaction:
        raise RuntimeError('La captura requiere la transacción de confirmación de venta.')
    crear_esquema(db)
    for linea, item in enumerate(pedido['items'], 1):
        base = costo_unitario_para_venta(item['id_producto'], _conexion=db)
        valor = _importe(base.get('costo_unitario'))
        componentes = [{**base, 'tipo': 'producto', 'estado': 'estimado' if valor is not None else 'desconocido',
                        'costo_unitario': str(valor) if valor is not None else None}]
        faltantes = [] if valor is not None else ['costo del producto']
        parcial = valor if valor is not None else Decimal(0)
        version = base.get('metadata', {}).get('version_receta')
        if str(item['categoria']).strip().lower() == 'postres' and not base.get('metadata', {}).get('id_produccion'):
            receta = obtener_receta(item['producto'], _conexion=db)
            estimacion = estimar_costo_receta(item['producto'], 1, _conexion=db)
            componentes[0]['receta'] = receta
            componentes[0]['estimacion'] = estimacion
            version = estimacion.get('version_receta')
            if valor is None:
                parcial = _importe(estimacion.get('costo_parcial_conocido')) or Decimal(0)
        for extra in item['adicionales']:
            fila = db.execute('SELECT costo_unitario FROM adicionales_catalogo WHERE id_adicional_catalogo=?',
                              (extra['id_adicional_catalogo'],)).fetchone()
            costo = _importe(fila[0]) if fila else None
            componentes.append({'tipo': 'adicional_catalogo', 'id': extra['id_adicional_catalogo'],
                                'estado': 'conocido' if costo is not None else 'desconocido',
                                'fuente': 'costo declarado de catálogo',
                                'costo_unitario': str(costo) if costo is not None else None})
            if costo is None:
                faltantes.append('adicional: ' + extra['nombre'])
            else:
                parcial += costo
        # No se puede inferir composición ni ahorro a partir del recargo o texto.
        for campo in ('ingredientes_quitados', 'adicionales_preparacion',
                      'recargo_papas_dobles_centavos', 'observacion'):
            if item.get(campo):
                faltantes.append('composición de personalización: ' + campo)
        completo = not faltantes
        estado = 'estimado' if completo else ('parcial' if parcial > 0 else 'desconocido')
        detalle = {'version_modelo': VERSION, 'componentes': componentes, 'faltantes': faltantes,
                   'personalizacion': {k: item[k] for k in ('ingredientes_quitados', 'adicionales_preparacion',
                       'recargo_papas_dobles_centavos', 'observacion') if item.get(k)},
                   'nota': 'Promedios y última producción no identifican el lote vendido.'}
        cantidad = item['cantidad']
        cursor = db.execute("""INSERT INTO pos_costos_lineas
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (id_venta, linea, cantidad, estado, str(parcial) if completo else None,
             _centavos(parcial * cantidad) if completo else None, _centavos(parcial * cantidad),
             base.get('fuente') or 'sin fuente de producto',
             'fuentes existentes; suma de componentes por unidad; redondeo por línea HALF_UP',
             version, VERSION, json.dumps(detalle, ensure_ascii=False, allow_nan=False)))
        if cursor.rowcount != 1:
            raise RuntimeError('No se guardó el costo histórico de la línea POS.')


def _asignado(total, cantidad, originales):
    """Prorrateo acumulado: toda devolución completa revierte exactamente el original."""
    return int((Decimal(total) * cantidad / originales).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def movimientos_pos(db, desde='0001-01-01', hasta='9999-12-31'):
    """Venta y reversiones por fecha del evento; abonos no generan costo ni ingreso."""
    if not db.execute("SELECT 1 FROM sqlite_schema WHERE name='pos_ventas_simuladas'").fetchone():
        return []
    capturas = {}
    if existe(db):
        capturas = {(r[0], r[1]): r[2:] for r in db.execute(
            'SELECT id_venta,linea,cantidad,estado,costo_total_centavos,costo_parcial_centavos FROM pos_costos_lineas')}
    ventas = {v: json.loads(p) for v, p in db.execute('SELECT id_venta,pedido FROM pos_ventas_simuladas')}
    devueltas = {}
    filas = []
    for evento, venta, tipo, fecha in db.execute("""SELECT id_evento,id_venta,tipo,date(fecha,'-3 hours')
        FROM pos_eventos_simulados WHERE tipo IN ('venta','anulacion','devolucion') ORDER BY id_evento"""):
        pedido = ventas[venta]
        unidades = ({n: i['cantidad'] for n, i in enumerate(pedido['items'], 1)} if tipo == 'venta'
                    else dict(db.execute('SELECT linea,cantidad FROM pos_unidades_devueltas WHERE id_evento=?', (evento,))))
        for linea, cantidad in unidades.items():
            item = pedido['items'][linea - 1]
            anterior = devueltas.get((venta, linea), 0)
            captura = capturas.get((venta, linea))
            estado, costo, parcial = 'desconocido', None, 0
            signo = 1 if tipo == 'venta' else -1
            if captura:
                originales, estado, total, subtotal = captura
                def delta(importe):
                    if importe is None:
                        return None
                    if tipo == 'venta':
                        return importe
                    return -(_asignado(importe, anterior + cantidad, originales) - _asignado(importe, anterior, originales))
                costo, parcial = delta(total), delta(subtotal)
            if tipo != 'venta':
                devueltas[venta, linea] = anterior + cantidad
            if desde <= fecha <= hasta:
                filas.append({'origen': 'pos', 'id_venta': venta, 'id_evento': evento, 'linea': linea,
                              'id_producto': item['id_producto'], 'categoria': item['categoria'].strip().lower(),
                              'seccion': item['seccion'], 'fecha': fecha, 'cantidad': signo * cantidad,
                              'ingresos_centavos': signo * item['precio_unitario_centavos'] * cantidad,
                              'estado': estado, 'costo_total_centavos': costo, 'costo_parcial_valorado_centavos': parcial,
                              'motivo': None if captura else 'Venta anterior sin captura; no se reconstruye.'})
    return filas


def movimientos_legados(db, desde='0001-01-01', hasta='9999-12-31'):
    """Solo snapshots existentes; libros disjuntos, no un JOIN que multiplique ventas."""
    filas = []
    for venta, producto, fecha, cantidad, precio, costo, fuente, categoria in db.execute("""
        SELECT v.id_venta,v.id_producto,v.fecha,v.cantidad,v.precio_unitario,
               v.costo_unitario_snapshot,v.fuente_costo_snapshot,p.categoria
        FROM ventas v JOIN productos p USING(id_producto)
        WHERE v.anulada=0 AND substr(v.fecha,1,10) BETWEEN ? AND ?""", (desde, hasta)):
        costos = [(_importe(costo), cantidad)]
        ingresos = Decimal(str(precio)) * cantidad
        for unidades, ingreso, snapshot in db.execute(
                'SELECT cantidad,precio_total,costo_unitario_snapshot FROM venta_adicionales WHERE id_venta=?', (venta,)):
            ingresos += Decimal(str(ingreso))
            costos.append((_importe(snapshot), unidades))
        completo = all(c is not None for c, _ in costos)
        parcial = sum((c * n for c, n in costos if c is not None), Decimal(0))
        categoria = str(categoria).strip().lower()
        filas.append({'origen': 'legado', 'id_venta': venta, 'linea': 1, 'id_producto': producto,
                      'categoria': categoria, 'seccion': 'bebidas_postres' if categoria in ('bebidas','postres') else 'comidas',
                      'fecha': fecha, 'cantidad': cantidad, 'ingresos_centavos': _centavos(ingresos),
                      'estado': 'estimado' if completo else ('parcial' if parcial > 0 else 'desconocido'),
                      'costo_total_centavos': _centavos(parcial) if completo else None,
                      'costo_parcial_valorado_centavos': _centavos(parcial), 'fuente': fuente,
                      'motivo': 'Snapshot legado sin certificación de lote; anulaciones excluidas según política legada.'})
    return filas


def resumir(filas):
    ingresos = sum(f['ingresos_centavos'] for f in filas)
    completo = all(f['costo_total_centavos'] is not None for f in filas)
    costo = sum(f['costo_total_centavos'] or 0 for f in filas)
    peso = sum(abs(f['cantidad']) for f in filas)
    cubiertas = sum(abs(f['cantidad']) for f in filas if f['costo_total_centavos'] is not None)
    return {'ingresos_productos_centavos': ingresos,
            'costo_ventas_centavos': costo if completo else None,
            'costo_lineas_cubiertas_centavos': costo,
            'costo_parcial_valorado_centavos': sum(f['costo_parcial_valorado_centavos'] for f in filas),
            'margen_bruto_centavos': ingresos - costo if completo else None,
            'margen_bruto_pct': (ingresos - costo) * 100 / ingresos if completo and ingresos > 0 else None,
            'cobertura_completa': completo, 'historico_exacto': completo and all(f['estado']=='conocido' for f in filas),
            'unidades_movidas_absolutas': peso, 'unidades_con_costo_completo_absolutas': cubiertas,
            'cobertura_unidades_pct': cubiertas * 100 / peso if peso else None,
            'movimientos_por_estado': {e: sum(f['estado']==e for f in filas) for e in ('conocido','estimado','parcial','desconocido')}}


def informe(db, desde, hasta, *, id_evento_minimo=0, incluir_legado=True):
    filas = ([f for f in movimientos_pos(db, desde, hasta) if f['id_evento'] > id_evento_minimo]
             + (movimientos_legados(db, desde, hasta) if incluir_legado else []))
    return {'version_modelo': VERSION, 'desde': desde, 'hasta': hasta, **resumir(filas),
            'secciones': {s: resumir([f for f in filas if f['seccion']==s]) for s in ('comidas','bebidas_postres')},
            'movimientos': filas,
            'id_evento_minimo': id_evento_minimo, 'incluye_legado': incluir_legado,
            'alcance': 'Mercadería; excluye envío, gastos y caja. POS por evento; legado vigente sin reversiones fechadas.',
            'cobertura_metodo': 'Unidades absolutas de venta y reversión; costo completo puede ser estimado.'}
