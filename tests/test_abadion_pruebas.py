"""Real fictional SQLite/API, release failures, worker restart and isolated recovery."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
from contextlib import closing
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from database import obtener_conexion
from pos_contabilidad import fecha_local
from pos_entrenamiento_db import bloquear_entrenamiento
from pos_preproduccion import (MODO_PRUEBAS, abrir_base, configuracion, actualizar_catalogo,
    integridad, respaldo, validar_respaldo)
from scripts import abadion_pruebas as p
from scripts.abadion_preproduccion import preparar, crear_app
from tests.test_preproduccion import SIM, post
from tests.test_preproduccion_jornada_v1 import servidor, ingresar

ROOT = Path(__file__).resolve().parents[1]
CATALOGO = ROOT / 'scripts/catalogo-comercial.json'


@pytest.fixture
def nueva(tmp_path):
    path = tmp_path / 'Pruebas'
    preparar(path, pruebas=True)
    return path


def aprobar(path):
    plan = actualizar_catalogo(path, CATALOGO, validar=True)
    actualizar_catalogo(path, CATALOGO, sha256=plan['sha256'], aprobacion=plan['instancia'])
    return plan


def conexion(path, role='admin'):
    url='http://127.0.0.1:8079'
    c=TestClient(crear_app(path, pruebas=True), base_url=url, headers={'Origin':url})
    ingresar(path,c,role)
    return c


def snapshot(path):
    with closing(abrir_base(path, configuracion(path)['id'], lectura=True)) as db:
        integridad(db)
        return '\n'.join(db.iterdump())


def test_nueva_vacia_catalogo_aprobacion_stock_y_disponibilidad(nueva):
    antes=snapshot(nueva)
    plan=actualizar_catalogo(nueva,CATALOGO,validar=True)
    assert snapshot(nueva)==antes
    for sha,identidad in [(None,None),(plan['sha256'],None),('0'*64,plan['instancia']),(plan['sha256'],str(uuid4()))]:
        with pytest.raises(ValueError):
            actualizar_catalogo(nueva,CATALOGO,sha256=sha,aprobacion=identidad)
        assert snapshot(nueva)==antes
    aprobar(nueva)
    with closing(abrir_base(nueva,plan['instancia'])) as db:
        assert db.execute('SELECT COUNT(*),MIN(stock),MAX(stock) FROM productos').fetchone()==(38,0,0)
        assert db.execute("SELECT COUNT(*) FROM pos_catalogo_entrenamiento WHERE estado='disponible'").fetchone()==(38,)
    c=conexion(nueva)
    with closing(abrir_base(nueva,plan['instancia'])) as db:
        bebida=db.execute("SELECT id_producto FROM productos WHERE nombre='Manaos Cola 600ml'").fetchone()[0]
    assert c.post('/pos-api/pedidos/validar',json={'items':[{'id_producto':bebida,'cantidad':1}]}).status_code==409
    antes=snapshot(nueva)
    with pytest.raises(ValueError,match='nueva y vacía'):
        aprobar(nueva)
    assert snapshot(nueva)==antes
    with pytest.raises(ValueError):
        preparar(nueva,pruebas=True)


def test_aislamiento_entre_instalaciones_y_general(nueva,tmp_path,monkeypatch):
    pre=tmp_path/'Preproduccion'
    preparar(pre)
    old=(pre/'abadion-preproduccion.db').read_bytes()
    with pytest.raises(ValueError):
        preparar(pre,pruebas=True)
    with pytest.raises(ValueError):
        crear_app(nueva)
    with pytest.raises(ValueError):
        crear_app(pre,pruebas=True)
    c=conexion(nueva)
    assert 'ABADION PRUEBAS PERSISTENTE' in c.get('/pos/').text
    assert c.get('/pos/').headers['X-Abadion-Modo']==MODO_PRUEBAS
    assert c.get('/_pruebas/status').status_code==403
    assert c.get('/_preprod/status').status_code==404
    assert c.post('/comandos',json={}).status_code==404
    assert set(c.cookies.keys())=={'abadion_pruebas_admin'}
    for name in ('abadion-pruebas.db','renombrada.db'):
        path=nueva/name
        if name=='renombrada.db':
            path.write_bytes((nueva/'abadion-pruebas.db').read_bytes())
        monkeypatch.setenv('NEGOCIO_DB_PATH',str(path))
        with pytest.raises(ValueError):
            obtener_conexion()
    with pytest.raises(ValueError):
        abrir_base(nueva,configuracion(pre)['id'])
    with pytest.raises(ValueError):
        p.carpeta_pruebas(tmp_path/'Entrenamiento')
    assert (pre/'abadion-preproduccion.db').read_bytes()==old


@pytest.mark.parametrize('alteracion',['schema','uuid','modo','hardlink'])
def test_rechazo_identidad_esquema_y_enlaces(nueva,alteracion,tmp_path):
    path=nueva/'abadion-pruebas.db'
    if alteracion=='hardlink':
        os.link(path,tmp_path/'alias.db')
    else:
        with closing(sqlite3.connect(path)) as db,db:
            if alteracion=='schema':
                db.execute('PRAGMA user_version=999')
            else:
                col='instalacion' if alteracion=='uuid' else 'modo'
                db.execute(f'UPDATE pos_preproduccion SET {col}=?',('ajeno',))
    with pytest.raises(ValueError):
        p.comprobar(nueva)


def release(nueva,commit,monkeypatch):
    target=nueva/'releases'/commit
    for folder in ('src','scripts','pos-web'):
        shutil.copytree(ROOT/folder,target/folder,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    files={str(f.relative_to(target)).replace('\\','/'):hashlib.sha256(f.read_bytes()).hexdigest()
           for f in target.rglob('*') if f.is_file()}
    p.guardar(target/'release.json',{'commit':commit,'archivos':files})
    monkeypatch.setattr(p,'release_python',lambda _:Path(sys.executable))
    return target


def test_actualizacion_backup_rollback_sin_perder_historia(nueva,monkeypatch):
    aprobar(nueva)
    uno=release(nueva,'a'*40,monkeypatch)
    dos=release(nueva,'b'*40,monkeypatch)
    p.activar(nueva,uno)
    before=snapshot(nueva)
    monkeypatch.setattr(p,'preparar_release',lambda *args:dos)
    p.actualizar(nueva,ROOT,'b'*40)
    assert snapshot(nueva)==before
    pointer=(nueva/'activa.json').read_bytes()
    p.actualizar(nueva,ROOT,'b'*40)
    assert (nueva/'activa.json').read_bytes()==pointer
    backups=list((nueva/'backups').glob('*pre-actualizacion.db'))
    assert len(backups)==2
    validar_respaldo(nueva,backups[0].name)
    with closing(abrir_base(nueva,configuracion(nueva)['id'])) as db,db:
        db.execute('UPDATE productos SET stock=9 WHERE controla_stock=1')
    after=snapshot(nueva)
    p.rollback(nueva)
    assert snapshot(nueva)==after
    active=json.loads((nueva/'activa.json').read_text())
    assert active['commit']=='a'*40
    assert active['anterior']=='b'*40


@pytest.mark.parametrize('fallo',['backup','codigo','schema','dependencias'])
def test_fallo_actualizacion_no_cambia_version_ni_datos(nueva,monkeypatch,fallo):
    uno=release(nueva,'a'*40,monkeypatch)
    dos=release(nueva,'b'*40,monkeypatch)
    p.activar(nueva,uno)
    if fallo=='backup':
        monkeypatch.setattr(p,'validar_respaldo',lambda *a: (_ for _ in ()).throw(ValueError('backup inválido')))
    elif fallo=='codigo':
        (dos/'scripts/abadion_pruebas.py').write_text('alterado')
    elif fallo=='schema':
        with closing(abrir_base(nueva,configuracion(nueva)['id'])) as db,db:
            db.execute('PRAGMA user_version=999')
    def stage(*a):
        if fallo=='dependencias':
            raise ValueError('No se pudieron instalar dependencias')
        return dos
    monkeypatch.setattr(p,'preparar_release',stage)
    old=(nueva/'activa.json').read_bytes()
    dbbytes=(nueva/'abadion-pruebas.db').read_bytes()
    with pytest.raises(ValueError):
        p.actualizar(nueva,ROOT,'b'*40)
    assert (nueva/'activa.json').read_bytes()==old
    assert (nueva/'abadion-pruebas.db').read_bytes()==dbbytes


def test_actualizacion_y_catalogo_rechazan_servidor_activo(nueva,monkeypatch):
    with bloquear_entrenamiento(nueva):
        with pytest.raises(ValueError,match='uso'):
            p.actualizar(nueva,ROOT,'a'*40)
        with pytest.raises(ValueError,match='uso'):
            aprobar(nueva)


def test_backup_alterado_y_otra_instancia_no_recuperan(nueva,tmp_path):
    copia=respaldo(nueva)
    otra=tmp_path/'otra'/'Pruebas'
    preparar(otra,pruebas=True)
    for f in (copia,copia.with_suffix('.json')):
        shutil.copyfile(f,otra/'backups'/f.name)
    with pytest.raises(ValueError):
        p.recuperar(otra,copia.name,tmp_path/'fallo'/'Pruebas')
    copia.write_bytes(copia.read_bytes()+b'alterado')
    with pytest.raises(ValueError):
        p.recuperar(nueva,copia.name,tmp_path/'fallo'/'Pruebas')
    assert not (tmp_path/'fallo').exists()


def test_jornada_comercial_integrada_worker_reinicio_restore(nueva,tmp_path):
    aprobar(nueva)
    with closing(abrir_base(nueva,configuracion(nueva)['id'])) as db:
        ids=dict(db.execute('SELECT nombre,id_producto FROM productos'))
    with servidor(nueva,pruebas=True) as (c,control):
        ingresar(nueva,c,'ventas')
        jornadas={caja:post(c,SIM+f'/caja-diaria/{caja}/apertura',fecha=fecha_local(),inicial_centavos=2_000_000)['id_jornada']
                  for caja in ('comidas','bebidas_postres')}
        # Stock introduced as an explicit fictitious PURCHASE after the initial zero check.
        assert c.post(SIM+'/compras',json={}).status_code==403
        ingresar(nueva,c,'admin')
        post(c,SIM+'/compras',id_producto=ids['Manaos Cola 600ml'],cantidad=10,precio_unitario_centavos=10000,
             pagado_centavos=100000,pagador='comidas_efectivo',medio_pago='efectivo')
        cliente=post(c,SIM+'/clientes',nombre='Cliente ficticio jornada integrada')['id_cliente']
        ingresar(nueva,c,'ventas')
        items=[{'id_producto':ids['Clásica simple'],'cantidad':1,'adicionales_preparacion':[
            {'tipo':t,'destino':'principal','cantidad':1} for t in ('cheddar','huevo')]},
            {'id_producto':ids['Manaos Cola 600ml'],'cantidad':1},
            {'id_producto':ids['Pepitos chico'],'cantidad':1},{'id_producto':ids['Oreo chico'],'cantidad':1}]
        venta={'id_solicitud':str(uuid4()),'items':items,'total_esperado_centavos':1_730_000,
               'entrega':{'origen':'mostrador','modalidad':'envio','direccion':'Domicilio ficticio 123','circuito':'sencillo'},
               'pagos':[{'receptor':'comidas_efectivo','medio_pago':'efectivo','importe_centavos':900000},
                        {'receptor':'bebidas_postres_banco','medio_pago':'transferencia','importe_centavos':830000}]}
        v=c.post(SIM+'/ventas',json=venta).raise_for_status().json()
        assert c.post(SIM+'/ventas',json=venta).json()==v
        assert v['total_centavos']==1_530_000 and v['delivery']['cobrado_centavos']==200000
        entrega={'id_solicitud':str(uuid4()),'version':1,'estado':'entregado','receptor_reparto':'comidas_efectivo'}
        ruta=SIM+f"/pedidos/{v['id_pedido']}/estado"
        e=c.post(ruta,json=entrega).raise_for_status().json()
        assert c.post(ruta,json=entrega).json()==e
        assert e['delivery']['entregado_centavos']==200000
        assert e['delivery']['custodia_centavos']==0
        fiado=post(c,SIM+'/ventas',items=[{'id_producto':ids['Pepitos chico'],'cantidad':1}],
            total_esperado_centavos=300000,pagos=[],fiado=True,id_cliente=cliente,
            entrega={'origen':'mostrador','modalidad':'retiro','circuito':'sencillo'})
        post(c,SIM+f"/ventas/{fiado['id_venta']}/abonos",pagos=[{
            'receptor':'bebidas_postres_efectivo','medio_pago':'efectivo','importe_centavos':100000}])
        cancel=post(c,SIM+'/ventas',items=[{'id_producto':ids['Oreo chico'],'cantidad':1}],
            total_esperado_centavos=300000,medio_pago='efectivo',
            entrega={'origen':'mostrador','modalidad':'retiro','circuito':'sencillo'})
        assert c.post(SIM+f"/ventas/{cancel['id_venta']}/anulacion",json={'id_solicitud':str(uuid4()),'motivo':'QA'}).status_code==403
        ingresar(nueva,c,'admin')
        post(c,SIM+f"/ventas/{cancel['id_venta']}/anulacion",motivo='Cancelación ficticia')
        post(c,SIM+f"/pedidos/{cancel['id_pedido']}/estado",version=1,estado='cancelado',motivo='Cancelación ficticia')
        post(c,SIM+f"/ventas/{v['id_venta']}/devoluciones",motivo='Devuelve bebida ficticia',items=[{'linea':2,'cantidad':1}])
        assert c.get(SIM+f'/clientes/{cliente}').json()['saldo_centavos']==200000
        for caja in jornadas:
            estado=c.get(SIM+'/caja-diaria').json()['cajas'][caja]
            arqueo=post(c,SIM+f'/caja-diaria/{caja}/arqueo',id_jornada=jornadas[caja],
                        revision_efectivo=estado['revision_efectivo'],contado_centavos=estado['esperado_centavos'])
            post(c,SIM+f'/caja-diaria/{caja}/cierre',id_jornada=jornadas[caja],id_arqueo=arqueo['id_evento'])
        rutas=['ventas','pedidos?finalizados=true','cajas','caja-diaria','conciliacion','contabilidad',f'clientes/{cliente}']
        def estado(c):
            result={r:c.get(SIM+'/'+r).raise_for_status().json() for r in rutas}
            assert result['conciliacion']['cuadrado']
            return result
        antes=estado(c)
        nombre=c.post('/_pruebas/backup',headers=control).raise_for_status().json()['archivo']
    with servidor(nueva,pruebas=True) as (c,_):
        ingresar(nueva,c,'admin')
        assert estado(c)==antes
        ingresar(nueva,c,'ventas')
        before=snapshot(nueva)
        assert c.post(SIM+'/ventas',json=venta).raise_for_status().json()['id_venta']==v['id_venta']
        assert snapshot(nueva)==before
    recuperada=tmp_path/'recuperacion'/'Pruebas'
    p.recuperar(nueva,nombre,recuperada)
    with servidor(recuperada,pruebas=True) as (c,_):
        ingresar(recuperada,c,'admin')
        assert estado(c)==antes
    with closing(abrir_base(recuperada,configuracion(recuperada)['id'])) as db:
        assert db.execute("SELECT stock FROM productos WHERE nombre='Manaos Cola 600ml'").fetchone()==(10,)
        integridad(db)
    with pytest.raises(ValueError,match='inexistente'):
        p.recuperar(nueva,nombre,recuperada)


def test_edge_pruebas_perfil_y_catalogo(nueva,tmp_path):
    browser=os.getenv('POS_TEST_BROWSER')
    if not browser:
        pytest.skip('Configurar POS_TEST_BROWSER con Edge')
    import websocket
    from tests.test_pos_web import abrir_navegador,esperar
    aprobar(nueva)
    navegador=abrir_navegador(crear_app(nueva,pruebas=True),browser,tmp_path,websocket)
    with closing(navegador):
        evaluar=next(navegador)
        esperar(lambda:evaluar("document.querySelector('#entrenamientoAviso') !== null"))
        assert 'ABADION PRUEBAS' in evaluar("document.querySelector('#entrenamientoAviso').textContent")
        evaluar("document.querySelector('#adminAccess').click()")
        esperar(lambda:evaluar("document.querySelector('#usuarioPos') !== null"))
        clave=json.loads((nueva/'credenciales.json').read_text())['admin-pruebas']
        evaluar("document.querySelector('#usuarioPos').value='admin-pruebas';document.querySelector('#claveAdmin').value="+json.dumps(clave)+";document.querySelector('#accept').click()")
        esperar(lambda:evaluar("document.querySelector('#cardsReal').textContent.includes('Fugazzeta')"))
        assert 'Pepitos' in evaluar("document.querySelector('#cardsReal').textContent")
        assert evaluar("document.title.includes('ABADION PRUEBAS')")
        if output:=os.getenv('POS_UI_CAPTURAS'):
            Path(output).mkdir(parents=True,exist_ok=True)
            (Path(output)/'abadion-paso-pruebas-integradas.png').write_bytes(evaluar.captura())


@pytest.mark.parametrize('falla',['corrupta','ausente'])
def test_recuperacion_aislada_sin_abrir_base_danada(nueva,tmp_path,falla):
    aprobar(nueva)
    copia=respaldo(nueva)
    base=nueva/'abadion-pruebas.db'
    if falla=='corrupta':
        base.write_bytes(b'SQLite corrupto de ejercicio')
    else:
        base.unlink()
    destino=tmp_path/'rescate'/'Pruebas'
    p.recuperar(nueva,copia.name,destino)
    p.comprobar(destino)
    with closing(abrir_base(destino,configuracion(destino)['id'])) as db:
        assert db.execute('SELECT COUNT(*) FROM productos').fetchone()==(38,)
    assert not base.exists() if falla=='ausente' else base.read_bytes()==b'SQLite corrupto de ejercicio'


def test_catalogo_rechaza_base_con_jornada_aunque_sin_productos(nueva):
    c=conexion(nueva,'ventas')
    post(c,SIM+'/caja-diaria/comidas/apertura',fecha=fecha_local(),inicial_centavos=0)
    with pytest.raises(ValueError,match='nueva y vacía'):
        aprobar(nueva)


def test_launcher_edge_perfil_diferenciado_y_entorno(nueva,monkeypatch,tmp_path):
    fake=tmp_path/'Microsoft/Edge/Application/msedge.exe'
    fake.parent.mkdir(parents=True)
    fake.write_bytes(b'fake executable; never executed')
    monkeypatch.setenv('ProgramFiles(x86)',str(tmp_path))
    monkeypatch.setenv('NEGOCIO_DB_PATH','no-usar-real.db')
    monkeypatch.setenv('ABADION_BOT_TOKEN','ficticio-test')
    calls=[]
    monkeypatch.setattr(p.subprocess,'Popen',lambda args,**kwargs:calls.append((args,kwargs)))
    p.abrir_edge(nueva)
    args,kwargs=calls[0]
    assert '--user-data-dir='+str(nueva/'Edge-Pruebas') in args
    assert args[-1]=='http://127.0.0.1:8079/pos/'
    assert 'NEGOCIO_DB_PATH' not in kwargs['env']
    assert 'ABADION_BOT_TOKEN' not in kwargs['env']
    assert kwargs['env']['PYTHON_DOTENV_DISABLED']=='1'


def test_codigo_candidato_incompatible_no_activa(nueva,monkeypatch):
    old=release(nueva,'a'*40,monkeypatch)
    candidate=release(nueva,'b'*40,monkeypatch)
    p.activar(nueva,old)
    source=candidate/'src/pos_simulacion.py'
    source.write_text(source.read_text(encoding='utf-8').replace('VERSION_ESQUEMA_SIMULACION = 4','VERSION_ESQUEMA_SIMULACION = 999'),encoding='utf-8')
    manifest=json.loads((candidate/'release.json').read_text())
    manifest['archivos']['src/pos_simulacion.py']=hashlib.sha256(source.read_bytes()).hexdigest()
    p.guardar(candidate/'release.json',manifest)
    monkeypatch.setattr(p,'preparar_release',lambda *a:candidate)
    before=snapshot(nueva)
    active=(nueva/'activa.json').read_bytes()
    with pytest.raises(p.subprocess.CalledProcessError):
        p.actualizar(nueva,ROOT,'b'*40)
    assert snapshot(nueva)==before
    assert (nueva/'activa.json').read_bytes()==active
