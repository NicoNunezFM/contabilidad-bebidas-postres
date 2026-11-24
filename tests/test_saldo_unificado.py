"""Ensayos ficticios: ninguna instalación ni importe real participa."""
import json
import os
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path

import pytest

from pos_saldo_unificado import crear_esquema
from pos_preproduccion import abrir_base, configuracion
from tests.test_lo_de_clau_delivery import circuito, venta, entregar, cuadrado
from tests.test_preproduccion import SIM, cliente, post
from tests.test_pos_qa_integrado import solicitud

RUTA = SIM + '/saldo-unificado'


@pytest.fixture
def unificado(circuito):
    carpeta, c, ids = circuito
    with closing(abrir_base(carpeta, configuracion(carpeta)['id'])) as db, db:
        bebida = db.execute("INSERT INTO productos(nombre,categoria,precio_venta,controla_stock,stock) VALUES ('Bebida inexistente QA','Bebidas',100,1,0)").lastrowid
        crear_esquema(db)
        db.execute("UPDATE pos_saldos_iniciales SET saldo_centavos=3000000,corte='2020-01-01T00:00:00-03:00',responsable='Responsable ficticio'")
        db.execute("INSERT INTO pos_deudas_apertura VALUES (1,'comidas','Tarjeta QA',500000,'2030-01-15','pago_unico')")
    return carpeta, c, ids, bebida


def saldos(c):
    return {k: v['saldo_centavos'] for k,v in c.get(RUTA).json()['cajas'].items()}


def pago(caja, importe):
    return {'medio_pago':'saldo_unificado','receptor':caja+'_saldo_unificado','importe_centavos':importe}


def test_delivery_custodia_anulacion_y_stock(unificado):
    carpeta,c,ids,_ = unificado
    inicial=saldos(c)
    v=venta(c,ids,pagos=[pago('comidas',1450000)])
    assert saldos(c)=={**inicial,'comidas':4250000}
    assert c.get(RUTA).json()['cajas']['comidas']['custodia_reparto_centavos']==200000
    entregar(c,v,'comidas_saldo_unificado')
    assert saldos(c)['comidas']==4250000
    assert c.get(RUTA).json()['cajas']['comidas']['custodia_reparto_centavos']==0
    cuadrado(c)
    post(c,SIM+f"/ventas/{v['id_venta']}/anulacion",motivo='Reverso ficticio')
    assert saldos(c)==inicial
    with closing(abrir_base(carpeta,configuracion(carpeta)['id'],lectura=True)) as db:
        assert db.execute('SELECT stock FROM productos WHERE id_producto IN (?,?) ORDER BY id_producto',ids).fetchall()==[(10.0,),(10.0,)]


def test_pago_deuda_unico_concurrente_roles_y_sin_gasto(unificado):
    carpeta,c,_,_=unificado
    ventas=cliente(carpeta,'ventas')
    datos=solicitud(importe_centavos=500000,motivo='Pago ficticio')
    ruta=RUTA+'/deudas/1/pago'
    assert ventas.post(ruta,json=datos).status_code==403
    assert c.post(ruta,json=datos,headers={'X-POS-Usuario':'0'}).status_code==409
    assert c.post(ruta,json={**datos,'importe_centavos':1}).status_code==409
    antes=c.get(SIM+'/contabilidad').json()
    with ThreadPoolExecutor(max_workers=2) as equipo:
        respuestas=list(equipo.map(lambda _:c.post(ruta,json=datos),range(2)))
    assert [r.status_code for r in respuestas]==[200,200]
    assert respuestas[0].json()==respuestas[1].json()
    assert c.post(ruta,json=solicitud(importe_centavos=500000,motivo='Duplicado')).status_code==409
    assert saldos(c)=={'comidas':2500000,'bebidas_postres':3000000}
    despues=c.get(SIM+'/contabilidad').json()
    for campo in ('compras_centavos','gastos_centavos','devengado_centavos','resultado_base_diezmo_centavos'):
        assert antes[campo]==despues[campo]
    with closing(abrir_base(carpeta,configuracion(carpeta)['id'],lectura=True)) as db:
        assert db.execute('SELECT COUNT(*) FROM pos_pagos_deuda_apertura').fetchone()==(1,)


def test_stock_estricto_bebida_reposicion_y_rechazo_por_api(unificado):
    carpeta,c,ids,bebida=unificado
    for producto,cantidad,total in ((bebida,1,10000),(ids[1],11,4950000)):
        datos=solicitud(items=[{'id_producto':producto,'cantidad':cantidad}],total_esperado_centavos=total,
                        pagos=[pago('bebidas_postres',total)],confirmar_faltantes={str(producto):cantidad})
        assert c.post(SIM+'/ventas',json=datos).status_code==409
    validar=RUTA+f'/bebidas/{bebida}/validar'
    datos=solicitud(cantidad=2,referencia='Remito QA')
    assert c.post(validar,json=datos).status_code==409
    compra=solicitud(id_producto=bebida,cantidad=2,precio_unitario_centavos=1000,pagado_centavos=2000,
                    pagador='bebidas_postres_saldo_unificado',medio_pago='saldo_unificado')
    assert c.post(SIM+'/compras',json=compra).status_code==200
    assert saldos(c)['bebidas_postres']==2998000
    assert cliente(carpeta,'ventas').post(validar,json=datos).status_code==403
    assert c.post(validar,json=datos).status_code==200
    assert c.post(validar,json=datos).status_code==200
    venta=solicitud(items=[{'id_producto':bebida,'cantidad':2}],total_esperado_centavos=20000,
                    medio_pago='saldo_unificado')
    assert c.post(SIM+'/ventas',json=venta).status_code==200
    assert saldos(c)['bebidas_postres']==3018000
    assert c.post(SIM+'/ventas',json={**venta,**solicitud()}).status_code==409


def test_fiado_abono_y_corte_pendiente(unificado):
    carpeta,c,ids,_=unificado
    titular=post(c,SIM+'/clientes',nombre='Cliente ficticio')['id_cliente']
    datos=solicitud(items=[{'id_producto':ids[1],'cantidad':1}],total_esperado_centavos=450000,
                    pagos=[],fiado=True,id_cliente=titular)
    v=c.post(SIM+'/ventas',json=datos).json()
    assert v['saldo_pendiente_centavos']==450000
    assert saldos(c)['bebidas_postres']==3000000
    post(c,SIM+f"/ventas/{v['id_venta']}/abonos",pagos=[pago('bebidas_postres',450000)])
    assert saldos(c)['bebidas_postres']==3450000
    with closing(abrir_base(carpeta,configuracion(carpeta)['id'])) as db,db:
        db.execute('UPDATE pos_saldos_iniciales SET saldo_centavos=NULL,corte=NULL,responsable=NULL')
    assert c.get(RUTA).status_code==409
    assert c.post(SIM+'/ventas',json={**datos,**solicitud()}).status_code==409


def test_edge_saldos_y_checkout_sin_desglose(unificado,tmp_path):
    ejecutable=os.getenv('POS_TEST_BROWSER')
    if not ejecutable:
        pytest.skip('Configurar POS_TEST_BROWSER con Edge')
    import websocket
    from scripts.abadion_preproduccion import crear_app
    from tests.test_pos_web import abrir_navegador,esperar
    carpeta,_,_,_=unificado
    with closing(abrir_navegador(crear_app(carpeta),ejecutable,tmp_path,websocket)) as navegador:
        evaluar=next(navegador)
        def clic(selector):
            esperar(lambda:evaluar(f"document.querySelector({json.dumps(selector)}) && !document.querySelector({json.dumps(selector)}).disabled"))
            evaluar(f"document.querySelector({json.dumps(selector)}).click(); void 0")
        esperar(lambda:evaluar("document.querySelector('#cardsReal').textContent.includes('Comida QA')"))
        clic('#adminAccess')
        clave=json.loads((carpeta/'credenciales.json').read_text())['admin-preprod']
        evaluar("document.querySelector('#usuarioPos').value='admin-preprod'; document.querySelector('#claveAdmin').value="+json.dumps(clave))
        clic('#accept')
        esperar(lambda:evaluar("document.querySelector('#adminAccess').textContent.includes('admin-preprod')"))
        clic('#cajaDiariaPos')
        esperar(lambda:evaluar("document.querySelectorAll('[data-saldo-unificado]').length===2"))
        assert evaluar("!/Efectivo|Mercado Pago|Transferencia/.test(document.querySelector('#consultaPos').textContent)")
        clic('#closeDialog')
        evaluar("[...document.querySelectorAll('#cardsReal article')].find(a=>a.textContent.includes('Postre QA')).querySelector('button').click(); void 0")
        esperar(lambda:evaluar("document.querySelector('#totalPostre') !== null"))
        clic('[aria-label="Aumentar cantidad de Postre QA"]')
        clic('#accept')
        esperar(lambda:evaluar("document.querySelector('#lines').textContent.includes('Postre QA')"))
        clic('#validarPedido')
        esperar(lambda:evaluar("document.querySelector('#estadoPedido').textContent.includes('4.500')"))
        assert evaluar("!/Efectivo|Mercado Pago|Transferencia/.test(document.querySelector('#payments').textContent)")
        evaluar("[...document.querySelectorAll('#payments button')].find(b=>b.textContent.includes('Saldo de caja')).click(); void 0")
        clic('#checkout')
        esperar(lambda:evaluar("document.querySelector('#resumenVentaPos') !== null"))
        evaluar("[...document.querySelectorAll('#dialogBody label')].find(l=>l.firstChild.textContent.trim()==='Receptor').querySelector('select').value='bebidas_postres_saldo_unificado'; document.querySelector('#accept').click(); document.querySelector('#accept').click(); void 0")
        esperar(lambda:evaluar("document.querySelector('#notice').textContent.includes('registrada')"))
        assert saldos(unificado[1])['bebidas_postres']==3450000
        clic('#cajaDiariaPos')
        esperar(lambda:evaluar("document.querySelectorAll('[data-saldo-unificado]').length===2"))
        salida=os.getenv('POS_UI_CAPTURAS')
        if salida:
            Path(salida).mkdir(parents=True,exist_ok=True)
            (Path(salida)/'abadion-paso-saldo-unificado.png').write_bytes(evaluar.captura())
        def boton_texto(texto):
            evaluar("[...document.querySelectorAll('#consultaPos button')].find(b=>b.textContent==="+json.dumps(texto)+").click(); void 0")
        boton_texto('Pagar deuda completa')
        evaluar("document.querySelector('#camposOperacionPos textarea').value='Pago ficticio Edge'; document.querySelector('#accept').click(); document.querySelector('#accept').click(); void 0")
        esperar(lambda:evaluar("document.querySelector('#consultaPos')?.textContent.includes('Pago de deuda #1')"))
        assert saldos(unificado[1])['comidas']==2500000
        boton_texto('Revertir pago #1')
        evaluar("document.querySelector('#camposOperacionPos textarea').value='Pago no realizado QA'; document.querySelector('#accept').click(); document.querySelector('#accept').click(); void 0")
        esperar(lambda:evaluar("document.querySelector('#consultaPos')?.textContent.includes('Revertido')"))
        assert saldos(unificado[1])['comidas']==3000000
        boton_texto('Conciliar y cerrar Rotisería')
        evaluar("document.querySelectorAll('#camposOperacionPos input')[0].value='30000'; document.querySelectorAll('#camposOperacionPos input')[1].value='0'; document.querySelector('#referenciaCierreUnificado').value='Conteo ficticio Edge'; document.querySelector('#camposOperacionPos textarea').value='Cierre sintético'; document.querySelector('#accept').click(); document.querySelector('#accept').click(); void 0")
        esperar(lambda:evaluar("document.querySelector('#consultaPos')?.textContent.includes('Último cierre #1')"))
        assert saldos(unificado[1])['comidas']==3000000
        assert len(unificado[1].get(RUTA+'/conciliacion').json()['cierres'])==1
        if salida:
            (Path(salida)/'abadion-paso-cierre-unificado.png').write_bytes(evaluar.captura())


def test_deuda_insuficiente_no_mueve_fondos(unificado):
    carpeta,c,_,_=unificado
    with closing(abrir_base(carpeta,configuracion(carpeta)['id'])) as db,db:
        db.execute("UPDATE pos_saldos_iniciales SET saldo_centavos=1 WHERE caja='comidas'")
    datos=solicitud(importe_centavos=500000,motivo='Sin fondos QA')
    assert c.post(RUTA+'/deudas/1/pago',json=datos).status_code==409
    assert c.get(RUTA).json()['deudas'][0]['pendiente_centavos']==500000
    with closing(abrir_base(carpeta,configuracion(carpeta)['id'])) as db,db:
        assert db.execute('SELECT COUNT(*) FROM pos_pagos_deuda_apertura').fetchone()==(0,)


def test_ultima_unidad_concurrente_y_medio_legado_rechazado(unificado):
    carpeta,c,ids,_=unificado
    with closing(abrir_base(carpeta,configuracion(carpeta)['id'])) as db,db:
        db.execute('UPDATE productos SET stock=1 WHERE id_producto=?',(ids[1],))
    datos=dict(items=[{'id_producto':ids[1],'cantidad':1}],total_esperado_centavos=450000,
               medio_pago='saldo_unificado')
    assert c.post(SIM+'/ventas',json=solicitud(**{**datos,'medio_pago':'efectivo'})).status_code==409
    with ThreadPoolExecutor(max_workers=2) as equipo:
        respuestas=list(equipo.map(lambda _:c.post(SIM+'/ventas',json=solicitud(**datos)),range(2)))
    assert sorted(r.status_code for r in respuestas)==[200,409]
    assert saldos(c)['bebidas_postres']==3450000
    with closing(abrir_base(carpeta,configuracion(carpeta)['id'],lectura=True)) as db:
        assert db.execute('SELECT stock FROM productos WHERE id_producto=?',(ids[1],)).fetchone()==(0.0,)


@pytest.mark.parametrize('corte', ['2099-01-01T00:00:00-03:00', '2020-01-01', 'fecha-invalida'])
def test_corte_no_admite_futuro_ni_fecha_sin_zona(unificado,corte):
    carpeta,c,_,_=unificado
    with closing(abrir_base(carpeta,configuracion(carpeta)['id'])) as db,db:
        db.execute('UPDATE pos_saldos_iniciales SET corte=?',(corte,))
    assert c.get(RUTA).status_code==409


def test_delivery_fiado_adelanto_y_abono_en_otra_caja(unificado):
    _,c,ids,_=unificado
    titular=post(c,SIM+'/clientes',nombre='Cliente reparto ficticio')['id_cliente']
    v=venta(c,ids,pagos=[],fiado=True,id_cliente=titular)
    assert saldos(c)=={'comidas':3000000,'bebidas_postres':3000000}
    entregar(c,v,'comidas_saldo_unificado',confirmar_pendiente=True,
             saldo_confirmado_centavos=1450000,motivo='Adelanto ficticio del reparto')
    assert saldos(c)=={'comidas':2800000,'bebidas_postres':3000000}
    post(c,SIM+f"/ventas/{v['id_venta']}/abonos",pagos=[pago('bebidas_postres',1450000)])
    assert saldos(c)=={'comidas':2800000,'bebidas_postres':4450000}
    assert all(caja['custodia_reparto_centavos']==0 for caja in c.get(RUTA).json()['cajas'].values())
    assert c.get(SIM+f'/clientes/{titular}').json()['saldo_centavos']==0
    cuadrado(c)
