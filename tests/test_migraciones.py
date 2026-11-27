"""Actualizaciones y caídas de proceso sobre instalaciones exclusivamente ficticias."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import zipfile

import pytest

import migraciones as m
from pos_entrenamiento_db import bloquear_entrenamiento
from pos_preproduccion import abrir_base,configuracion,respaldo,restaurar,validar_respaldo
from scripts.abadion_preproduccion import preparar
from scripts.abadion_migraciones import preparar_nueva,recuperar_actual
from tests.test_saldo_unificado import unificado,circuito,venta,pago

ROOT=Path(__file__).resolve().parents[1]
REFS=['6a193c1b79d456a95a832b70447010da287724b1','4c312768528207d774247be42d075f1be8727d33',
      '91f293b8b5c303170626b202cdd72cc6c33ba718','3c5b5ae53b4a1d660314923f48b6f96349171a0e',
      '1ec1ab98755a248f86c3a50ba3164320e4381448']


def ruta(carpeta): return carpeta/('abadion-pruebas.db' if carpeta.name=='Pruebas' else 'abadion-preproduccion.db')


def sql(carpeta,texto,args=()):
    with closing(sqlite3.connect(ruta(carpeta))) as db,db:
        return db.execute(texto,args).fetchall()


def huella(carpeta): return hashlib.sha256(ruta(carpeta).read_bytes()).hexdigest()


def estado(carpeta):
    with closing(sqlite3.connect(ruta(carpeta))) as db: return m.datos(db)


@pytest.fixture
def instalada(tmp_path):
    carpeta=tmp_path/'Pruebas'
    preparar(carpeta,pruebas=True)
    return carpeta


@pytest.mark.parametrize('pruebas',[False,True])
def test_instalacion_limpia_y_repeticion(tmp_path,pruebas):
    carpeta=tmp_path/('Pruebas' if pruebas else 'Preproduccion')
    assert preparar_nueva(carpeta,pruebas=pruebas)['aplicada']
    assert m.diagnosticar(carpeta)['version']==5
    antes=huella(carpeta)
    assert m.migrar(carpeta)['aplicada'] is False
    assert huella(carpeta)==antes
    assert sql(carpeta,'SELECT COUNT(*) FROM abadion_migraciones')==[(1,)]
    with pytest.raises(ValueError): preparar_nueva(carpeta,pruebas=pruebas)
    destino=tmp_path/'recuperada'/carpeta.name
    recuperar_actual(carpeta,destino)
    assert m.diagnosticar(destino)['version']==5


@pytest.mark.parametrize('ref',REFS)
def test_versiones_reales_38_a_42_generadas_desde_git(tmp_path,ref):
    exportado=tmp_path/'fuentes-ficticias'
    exportado.mkdir()
    archivo=subprocess.check_output(['git','archive','--format=zip',ref,'src','scripts'],cwd=ROOT)
    with zipfile.ZipFile(io.BytesIO(archivo)) as z:
        for n in z.namelist():
            if n.endswith('/'): continue
            assert '..' not in Path(n).parts and not Path(n).is_absolute()
            p=exportado/n; p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(z.read(n))
    carpeta=tmp_path/'Pruebas'
    programa="import sys; from pathlib import Path; sys.path[:0]=[sys.argv[1],str(Path(sys.argv[1])/'src')]; from scripts.abadion_preproduccion import preparar; preparar(Path(sys.argv[2]),pruebas=True)"
    env={k:v for k,v in os.environ.items() if not k.startswith(('POS_','ABADION_','NEGOCIO_'))}
    subprocess.run([sys.executable,'-c',programa,str(exportado),str(carpeta)],check=True,env={**env,'PYTHON_DOTENV_DISABLED':'1'},cwd=exportado,capture_output=True,timeout=90)
    antes=estado(carpeta)
    assert m.migrar(carpeta)['aplicada']
    despues=estado(carpeta)
    assert all(despues[k]==v for k,v in antes.items())
    assert sql(carpeta,'SELECT COUNT(*) FROM pos_costos_lineas')==[(0,)]
    assert m.diagnosticar(carpeta)['version']==5


@pytest.mark.parametrize('version',[0,3,6,999])
def test_versiones_no_soportadas_no_escriben(instalada,version):
    sql(instalada,f'PRAGMA user_version={version}')
    antes=huella(instalada)
    with pytest.raises(ValueError): m.migrar(instalada)
    assert huella(instalada)==antes
    assert 'esquema_minimo' not in configuracion(instalada)


@pytest.mark.parametrize('alteracion',[
    "PRAGMA application_id=1", "ALTER TABLE pos_preproduccion RENAME COLUMN instalacion TO identidad",
    "UPDATE pos_preproduccion SET instalacion='00000000-0000-0000-0000-000000000001'",
    'CREATE TABLE saldos_iniciales_caja(id INTEGER)', 'CREATE TABLE candidata_corte(id INTEGER)',
    'CREATE TABLE desconocida(id INTEGER)', 'DROP TABLE sesiones_pos_contexto',
    'DROP TRIGGER seguridad_revocar_cambio_usuario', 'ALTER TABLE productos ADD COLUMN ajena TEXT'])
def test_identidad_y_esquemas_incompletos_rechazados(instalada,alteracion):
    sql(instalada,alteracion)
    antes=huella(instalada)
    with pytest.raises((ValueError,sqlite3.Error)): m.migrar(instalada)
    assert huella(instalada)==antes


@pytest.mark.parametrize('fase',['ddl','datos','registro','integridad','commit'])
def test_fallos_revierten_y_reanudan(instalada,monkeypatch,fase):
    antes=estado(instalada)
    aplicar=m.aplicar_paso
    crear=m.crear_registro
    verificar=m.verificar_version
    verificar_integridad=m.integridad
    if fase in ('ddl','datos'):
        def fallo(db):
            aplicar(db)
            if fase=='datos': db.execute("INSERT INTO productos(nombre,categoria,stock) VALUES('Ficticio','Bebidas',1)")
            else: raise RuntimeError('fallo ficticio después del DDL')
        monkeypatch.setattr(m,'aplicar_paso',fallo)
    elif fase=='registro':
        def fallo(db): crear(db); raise RuntimeError('fallo ficticio al registrar')
        monkeypatch.setattr(m,'crear_registro',fallo)
    elif fase=='integridad':
        original=m.integridad
        def fallo(db):
            original(db)
            if db.execute('PRAGMA user_version').fetchone()[0]==5: raise RuntimeError('fallo ficticio de integridad')
        monkeypatch.setattr(m,'integridad',fallo)
    else:
        def fallo(db,*args):
            resultado=verificar(db,*args)
            if resultado==5:
                db.execute('CREATE TABLE padre_fallo(id INTEGER PRIMARY KEY)')
                db.execute('CREATE TABLE hijo_fallo(id INTEGER REFERENCES padre_fallo DEFERRABLE INITIALLY DEFERRED)')
                db.execute('INSERT INTO hijo_fallo VALUES(999)')
            return resultado
        monkeypatch.setattr(m,'verificar_version',fallo)
    with pytest.raises((RuntimeError,ValueError,sqlite3.Error)): m.migrar(instalada)
    assert estado(instalada)==antes
    assert sql(instalada,'PRAGMA user_version')==[(4,)]
    assert not sql(instalada,"SELECT name FROM sqlite_schema WHERE name='abadion_migraciones'")
    with pytest.raises(ValueError,match='pendiente'): abrir_base(instalada,configuracion(instalada)['id'])
    monkeypatch.setattr(m,'aplicar_paso',aplicar)
    monkeypatch.setattr(m,'crear_registro',crear)
    monkeypatch.setattr(m,'verificar_version',verificar)
    monkeypatch.setattr(m,'integridad',verificar_integridad)
    assert m.migrar(instalada)['aplicada']


def test_backup_invalido_detiene_antes_del_ddl(instalada,monkeypatch):
    import pos_preproduccion as p
    antes=huella(instalada)
    def rechazar(*a): raise ValueError('backup ficticio inválido')
    monkeypatch.setattr(p,'validar_respaldo',rechazar)
    with pytest.raises(ValueError): m.migrar(instalada)
    assert huella(instalada)==antes
    assert 'esquema_minimo' not in configuracion(instalada)


def test_corrupcion_no_se_repara_ni_sobrescribe(instalada):
    ruta(instalada).write_bytes(b'base ficticia corrupta')
    antes=ruta(instalada).read_bytes()
    with pytest.raises(sqlite3.Error): m.migrar(instalada)
    assert ruta(instalada).read_bytes()==antes


def test_fk_rota_rechaza_antes_de_actualizar(instalada):
    sql(instalada,"INSERT INTO pos_ventas_clientes VALUES(999,999)")
    antes=huella(instalada)
    with pytest.raises(ValueError): m.migrar(instalada)
    assert huella(instalada)==antes


def test_bloqueos_de_proceso_y_de_escritura(instalada):
    with bloquear_entrenamiento(instalada):
        with pytest.raises(ValueError): m.migrar(instalada)
    with closing(sqlite3.connect(ruta(instalada))) as db:
        db.execute('BEGIN IMMEDIATE')
        with pytest.raises(sqlite3.OperationalError): m.migrar(instalada)
        db.rollback()
    assert m.migrar(instalada)['aplicada']


def test_dos_solicitudes_concurrentes_no_duplican(instalada):
    def intentar(_):
        try: return m.migrar(instalada)['aplicada']
        except (ValueError,sqlite3.OperationalError): return False
    with ThreadPoolExecutor(max_workers=2) as pool: resultados=list(pool.map(intentar,range(2)))
    assert resultados.count(True)==1
    assert sql(instalada,'SELECT COUNT(*) FROM abadion_migraciones')==[(1,)]


@pytest.mark.parametrize('punto',['antes_commit','despues_commit'])
def test_interrupcion_de_proceso_y_repeticion(instalada,punto):
    antes=estado(instalada)
    programa='''
import os,sys
from pathlib import Path
import migraciones as m
original=m.verificar_version
def salir(db,*args):
    v=original(db,*args)
    if v==5: os._exit(73)
    return v
if sys.argv[2]=='antes_commit': m.verificar_version=salir
m.migrar(Path(sys.argv[1]))
os._exit(74)
'''
    proc=subprocess.run([sys.executable,'-c',programa,str(instalada),punto],cwd=ROOT,
        env={**os.environ,'PYTHONPATH':str(ROOT/'src'),'PYTHON_DOTENV_DISABLED':'1'},capture_output=True,timeout=40)
    assert proc.returncode==(73 if punto=='antes_commit' else 74),proc.stderr.decode(errors='replace')
    assert m.migrar(instalada)['aplicada']==(punto=='antes_commit')
    assert all(estado(instalada)[k]==v for k,v in antes.items())


def test_sesion_de_42_preservada_y_usuario_deshabilitado_revoca(instalada):
    from tests.test_abadion_pruebas import conexion
    c=conexion(instalada,'ventas')
    cookies=dict(c.cookies)
    assert m.migrar(instalada)['aplicada']
    assert c.get('/pos-api/yo').status_code==200
    sql(instalada,"UPDATE usuarios_pos SET activo=0 WHERE rol='ventas'")
    assert c.get('/pos-api/yo').status_code==401
    sql(instalada,"UPDATE usuarios_pos SET activo=1 WHERE rol='ventas'")
    c.cookies.update(cookies)
    assert c.get('/pos-api/yo').status_code==401


def test_registro_inmutable_version_futura_y_falsa_rebaja(instalada):
    m.migrar(instalada)
    for orden in ('DELETE FROM abadion_migraciones','UPDATE abadion_esquema SET version=4'):
        with pytest.raises(sqlite3.Error): sql(instalada,orden)
    sql(instalada,'PRAGMA user_version=4')
    with pytest.raises(ValueError): m.migrar(instalada)
    with pytest.raises(ValueError): abrir_base(instalada,configuracion(instalada)['id'])


def test_actualizacion_no_habilita_inicializadores_implicitos(instalada,monkeypatch):
    from database import inicializar_base_de_datos,RUTA_ENTRENAMIENTO
    m.migrar(instalada)
    c=RUTA_ENTRENAMIENTO.set(ruta(instalada))
    try:
        with pytest.raises(ValueError,match='implícitamente'): inicializar_base_de_datos()
    finally: RUTA_ENTRENAMIENTO.reset(c)


def test_operaciones_financieras_costos_y_saldos_no_se_reescriben(unificado):
    from tests.test_saldo_unificado import saldos
    carpeta,c,ids,_=unificado
    campos={'pagos':[pago('comidas',1250000)],'total_esperado_centavos':1250000,
            'envio':{'titular':'repartidor','importe_centavos':0,'motivo_bonificacion':'Fixture ficticio'}}
    venta(c,ids,**campos)
    venta(c,ids,pagos=[],fiado=True,id_cliente=c.post('/pos-api/simulacion/clientes',json={'id_solicitud':__import__('uuid').uuid4().hex,'nombre':'Persona ficticia'}).json()['id_cliente'])
    antes=estado(carpeta)
    saldos_antes=saldos(c)
    m.migrar(carpeta)
    assert all(estado(carpeta)[k]==v for k,v in antes.items())
    assert saldos(c)==saldos_antes
    venta(c,ids,**campos)
    assert c.get('/pos-api/simulacion/conciliacion').json()['cuadrado']


def test_recuperacion_actual_conserva_operaciones_posteriores_al_prebackup(instalada,tmp_path):
    m.migrar(instalada)
    sql(instalada,"INSERT INTO productos(nombre,categoria,stock) VALUES('Operación ficticia posterior','Bebidas',17)")
    antes=estado(instalada)
    destino=tmp_path/'recuperada'/'Pruebas'
    recuperar_actual(instalada,destino)
    despues=estado(destino)
    assert all(despues[k]==v for k,v in antes.items() if k not in ('sesiones_pos','sesiones_pos_contexto'))
    assert estado(instalada)==antes
    assert m.diagnosticar(destino)['instancia']==configuracion(instalada)['id']
    assert configuracion(destino)['control']!=configuracion(instalada)['control']
    with pytest.raises(ValueError): recuperar_actual(instalada,destino)


def test_recuperacion_posterior_a_fallo_y_rechazo_restore_obsoleto(instalada,tmp_path,monkeypatch):
    vieja=respaldo(instalada)
    original=m.aplicar_paso
    def fallo(db): original(db); raise RuntimeError('ficticio')
    monkeypatch.setattr(m,'aplicar_paso',fallo)
    with pytest.raises(RuntimeError): m.migrar(instalada)
    destino=tmp_path/'recuperada'/'Pruebas'
    recuperar_actual(instalada,destino)
    assert sql(destino,'PRAGMA user_version')==[(4,)]
    monkeypatch.setattr(m,'aplicar_paso',original)
    m.migrar(destino)
    for archivo in (vieja,vieja.with_suffix('.json')):
        (destino/'backups'/archivo.name).write_bytes(archivo.read_bytes())
    with pytest.raises(ValueError):
        with bloquear_entrenamiento(destino): restaurar(destino,vieja.name)
    with pytest.raises(ValueError):
        with bloquear_entrenamiento(destino): restaurar(destino,respaldo(destino).name)


def test_launcher_anterior_no_admite_la_version_5(instalada):
    m.migrar(instalada)
    viejo=instalada.parent/'codigo42'
    viejo.mkdir()
    archivo=subprocess.check_output(['git','archive','--format=zip',REFS[-1],'src','scripts'],cwd=ROOT)
    with zipfile.ZipFile(io.BytesIO(archivo)) as z:
        for n in z.namelist():
            if n.endswith('/'): continue
            assert '..' not in Path(n).parts and not Path(n).is_absolute()
            p=viejo/n; p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(z.read(n))
    antes=huella(instalada)
    programa="import sys; from pathlib import Path; sys.path[:0]=[sys.argv[1],str(Path(sys.argv[1])/'src')]; from pos_preproduccion import abrir_base,configuracion; p=Path(sys.argv[2]); abrir_base(p,configuracion(p)['id'],lectura=True)"
    proc=subprocess.run([sys.executable,'-c',programa,str(viejo),str(instalada)],cwd=viejo,
        env={**os.environ,'PYTHON_DOTENV_DISABLED':'1'},capture_output=True,timeout=30)
    assert proc.returncode!=0 and b'ValueError' in proc.stderr
    assert huella(instalada)==antes
    assert sql(instalada,'PRAGMA user_version')!=[(4,)]
    with closing(sqlite3.connect(ruta(instalada))) as db: assert m.verificar_version(db)==5


def test_backup_gestionado_alterado_no_recupera(instalada,tmp_path):
    from scripts.abadion_pruebas import recuperar
    m.migrar(instalada)
    copia=respaldo(instalada)
    copia.write_bytes(copia.read_bytes()+b'alteracion ficticia')
    antes=huella(instalada)
    destino=tmp_path/'rechazada'/'Pruebas'
    with pytest.raises(ValueError): recuperar(instalada,copia.name,destino)
    assert huella(instalada)==antes and not destino.exists()


def test_fallo_al_publicar_configuracion_recupera_en_otro_destino(instalada,tmp_path,monkeypatch):
    from scripts import abadion_pruebas as p
    antes=estado(instalada)
    guardar=p.guardar
    def fallo(path,data):
        path.with_suffix('.pendiente').write_text('publicación ficticia interrumpida')
        raise OSError('interrupción ficticia')
    monkeypatch.setattr(p,'guardar',fallo)
    with pytest.raises(OSError): m.migrar(instalada)
    assert estado(instalada)==antes
    monkeypatch.setattr(p,'guardar',guardar)
    destino=tmp_path/'recuperada'/'Pruebas'
    recuperar_actual(instalada,destino)
    assert m.migrar(destino)['aplicada']
    assert all(estado(destino)[k]==v for k,v in antes.items() if k not in ('sesiones_pos','sesiones_pos_contexto'))
