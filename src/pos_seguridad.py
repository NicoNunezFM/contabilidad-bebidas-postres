"""Controles del transporte POS; no escribe movimientos comerciales."""
import hashlib
import hmac
import json
import logging
import math
import secrets
import sqlite3
from collections import OrderedDict, deque
from contextlib import closing
from contextvars import ContextVar
from threading import Lock
from time import monotonic

from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from fastapi.responses import JSONResponse


PETICION_POS = ContextVar('peticion_pos_segura', default=None)
LOG = logging.getLogger('abadion.seguridad')
_SAL = secrets.token_bytes(32)
_CANDADO = Lock()
_LOGIN = OrderedDict()
_AUDITORIA = OrderedDict()
LIMITE_LOGIN = 20
VENTANA = 60
MAX_CLAVES = 4096


def preparar_esquema(db):
    """Invoca el inicializador o emisor dentro de una transacción; sin backfill."""
    db.execute('''CREATE TABLE IF NOT EXISTS sesiones_pos_contexto (
        token_hash TEXT PRIMARY KEY REFERENCES sesiones_pos(token_hash),
        huella TEXT NOT NULL CHECK(length(huella)=64))''')
    db.execute('''CREATE TABLE IF NOT EXISTS eventos_seguridad_pos (
        id_evento INTEGER PRIMARY KEY, fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        evento TEXT NOT NULL, id_usuario INTEGER, ruta TEXT NOT NULL, estado_http INTEGER NOT NULL)''')
    for accion in ('UPDATE','DELETE'):
        db.execute(f'''CREATE TRIGGER IF NOT EXISTS seguridad_auditoria_inmutable_{accion.lower()}
            BEFORE {accion} ON eventos_seguridad_pos BEGIN
                SELECT RAISE(ABORT,'La auditoría de seguridad es inmutable.'); END''')
    db.execute('''CREATE TRIGGER IF NOT EXISTS seguridad_revocar_cambio_usuario
        AFTER UPDATE OF password_hash,rol,activo,usuario ON usuarios_pos
        WHEN NEW.password_hash IS NOT OLD.password_hash OR NEW.rol IS NOT OLD.rol
          OR NEW.activo IS NOT OLD.activo OR NEW.usuario IS NOT OLD.usuario
        BEGIN
            UPDATE sesiones_pos SET revocada=1 WHERE id_usuario=OLD.id_usuario AND revocada=0;
            INSERT INTO eventos_seguridad_pos(evento,id_usuario,ruta,estado_http)
                VALUES('usuario_modificado',NEW.id_usuario,'cambio_directo_usuario',0);
        END''')


def huella_usuario(fila):
    return hashlib.sha256(json.dumps(list(fila),ensure_ascii=True,separators=(',',':')).encode()).hexdigest()


def guardar_evento(db, evento, usuario=None, ruta='sesiones', estado=200):
    cursor=db.execute('INSERT INTO eventos_seguridad_pos(evento,id_usuario,ruta,estado_http) VALUES(?,?,?,?)',
                     (evento,usuario,ruta,estado))
    if cursor.rowcount!=1:
        raise sqlite3.IntegrityError('No se registró el evento de seguridad.')


def _clave_origen(request):
    from database import obtener_ruta_base
    # No confiar en IPs/identidades declaradas por el cliente ni registrar la IP.
    origen=request.client.host if request.client else 'sin-origen'
    valor=str(obtener_ruta_base().resolve())+'\0'+origen
    return hmac.new(_SAL,valor.encode('utf-8',errors='replace'),hashlib.sha256).digest()


def _consumir(almacen,clave,limite):
    ahora=monotonic()
    with _CANDADO:
        while almacen:
            primera, valores=next(iter(almacen.items()))
            if valores and valores[-1]>ahora-VENTANA:
                break
            almacen.pop(primera)
        valores=almacen.setdefault(clave,deque())
        while valores and valores[0]<=ahora-VENTANA:
            valores.popleft()
        if len(valores)>=limite:
            return max(1,math.ceil(valores[0]+VENTANA-ahora))
        valores.append(ahora)
        almacen.move_to_end(clave)
        while len(almacen)>MAX_CLAVES:
            almacen.popitem(last=False)
        return 0


def limitar_login(request):
    espera=_consumir(_LOGIN,_clave_origen(request),LIMITE_LOGIN)
    if espera:
        raise HTTPException(429,'Demasiados intentos. Esperá antes de volver a intentar.',
                            headers={'Retry-After':str(espera)})


def errores_validacion_seguros(error):
    salida=[]
    for e in error.errors():
        loc=list(e.get('loc',()))
        if e.get('type')=='extra_forbidden' and loc:
            loc[-1]='campo_no_permitido'
        mensaje=e.get('msg','Valor inválido.')
        if e.get('type') in ('value_error','assertion_error'):
            mensaje='Valor inválido.'
        salida.append({'type':e.get('type','valor_invalido'),'loc':loc,'msg':mensaje})
    return salida


def fijar_identidad(request,token,usuario):
    request.state.identidad_pos=(hashlib.sha256(token.encode()).hexdigest(),usuario['id_usuario'],usuario['rol'])


def validar_sesion_en_transaccion(db):
    """Revalida tras BEGIN IMMEDIATE para cerrar la carrera con revocación/rol."""
    request=PETICION_POS.get()
    if request is None:
        return  # Llamadores internos/offline, no una credencial HTTP alternativa.
    identidad=getattr(request.state,'identidad_pos',None)
    if identidad is None:
        raise HTTPException(401,'No hay una sesión válida.')
    from pos_auth import leer_sesion_en_db
    usuario=leer_sesion_en_db(db,identidad[0])
    if usuario is None or (usuario['id_usuario'],usuario['rol'])!=identidad[1:]:
        raise HTTPException(401,'La sesión cambió. Iniciá sesión nuevamente.')


def auditar_http(request,estado):
    sensible=request.method not in ('GET','HEAD','OPTIONS')
    ruta=request.scope['route'].path
    if ruta=='/pos-api/pedidos/validar' or ruta.endswith('/abonos/vista-previa'):
        sensible=False
    if not sensible and estado not in (401,403):
        return
    identidad=getattr(request.state,'identidad_pos',None)
    if (estado in (401,403,429) or identidad is None) and _consumir(_AUDITORIA,_clave_origen(request),20):
        return  # Acotar escritura de auditoría anónima, sin registrar cada paquete de un ataque.
    usuario=identidad[1] if identidad else None
    evento=('login_denegado' if ruta=='/pos-api/login' else 'acceso_denegado') if estado in (401,403,429) else 'solicitud_sensible'
    emitir=LOG.warning if estado in (401,403,429) else LOG.info
    emitir('evento=%s ruta=%s metodo=%s estado=%d id_usuario=%s',evento,ruta,request.method,estado,usuario)
    if estado>=400:
        return  # Denegaciones al log seguro, sin escribir dentro de una operación revertida.
    if identidad is None or not ruta.startswith('/pos-api/admin/'):
        # Las operaciones comerciales ya tienen eventos transaccionales e idempotencia.
        # Emisión/revocación ya se auditan atómicamente; logout anónimo no debe escribir.
        return
    try:
        from database import obtener_conexion
        with closing(obtener_conexion()) as db,db:
            if db.execute("SELECT 1 FROM sqlite_schema WHERE name='eventos_seguridad_pos'").fetchone():
                guardar_evento(db,evento,usuario,ruta,estado)
    except (sqlite3.Error,ValueError,OSError):
        LOG.warning('auditoria_seguridad_no_disponible')


class RutaPosSegura(APIRoute):
    def get_route_handler(self):
        original=super().get_route_handler()

        async def protegido(request):
            contexto=PETICION_POS.set(request)
            request.state.identidad_pos=None
            estado=500
            try:
                try:
                    respuesta=await original(request)
                except RequestValidationError as error:
                    respuesta=JSONResponse({'detail':errores_validacion_seguros(error)},status_code=422)
                except HTTPException as error:
                    respuesta=JSONResponse({'detail':error.detail},status_code=error.status_code,headers=error.headers)
                except (sqlite3.Error,UnicodeError):
                    # No serializar valores, rutas SQLite, tokens o detalles del driver.
                    respuesta=JSONResponse({'detail':'No se pudo completar la operación.'},status_code=500)
                estado=respuesta.status_code
                respuesta.headers['Cache-Control']='no-store'
                respuesta.headers['X-Content-Type-Options']='nosniff'
                respuesta.headers['Referrer-Policy']='no-referrer'
                respuesta.headers['X-Frame-Options']='DENY'
                return respuesta
            finally:
                try:
                    auditar_http(request,estado)
                finally:
                    PETICION_POS.reset(contexto)
        return protegido
