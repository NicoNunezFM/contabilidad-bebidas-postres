"""Perímetro HTTPS del laboratorio ficticio; no es un servidor de producción."""
from ipaddress import IPv4Address, IPv4Network
from collections import deque
from time import monotonic

from starlette.requests import Request
from starlette.responses import PlainTextResponse

from pos_entrenamiento_web import crear_app_entrenamiento


REDES_LOCALES = tuple(IPv4Network(red) for red in (
    "127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",
))


def ipv4_local(valor):
    ip = IPv4Address(valor)
    if not any(ip in red for red in REDES_LOCALES) or ip.is_unspecified:
        raise ValueError("Usá una IPv4 de loopback o de red privada explícita.")
    return str(ip)


class PerimetroTablet:
    """No confía en cabeceras proxy ni redirige credenciales recibidas por HTTP."""

    def __init__(self, app, *, host, port, clientes):
        self.app = app
        self.host = ipv4_local(host)
        if not 1024 <= port <= 65535:
            raise ValueError("El puerto debe estar entre 1024 y 65535.")
        self.autoridad = f"{self.host}:{port}"
        self.origen = f"https://{self.autoridad}"
        self.clientes = frozenset(ipv4_local(ip) for ip in clientes)
        self.intentos_login = {}
        if not self.clientes:
            raise ValueError("Indicá al menos una IPv4 cliente permitida.")

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            return await self.app(scope, receive, send)
        if scope["type"] != "http":
            return await send({"type": "websocket.close", "code": 1008})
        request = Request(scope)
        error = None
        if scope.get("scheme") != "https":
            error = (403, "El laboratorio exige HTTPS directo.")
        elif not scope.get("client") or scope["client"][0] not in self.clientes:
            error = (403, "Dispositivo no permitido.")
        elif request.headers.getlist("host") != [self.autoridad]:
            error = (400, "Destino no permitido.")
        elif any(nombre.lower().startswith(b"x-forwarded-") or nombre.lower() == b"forwarded"
                 for nombre, _ in scope["headers"]):
            error = (400, "Este laboratorio no admite proxies.")
        elif request.method not in ("GET", "HEAD") and request.headers.getlist("origin") != [self.origen]:
            error = (403, "Origen no permitido.")
        elif request.url.path == "/pos-api/login":
            ahora = monotonic()
            intentos = self.intentos_login.setdefault(scope["client"][0], deque())
            while intentos and intentos[0] <= ahora - 60:
                intentos.popleft()
            if len(intentos) >= 10:
                error = (429, "Demasiados intentos. Esperá un minuto.")
            else:
                intentos.append(ahora)

        async def proteger(message):
            if message["type"] == "http.response.start":
                headers = [(k, v) for k, v in message.get("headers", [])
                           if k.lower() not in (b"cache-control", b"x-content-type-options", b"referrer-policy")]
                headers.extend([(b"cache-control", b"no-store"),
                                (b"x-content-type-options", b"nosniff"),
                                (b"referrer-policy", b"no-referrer"),
                                (b"x-frame-options", b"DENY")])
                message = {**message, "headers": headers}
            await send(message)

        if error:
            return await PlainTextResponse(error[1], status_code=error[0])(scope, receive, proteger)
        # El POS consulta sus indicadores de modo antes del login; no contienen datos comerciales.
        publicas = ("/pos-api/login", "/pos-api/simulacion/estado")
        if request.url.path.startswith("/pos-api/") and request.url.path not in publicas:
            from database import RUTA_ENTRENAMIENTO
            from fastapi import HTTPException
            from pos_api import exigir_usuario_pos
            contexto = RUTA_ENTRENAMIENTO.set(self.app.state.ruta_laboratorio)
            scope["app"] = self.app
            try:
                exigir_usuario_pos(request)
            except HTTPException as exc:
                return await PlainTextResponse("Iniciá sesión en el laboratorio.", status_code=exc.status_code)(scope, receive, proteger)
            finally:
                RUTA_ENTRENAMIENTO.reset(contexto)
        return await self.app(scope, receive, proteger)


def crear_app_tablet(carpeta, *, host="127.0.0.1", port=8460, clientes=("127.0.0.1",)):
    host = ipv4_local(host)
    # Solo acepta el marcador adicional creado por el launcher de laboratorio.
    from contextlib import closing
    from pos_entrenamiento_db import ARCHIVO_BASE, abrir_base_entrenamiento
    with closing(abrir_base_entrenamiento(carpeta / ARCHIVO_BASE, solo_lectura=True)) as db:
        if not db.execute("SELECT 1 FROM sqlite_schema WHERE type='table' AND name='pos_tablet_laboratorio'").fetchone():
            raise ValueError("Falta el marcador pos_tablet_laboratorio de base ficticia nueva.")
        if db.execute("SELECT identidad FROM pos_tablet_laboratorio").fetchall() != [("ficticio-efimero-v1",)]:
            raise ValueError("Se requiere una base nueva del laboratorio ficticio.")
    app = crear_app_entrenamiento(carpeta, hosts_permitidos=(host,),
                                 aviso="LABORATORIO FICTICIO TEMPORAL - SIN VALIDEZ CONTABLE")
    app.state.ruta_laboratorio = carpeta / ARCHIVO_BASE
    app.state.cookies_pos = ("abadion_tablet_lab_admin", "abadion_tablet_lab_ventas")
    return PerimetroTablet(app, host=host, port=port, clientes=clientes)
