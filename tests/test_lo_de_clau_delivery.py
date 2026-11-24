import json
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from uuid import uuid4

import pytest

from pos_preproduccion import abrir_base, configuracion, integridad
from pos_contabilidad import fecha_local
from scripts.abadion_preproduccion import preparar
from tests.test_preproduccion import cliente, SIM, post


def solicitud(**datos):
    return {'id_solicitud': str(uuid4()), **datos}


@pytest.fixture
def circuito(tmp_path):
    carpeta = tmp_path / 'Preproduccion'
    preparar(carpeta)
    with closing(abrir_base(carpeta, configuracion(carpeta)['id'])) as db, db:
        db.executemany('INSERT INTO productos(nombre,categoria,precio_venta,controla_stock,stock) VALUES (?,?,?,1,10)',
                       [('Comida QA', 'Comidas', 8000), ('Postre QA', 'Postres', 4500)])
        ids = [r[0] for r in db.execute('SELECT id_producto FROM productos ORDER BY id_producto')]
    c = cliente(carpeta)
    for caja in ('comidas', 'bebidas_postres'):
        post(c, SIM + f'/caja-diaria/{caja}/apertura', fecha=fecha_local(), inicial_centavos=2_000_000)
    return carpeta, c, ids


def venta(c, ids, **campos):
    datos = solicitud(items=[{'id_producto': p, 'cantidad': 1} for p in ids],
                      entrega={'origen': 'mostrador', 'modalidad': 'envio', 'direccion': 'Calle QA 123', 'circuito': 'sencillo'},
                      total_esperado_centavos=1_450_000,
                      pagos=[{'receptor': 'comidas_efectivo', 'medio_pago': 'efectivo', 'importe_centavos': 1_450_000}])
    datos.update(campos)
    r = c.post(SIM + '/ventas', json=datos)
    assert r.status_code == 200, r.text
    assert c.post(SIM + '/ventas', json=datos).json() == r.json()
    return r.json()


def entregar(c, v, receptor='comidas_efectivo', **datos):
    return post(c, SIM + f"/pedidos/{v['id_pedido']}/estado", version=1, estado='entregado', receptor_reparto=receptor, **datos)


def cuadrado(c):
    r = c.get(SIM + '/conciliacion').json()
    assert r['cuadrado'], r['diferencias']
    return r


@pytest.mark.parametrize('receptor,medio', [('comidas_efectivo','efectivo'), ('bebidas_postres_banco','transferencia'), ('comidas_mercado_pago','mercado_pago')])
def test_cobro_conjunto_entrega_idempotente_y_cajas(circuito, receptor, medio):
    carpeta, c, ids = circuito
    v = venta(c, ids, pagos=[{'receptor': receptor, 'medio_pago': medio, 'importe_centavos':1_450_000, 'referencia':'QA-pago'}])
    assert v['total_centavos'] == v['cobrado_centavos'] == 1_250_000
    assert v['delivery']['cobrado_centavos'] == 200_000
    assert v['saldo_cliente_centavos'] == v['saldo_pendiente_centavos'] == 0
    assert v['devengado_centavos'] == {'comidas':800_000, 'bebidas_postres':450_000}
    estado = solicitud(version=1, estado='entregado', receptor_reparto=receptor)
    endpoint = SIM + f"/pedidos/{v['id_pedido']}/estado"
    with ThreadPoolExecutor(max_workers=2) as equipo:
        respuestas = list(equipo.map(lambda _: c.post(endpoint, json=estado), range(2)))
    assert [r.status_code for r in respuestas] == [200,200]
    assert respuestas[0].json() == respuestas[1].json()
    final = respuestas[0].json()
    assert [h['estado'] for h in final['historial']] == ['pendiente','entregado']
    assert final['delivery']['custodia_centavos'] == final['saldo_reparto_centavos'] == 0
    assert c.post(endpoint, json=solicitud(version=1, estado='entregado', receptor_reparto=receptor)).status_code == 409
    informe = cuadrado(c)
    assert sum(s['devengado_centavos'] for s in informe['pos_centavos']['secciones'].values()) == 1_250_000
    contable = c.get(SIM+'/contabilidad').json()
    assert contable['cobrado_neto_centavos'] == 1_250_000
    assert contable['gastos_centavos'] == 0
    with closing(abrir_base(carpeta, configuracion(carpeta)['id'])) as db:
        integridad(db)
        assert db.execute("SELECT COUNT(*) FROM pos_delivery_movimientos WHERE tipo='entrega'").fetchone()[0] == 1
        assert db.execute('SELECT SUM(importe_centavos) FROM pos_movimientos_simulados WHERE receptor=?', (receptor,)).fetchone()[0] == 1_250_000


def test_transferencia_no_saca_efectivo_hasta_elegir_caja(circuito):
    _, c, ids = circuito
    v = venta(c, ids, pagos=[{'receptor':'bebidas_postres_banco','medio_pago':'transferencia','importe_centavos':1_450_000}])
    cajas = c.get(SIM+'/caja-diaria').json()['cajas']
    assert cajas['comidas']['esperado_centavos'] == 2_000_000
    ruta = SIM + f"/pedidos/{v['id_pedido']}/estado"
    assert c.post(ruta, json=solicitud(version=1, estado='entregado')).status_code == 422
    entregar(c,v, 'comidas_efectivo')
    cajas = c.get(SIM+'/caja-diaria').json()['cajas']
    assert cajas['comidas']['esperado_centavos'] == 1_800_000
    assert cajas['bebidas_postres']['esperado_centavos'] == 2_000_000
    assert sum(f['custodia_centavos'] for f in cuadrado(c)['pos_centavos']['delivery']) == 0


@pytest.mark.parametrize('entregada', [False,True])
@pytest.mark.parametrize('tipo', ['anulacion','devoluciones'])
def test_reembolso_antes_y_despues_del_reparto(circuito, entregada, tipo):
    _, c, ids = circuito
    v = venta(c, ids)
    if entregada:
        entregar(c,v)
    ruta = SIM+f"/ventas/{v['id_venta']}/{tipo}"
    datos = solicitud(motivo='Reverso QA', **({'items':[{'linea':1,'cantidad':1},{'linea':2,'cantidad':1}]} if tipo=='devoluciones' else {}))
    r = c.post(ruta,json=datos)
    assert r.status_code == 200, r.text
    assert c.post(ruta,json=datos).json() == r.json()
    assert r.json()['reembolsado_centavos'] == (1_250_000 if entregada else 1_450_000)
    assert r.json()['saldo_cliente_centavos'] == 0
    assert r.json()['delivery']['custodia_centavos'] == 0
    if not entregada:
        assert c.post(SIM+f"/pedidos/{v['id_pedido']}/estado",json=solicitud(
            version=1,estado='entregado',receptor_reparto='comidas_efectivo')).status_code==409
    cuadrado(c)


def test_fiado_total_adelanto_abono_y_cuenta_cliente(circuito):
    _, c, ids = circuito
    persona = post(c, SIM+'/clientes', nombre='Cliente QA')['id_cliente']
    v = venta(c,ids,pagos=[],fiado=True,id_cliente=persona)
    ruta = SIM+f"/pedidos/{v['id_pedido']}/estado"
    assert c.post(ruta,json=solicitud(version=1,estado='entregado',receptor_reparto='comidas_efectivo')).status_code == 409
    e = entregar(c,v, confirmar_pendiente=True, saldo_confirmado_centavos=1_450_000, motivo='Fiado excepcional QA')
    assert e['delivery']['entregado_centavos'] == 200_000
    assert e['saldo_cliente_centavos'] == 1_450_000
    assert c.get(SIM+f'/clientes/{persona}').json()['saldo_centavos'] == 1_450_000
    abono = post(c,SIM+f"/ventas/{v['id_venta']}/abonos",pagos=[{'receptor':'comidas_efectivo','medio_pago':'efectivo','importe_centavos':1_450_000}])
    assert abono['saldo_cliente_centavos'] == abono['delivery']['custodia_centavos'] == 0
    assert c.get(SIM+f'/clientes/{persona}').json()['saldo_centavos'] == 0
    cuadrado(c)


def test_bonificacion_retiro_cancelacion_y_permisos(circuito):
    carpeta,c,ids = circuito
    envio = {'titular':'repartidor','importe_centavos':0,'motivo_bonificacion':'Atención QA'}
    v = venta(c,ids,envio=envio,total_esperado_centavos=1_250_000,pagos=[{'receptor':'comidas_efectivo','medio_pago':'efectivo','importe_centavos':1_250_000}])
    assert v['envio']['motivo_bonificacion'] == 'Atención QA'
    entregar(c,v,receptor=None)
    otra = venta(c,ids,entrega={'origen':'mostrador','modalidad':'retiro','circuito':'sencillo'},total_esperado_centavos=1_250_000,medio_pago='efectivo',pagos=None)
    ruta = SIM+f"/pedidos/{otra['id_pedido']}/estado"
    op = cliente(carpeta,'ventas')
    assert op.post(ruta,json=solicitud(version=1,estado='cancelado',motivo='QA')).status_code == 403
    assert c.post(ruta,json=solicitud(version=1,estado='cancelado',motivo='QA')).status_code == 409
    post(c,SIM+f"/ventas/{otra['id_venta']}/anulacion",motivo='QA')
    assert post(c,ruta,version=1,estado='cancelado',motivo='QA')['estado']=='cancelado'
    cuadrado(c)


def test_validaciones_no_crean_cobros_ni_salida_sin_fondos(circuito):
    _,c,ids = circuito
    base = solicitud(items=[{'id_producto':ids[0],'cantidad':1}], entrega={'origen':'mostrador','modalidad':'envio','direccion':'QA','circuito':'sencillo'},total_esperado_centavos=1_000_000, pagos=[{'receptor':'comidas_banco','medio_pago':'transferencia','importe_centavos':1_000_000}])
    for envio in ({'titular':'negocio','importe_centavos':200_000},{'titular':'repartidor','importe_centavos':0}):
        assert c.post(SIM+'/ventas',json={**base,'envio':envio}).status_code == 422
    v = c.post(SIM+'/ventas',json=base).json()
    ruta = SIM+f"/pedidos/{v['id_pedido']}/estado"
    assert c.post(ruta,json=solicitud(version=1,estado='entregado',receptor_reparto='bebidas_postres_banco')).status_code==409
    assert c.get(SIM+'/pedidos').json()['pedidos'][0]['version']==1
    cuadrado(c)


def test_abono_global_delivery_y_correccion_sin_doble_reembolso(circuito):
    _,c,ids = circuito
    persona = post(c,SIM+'/clientes',nombre='Cliente global QA')['id_cliente']
    v = venta(c,ids,pagos=[],fiado=True,id_cliente=persona)
    ruta = SIM+f'/clientes/{persona}'
    pago = {'receptor':'comidas_banco','medio_pago':'transferencia','importe_centavos':1_450_000,'referencia':'global-QA'}
    previa = c.post(ruta+'/abonos/vista-previa',json=pago).json()
    assert previa['imputaciones'][0]['delivery_centavos']==200_000
    datos = solicitud(pago=pago,vista_previa=previa['vista_previa'])
    r = c.post(ruta+'/abonos',json=datos)
    assert r.status_code==200,r.text
    assert c.post(ruta+'/abonos',json=datos).json()==r.json()
    assert c.get(ruta).json()['saldo_centavos']==0
    correccion = solicitud(motivo='Corrección de abono QA')
    endpoint = ruta+f"/abonos/{datos['id_solicitud']}/correccion"
    r = c.post(endpoint,json=correccion)
    assert r.status_code==200,r.text
    assert c.post(endpoint,json=correccion).json()==r.json()
    assert c.post(endpoint,json=solicitud(motivo='Otro clic')).status_code==409
    assert c.get(ruta).json()['saldo_centavos']==1_450_000
    cuadrado(c)


def test_pago_combinado_devolucion_parcial_y_caja_cerrada(circuito):
    _,c,ids = circuito
    v = venta(c,ids,pagos=[{'receptor':'comidas_efectivo','medio_pago':'efectivo','importe_centavos':800_000},
                          {'receptor':'bebidas_postres_banco','medio_pago':'transferencia','importe_centavos':650_000}])
    parcial = post(c,SIM+f"/ventas/{v['id_venta']}/devoluciones",motivo='Devuelve postre QA',items=[{'linea':2,'cantidad':1}])
    assert parcial['reembolsado_centavos']==450_000
    assert parcial['delivery']['cobrado_centavos']==200_000
    assert parcial['saldo_cliente_centavos']==0
    caja = c.get(SIM+'/caja-diaria').json()['cajas']['comidas']
    arqueo = post(c,SIM+'/caja-diaria/comidas/arqueo',id_jornada=caja['id_jornada'],
                  revision_efectivo=caja['revision_efectivo'],contado_centavos=caja['esperado_centavos'])
    post(c,SIM+'/caja-diaria/comidas/cierre',id_jornada=caja['id_jornada'],id_arqueo=arqueo['id_evento'])
    ruta = SIM+f"/pedidos/{v['id_pedido']}/estado"
    assert c.post(ruta,json=solicitud(version=1,estado='entregado',receptor_reparto='comidas_efectivo')).status_code==409
    assert c.get(SIM+'/pedidos').json()['pedidos'][0]['version']==1
    entregar(c,v,'bebidas_postres_banco')
    cuadrado(c)


def test_conciliacion_detecta_manipulacion_delivery(circuito):
    carpeta,c,ids = circuito
    venta(c,ids)
    with closing(abrir_base(carpeta, configuracion(carpeta)['id'])) as db,db:
        db.execute('UPDATE pos_delivery_movimientos SET importe_centavos=importe_centavos+1')
    r = c.get(SIM+'/conciliacion').json()
    assert not r['cuadrado']
    assert {'DELIVERY_DESCUADRADO','DELIVERY_AUDITORIA_INVALIDA','EVENTO_POS_DESCUADRADO'} <= {d['codigo'] for d in r['diferencias']}


def test_worker_delivery_reinicio_backup_restore(circuito,tmp_path):
    import shutil
    from pos_preproduccion import restaurar, validar_respaldo
    from pos_entrenamiento_db import bloquear_entrenamiento
    from tests.test_preproduccion_jornada_v1 import servidor, ingresar

    carpeta,c,ids = circuito
    v = venta(c,ids)
    entregar(c,v)
    persona = post(c,SIM+'/clientes',nombre='Cliente restore QA')['id_cliente']
    fiada = venta(c,ids,pagos=[],fiado=True,id_cliente=persona)
    entregar(c,fiada,confirmar_pendiente=True,saldo_confirmado_centavos=1_450_000,motivo='QA fiado restore')
    venta(c,ids,envio={'titular':'repartidor','importe_centavos':0,'motivo_bonificacion':'QA restore'},
          total_esperado_centavos=1_250_000,pagos=[{'receptor':'comidas_banco','medio_pago':'transferencia','importe_centavos':1_250_000}])
    rutas = ['ventas','pedidos','pedidos?finalizados=true','cajas','caja-diaria','conciliacion','contabilidad',f'clientes/{persona}']
    def relevar(conexion):
        estado = {r:conexion.get(SIM+'/'+r).raise_for_status().json() for r in rutas}
        assert estado['conciliacion']['cuadrado']
        with closing(abrir_base(carpeta,configuracion(carpeta)['id'],lectura=True)) as db:
            integridad(db)
            estado['stock'] = db.execute('SELECT id_producto,stock FROM productos ORDER BY id_producto').fetchall()
        return estado
    with servidor(carpeta) as (conexion,control):
        ingresar(carpeta,conexion,'admin')
        antes = relevar(conexion)
        nombre = conexion.post('/_preprod/backup',headers=control).raise_for_status().json()['archivo']
    copia = validar_respaldo(carpeta,nombre)
    with servidor(carpeta) as (conexion,_):
        ingresar(carpeta,conexion,'admin')
        assert relevar(conexion)==antes
    destino = tmp_path/'recuperacion'/'Preproduccion'
    (destino/'backups').mkdir(parents=True)
    datos = configuracion(carpeta)
    (destino/'instalacion.json').write_text(json.dumps({**datos,'carpeta':str(destino)}),encoding='utf-8')
    shutil.copyfile(carpeta/'credenciales.json',destino/'credenciales.json')
    for archivo in (copia,copia.with_suffix('.json')):
        shutil.copyfile(archivo,destino/'backups'/archivo.name)
    with bloquear_entrenamiento(destino):
        restaurar(destino,nombre,base_ausente=True)
    with servidor(destino) as (conexion,_):
        ingresar(destino,conexion,'admin')
        assert relevar(conexion)==antes
    with closing(abrir_base(destino,configuracion(destino)['id'],lectura=True)) as db:
        integridad(db)
        assert db.execute('SELECT SUM(importe_centavos) FROM pos_delivery_movimientos').fetchone()[0]==-200_000

@pytest.mark.parametrize('en_transito',[False,True])
def test_efectivo_retenido_no_ingresa_ni_sale_de_caja(circuito,en_transito):
    _,c,ids = circuito
    receptor = 'comidas_efectivo' + ('_en_transito' if en_transito else '')
    v = venta(c,ids,pagos=[{'receptor':receptor,'medio_pago':'efectivo','importe_centavos':1_450_000,'envio_directo':True}])
    assert v['delivery']['cobrado_directo_centavos']==200_000
    assert v['delivery']['custodia_centavos']==0
    antes = c.get(SIM+'/caja-diaria').json()['cajas']['comidas']['esperado_centavos']
    assert antes == (2_000_000 if en_transito else 3_250_000)
    ruta = SIM+f"/pedidos/{v['id_pedido']}/estado"
    assert c.post(ruta,json=solicitud(version=1,estado='entregado',receptor_reparto='comidas_efectivo')).status_code==422
    entregar(c,v,receptor=None)
    assert c.get(SIM+'/caja-diaria').json()['cajas']['comidas']['esperado_centavos']==antes
    if en_transito:
        historial = c.get(SIM+'/ventas').json()['ventas'][0]
        cobro = historial['historial'][0]['movimientos'][0]
        assert cobro['pendiente_rendicion_centavos']==1_250_000
        post(c,SIM+f"/cobros/{cobro['id_movimiento']}/rendiciones",importe_centavos=1_250_000,motivo='Entrega de productos QA')
        assert c.get(SIM+'/caja-diaria').json()['cajas']['comidas']['esperado_centavos']==3_250_000
    cuadrado(c)


def test_pedido_sencillo_sin_venta_conversion_y_cancelacion(circuito):
    _,c,ids = circuito
    datos = solicitud(items=[{'id_producto':p,'cantidad':1} for p in ids],
                      entrega={'origen':'mostrador','modalidad':'envio','direccion':'QA','circuito':'sencillo'})
    r = c.post(SIM+'/pedidos',json=datos)
    assert r.status_code==200,r.text
    p = r.json()
    assert c.post(SIM+'/pedidos',json=datos).json()==p
    assert p['total_estimado_centavos']==1_450_000
    ruta=SIM+f"/pedidos/{p['id_pedido']}"
    assert c.post(ruta+'/estado',json=solicitud(version=1,estado='entregado')).status_code==409
    assert c.get(ruta+'/cotizacion').json()['total_centavos']==1_450_000
    conversion=solicitud(total_esperado_centavos=1_450_000,pagos=[{'receptor':'comidas_efectivo','medio_pago':'efectivo','importe_centavos':1_450_000}])
    v=c.post(ruta+'/venta',json=conversion)
    assert v.status_code==200,v.text
    assert c.post(ruta+'/venta',json=conversion).json()==v.json()
    entregar(c,v.json())
    cancelable = c.post(SIM+'/pedidos',json={**datos,**solicitud()}).json()
    post(c,SIM+f"/pedidos/{cancelable['id_pedido']}/estado",version=1,estado='cancelado',motivo='QA sin venta')
    assert c.get(SIM+'/ventas').json()['ventas'][0]['saldo_cliente_centavos']==0
    cuadrado(c)
