"""Preparación y conciliación exclusivamente con datos sintéticos en carpetas temporales."""
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from pos_apertura_ensayo import AperturaEnsayo, ensayar_apertura, huella_catalogo
from pos_preproduccion import abrir_base, configuracion, respaldo, restaurar
from pos_saldo_unificado import crear_esquema
from tests.test_saldo_unificado import unificado, circuito, RUTA, saldos
from tests.test_lo_de_clau_delivery import venta
from tests.test_preproduccion import instalada, cliente, SIM, post
from tests.test_pos_qa_integrado import solicitud


@pytest.fixture
def apertura(instalada):
    identidad = configuracion(instalada)['id']
    with closing(abrir_base(instalada, identidad)) as db, db:
        db.executemany('INSERT INTO productos(nombre,categoria,precio_venta,controla_stock,stock) VALUES (?,?,100,1,0)',
                       [('Postre sintético A','Postres'),('Postre sintético B','Postres'),('Bebida sintética','Bebidas')])
        crear_esquema(db)
        admin = {'id_usuario': db.execute("SELECT id_usuario FROM usuarios_pos WHERE rol='admin'").fetchone()[0], 'rol':'admin'}
        stock = {p: 3 for p, in db.execute("SELECT id_producto FROM productos WHERE categoria='Postres'")}
        datos = AperturaEnsayo(**solicitud(
            consentimiento='ENSAYO FICTICIO SIN ACTIVACION PRODUCTIVA', instancia=identidad,
            version_codigo='a'*40, catalogo_sha256=huella_catalogo(db), evidencia_sha256='b'*64,
            responsable='Responsable sintético', corte='2020-01-01T12:00:00-03:00',
            saldos={'comidas':1200000,'bebidas_postres':900000}, postres=stock,
            deuda_tarjeta={'caja':'comidas','concepto':'Obligación sintética','importe_centavos':200000,'vencimiento':'2031-06-01'},
            fiados_previos_centavos=0, bebidas_sin_existencias=True,
            conciliacion_sin_duplicados=True, sin_operaciones_en_transito=True, modelo_rotiseria_aceptado=True))
    return instalada, datos, admin


def test_apertura_atomica_idempotente_reinicio_y_restore(apertura):
    carpeta, datos, usuario = apertura
    identidad = configuracion(carpeta)['id']
    def ejecutar(_):
        with closing(abrir_base(carpeta, identidad)) as db:
            return ensayar_apertura(db, datos, usuario)
    with ThreadPoolExecutor(max_workers=2) as equipo:
        resultados = list(equipo.map(ejecutar, range(2)))
    assert resultados[0] == resultados[1]
    assert resultados[0]['habilitacion_productiva'] is False
    c = cliente(carpeta)
    assert saldos(c) == datos.saldos
    assert c.get(RUTA).json()['stock'][-1]['cantidad'] == 3
    with closing(abrir_base(carpeta, identidad)) as db:
        assert db.execute('SELECT COUNT(*) FROM pos_apertura_ensayo').fetchone() == (1,)
        assert db.execute('SELECT COUNT(*) FROM pos_deudas_apertura').fetchone() == (1,)
        assert db.execute("SELECT stock FROM productos WHERE categoria='Bebidas'").fetchone() == (0.0,)
        assert db.execute('SELECT COUNT(*) FROM pos_stock_progresivo WHERE habilitado<>0').fetchone() == (0,)
        assert db.execute('SELECT COUNT(*) FROM pos_ventas_simuladas').fetchone() == (0,)
        with pytest.raises(HTTPException):
            ensayar_apertura(db, datos.model_copy(update={'responsable':'Otro'}), usuario)
    copia = respaldo(carpeta)
    restaurar(carpeta, copia.name)
    assert saldos(cliente(carpeta)) == datos.saldos


def test_apertura_rollback_si_falla_ultimo_registro(apertura):
    carpeta, datos, usuario = apertura
    with closing(abrir_base(carpeta, configuracion(carpeta)['id'])) as db:
        db.execute("CREATE TRIGGER fallo_ensayo BEFORE INSERT ON pos_apertura_ensayo BEGIN SELECT RAISE(ABORT,'fallo ficticio'); END")
        db.commit()
        with pytest.raises(sqlite3.IntegrityError, match='fallo ficticio'):
            ensayar_apertura(db, datos, usuario)
        assert db.execute('SELECT COUNT(*) FROM pos_saldos_iniciales WHERE saldo_centavos IS NOT NULL').fetchone() == (0,)
        assert db.execute('SELECT COUNT(*) FROM pos_deudas_apertura').fetchone() == (0,)
        assert db.execute('SELECT COUNT(*) FROM productos WHERE stock<>0').fetchone() == (0,)


def test_apertura_rechaza_cualquier_libro_o_pendiente_desconocido(apertura):
    carpeta, datos, usuario = apertura
    with closing(abrir_base(carpeta, configuracion(carpeta)['id'])) as db:
        db.execute('CREATE TABLE pendiente_qa(id INTEGER)')
        db.execute('INSERT INTO pendiente_qa VALUES (1)')
        db.commit()
        with pytest.raises(HTTPException, match='sin operaciones'):
            ensayar_apertura(db, datos, usuario)
        assert not db.execute('SELECT 1 FROM pos_apertura_ensayo').fetchone()


@pytest.mark.parametrize('cambio', [
    {'saldos':{'comidas':1}}, {'saldos':{'comidas':True,'bebidas_postres':1}},
    {'corte':'2099-01-01T00:00:00-03:00'}, {'corte':'2020-01-01T00:00:00'},
    {'corte':'2020-01-01T00:00:00+00:00'}, {'responsable':' '},
    {'consentimiento':'APROBAR PRODUCCION'}, {'fiados_previos_centavos':1},
])
def test_apertura_datos_incompletos_rechazados(apertura,cambio):
    _, datos, _ = apertura
    with pytest.raises(ValidationError):
        AperturaEnsayo.model_validate({**datos.model_dump(),**cambio})


@pytest.mark.parametrize('cambio', [{'instancia':'ajena'}, {'catalogo_sha256':'0'*64}, {'postres':{}}])
def test_apertura_no_escribe_si_revision_invalida(apertura,cambio):
    carpeta, datos, usuario = apertura
    with closing(abrir_base(carpeta, configuracion(carpeta)['id'])) as db:
        with pytest.raises(HTTPException):
            ensayar_apertura(db, datos.model_copy(update=cambio), usuario)
        assert not db.execute('SELECT 1 FROM pos_apertura_ensayo').fetchone()
        assert not db.execute('SELECT 1 FROM pos_saldos_iniciales WHERE saldo_centavos IS NOT NULL').fetchone()


def test_reverso_concurrente_roles_reintento_y_nuevo_pago(unificado):
    carpeta,c,_,_=unificado
    antes=c.get(SIM+'/contabilidad').json()
    datos=solicitud(importe_centavos=500000,motivo='Pago sintético')
    pago=c.post(RUTA+'/deudas/1/pago',json=datos).json()
    ruta=RUTA+f"/pagos/{pago['id_pago']}/reverso"
    reverso=solicitud(motivo='Pago no realizado, ensayo')
    assert cliente(carpeta,'ventas').post(ruta,json=reverso).status_code==403
    assert c.post(ruta,json=reverso,headers={'X-POS-Usuario':'0'}).status_code==409
    with ThreadPoolExecutor(max_workers=2) as equipo:
        respuestas=list(equipo.map(lambda _:c.post(ruta,json=reverso),range(2)))
    assert [r.status_code for r in respuestas]==[200,200]
    assert respuestas[0].json()==respuestas[1].json()
    assert saldos(c)['comidas']==3000000
    assert c.post(ruta,json={**reverso,'motivo':'Otro'}).status_code==409
    assert c.post(ruta,json=solicitud(motivo='Repetición distinta')).status_code==409
    # Un reintento del pago original devuelve su resultado histórico; no vuelve a pagar.
    assert c.post(RUTA+'/deudas/1/pago',json=datos).json()==pago
    assert saldos(c)['comidas']==3000000
    nuevo=post(c,RUTA+'/deudas/1/pago',importe_centavos=500000,motivo='Nuevo pago sintético')
    assert nuevo['id_pago']!=pago['id_pago']
    assert saldos(c)['comidas']==2500000
    assert c.get(RUTA).json()['deudas'][0]['pendiente_centavos']==0
    despues=c.get(SIM+'/contabilidad').json()
    for campo in ('gastos_centavos','resultado_base_diezmo_centavos','devengado_centavos'):
        assert despues[campo]==antes[campo]
    with closing(abrir_base(carpeta,configuracion(carpeta)['id'])) as db:
        for tabla in ('pos_pagos_deuda_apertura','pos_reversos_deuda_apertura'):
            for accion in ('DELETE FROM '+tabla,'UPDATE '+tabla+' SET id_usuario=id_usuario'):
                with pytest.raises(sqlite3.IntegrityError,match='inmutable'):
                    db.execute(accion)
                db.rollback()


def cierre(c, **cambios):
    estado=c.get(RUTA+'/conciliacion').json()
    return solicitud(caja='comidas',revision=estado['revision'],secuencia=1,
                     saldo_contado_centavos=2999900,custodia_contada_centavos=0,
                     motivo='Diferencia sintética documentada',referencia='Conteo QA',**cambios)


def test_cierre_concurrente_diferencia_historial_y_sin_ajuste(unificado):
    carpeta,c,_,_=unificado
    datos=cierre(c)
    antes=saldos(c)
    assert cliente(carpeta,'ventas').post(RUTA+'/cierres',json=datos).status_code==403
    assert c.post(RUTA+'/cierres',json=datos,headers={'X-POS-Usuario':'0'}).status_code==409
    with ThreadPoolExecutor(max_workers=2) as equipo:
        respuestas=list(equipo.map(lambda _:c.post(RUTA+'/cierres',json=datos),range(2)))
    assert [r.status_code for r in respuestas]==[200,200]
    assert respuestas[0].json()==respuestas[1].json()
    assert respuestas[0].json()['diferencia_centavos']==-100
    assert saldos(c)==antes
    assert c.get(RUTA+'/conciliacion').json()['cierres']==[respuestas[0].json()]
    assert c.post(RUTA+'/cierres',json={**datos,**solicitud()}).status_code==409
    assert c.post(RUTA+'/cierres',json={**datos,'referencia':'Otra'}).status_code==409
    with closing(abrir_base(carpeta,configuracion(carpeta)['id'])) as db:
        with pytest.raises(sqlite3.IntegrityError,match='inmutable'):
            db.execute('DELETE FROM pos_cierres_unificados')


def test_cierre_rechaza_revision_tras_pago_y_tras_reverso_compensado(unificado):
    _,c,_,_=unificado
    datos=cierre(c)
    p=post(c,RUTA+'/deudas/1/pago',importe_centavos=500000,motivo='Pago QA')
    assert c.post(RUTA+'/cierres',json=datos).status_code==409
    post(c,RUTA+f"/pagos/{p['id_pago']}/reverso",motivo='Reverso QA')
    assert saldos(c)['comidas']==3000000
    assert c.post(RUTA+'/cierres',json=datos).status_code==409
    assert not c.get(RUTA+'/conciliacion').json()['cierres']


def test_cierre_separa_custodia_y_reverso_posterior_no_reescribe_historia(unificado):
    _,c,ids,_=unificado
    venta(c,ids,pagos=[{'receptor':'comidas_saldo_unificado','medio_pago':'saldo_unificado','importe_centavos':1450000}])
    p=post(c,RUTA+'/deudas/1/pago',importe_centavos=500000,motivo='Pago QA')
    estado=c.get(RUTA+'/conciliacion').json()
    datos=solicitud(caja='comidas',revision=estado['revision'],secuencia=1,
                    saldo_contado_centavos=3750000,custodia_contada_centavos=199900,
                    motivo='Diferencia custodia QA',referencia='Planilla QA')
    r=c.post(RUTA+'/cierres',json=datos)
    assert r.status_code==200,r.text
    guardado=r.json()
    assert guardado['saldo_libro_centavos']==3750000
    assert guardado['custodia_libro_centavos']==200000
    assert guardado['diferencia_centavos']==0
    assert guardado['diferencia_custodia_centavos']==-100
    post(c,RUTA+f"/pagos/{p['id_pago']}/reverso",motivo='Devolución ficticia posterior')
    assert c.get(RUTA+'/conciliacion').json()['cierres']==[guardado]
    assert c.post(RUTA+'/cierres',json=datos).json()==guardado
    assert saldos(c)['comidas']==4250000


@pytest.mark.parametrize('campo,valor', [('saldo_contado_centavos',-1),('saldo_contado_centavos',True),
    ('custodia_contada_centavos',-1),('motivo',' '),('referencia',' '),('secuencia',0)])
def test_cierre_rechaza_conteo_o_referencia_invalida(unificado,campo,valor):
    _,c,_,_=unificado
    datos={**cierre(c),campo:valor}
    assert c.post(RUTA+'/cierres',json=datos).status_code==422
    assert not c.get(RUTA+'/conciliacion').json()['cierres']
