"""Perímetro del POS ficticio detrás de un túnel administrado con Access."""
import asyncio
import re
from time import monotonic, time

from google.auth import jwt
from google.auth.exceptions import GoogleAuthError
import httpx
from starlette.datastructures import Headers
from starlette.responses import PlainTextResponse

from pos_tablet_laboratorio import PerimetroTablet, crear_app_laboratorio


ETIQUETA_DNS = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
HOST_PUBLICO = rf"(?:{ETIQUETA_DNS}\.)+[a-z]{{2,63}}"
CABECERA_ACCESS = b"cf-access-jwt-assertion"


class VerificadorAccess:
    def __init__(self, *, equipo, audiencia, correo):
        if not re.fullmatch(ETIQUETA_DNS, equipo):
            raise ValueError("Indicá el nombre de equipo de Cloudflare Access.")
        if not re.fullmatch(r"[a-f0-9]{64}", audiencia):
            raise ValueError("Indicá la audiencia de la aplicación Access.")
        if not re.fullmatch(r"[^\s,*@]+@[^\s,*@]+\.[^\s,*@]+", correo):
            raise ValueError("Indicá un único correo individual autorizado.")
        self.emisor = f"https://{equipo}.cloudflareaccess.com"
        self.audiencia = audiencia
        self.correo = correo.casefold()
        self.certificados = {}
        self.refrescar_en = 0
        self.candado = asyncio.Lock()

    async def _descargar_certificados(self):
        async with httpx.AsyncClient(timeout=5, follow_redirects=False, trust_env=False) as cliente:
            respuesta = await cliente.get(f"{self.emisor}/cdn-cgi/access/certs")
            respuesta.raise_for_status()
            return {entrada["kid"]: entrada["cert"] for entrada in respuesta.json()["public_certs"]}

    async def _claves(self):
        async with self.candado:
            if monotonic() >= self.refrescar_en:
                try:
                    self.certificados = await asyncio.wait_for(self._descargar_certificados(), timeout=6)
                except (TimeoutError, httpx.HTTPError, KeyError, TypeError, ValueError):
                    self.certificados = {}
                # No reutilizar claves vencidas ni provocar descargas por un kid desconocido.
                self.refrescar_en = monotonic() + (300 if self.certificados else 15)
            return self.certificados

    async def permite(self, token):
        if len(token) > 8192 or not re.fullmatch(r"[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", token):
            return False
        return self._valida_firma_y_datos(token, await self._claves())

    def _valida_firma_y_datos(self, token, claves):
        try:
            cabecera = jwt.decode_header(token)
            kid = cabecera.get("kid")
            if cabecera.get("alg") != "RS256" or not isinstance(kid, str) or kid not in claves:
                return False
            datos = jwt.decode(token, certs={kid: claves[kid]})
            audiencias = datos.get("aud")
            correo = datos.get("email")
            ahora = time()
            return (
                datos.get("iss") == self.emisor
                and datos.get("type") == "app"
                and isinstance(audiencias, list) and self.audiencia in audiencias
                and isinstance(correo, str) and correo.casefold() == self.correo
                and all(type(datos.get(campo)) is int for campo in ("iat", "nbf", "exp"))
                and datos["iat"] <= ahora and datos["nbf"] <= ahora < datos["exp"]
            )
        except (GoogleAuthError, AttributeError, KeyError, OverflowError, TypeError, ValueError):
            return False


class PerimetroAccess:
    def __init__(self, app, *, verificador):
        self.app = app
        self.verificador = verificador

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = Headers(scope=scope)
        tokens = headers.getlist("cf-access-jwt-assertion")
        if (
            not scope.get("client") or scope["client"][0] != "127.0.0.1"
            or headers.getlist("host") != [self.app.autoridad]
            or headers.getlist("x-forwarded-proto") != ["https"]
            or len(tokens) != 1 or not await self.verificador.permite(tokens[0])
        ):
            return await PlainTextResponse(
                "Acceso al laboratorio denegado.", status_code=403,
                headers={"Cache-Control": "no-store"},
            )(scope, receive, send)

        # Cloudflare sobrescribe el esquema del visitante. Uvicorn no interpreta
        # los headers proxy y la aplicación solo recibe la vista HTTPS autorizada.
        headers_internos = [
            (nombre, valor) for nombre, valor in scope["headers"]
            if nombre not in (b"forwarded", CABECERA_ACCESS)
            and not nombre.startswith(b"x-forwarded-")
        ]
        return await self.app(
            {**scope, "scheme": "https", "headers": headers_internos}, receive, send,
        )


def crear_app_remota(carpeta, *, host, port, verificador):
    if (len(host) > 253 or not re.fullmatch(HOST_PUBLICO, host)
            or host.endswith((".trycloudflare.com", ".cloudflareaccess.com", ".local"))):
        raise ValueError("Indicá el hostname público exacto del túnel administrado.")
    app = crear_app_laboratorio(carpeta, host=host, cookies=(
        "abadion_tablet_access_admin", "abadion_tablet_access_ventas",
    ))
    perimetro = PerimetroTablet(
        app, host="127.0.0.1", port=port, clientes=("127.0.0.1",), autoridad=host,
    )
    return PerimetroAccess(perimetro, verificador=verificador)
