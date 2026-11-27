import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from uuid import uuid4

import pytest

from database import obtener_conexion
from pos_costos_historicos import capturar, crear_esquema, existe, informe, movimientos_pos
from reportes import rentabilidad_historica_por_periodo
from tests.test_pos_pedidos import ORIGEN, pedido_prueba
from tests.test_pos_simulacion import VENTAS, _estado, _iniciar_sesion, venta_prueba
from tests.test_pos_entrenamiento import menu_entrenamiento
from tests.test_lo_de_clau_delivery import circuito, venta as venta_delivery


def ejecutar(sql, args=()):
    with closing(obtener_conexion()) as db, db:
        return db.execute(sql, args).fetchall()


@pytest.fixture
def venta_costeada(venta_prueba):
    cliente, venta = venta_prueba
    linea = venta['items'][0]
    linea.update(ingredientes_quitados=[], ids_adicionales=[])
    venta['total_esperado_centavos'] = 20026
    ejecutar('INSERT INTO compras(id_producto,fecha,cantidad,precio_unitario) VALUES (?, ?, 10, 30.005)',
             (linea['id_producto'], '2026-01-01'))
    return cliente, venta


def vender(cliente, venta):
    respuesta = cliente.post(VENTAS, headers=ORIGEN, json=venta)
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()


def reporte():
    return rentabilidad_historica_por_periodo('2000-01-01', '2099-12-31')


def captura():
    return ejecutar('SELECT estado,costo_unitario,costo_total_centavos,costo_parcial_centavos,detalle FROM pos_costos_lineas')[0]


@pytest.mark.parametrize('medio', ['efectivo', 'transferencia', 'fiado'])
def test_captura_misma_valoracion_sin_asiento_extra(venta_costeada, medio):
    cliente, venta = venta_costeada
    if medio == 'fiado':
        venta.pop('medio_pago')
        venta.update(pagos=[], fiado=True, deudor='Cliente ficticio')
    else:
        venta['medio_pago'] = medio
    vender(cliente, venta)
    estado, unitario, total, parcial, detalle = captura()
    assert (estado, total, parcial) == ('estimado', 6001, 6001)
    assert float(unitario) == pytest.approx(30.005)
    assert json.loads(detalle)['componentes'][0]['metadata']['compras_fuente'][0]['id_compra']
    assert ejecutar('SELECT COUNT(*) FROM gastos') == [(0,)]
    assert ejecutar('SELECT COUNT(*) FROM pos_movimientos_simulados') == [(0 if medio == 'fiado' else 1,)]
    r = reporte()
    assert r['costo_ventas_centavos'] == 6001
    assert r['margen_bruto_centavos'] == 14025
    assert r['cobertura_completa'] and not r['historico_exacto']


def test_precio_compra_y_catalogo_no_reescriben_historico(venta_costeada):
    cliente, venta = venta_costeada
    original = vender(cliente, venta)
    antes = captura()
    ejecutar('UPDATE compras SET precio_unitario=999')
    ejecutar('UPDATE productos SET precio_venta=800, categoria="Comidas"')
    assert vender(cliente, venta) == original
    assert captura() == antes
    assert reporte()['costo_ventas_centavos'] == 6001
    assert reporte()['secciones']['bebidas_postres']['ingresos_productos_centavos'] == 20026
    assert reporte()['secciones']['comidas']['ingresos_productos_centavos'] == 0


@pytest.mark.parametrize('costo_extra', [None, 0, 7.25])
def test_adicional_declarado_conocido_cero_valido_y_faltante(venta_costeada, costo_extra):
    cliente, venta = venta_costeada
    extra = ejecutar("SELECT id_adicional_catalogo FROM adicionales_catalogo WHERE nombre='Queso'")[0][0]
    ejecutar('UPDATE adicionales_catalogo SET costo_unitario=? WHERE id_adicional_catalogo=?', (costo_extra, extra))
    venta['items'][0]['ids_adicionales'] = [extra]
    venta['total_esperado_centavos'] += 3000
    vender(cliente, venta)
    estado, _, total, parcial, detalle = captura()
    componente = json.loads(detalle)['componentes'][1]
    if costo_extra is None:
        assert estado == 'parcial' and total is None and parcial == 6001
        assert reporte()['margen_bruto_centavos'] is None
    else:
        assert componente['estado'] == 'conocido'
        assert total == 6001 + round(costo_extra * 200)
    if costo_extra is None:
        assert componente['costo_unitario'] is None
    else:
        assert float(componente['costo_unitario']) == costo_extra


@pytest.mark.parametrize('campo,valor', [('ingredientes_quitados', ['Limón'])])
def test_personalizacion_no_infiere_ahorro(venta_costeada, campo, valor):
    cliente, venta = venta_costeada
    venta['items'][0][campo] = valor
    vender(cliente, venta)
    assert captura()[0] == 'parcial' and captura()[2] is None
    assert 'personalización' in captura()[4]
    assert reporte()['cobertura_unidades_pct'] == 0


def test_rotiseria_desconocida_y_secciones_independientes(venta_costeada):
    cliente, venta = venta_costeada
    vender(cliente, venta)
    ejecutar("UPDATE productos SET categoria='Comidas'")
    vender(cliente, {**venta, 'id_solicitud': str(uuid4())})
    r = reporte()
    assert r['margen_bruto_centavos'] is None
    assert r['cobertura_unidades_pct'] == 50
    assert r['secciones']['comidas']['costo_ventas_centavos'] is None
    assert r['secciones']['bebidas_postres']['costo_ventas_centavos'] == 6001


@pytest.mark.parametrize('accion', ['UPDATE pos_costos_lineas SET costo_unitario=0', 'DELETE FROM pos_costos_lineas'])
def test_captura_inmutable(venta_costeada, accion):
    vender(*venta_costeada)
    with pytest.raises(sqlite3.IntegrityError, match='inmutable'):
        ejecutar(accion)
    assert captura()[2] == 6001


@pytest.mark.parametrize('modo', ['ABORT', 'IGNORE'])
def test_fallo_captura_revierte_venta_stock_caja_y_gastos(venta_costeada, modo):
    cliente, venta = venta_costeada
    with closing(obtener_conexion()) as db, db:
        crear_esquema(db)
        db.execute(f"CREATE TRIGGER rechazo_costo BEFORE INSERT ON pos_costos_lineas BEGIN SELECT RAISE({modo}{', \'fallo ficticio\'' if modo=='ABORT' else ''}); END")
    antes = _estado()
    usuario = cliente.get('/pos-api/yo').json()['usuario']
    from pos_simulacion import registrar_venta_simulada, VentaSimuladaEntrada
    with pytest.raises((RuntimeError, sqlite3.IntegrityError)):
        registrar_venta_simulada(VentaSimuladaEntrada.model_validate(venta), usuario)
    assert _estado() == antes
    assert ejecutar('SELECT COUNT(*) FROM pos_costos_lineas') == [(0,)]


def test_fallo_despues_costos_y_antes_commit_restaura_ddl(venta_costeada, monkeypatch):
    cliente, venta = venta_costeada
    usuario = cliente.get('/pos-api/yo').json()['usuario']
    import pos_simulacion as pos
    def fallar(*args, **kwargs):
        raise RuntimeError('antes de commit')
    monkeypatch.setattr(pos, 'terminar_evento', fallar)
    antes = _estado()
    with pytest.raises(RuntimeError, match='antes de commit'):
        pos.registrar_venta_simulada(pos.VentaSimuladaEntrada.model_validate(venta), usuario)
    assert _estado() == antes
    with closing(obtener_conexion()) as db:
        assert not existe(db)


@pytest.mark.parametrize('misma_clave', [True, False])
def test_concurrencia_y_recibo_unico(venta_costeada, misma_clave):
    cliente, venta = venta_costeada
    usuario = cliente.get('/pos-api/yo').json()['usuario']
    from pos_simulacion import registrar_venta_simulada, VentaSimuladaEntrada
    def comprar(_):
        datos = dict(venta, id_solicitud=venta['id_solicitud'] if misma_clave else str(uuid4()))
        return registrar_venta_simulada(VentaSimuladaEntrada.model_validate(datos), usuario)['id_venta']
    with ThreadPoolExecutor(max_workers=3) as grupo:
        ids = list(grupo.map(comprar, range(3)))
    esperadas = 1 if misma_clave else 3
    assert len(set(ids)) == esperadas
    assert ejecutar('SELECT COUNT(*) FROM pos_costos_lineas') == [(esperadas,)]
    assert reporte()['costo_ventas_centavos'] == 6001 * esperadas


def test_devolucion_parcial_y_anulacion_revierten_original_sin_redondeo_residual(venta_costeada):
    cliente, venta = venta_costeada
    alta = vender(cliente, venta)
    _iniciar_sesion(cliente, 'admin', 'admin')
    ejecutar('UPDATE compras SET precio_unitario=1000')
    url = f"{VENTAS}/{alta['id_venta']}"
    datos = {'id_solicitud': str(uuid4()), 'motivo': 'Ficticio', 'items': [{'linea': 1, 'cantidad': 1}]}
    r = cliente.post(url+'/devoluciones', headers=ORIGEN, json=datos)
    assert r.status_code == 200, r.text
    assert cliente.post(url+'/devoluciones', headers=ORIGEN, json=datos).json() == r.json()
    assert reporte()['costo_ventas_centavos'] == 3000
    r = cliente.post(url+'/anulacion', headers=ORIGEN, json={'id_solicitud': str(uuid4()), 'motivo': 'Ficticio'})
    assert r.status_code == 200, r.text
    assert reporte()['costo_ventas_centavos'] == 0
    assert reporte()['ingresos_productos_centavos'] == 0
    assert captura()[2] == 6001
    assert _estado()[0] == 10


def test_abono_fiado_no_repite_ingreso_ni_costo(venta_costeada):
    cliente, venta = venta_costeada
    venta.pop('medio_pago')
    venta.update(pagos=[], fiado=True, deudor='Ficticio')
    alta = vender(cliente, venta)
    antes = reporte()
    r = cliente.post(f"{VENTAS}/{alta['id_venta']}/abonos", headers=ORIGEN, json={
        'id_solicitud': str(uuid4()), 'pagos': [{'receptor': 'bebidas_postres_banco', 'medio_pago': 'transferencia', 'importe_centavos': 20026}]})
    assert r.status_code == 200, r.text
    assert reporte() == antes


def test_base_anterior_no_backfill_ni_escritura_en_lectura(venta_costeada, base_prueba, monkeypatch):
    cliente, venta = venta_costeada
    import pos_costos_historicos
    with monkeypatch.context() as m:
        m.setattr(pos_costos_historicos, 'capturar', lambda *args: None)
        vender(cliente, venta)
    antes = base_prueba.read_bytes()
    assert reporte()['costo_ventas_centavos'] is None
    assert base_prueba.read_bytes() == antes
    vender(cliente, {**venta, 'id_solicitud': str(uuid4())})
    assert ejecutar('SELECT COUNT(*) FROM pos_costos_lineas') == [(1,)]
    assert reporte()['cobertura_unidades_pct'] == 50


def test_legado_y_pos_no_duplican_ni_recostean(venta_costeada):
    cliente, venta = venta_costeada
    producto = venta['items'][0]['id_producto']
    ejecutar("INSERT INTO ventas(id_producto,fecha,cantidad,precio_unitario,costo_unitario_snapshot,fuente_costo_snapshot) VALUES (?, '2026-01-01',1,100,20,'ficticio')", (producto,))
    vender(cliente, venta)
    r = reporte()
    assert r['ingresos_productos_centavos'] == 30026
    assert r['costo_ventas_centavos'] == 8001
    assert len(r['movimientos']) == 2
    from rentabilidad import rentabilidad_producto
    resumen = rentabilidad_producto(producto)
    assert resumen['unidades_vendidas'] == 3
    assert resumen['ingresos'] == pytest.approx(300.26)
    assert not resumen['rentabilidad_historica_exacta']


@pytest.mark.parametrize('completa', [True, False])
def test_receta_y_precios_posteriores_no_recostean(venta_costeada, completa):
    from costos_postres import inicializar_costos_postres
    inicializar_costos_postres()
    cliente, venta = venta_costeada
    ejecutar("UPDATE productos SET nombre='Oreo',categoria='Postres'")
    insumos = ejecutar('SELECT id_insumo FROM insumos')
    for (insumo,) in insumos if completa else insumos[:1]:
        ejecutar("INSERT INTO compras_insumos(id_insumo,fecha,cantidad_base,costo_total) VALUES (?, '2026-01-01',1000,1000)", (insumo,))
    vender(cliente, venta)
    antes = captura()
    assert antes[0] == ('estimado' if completa else 'parcial')
    ejecutar('UPDATE recetas SET costo_fijo_por_unidad=9999,version=version+10')
    ejecutar('UPDATE compras_insumos SET costo_total=9000')
    assert captura() == antes
    assert ejecutar('SELECT version_receta FROM pos_costos_lineas')[0][0] == 2
    assert reporte()['costo_ventas_centavos'] == antes[2]


def test_captura_exige_transaccion(venta_costeada):
    with closing(obtener_conexion()) as db:
        with pytest.raises(RuntimeError, match='transacción'):
            capturar(db, 1, {'items': []})


def test_eventos_en_periodos_distintos(venta_costeada):
    cliente, venta = venta_costeada
    alta = vender(cliente, venta)
    ejecutar("UPDATE pos_eventos_simulados SET fecha='2026-02-01 15:00:00'")
    _iniciar_sesion(cliente, 'admin', 'admin')
    r = cliente.post(f"{VENTAS}/{alta['id_venta']}/anulacion", headers=ORIGEN,
                     json={'id_solicitud': str(uuid4()), 'motivo': 'Ficticio'})
    assert r.status_code == 200
    ejecutar("UPDATE pos_eventos_simulados SET fecha='2026-03-01 15:00:00' WHERE tipo='anulacion'")
    assert rentabilidad_historica_por_periodo('2026-02-01','2026-02-28')['costo_ventas_centavos'] == 6001
    assert rentabilidad_historica_por_periodo('2026-03-01','2026-03-31')['costo_ventas_centavos'] == -6001


def test_rechazo_real_commit_revierte_todas_las_escrituras(venta_costeada):
    cliente, venta = venta_costeada
    ejecutar('CREATE TABLE padre_ficticio(id INTEGER PRIMARY KEY)')
    ejecutar('CREATE TABLE fk_ficticia(id INTEGER REFERENCES padre_ficticio DEFERRABLE INITIALLY DEFERRED)')
    with closing(obtener_conexion()) as db, db:
        crear_esquema(db)
        db.execute('CREATE TRIGGER fallar_commit AFTER INSERT ON pos_costos_lineas BEGIN INSERT INTO fk_ficticia VALUES(999); END')
    usuario = cliente.get('/pos-api/yo').json()['usuario']
    from pos_simulacion import registrar_venta_simulada, VentaSimuladaEntrada
    antes = _estado()
    with pytest.raises(sqlite3.IntegrityError, match='FOREIGN KEY'):
        registrar_venta_simulada(VentaSimuladaEntrada.model_validate(venta), usuario)
    assert _estado() == antes
    assert ejecutar('SELECT COUNT(*) FROM pos_costos_lineas') == [(0,)]
    assert ejecutar('PRAGMA foreign_key_check') == []


def test_costo_en_misma_conexion_y_lectura_no_observa_captura_sin_commit(venta_costeada, monkeypatch):
    cliente, venta = venta_costeada
    usuario = cliente.get('/pos-api/yo').json()['usuario']
    import costos_postres
    import rentabilidad
    import pos_simulacion as pos
    original = pos.terminar_evento
    def conexion_prohibida():
        raise AssertionError('Se abrió otra conexión para valorar')
    def observar(db, *args, **kwargs):
        assert db.execute('SELECT COUNT(*) FROM pos_costos_lineas').fetchone() == (1,)
        with closing(obtener_conexion()) as lector:
            assert lector.execute('SELECT COUNT(*) FROM pos_ventas_simuladas').fetchone() == (0,)
            assert not existe(lector)
        return original(db, *args, **kwargs)
    monkeypatch.setattr(costos_postres, 'obtener_conexion', conexion_prohibida)
    monkeypatch.setattr(rentabilidad, 'obtener_conexion', conexion_prohibida)
    monkeypatch.setattr(pos, 'terminar_evento', observar)
    pos.registrar_venta_simulada(pos.VentaSimuladaEntrada.model_validate(venta), usuario)
    assert captura()[2] == 6001


def test_ultima_produccion_guarda_version_y_no_sigue_nuevas_producciones(venta_costeada):
    from costos_postres import inicializar_costos_postres
    inicializar_costos_postres()
    cliente, venta = venta_costeada
    producto = venta['items'][0]['id_producto']
    ejecutar("UPDATE productos SET nombre='Oreo',categoria='Postres'")
    receta = ejecutar("SELECT id_receta FROM recetas WHERE producto='Oreo' AND version=2")[0][0]
    sql = '''INSERT INTO producciones_postres(fecha_hora,id_producto,producto,cantidad_producida,
             id_receta,version_receta,costo_insumos,costo_fijo,costo_total,costo_unitario)
             VALUES('2026-01-01 12:00:00',?,'Oreo',10,?,2,100,20,120,?)'''
    ejecutar(sql, (producto, receta, 12))
    vender(cliente, venta)
    antes = captura()
    assert antes[2] == 2400
    assert ejecutar('SELECT version_receta FROM pos_costos_lineas') == [(2,)]
    assert json.loads(antes[4])['componentes'][0]['metadata']['id_produccion'] == 1
    ejecutar(sql, (producto, receta, 80))
    assert captura() == antes
    assert reporte()['costo_ventas_centavos'] == 2400


@pytest.mark.parametrize('modalidad', ['promocion', 'personalizacion'])
def test_menu_real_promociones_y_preparaciones_sin_inventar_fuentes(menu_entrenamiento, modalidad):
    from pos_caja_diaria import ahora_local
    ruta, cliente, productos = menu_entrenamiento
    nombre = 'Oreo chico' if modalidad == 'promocion' else 'Clásica doble'
    item = {'id_producto': productos[nombre]['id_producto'], 'cantidad': 3 if modalidad == 'promocion' else 1}
    if modalidad == 'personalizacion':
        item.update(adicionales_preparacion=[{'tipo': 'cheddar', 'destino': 'principal', 'cantidad': 2}],
                    papas_dobles=True, observacion='Preparación ficticia')
    cotizacion = cliente.post('/pos-api/pedidos/validar', json={'items': [item]})
    assert cotizacion.status_code == 200, cotizacion.text
    for caja in ('comidas', 'bebidas_postres'):
        r = cliente.post(f'/pos-api/simulacion/caja-diaria/{caja}/apertura', json={
            'id_solicitud': str(uuid4()), 'fecha': ahora_local()[:10], 'inicial_centavos': 0})
        assert r.status_code == 200, r.text
    total = cotizacion.json()['total_centavos']
    if modalidad == 'promocion':
        # Fuente de producción ficticia exactamente vinculable por el nombre vigente.
        with closing(sqlite3.connect(ruta)) as db, db:
            receta = db.execute("INSERT INTO recetas(nombre,producto,version,rendimiento) VALUES ('QA','Oreo chico',1,10)").lastrowid
            db.execute("""INSERT INTO producciones_postres(fecha_hora,id_producto,producto,cantidad_producida,
                id_receta,version_receta,costo_insumos,costo_fijo,costo_total,costo_unitario)
                VALUES('2026-01-01 12:00:00',?,'Oreo chico',10,?,1,3000,0,3000,300)""", (item['id_producto'], receta))
    r = cliente.post(VENTAS, json={'id_solicitud': str(uuid4()), 'items': [item],
                                 'total_esperado_centavos': total, 'medio_pago': 'efectivo'})
    assert r.status_code == 200, r.text
    with closing(sqlite3.connect(ruta)) as db:
        filas = db.execute('SELECT cantidad,estado,costo_total_centavos,detalle FROM pos_costos_lineas ORDER BY linea').fetchall()
        if modalidad == 'promocion':
            assert [f[0] for f in filas] == [2, 1]
            assert cotizacion.json()['descuento_centavos'] == 100000
            assert [f[2] for f in filas] == [60000, 30000]
        else:
            assert all(f[1] == 'desconocido' and f[2] is None for f in filas)
            assert 'adicionales_preparacion' in filas[0][3] and 'recargo_papas_dobles' in filas[0][3]
        resumen = informe(db, '2000-01-01', '2099-12-31')
        assert resumen['ingresos_productos_centavos'] == total
        assert resumen['costo_ventas_centavos'] == (90000 if modalidad == 'promocion' else None)


def test_historico_sin_costo_no_se_completa_con_compras_nuevas(venta_costeada):
    cliente, venta = venta_costeada
    ejecutar('DELETE FROM compras')
    vender(cliente, venta)
    assert captura()[0] == 'desconocido' and captura()[2] is None
    ejecutar("INSERT INTO compras(id_producto,fecha,cantidad,precio_unitario) VALUES (?,'2026-01-01',10,20)",
             (venta['items'][0]['id_producto'],))
    assert reporte()['costo_ventas_centavos'] is None
    assert reporte()['margen_bruto_centavos'] is None


def test_adicional_congelado_tras_cambio_de_catalogo(venta_costeada):
    cliente, venta = venta_costeada
    extra = ejecutar("SELECT id_adicional_catalogo FROM adicionales_catalogo WHERE nombre='Queso'")[0][0]
    ejecutar('UPDATE adicionales_catalogo SET costo_unitario=4 WHERE id_adicional_catalogo=?', (extra,))
    venta['items'][0]['ids_adicionales'] = [extra]
    venta['total_esperado_centavos'] += 3000
    vender(cliente, venta)
    ejecutar('UPDATE adicionales_catalogo SET costo_unitario=900 WHERE id_adicional_catalogo=?', (extra,))
    assert reporte()['costo_ventas_centavos'] == 6801


def test_cobertura_en_informe_api_y_delivery_sin_duplicar_ingreso(circuito):
    _, cliente, ids = circuito
    venta_delivery(cliente, ids)
    r = cliente.get('/pos-api/simulacion/contabilidad').json()
    historico = r['rentabilidad_historica']
    assert historico['ingresos_productos_centavos'] == r['devengado_centavos'] == 1_250_000
    assert historico['costo_ventas_centavos'] is None
    assert historico['cobertura_unidades_pct'] == 0
    assert all(s['costo_ventas_centavos'] is None for s in historico['secciones'].values())


def test_corte_contable_por_id_no_reincluye_ventas_de_la_misma_fecha(circuito):
    from pos_preproduccion import abrir_base, configuracion
    carpeta, cliente, ids = circuito
    venta_delivery(cliente, ids)
    with closing(abrir_base(carpeta, configuracion(carpeta)['id'])) as db, db:
        corte = db.execute('SELECT MAX(id_evento) FROM pos_eventos_simulados').fetchone()[0]
        db.execute('UPDATE pos_inicio_contable SET ultimo_evento_pos=?', (corte,))
    vacio = cliente.get('/pos-api/simulacion/contabilidad').json()
    assert vacio['devengado_centavos'] == 0
    assert vacio['rentabilidad_historica']['ingresos_productos_centavos'] == 0
    venta_delivery(cliente, ids)
    datos = cliente.get('/pos-api/simulacion/contabilidad').json()
    historico = datos['rentabilidad_historica']
    assert historico['ingresos_productos_centavos'] == datos['devengado_centavos'] == 1_250_000
    assert historico['id_evento_minimo'] == corte and not historico['incluye_legado']
    assert len(historico['movimientos']) == 2


def test_edge_muestra_cobertura_y_no_muestra_margen_cero_por_faltantes(circuito, tmp_path):
    import os
    from pathlib import Path
    ejecutable = os.getenv('POS_TEST_BROWSER')
    if not ejecutable:
        pytest.skip('Configurar POS_TEST_BROWSER con Edge')
    import websocket
    from scripts.abadion_preproduccion import crear_app
    from tests.test_pos_web import abrir_navegador, esperar
    carpeta, cliente, ids = circuito
    venta_delivery(cliente, ids)
    with closing(abrir_navegador(crear_app(carpeta), ejecutable, tmp_path, websocket)) as navegador:
        evaluar = next(navegador)
        esperar(lambda: evaluar("document.querySelector('#adminAccess')?.getClientRects().length > 0"))
        evaluar("document.querySelector('#adminAccess').click()")
        esperar(lambda: evaluar("document.querySelector('#usuarioPos') !== null"))
        clave = json.loads((carpeta / 'credenciales.json').read_text())['admin-preprod']
        evaluar("document.querySelector('#usuarioPos').value='admin-preprod'; document.querySelector('#claveAdmin').value="
                + json.dumps(clave) + "; document.querySelector('#accept').click()")
        esperar(lambda: evaluar("document.querySelector('#contabilidadPos')?.hidden === false"))
        evaluar("document.querySelector('#contabilidadPos').click()")
        esperar(lambda: evaluar("document.querySelector('#costosHistoricosPos')?.textContent.includes('desconocido; faltan costos')"))
        texto = evaluar("document.querySelector('#costosHistoricosPos').textContent")
        assert 'Cobertura de costos: 0.0%' in texto
        assert 'Rotisería' in texto and 'Postres' in texto
        salida = os.getenv('POS_UI_CAPTURAS')
        if salida:
            Path(salida).mkdir(parents=True, exist_ok=True)
            evaluar("document.querySelector('#costosHistoricosPos').scrollIntoView({block:'start'}); void 0")
            (Path(salida) / 'abadion-costos-historicos-cobertura.png').write_bytes(evaluar.captura())
