import json
import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from uuid import uuid4

import pytest

from database import obtener_conexion
from pos_caja_diaria import crear_caja_diaria, ahora_local
from pos_contabilidad import crear_integracion_contable
from pos_conciliacion_financiera import informe, disponibilidad
from pos_simulacion import transferir_simulado
from pos_cobros import TransferenciaEntrada
from tests.test_pos_pedidos import ORIGEN, pedido_prueba
from tests.test_pos_simulacion import VENTAS, _iniciar_sesion, venta_prueba
from tests.test_saldo_unificado import unificado, circuito, venta as venta_delivery, pago as pago_unificado


SIM = '/pos-api/simulacion'
CONTRATO = SIM + '/conciliacion-financiera'
DIARIO = SIM + '/caja-diaria'


def sql(texto, datos=()):
    with closing(obtener_conexion()) as db, db:
        return db.execute(texto, datos).fetchall()


def post(cliente, ruta, datos, esperado=200):
    respuesta = cliente.post(ruta, headers=ORIGEN, json=datos)
    assert respuesta.status_code == esperado, respuesta.text
    return respuesta.json()


def solicitud(**datos):
    return {'id_solicitud': str(uuid4()), **datos}


@pytest.fixture
def flujo(venta_prueba, monkeypatch):
    cliente, venta = venta_prueba
    venta['items'][0].update(ingredientes_quitados=[], ids_adicionales=[])
    venta['total_esperado_centavos'] = 20026
    with closing(obtener_conexion()) as db, db:
        db.execute("INSERT INTO compras(id_producto,fecha,cantidad,precio_unitario) VALUES (?,'2026-01-01',10,30)", (venta['items'][0]['id_producto'],))
        crear_caja_diaria(db)
        crear_integracion_contable(db)
        db.execute('CREATE TABLE pos_puente_ficticio(version INTEGER)')
        db.execute('INSERT INTO pos_puente_ficticio VALUES(1)')
    monkeypatch.setenv('ABADION_PUENTE_FICTICIO', '1')
    _iniciar_sesion(cliente, 'admin-finanzas', 'admin')
    for caja in ('comidas', 'bebidas_postres'):
        post(cliente, f'{DIARIO}/{caja}/apertura', solicitud(fecha=ahora_local()[:10], inicial_centavos=1000))
    return cliente, venta


def contrato(cliente):
    r = cliente.get(CONTRATO)
    assert r.status_code == 200, r.text
    assert r.headers['Cache-Control'] == 'no-store'
    return r.json()


def receptor(cliente, nombre):
    return next(f for f in contrato(cliente)['receptores'] if f['receptor'] == nombre)


def transferir(cliente, origen, destino, importe, **extra):
    return post(cliente, SIM + '/cajas/transferencias', solicitud(origen=origen, destino=destino,
                importe_centavos=importe, motivo='Movimiento ficticio', **extra))


def movimiento(cliente, caja, tipo, importe, esperado=200):
    jornada = cliente.get(DIARIO).json()['cajas'][caja]['id_jornada']
    return post(cliente, f'{DIARIO}/{caja}/movimientos', solicitud(id_jornada=jornada, tipo=tipo,
                importe_centavos=importe, motivo='Movimiento ficticio'), esperado)


def comprar(cliente, producto, importe, pagador, medio):
    return post(cliente, SIM + '/compras', solicitud(id_producto=producto, cantidad=1,
                precio_unitario_centavos=importe, pagado_centavos=importe, pagador=pagador, medio_pago=medio))


def test_fuentes_fisicas_no_suman_apertura_ni_espejos_dos_veces(flujo, base_prueba):
    c, v = flujo
    v['medio_pago'] = 'efectivo'
    post(c, VENTAS, v)
    antes = base_prueba.read_bytes()
    propio = receptor(c, 'bebidas_postres_efectivo')
    assert propio['saldo_registrado_centavos'] == 21026
    assert base_prueba.read_bytes() == antes
    r = c.get(SIM + '/contabilidad').json()
    assert r['devengado_centavos'] == r['cobrado_neto_centavos'] == 20026
    assert r['rentabilidad_historica']['costo_ventas_centavos'] == 6000
    assert c.get(SIM + '/conciliacion').json()['cuadrado']


@pytest.mark.parametrize('destino', ['bebidas_postres_banco', 'bebidas_postres_mercado_pago'])
def test_transferencia_misma_seccion_no_devenga_ni_cobra(flujo, destino):
    c, _ = flujo
    transferir(c, 'bebidas_postres_efectivo', destino, 600)
    assert receptor(c, 'bebidas_postres_efectivo')['saldo_registrado_centavos'] == 400
    assert receptor(c, destino)['saldo_registrado_centavos'] == 600
    contable = c.get(SIM + '/contabilidad').json()
    assert contable['devengado_centavos'] == contable['cobrado_neto_centavos'] == 0
    assert c.get(SIM + '/conciliacion').json()['cuadrado']


def test_reintegro_compra_digital_restituye_disponibilidad(flujo):
    c, v = flujo
    transferir(c, 'bebidas_postres_efectivo', 'bebidas_postres_banco', 1000)
    compra = comprar(c, v['items'][0]['id_producto'], 300, 'bebidas_postres_banco', 'transferencia')
    assert receptor(c, 'bebidas_postres_banco')['saldo_registrado_centavos'] == 700
    post(c, f"{SIM}/compras/{compra['id_compra']}/devolucion", solicitud(motivo='Reintegro ficticio', reintegro_confirmado=True))
    assert receptor(c, 'bebidas_postres_banco')['saldo_registrado_centavos'] == 1000
    from pos_delivery import disponible_receptor
    with closing(obtener_conexion()) as db:
        assert disponible_receptor(db, 'bebidas_postres_banco') == 1000
    transferir(c, 'bebidas_postres_banco', 'bebidas_postres_mercado_pago', 1000)
    assert receptor(c, 'bebidas_postres_banco')['saldo_registrado_centavos'] == 0


def test_transferencia_no_gasta_dos_veces_pago_digital_compra(flujo):
    c, v = flujo
    transferir(c, 'bebidas_postres_efectivo', 'bebidas_postres_banco', 1000)
    comprar(c, v['items'][0]['id_producto'], 700, 'bebidas_postres_banco', 'transferencia')
    post(c, SIM+'/cajas/transferencias', solicitud(origen='bebidas_postres_banco',
         destino='bebidas_postres_mercado_pago', importe_centavos=301, motivo='Ficticio'), 409)
    assert receptor(c, 'bebidas_postres_banco')['saldo_registrado_centavos'] == 300


def test_gastos_aportes_retiros_y_compra_fisica_un_solo_efecto(flujo):
    c, v = flujo
    movimiento(c, 'comidas', 'aporte', 400)
    movimiento(c, 'comidas', 'retiro', 200)
    movimiento(c, 'comidas', 'gasto', 100)
    comprar(c, v['items'][0]['id_producto'], 300, 'comidas_efectivo', 'efectivo')
    assert receptor(c, 'comidas_efectivo')['saldo_registrado_centavos'] == 800
    contable = c.get(SIM+'/contabilidad').json()
    assert contable['aportes_fisicos_centavos'] == 400
    assert contable['retiros_fisicos_centavos'] == 200
    assert contable['gastos_con_receptor_centavos'] == 100
    assert contable['compras_centavos'] == 300
    assert receptor(c, 'bebidas_postres_efectivo')['saldo_registrado_centavos'] == 1000


def test_fiado_abonos_devolucion_anulacion_conservan_costos(flujo):
    c, v = flujo
    v.pop('medio_pago')
    v.update(pagos=[], fiado=True, deudor='Cliente ficticio')
    alta = post(c, VENTAS, v)
    ruta = f"{VENTAS}/{alta['id_venta']}"
    snapshot = sql('SELECT * FROM pos_costos_lineas')
    for medio, rec, importe in [('efectivo','bebidas_postres_efectivo',10000), ('transferencia','bebidas_postres_banco',10026)]:
        datos = solicitud(pagos=[{'medio_pago': medio, 'receptor': rec, 'importe_centavos': importe}])
        aplicado = post(c, ruta+'/abonos', datos)
        assert post(c, ruta+'/abonos', datos) == aplicado
    r = c.get(SIM+'/contabilidad').json()
    assert r['devengado_centavos'] == r['cobrado_neto_centavos'] == 20026
    assert r['fiado_al_cierre_centavos'] == 0
    post(c, ruta+'/devoluciones', solicitud(motivo='Ficticio', items=[{'linea':1,'cantidad':1}]))
    post(c, ruta+'/anulacion', solicitud(motivo='Ficticio'))
    assert sql('SELECT * FROM pos_costos_lineas') == snapshot
    r = c.get(SIM+'/contabilidad').json()
    assert r['devengado_centavos'] == r['cobrado_neto_centavos'] == 0
    assert r['rentabilidad_historica']['costo_ventas_centavos'] == 0
    assert c.get(SIM+'/conciliacion').json()['cuadrado']


@pytest.mark.parametrize('operacion', ['retiro','gasto','transferencia','compra'])
def test_custodia_no_se_ofrece_para_uso_propio(flujo, operacion):
    c, v = flujo
    v.update(entrega={'origen':'mostrador','modalidad':'envio','direccion':'Calle ficticia 123','circuito':'sencillo'},
             total_esperado_centavos=220026)
    v.pop('medio_pago')
    v['pagos']=[{'medio_pago':'efectivo','receptor':'bebidas_postres_efectivo','importe_centavos':220026}]
    post(c, VENTAS, v)
    f = receptor(c, 'bebidas_postres_efectivo')
    assert f['saldo_registrado_centavos'] == 21026
    assert f['custodia_delivery_centavos'] == 200000
    if operacion in ('retiro','gasto'):
        movimiento(c, 'bebidas_postres', operacion, 22000, 409)
    elif operacion == 'transferencia':
        post(c, SIM+'/cajas/transferencias', solicitud(origen='bebidas_postres_efectivo',destino='bebidas_postres_banco',importe_centavos=22000,motivo='Ficticio'),409)
    else:
        post(c, SIM+'/compras', solicitud(id_producto=v['items'][0]['id_producto'],cantidad=1,precio_unitario_centavos=22000,
             pagado_centavos=22000,pagador='bebidas_postres_efectivo',medio_pago='efectivo'),409)
    assert receptor(c, 'bebidas_postres_efectivo') == f


def test_rendicion_transito_no_repite_venta(flujo):
    c, v = flujo
    v.pop('medio_pago')
    v['pagos'] = [{'medio_pago':'efectivo','receptor':'bebidas_postres_efectivo_en_transito','importe_centavos':20026}]
    post(c, VENTAS, v)
    movimiento_id = sql("SELECT id_movimiento FROM pos_movimientos_simulados WHERE receptor LIKE '%_en_transito'")[0][0]
    r = c.post(f'{SIM}/cobros/{movimiento_id}/rendiciones', headers=ORIGEN, json=solicitud(importe_centavos=10000,motivo='Rendición ficticia'))
    assert r.status_code == 200, r.text
    assert receptor(c,'bebidas_postres_efectivo')['saldo_registrado_centavos'] == 11000
    assert receptor(c,'bebidas_postres_efectivo_en_transito')['saldo_registrado_centavos'] == 10026
    assert c.get(SIM+'/contabilidad').json()['cobrado_neto_centavos'] == 20026
    assert c.get(SIM+'/conciliacion').json()['cuadrado']


def cerrar(c, caja, contado):
    estado = c.get(DIARIO).json()['cajas'][caja]
    arqueo = post(c,f'{DIARIO}/{caja}/arqueo',solicitud(id_jornada=estado['id_jornada'],revision_efectivo=estado['revision_efectivo'],
                   contado_centavos=contado,motivo='Diferencia ficticia' if contado!=estado['esperado_centavos'] else None))
    return post(c,f'{DIARIO}/{caja}/cierre',solicitud(id_jornada=estado['id_jornada'],id_arqueo=arqueo['id_evento']))


@pytest.mark.parametrize('hora,propone', [('09:59',False),('10:00',True),('11:59',True),('12:00',False),('13:00',False)])
def test_jornadas_consecutivas_franja_y_diferencia_guardada(flujo, monkeypatch, hora, propone):
    from datetime import date,timedelta
    import pos_caja_diaria as diario
    c, _ = flujo
    cerrar(c,'comidas',990)
    cerrar(c,'bebidas_postres',1000)
    manana = (date.fromisoformat(ahora_local()[:10])+timedelta(days=1)).isoformat()
    monkeypatch.setattr(diario,'ahora_local',lambda:manana+'T'+hora+':00-03:00')
    estado = c.get(DIARIO).json()
    assert ('comidas' in estado['propuestas_apertura']) is propone
    post(c,f'{DIARIO}/comidas/apertura',solicitud(fecha=manana,inicial_centavos=980))
    apertura = c.get(DIARIO).json()['cajas']['comidas']['apertura']
    assert apertura['resultado']['diferencia_centavos'] == -10
    assert receptor(c,'comidas_efectivo')['saldo_registrado_centavos'] == 980
    assert contrato(c)['alertas_administrativas'][0]['codigo'] == 'CIERRE_CON_DIFERENCIA'


def test_jornada_pendiente_y_estado_incompatible_visibles(flujo, monkeypatch):
    from datetime import date,timedelta
    import pos_caja_diaria as diario
    c, _ = flujo
    manana=(date.fromisoformat(ahora_local()[:10])+timedelta(days=1)).isoformat()
    monkeypatch.setattr(diario,'ahora_local',lambda:manana+'T11:00:00-03:00')
    assert len(contrato(c)['jornadas_pendientes']) == 2
    sql("UPDATE pos_jornadas_caja SET cerrada=1 WHERE caja='comidas'")
    assert 'JORNADA_ESTADO_INCOMPATIBLE' in {x['codigo'] for x in contrato(c)['diferencias']}


def test_espejo_sin_enlace_detectado_sin_ajustar(flujo):
    c, v = flujo
    post(c,VENTAS,v)
    sql("UPDATE pos_diario_caja SET id_movimiento_pos=NULL WHERE tipo='cobro'")
    antes=sql('SELECT * FROM pos_diario_caja')
    assert 'ESPEJO_DIARIO_INCOMPATIBLE' in {x['codigo'] for x in contrato(c)['diferencias']}
    assert not c.get(SIM+'/conciliacion').json()['cuadrado']
    assert sql('SELECT * FROM pos_diario_caja') == antes


@pytest.mark.parametrize('fallo', ['movimiento','diario','recibo','inicio'])
def test_fallo_silencioso_transferencia_revierte_todo(flujo, fallo):
    c, _ = flujo
    if fallo == 'movimiento':
        sql("CREATE TRIGGER rechazo BEFORE INSERT ON pos_movimientos_simulados WHEN NEW.importe_centavos>0 BEGIN SELECT RAISE(IGNORE); END")
    elif fallo == 'diario':
        sql("CREATE TRIGGER rechazo BEFORE INSERT ON pos_diario_caja WHEN NEW.tipo='transferencia' BEGIN SELECT RAISE(IGNORE); END")
    elif fallo=='recibo':
        sql('CREATE TRIGGER rechazo BEFORE UPDATE ON pos_eventos_simulados BEGIN SELECT RAISE(IGNORE); END')
    else:
        sql('CREATE TRIGGER rechazo BEFORE INSERT ON pos_eventos_simulados BEGIN SELECT RAISE(IGNORE); END')
    usuario=c.get('/pos-api/yo').json()['usuario']
    datos=TransferenciaEntrada.model_validate(solicitud(origen='comidas_efectivo',destino='comidas_banco',importe_centavos=100,motivo='Ficticio'))
    with pytest.raises(sqlite3.IntegrityError):
        transferir_simulado(datos,usuario)
    assert sql('SELECT COUNT(*) FROM pos_movimientos_simulados') == [(0,)]
    assert sql('SELECT COUNT(*) FROM pos_eventos_simulados') == [(0,)]
    assert receptor(c,'comidas_efectivo')['saldo_registrado_centavos'] == 1000


def test_concurrencia_idempotente_no_duplica_transferencias(flujo):
    c, _ = flujo
    usuario=c.get('/pos-api/yo').json()['usuario']
    datos=TransferenciaEntrada.model_validate(solicitud(origen='comidas_efectivo',destino='comidas_banco',importe_centavos=200,motivo='Ficticio'))
    with ThreadPoolExecutor(max_workers=3) as h:
        ids=list(h.map(lambda _:transferir_simulado(datos,usuario)['id_evento'],range(3)))
    assert len(set(ids)) == 1
    assert sql('SELECT COUNT(*) FROM pos_movimientos_simulados') == [(2,)]
    assert receptor(c,'comidas_efectivo')['saldo_registrado_centavos'] == 800


def test_registros_laterales_bloqueados_lectura_sin_importar(flujo):
    c, _ = flujo
    sql('CREATE TABLE saldos_iniciales_caja(id_saldo_inicial INTEGER PRIMARY KEY,seccion TEXT,monto REAL,fecha_hora TEXT,id_venta_corte INTEGER,id_compra_corte INTEGER,id_gasto_corte INTEGER,id_movimiento_caja_corte INTEGER)')
    sql("INSERT INTO saldos_iniciales_caja VALUES(1,'rotiseria',500,'2020-01-01T11:00:00',0,0,0,0)")
    antes=sql('SELECT * FROM pos_diario_caja')
    r=contrato(c)['compatibilidad_legada']
    assert r['detectado'] and not r['integracion_habilitada'] and r['aperturas']==1
    assert sql('SELECT * FROM pos_diario_caja') == antes


def test_base_anterior_sin_tablas_opcionales_no_crea_esquema(venta_prueba):
    c,_=venta_prueba
    _iniciar_sesion(c,'admin-lectura','admin')
    antes=sql('SELECT name,sql FROM sqlite_schema ORDER BY name')
    r=contrato(c)
    assert r['asignacion_pagos']=={} and r['diferencias']==[]
    assert sql('SELECT name,sql FROM sqlite_schema ORDER BY name') == antes


def test_corte_unificado_no_se_descompone_ni_omite_eventos_directos(unificado):
    from pos_preproduccion import abrir_base,configuracion
    from pos_saldo_unificado import conciliacion
    carpeta,c,ids,_=unificado
    with closing(abrir_base(carpeta,configuracion(carpeta)['id'])) as db:
        anterior=conciliacion(db)['revision']
    venta_delivery(c,ids,pagos=[{**pago_unificado('comidas',1250000)},
        {'receptor':'comidas_efectivo_en_transito','medio_pago':'efectivo','importe_centavos':200000,'envio_directo':True}])
    with closing(abrir_base(carpeta,configuracion(carpeta)['id'])) as db:
        r=informe(db)
        assert all(not f['efectivo_identificable'] and not f['digital_identificable'] for f in r['receptores'])
        assert conciliacion(db)['revision'] != anterior


def test_jornada_completa_conciliada_con_evidencia(flujo):
    from pathlib import Path
    c,v=flujo
    v.pop('medio_pago')
    v.update(fiado=True,deudor='Cliente ficticio',pagos=[
        {'medio_pago':'efectivo','receptor':'bebidas_postres_efectivo','importe_centavos':10000},
        {'medio_pago':'transferencia','receptor':'bebidas_postres_banco','importe_centavos':5000}])
    alta=post(c,VENTAS,v)
    captura=sql('SELECT * FROM pos_costos_lineas')
    movimiento(c,'bebidas_postres','aporte',200)
    movimiento(c,'bebidas_postres','retiro',100)
    movimiento(c,'bebidas_postres','gasto',50)
    comprar(c,v['items'][0]['id_producto'],300,'bebidas_postres_efectivo','efectivo')
    post(c,f"{VENTAS}/{alta['id_venta']}/abonos",solicitud(pagos=[
        {'medio_pago':'transferencia','receptor':'bebidas_postres_banco','importe_centavos':5026}]))
    post(c,f"{VENTAS}/{alta['id_venta']}/devoluciones",solicitud(motivo='Devolución ficticia',items=[{'linea':1,'cantidad':1}]))
    assert receptor(c,'bebidas_postres_efectivo')['saldo_registrado_centavos']==10750
    assert receptor(c,'bebidas_postres_banco')['saldo_registrado_centavos']==13
    cerrar(c,'bebidas_postres',10740)
    cerrar(c,'comidas',1000)
    diagnostico=c.get(SIM+'/conciliacion').json()
    assert diagnostico['cuadrado'] and not diagnostico['diferencias']
    assert diagnostico['contrato_financiero']['alertas_administrativas']
    assert not diagnostico['contrato_financiero']['jornadas_pendientes']
    r=c.get(SIM+'/contabilidad').json()
    assert r['devengado_centavos']==r['cobrado_neto_centavos']==10013
    assert r['compras_centavos']==300 and r['gastos_centavos']==50
    assert r['rentabilidad_historica']['costo_ventas_centavos']==3000
    assert sql('SELECT * FROM pos_costos_lineas')==captura
    ruta=Path(__file__).resolve().parents[1]/'.audit-artifacts'/'jornada-financiera.json'
    ruta.parent.mkdir(exist_ok=True)
    ruta.write_text(json.dumps({'datos':'exclusivamente ficticios','esperado_fisico':10750,
        'contado_fisico':10740,'diferencia':-10,'banco_registrado':13,
        'contabilidad':r,'conciliacion':diagnostico},ensure_ascii=False,indent=2),encoding='utf-8')


@pytest.mark.parametrize('tabla', ['pos_compras_caja','pos_delivery_movimientos'])
def test_recibo_omitido_revierte_compra_o_custodia(flujo, tabla):
    from fastapi import HTTPException
    from pos_simulacion import transaccion_simulacion,registrar_venta_simulada,VentaSimuladaEntrada
    from pos_compras_caja import preparar_compras_caja,operar_compra,CompraCajaEntrada
    from pos_delivery import crear
    c,v=flujo
    with closing(obtener_conexion()) as db,db:
        (preparar_compras_caja if tabla=='pos_compras_caja' else crear)(db)
        db.execute(f'CREATE TRIGGER rechazar_recibo BEFORE INSERT ON {tabla} BEGIN SELECT RAISE(IGNORE); END')
    usuario=c.get('/pos-api/yo').json()['usuario']
    antes=sql('SELECT stock FROM productos WHERE id_producto=?',(v['items'][0]['id_producto'],))
    with pytest.raises(HTTPException):
        if tabla=='pos_compras_caja':
            with transaccion_simulacion(escritura=True) as db:
                operar_compra(db,'alta',CompraCajaEntrada.model_validate(solicitud(
                    id_producto=v['items'][0]['id_producto'],cantidad=1,precio_unitario_centavos=100,
                    pagado_centavos=100,pagador='bebidas_postres_efectivo',medio_pago='efectivo')),usuario)
        else:
            v.pop('medio_pago')
            v.update(entrega={'origen':'mostrador','modalidad':'envio','direccion':'Calle ficticia','circuito':'sencillo'},
                total_esperado_centavos=220026,pagos=[{'medio_pago':'efectivo','receptor':'bebidas_postres_efectivo','importe_centavos':220026}])
            registrar_venta_simulada(VentaSimuladaEntrada.model_validate(v),usuario)
    assert sql('SELECT stock FROM productos WHERE id_producto=?',(v['items'][0]['id_producto'],))==antes
    assert sql('SELECT COUNT(*) FROM pos_ventas_simuladas')==[(0,)]
    assert sql(f'SELECT COUNT(*) FROM {tabla}')==[(0,)]
    assert receptor(c,'bebidas_postres_efectivo')['saldo_registrado_centavos']==1000


@pytest.mark.parametrize('modo', ['ABORT','IGNORE'])
def test_fallo_final_venta_revierte_costos_stock_y_finanzas(flujo,modo):
    from pos_simulacion import registrar_venta_simulada,VentaSimuladaEntrada
    c,v=flujo
    orden="SELECT RAISE(ABORT,'fallo ficticio')" if modo=='ABORT' else 'SELECT RAISE(IGNORE)'
    sql('CREATE TRIGGER rechazo_final BEFORE UPDATE ON pos_eventos_simulados BEGIN '+orden+'; END')
    usuario=c.get('/pos-api/yo').json()['usuario']
    antes=sql('SELECT stock FROM productos WHERE id_producto=?',(v['items'][0]['id_producto'],))
    with pytest.raises(sqlite3.IntegrityError):
        registrar_venta_simulada(VentaSimuladaEntrada.model_validate(v),usuario)
    assert sql('SELECT COUNT(*) FROM pos_ventas_simuladas')==[(0,)]
    assert sql('SELECT stock FROM productos WHERE id_producto=?',(v['items'][0]['id_producto'],))==antes
    assert receptor(c,'bebidas_postres_efectivo')['saldo_registrado_centavos']==1000
    assert sql("SELECT COUNT(*) FROM sqlite_schema WHERE name='pos_costos_lineas'")==[(0,)]


def test_delivery_se_entrega_sin_nuevo_ingreso(flujo):
    c,v=flujo
    v.pop('medio_pago')
    v.update(entrega={'origen':'mostrador','modalidad':'envio','direccion':'Calle ficticia','circuito':'sencillo'},
        total_esperado_centavos=220026,pagos=[{'medio_pago':'efectivo','receptor':'bebidas_postres_efectivo','importe_centavos':220026}])
    alta=post(c,VENTAS,v)
    datos=solicitud(version=1,estado='entregado',receptor_reparto='bebidas_postres_efectivo')
    entrega=post(c,f"{SIM}/pedidos/{alta['id_pedido']}/estado",datos)
    assert post(c,f"{SIM}/pedidos/{alta['id_pedido']}/estado",datos)==entrega
    propio=receptor(c,'bebidas_postres_efectivo')
    assert propio['saldo_registrado_centavos']==21026 and propio['custodia_delivery_centavos']==0
    assert c.get(SIM+'/contabilidad').json()['devengado_centavos']==20026
    assert c.get(SIM+'/conciliacion').json()['cuadrado']


def test_modelo_unificado_pendiente_visible_sin_saldo_inventado(unificado):
    from pos_preproduccion import abrir_base,configuracion
    carpeta,c,_,_=unificado
    with closing(abrir_base(carpeta,configuracion(carpeta)['id'])) as db,db:
        db.execute('UPDATE pos_saldos_iniciales SET saldo_centavos=NULL,corte=NULL,responsable=NULL')
    r=c.get(CONTRATO).json()
    assert r['receptores']==[] and r['diferencias'][0]['codigo']=='SALDO_UNIFICADO_PENDIENTE_VALIDACION'


def test_edge_muestra_fuentes_y_no_certifica_saldo_global(circuito,tmp_path):
    from pathlib import Path
    navegador_path=os.getenv('POS_TEST_BROWSER')
    if not navegador_path:
        pytest.skip('Configurar POS_TEST_BROWSER con Edge')
    import websocket
    from scripts.abadion_preproduccion import crear_app
    from tests.test_pos_web import abrir_navegador,esperar
    carpeta,c,ids=circuito
    venta_delivery(c,ids)
    with closing(abrir_navegador(crear_app(carpeta),navegador_path,tmp_path,websocket)) as navegador:
        evaluar=next(navegador)
        esperar(lambda:evaluar("document.querySelector('#adminAccess')?.getClientRects().length>0"))
        evaluar("document.querySelector('#adminAccess').click()")
        esperar(lambda:evaluar("document.querySelector('#usuarioPos')!==null"))
        clave=json.loads((carpeta/'credenciales.json').read_text())['admin-preprod']
        evaluar("document.querySelector('#usuarioPos').value='admin-preprod';document.querySelector('#claveAdmin').value="+json.dumps(clave)+";document.querySelector('#accept').click()")
        esperar(lambda:evaluar("document.querySelector('#contabilidadPos')?.hidden===false"))
        evaluar("document.querySelector('#contabilidadPos').click()")
        esperar(lambda:evaluar("document.querySelector('#conciliacionFinancieraPos')?.textContent.includes('No es un saldo global certificado')"))
        texto=evaluar("document.querySelector('#conciliacionFinancieraPos').textContent")
        assert 'Custodia delivery' in texto and 'Libro propio' in texto
        if os.getenv('POS_UI_CAPTURAS'):
            salida=Path(os.environ['POS_UI_CAPTURAS']);salida.mkdir(parents=True,exist_ok=True)
            evaluar("document.querySelector('#conciliacionFinancieraPos').scrollIntoView({block:'start'});void 0")
            (salida/'abadion-conciliacion-financiera.png').write_bytes(evaluar.captura())


def test_caida_tras_primera_pata_recupera_sin_transferencia_parcial(flujo):
    import subprocess,sys
    from pathlib import Path
    c,_=flujo
    usuario=c.get('/pos-api/yo').json()['usuario']
    datos=solicitud(origen='comidas_efectivo',destino='comidas_banco',importe_centavos=200,motivo='Ficticio')
    codigo='''
import os,sys,json,pos_simulacion
from pos_cobros import TransferenciaEntrada
original=pos_simulacion.registrar_movimiento
def caer(*args,**kwargs):
    original(*args,**kwargs)
    os._exit(23)
pos_simulacion.registrar_movimiento=caer
datos,usuario=json.loads(sys.argv[1])
pos_simulacion.transferir_simulado(TransferenciaEntrada.model_validate(datos),usuario)
'''
    r=subprocess.run([sys.executable,'-c',codigo,json.dumps([datos,usuario])],
        env={**os.environ,'PYTHONPATH':str(Path(__file__).resolve().parents[1]/'src')},capture_output=True,timeout=30)
    assert r.returncode==23,r.stderr.decode(errors='replace')
    assert sql('SELECT COUNT(*) FROM pos_eventos_simulados')==[(0,)]
    assert sql('SELECT COUNT(*) FROM pos_movimientos_simulados')==[(0,)]
    assert sql('PRAGMA integrity_check')==[('ok',)]
    assert receptor(c,'comidas_efectivo')['saldo_registrado_centavos']==1000


def test_diagnostico_solo_administracion(flujo):
    from fastapi.testclient import TestClient
    from api import app
    c,_=flujo
    assert TestClient(app).get(CONTRATO).status_code==401
    c.cookies.delete('abadion_pos_admin')
    assert c.get(CONTRATO).status_code==403


@pytest.mark.parametrize('operacion',['compra','transferencia'])
def test_custodia_digital_no_financia_operaciones_propias(flujo,operacion):
    c,v=flujo
    v.pop('medio_pago')
    v.update(entrega={'origen':'mostrador','modalidad':'envio','direccion':'Calle ficticia','circuito':'sencillo'},
        total_esperado_centavos=220026,pagos=[{'medio_pago':'transferencia','receptor':'bebidas_postres_banco','importe_centavos':220026}])
    post(c,VENTAS,v)
    antes=receptor(c,'bebidas_postres_banco')
    if operacion=='compra':
        post(c,SIM+'/compras',solicitud(id_producto=v['items'][0]['id_producto'],cantidad=1,precio_unitario_centavos=21000,
            pagado_centavos=21000,pagador='bebidas_postres_banco',medio_pago='transferencia'),409)
    else:
        post(c,SIM+'/cajas/transferencias',solicitud(origen='bebidas_postres_banco',destino='bebidas_postres_mercado_pago',importe_centavos=21000,motivo='Ficticio'),409)
    assert receptor(c,'bebidas_postres_banco')==antes


@pytest.mark.parametrize('anomalia',['espejo','dos_modelos'])
def test_incompatibilidad_custodia_visible_sin_reparacion(flujo,anomalia):
    c,v=flujo
    v.pop('medio_pago')
    v.update(entrega={'origen':'mostrador','modalidad':'envio','direccion':'Calle ficticia','circuito':'sencillo'},
        total_esperado_centavos=220026,pagos=[{'medio_pago':'efectivo','receptor':'bebidas_postres_efectivo','importe_centavos':220026}])
    alta=post(c,VENTAS,v)
    if anomalia=='espejo':
        sql('UPDATE pos_delivery_movimientos SET id_movimiento=NULL')
        esperado='ESPEJO_DELIVERY_INCOMPATIBLE'
    else:
        from pos_envios import crear_libro_reparto
        with closing(obtener_conexion()) as db,db:
            crear_libro_reparto(db)
            evento=db.execute("SELECT id_evento FROM pos_eventos_simulados WHERE tipo='venta'").fetchone()[0]
            db.execute("INSERT INTO pos_fondos_reparto VALUES(?,?,'bebidas_postres_banco',100,'solo-ficticio','recepcion')",(evento,alta['id_venta']))
        esperado='DOS_MODELOS_CUSTODIA_MISMA_VENTA'
    antes=sql('SELECT * FROM pos_delivery_movimientos')
    assert esperado in {d['codigo'] for d in contrato(c)['diferencias']}
    assert sql('SELECT * FROM pos_delivery_movimientos')==antes


def test_compra_financiada_separa_pago_y_deuda_sin_otro_gasto(flujo):
    c,v=flujo
    post(c,SIM+'/compras',solicitud(id_producto=v['items'][0]['id_producto'],cantidad=1,
        precio_unitario_centavos=300,pagado_centavos=100,pagador='bebidas_postres_efectivo',
        medio_pago='efectivo',cuenta_deuda='Proveedor ficticio conciliación'))
    f=contrato(c)
    deuda=next(d for d in f['deudas_negocio_por_cuenta'] if d['nombre']=='Proveedor ficticio conciliación')
    assert deuda['saldo_moneda_origen']==2 and deuda['reserva_moneda_origen']==0
    assert receptor(c,'bebidas_postres_efectivo')['saldo_registrado_centavos']==900
    assert c.get(SIM+'/contabilidad').json()['compras_centavos']==300
    assert sql('SELECT COUNT(*) FROM gastos')==[(0,)]


def test_venta_omitida_no_reutiliza_id_anterior_ni_captura_costos(flujo):
    from fastapi import HTTPException
    from pos_simulacion import registrar_venta_simulada,VentaSimuladaEntrada
    c,v=flujo
    sql('CREATE TRIGGER omitir_venta BEFORE INSERT ON pos_ventas_simuladas BEGIN SELECT RAISE(IGNORE); END')
    usuario=c.get('/pos-api/yo').json()['usuario']
    with pytest.raises(HTTPException):
        registrar_venta_simulada(VentaSimuladaEntrada.model_validate(v),usuario)
    assert sql('SELECT COUNT(*) FROM pos_ventas_simuladas')==[(0,)]
    assert sql('SELECT COUNT(*) FROM pos_movimientos_simulados')==[(0,)]
    assert sql("SELECT COUNT(*) FROM sqlite_schema WHERE name='pos_costos_lineas'")==[(0,)]
