"""Ataques simulados y regresión sobre bases creadas por pytest, nunca instalaciones."""
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from api import app, responder_resultado
from database import obtener_conexion
from pos_auth import (autenticar_y_crear_sesion, crear_sesion_pos, generar_hash,
                      obtener_usuario_sesion_pos, revocar_sesion_pos)
import pos_seguridad as seguridad
from tests.test_pos_pedidos import ORIGEN, pedido_prueba
from tests.test_pos_simulacion import venta_prueba, VENTAS, _estado


def sql(texto, valores=()):
    with closing(obtener_conexion()) as db, db:
        return db.execute(texto, valores).fetchall()


@pytest.fixture
def cuenta(base_prueba):
    sql("INSERT INTO usuarios_pos(usuario,rol,password_hash) VALUES('ventas','ventas',?)",
        (generar_hash('Clave-ficticia-123!'),))
    return sql('SELECT id_usuario FROM usuarios_pos')[0][0]


@pytest.mark.parametrize('columna,valor', [
    ('password_hash', 'otro-hash-ficticio'), ('rol', 'admin'), ('usuario', 'otro-nombre'), ('activo', 0)])
def test_cambio_usuario_revoca_todas_las_sesiones(cuenta, columna, valor):
    tokens=[crear_sesion_pos(cuenta) for _ in range(2)]
    sql(f'UPDATE usuarios_pos SET {columna}=? WHERE id_usuario=?', (valor, cuenta))
    assert all(obtener_usuario_sesion_pos(t) is None for t in tokens)
    assert sql('SELECT revocada FROM sesiones_pos') == [(1,), (1,)]
    assert sql("SELECT COUNT(*) FROM eventos_seguridad_pos WHERE evento='usuario_modificado'") == [(1,)]
    if columna == 'activo':
        sql('UPDATE usuarios_pos SET activo=1 WHERE id_usuario=?', (cuenta,))
        assert all(obtener_usuario_sesion_pos(t) is None for t in tokens)


def test_token_anterior_no_adopta_rol_admin(cuenta):
    token=crear_sesion_pos(cuenta)
    sql("UPDATE usuarios_pos SET rol='admin'")
    cliente=TestClient(app)
    cliente.cookies.set('abadion_pos_admin', token, path='/pos-api')
    assert cliente.get('/pos-api/admin/verificar').status_code == 401
    cliente.cookies.set('abadion_pos_admin', crear_sesion_pos(cuenta), path='/pos-api')
    assert cliente.get('/pos-api/admin/verificar').status_code == 200


@pytest.mark.parametrize('vencimiento', ['2000-01-01T00:00:00+00:00', '2099-01-01T00:00:00+00:00',
                                         '2099-01-01', 'fecha-invalida', None])
def test_vencimiento_invalido_no_autentica(cuenta, vencimiento):
    token=crear_sesion_pos(cuenta)
    if vencimiento is None:
        sql("UPDATE sesiones_pos SET creada_en='2099-01-01T00:00:00+00:00'")
    else:
        sql('UPDATE sesiones_pos SET expira_en=?', (vencimiento,))
    assert obtener_usuario_sesion_pos(token) is None


@pytest.mark.parametrize('rol,segundos', [('ventas', 30*24*3600), ('admin', 8*3600)])
def test_duracion_y_cookie_conservadas(cuenta, rol, segundos):
    sql('UPDATE usuarios_pos SET rol=?', (rol,))
    cliente=TestClient(app, base_url='https://testserver')
    r=cliente.post('/pos-api/login', headers={'Origin':'https://testserver'},
                   json={'usuario':'ventas','contrasena':'Clave-ficticia-123!'})
    assert r.status_code==200
    cookie=r.headers['set-cookie'].lower()
    assert f'max-age={segundos}' in cookie
    assert all(s in cookie for s in ('httponly','secure','samesite=strict','path=/pos-api'))
    fechas=sql('SELECT creada_en,expira_en FROM sesiones_pos')[0]
    assert (datetime.fromisoformat(fechas[1])-datetime.fromisoformat(fechas[0])).total_seconds()==segundos


@pytest.mark.parametrize('token', ['', 'inventado', "' OR 1=1 --", 'a'*257, '\ud800'])
def test_tokens_manipulados_no_autentican(cuenta, token):
    crear_sesion_pos(cuenta)
    assert obtener_usuario_sesion_pos(token) is None


def test_sesion_legada_sin_contexto_exige_login(cuenta):
    token=crear_sesion_pos(cuenta)
    sql('DROP TABLE sesiones_pos_contexto')
    assert obtener_usuario_sesion_pos(token) is None
    nuevo=autenticar_y_crear_sesion('ventas', 'Clave-ficticia-123!')
    assert nuevo and obtener_usuario_sesion_pos(nuevo[1])
    assert obtener_usuario_sesion_pos(token) is None
    assert sql('PRAGMA integrity_check') == [('ok',)]
    assert sql('PRAGMA foreign_key_check') == []


def test_emision_revierte_si_falla_auditoria(cuenta):
    sql("CREATE TRIGGER fallo BEFORE INSERT ON eventos_seguridad_pos BEGIN SELECT RAISE(ABORT,'ficticio'); END")
    with pytest.raises(sqlite3.IntegrityError):
        crear_sesion_pos(cuenta)
    assert sql('SELECT COUNT(*) FROM sesiones_pos')==[(0,)]
    assert sql('SELECT COUNT(*) FROM sesiones_pos_contexto')==[(0,)]


def test_carrera_cambio_clave_antes_de_emitir(cuenta, monkeypatch):
    import pos_auth
    original=pos_auth.crear_sesion_pos
    def cambiar(*args, **kwargs):
        sql("UPDATE usuarios_pos SET password_hash='hash-rotado'")
        return original(*args, **kwargs)
    monkeypatch.setattr(pos_auth, 'crear_sesion_pos', cambiar)
    assert autenticar_y_crear_sesion('ventas','Clave-ficticia-123!') is None
    assert sql('SELECT COUNT(*) FROM sesiones_pos')==[(0,)]


def test_login_limita_y_se_recupera_sin_bloqueo_permanente(cuenta, monkeypatch):
    reloj=[0.0]
    monkeypatch.setattr(seguridad, 'monotonic', lambda: reloj[0])
    monkeypatch.setattr(seguridad, 'LIMITE_LOGIN', 2)
    cliente=TestClient(app)
    datos={'usuario':'ventas','contrasena':'clave-erronea'}
    for _ in range(2):
        assert cliente.post('/pos-api/login',headers=ORIGEN,json=datos).status_code==401
    for tiempo in (1,30,59):
        reloj[0]=tiempo
        r=cliente.post('/pos-api/login',headers=ORIGEN,json=datos)
        assert r.status_code==429 and 0<int(r.headers['Retry-After'])<=60
    reloj[0]=60.01
    datos['contrasena']='Clave-ficticia-123!'
    assert cliente.post('/pos-api/login',headers=ORIGEN,json=datos).status_code==200
    assert sql('SELECT activo FROM usuarios_pos')==[(1,)]


def test_limite_concurrente_y_memoria_acotada(monkeypatch):
    almacen={}
    from collections import OrderedDict
    almacen=OrderedDict()
    monkeypatch.setattr(seguridad, 'monotonic', lambda: 100.0)
    with ThreadPoolExecutor(max_workers=8) as pool:
        resultados=list(pool.map(lambda _:seguridad._consumir(almacen,b'origen-ficticio',20),range(40)))
    assert resultados.count(0)==20
    monkeypatch.setattr(seguridad, 'MAX_CLAVES', 3)
    for i in range(10):
        seguridad._consumir(almacen,str(i),20)
    assert len(almacen)==3


def test_limite_ignora_forwarded_y_distingue_peer_y_base(base_prueba, monkeypatch):
    from starlette.requests import Request
    def request(peer,xff):
        return Request({'type':'http','client':(peer,123), 'headers':[(b'x-forwarded-for',xff.encode())]})
    a=seguridad._clave_origen(request('127.0.0.1','uno'))
    assert a==seguridad._clave_origen(request('127.0.0.1','otro'))
    assert a!=seguridad._clave_origen(request('127.0.0.2','uno'))
    monkeypatch.setenv('NEGOCIO_DB_PATH',str(base_prueba.parent/'otra-ficticia.db'))
    assert a!=seguridad._clave_origen(request('127.0.0.1','uno'))


@pytest.mark.parametrize('headers', [{}, {'Origin':'https://intruso.invalid'},
    {'Origin':'http://testserver','Sec-Fetch-Site':'cross-site'},
    [('Origin','http://testserver'),('Origin','http://testserver')]])
def test_csrf_login_y_logout_denegados(cuenta, headers):
    cliente=TestClient(app)
    token=crear_sesion_pos(cuenta)
    cliente.cookies.set('abadion_pos_ventas', token, path='/pos-api')
    assert cliente.post('/pos-api/logout',headers=headers).status_code==403
    assert cliente.post('/pos-api/login',headers=headers,
        json={'usuario':'ventas','contrasena':'Clave-ficticia-123!'}).status_code==403
    assert obtener_usuario_sesion_pos(token)


@pytest.mark.parametrize('ruta', ['/pos-api/catalogo/productos', '/pos-api/catalogo/adicionales',
                                     '/pos-api/catalogo/productos/1/personalizaciones'])
def test_catalogo_legado_privado(cuenta, ruta):
    r=TestClient(app).get(ruta)
    assert r.status_code==401
    assert r.headers['Cache-Control']=='no-store'


def test_login_no_refleja_secretos_ni_input(cuenta, caplog):
    cliente=TestClient(app)
    secreto='NO-PUBLICAR-ESTE-VALOR-'
    r=cliente.post('/pos-api/login',headers=ORIGEN,json={'usuario':'ventas','contrasena':secreto*30})
    assert r.status_code==422 and secreto not in r.text
    assert all('input' not in e and 'ctx' not in e for e in r.json()['detail'])
    r=cliente.post('/pos-api/login',headers=ORIGEN,json={'usuario':"' OR 1=1 --",'contrasena':secreto})
    assert r.status_code==401 and secreto not in r.text
    assert secreto not in caplog.text and 'OR 1=1' not in caplog.text
    assert sql('SELECT COUNT(*) FROM sesiones_pos')==[(0,)]


def test_errores_sqlite_no_exponen_driver(cuenta):
    respuesta=responder_resultado({'ok':False,'codigo':'ERROR_BASE_DATOS',
                                  'mensaje':'C:/secreto/archivo.db token=valor-ficticio'})
    assert respuesta.status_code==500
    assert b'archivo.db' not in respuesta.body and b'valor-ficticio' not in respuesta.body


def test_auditoria_minima_inmutable_y_sin_token(cuenta):
    token=crear_sesion_pos(cuenta)
    assert revocar_sesion_pos(token)
    registros=sql('SELECT evento,id_usuario,ruta,estado_http FROM eventos_seguridad_pos')
    assert [r[0] for r in registros]==['sesion_emitida','sesion_revocada']
    assert token not in json.dumps(registros)
    assert 'Clave-ficticia' not in json.dumps(registros)
    with pytest.raises(sqlite3.IntegrityError,match='inmutable'):
        sql('DELETE FROM eventos_seguridad_pos')


def test_revocacion_entre_autorizacion_y_venta_revierte(venta_prueba, monkeypatch):
    import pos_api
    cliente, venta=venta_prueba
    original=pos_api.registrar_venta_simulada
    def revocar(*args, **kwargs):
        sql('UPDATE usuarios_pos SET activo=0')
        return original(*args, **kwargs)
    monkeypatch.setattr(pos_api,'registrar_venta_simulada',revocar)
    r=cliente.post(VENTAS,headers=ORIGEN,json=venta)
    assert r.status_code==401
    assert _estado()==(10,0,0,0)
    assert sql('PRAGMA integrity_check')==[('ok',)]


def test_fallo_financiero_http_generico_y_rollback(venta_prueba):
    cliente,venta=venta_prueba
    sql("CREATE TRIGGER fallo_stock BEFORE UPDATE OF stock ON productos BEGIN SELECT RAISE(ABORT,'token=secreto-ficticio'); END")
    r=cliente.post(VENTAS,headers=ORIGEN,json=venta)
    assert r.status_code==500 and 'secreto-ficticio' not in r.text
    assert _estado()==(10,0,0,0)
    assert sql("SELECT COUNT(*) FROM eventos_seguridad_pos WHERE ruta=?",(VENTAS,))==[(0,)]


def test_ventas_concurrentes_idempotentes_y_auditoria_sin_movimiento_extra(venta_prueba):
    cliente,venta=venta_prueba
    cookies=dict(cliente.cookies)
    def enviar(_):
        with TestClient(app) as c:
            c.cookies.update(cookies)
            return c.post(VENTAS,headers=ORIGEN,json=venta)
    with ThreadPoolExecutor(max_workers=2) as pool:
        respuestas=list(pool.map(enviar,range(2)))
    assert all(r.status_code==200 for r in respuestas), [r.text for r in respuestas]
    assert respuestas[0].json()==respuestas[1].json()
    assert _estado()==(8,1,0,1)
    assert sql('PRAGMA foreign_key_check')==[]


def test_todos_los_endpoints_privados_rechazan_acceso_directo(venta_prueba):
    import re
    from pathlib import Path
    matriz=json.loads((Path(__file__).resolve().parents[1]/'docs/seguridad/endpoints-consolidados.json').read_text(encoding='utf-8'))
    cliente=TestClient(app)
    for fila in matriz:
        if fila['permiso'] not in ('Administración','Administración o Ventas'):
            continue
        ruta=re.sub(r'\{[^}]+\}','1',fila['ruta'])
        for metodo in fila['metodos']:
            r=cliente.request(metodo,ruta,headers=ORIGEN,json={})
            assert r.status_code==401,(metodo,ruta,r.text)


def test_todos_los_endpoints_admin_rechazan_ventas(venta_prueba):
    import re
    from pathlib import Path
    cliente,_=venta_prueba
    matriz=json.loads((Path(__file__).resolve().parents[1]/'docs/seguridad/endpoints-consolidados.json').read_text(encoding='utf-8'))
    for fila in matriz:
        if fila['permiso']!='Administración':
            continue
        ruta=re.sub(r'\{[^}]+\}','1',fila['ruta'])
        for metodo in fila['metodos']:
            r=cliente.request(metodo,ruta,headers=ORIGEN,json={})
            assert r.status_code==403,(metodo,ruta,r.text)


def test_auditoria_http_fallida_no_convierte_commit_en_error(venta_prueba,caplog):
    cliente,venta=venta_prueba
    sql("CREATE TRIGGER fallo_audit BEFORE INSERT ON eventos_seguridad_pos BEGIN SELECT RAISE(ABORT,'secreto-audit-ficticio'); END")
    r=cliente.post(VENTAS,headers=ORIGEN,json=venta)
    assert r.status_code==200,r.text
    assert _estado()==(8,1,0,1)
    request=SimpleNamespace(method='PATCH', state=SimpleNamespace(identidad_pos=None),
                            scope={'route':SimpleNamespace(path='/pos-api/admin/productos/{id_producto}/precio')})
    seguridad.auditar_http(request,200)
    assert 'auditoria_seguridad_no_disponible' in caplog.text
    assert 'secreto-audit-ficticio' not in caplog.text


def test_rotacion_concurrente_final_revoca_sesiones(cuenta):
    def emitir(_):
        return crear_sesion_pos(cuenta)
    with ThreadPoolExecutor(max_workers=3) as pool:
        tokens=list(pool.map(emitir,range(3)))
    sql("UPDATE usuarios_pos SET password_hash='rotada-ficticia'")
    assert all(obtener_usuario_sesion_pos(t) is None for t in tokens)
    assert sql('PRAGMA integrity_check')==[('ok',)]


def test_rol_en_json_no_eleva_permisos_y_cookie_renombrada_no_sirve(cuenta):
    cliente=TestClient(app)
    r=cliente.post('/pos-api/login',headers=ORIGEN,json={
        'usuario':'ventas','contrasena':'Clave-ficticia-123!','rol':'admin','id_usuario':999})
    assert r.status_code==200 and r.json()['rol']=='ventas'
    token=cliente.cookies.get('abadion_pos_ventas')
    assert cliente.get('/pos-api/admin/verificar').status_code==403
    cliente.cookies.clear()
    cliente.cookies.set('abadion_pos_admin',token,path='/pos-api')
    assert cliente.get('/pos-api/admin/verificar').status_code==401


def test_inventario_endpoints_se_verifica_sin_abrir_db(base_prueba,monkeypatch):
    from scripts.auditar_endpoints import inventario
    import database
    def prohibir():
        raise AssertionError('El inventario no debe abrir SQLite')
    monkeypatch.setattr(database,'obtener_conexion',prohibir)
    filas=inventario()
    assert sum(len(f['metodos']) for f in filas)==83


@pytest.mark.parametrize('correcto',[False,True])
def test_inicio_api_no_registra_ruta_ni_error_del_backup(base_prueba,monkeypatch,capsys,correcto):
    import api
    secreto='SECRETO-FICTICIO-NO-REGISTRAR'
    monkeypatch.setattr(api,'crear_backup_diario',lambda:{'ok':correcto,'creado':True,
                         'ruta':'C:/usuarios/'+secreto+'/archivo.db','mensaje':secreto})
    api.preparar_base_de_datos()
    salida=capsys.readouterr()
    assert secreto not in salida.out+salida.err
    esperado='Backup diario creado.' if correcto else 'no se pudo crear el backup diario'
    assert esperado in salida.out
