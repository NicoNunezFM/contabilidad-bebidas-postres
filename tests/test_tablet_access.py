"""El origen recibe solicitudes simuladas con JWT firmados por claves efímeras."""
from contextlib import closing
from time import time
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from google.auth import crypt, jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from pos_caja_diaria import ahora_local
from pos_entrenamiento_db import ARCHIVO_BASE, abrir_base_entrenamiento
from pos_tablet_access import VerificadorAccess, crear_app_remota
from tests.test_tablet_https import ADMIN, VENTAS, laboratorio


HOST = "pos-lab.example.com"
ORIGEN = f"https://{HOST}"
AUD = "a" * 64
CORREO = "operador@example.com"
AFIRMACION = "Cf-Access-Jwt-Assertion"


@pytest.fixture(scope="module")
def firmante():
    clave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    privada = clave.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    publica = clave.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return crypt.RSASigner.from_string(privada, key_id="clave-test"), publica


@pytest.fixture
def acceso(firmante, monkeypatch):
    verificador = VerificadorAccess(equipo="equipo-test", audiencia=AUD, correo=CORREO)
    signer, publica = firmante

    def responder(peticion):
        assert str(peticion.url) == f"{verificador.emisor}/cdn-cgi/access/certs"
        return httpx.Response(200, json={"public_certs": [
            {"kid": "clave-test", "cert": publica.decode("ascii")},
        ]})

    clase_cliente = httpx.AsyncClient

    def cliente_claves(**opciones):
        assert opciones["follow_redirects"] is False
        assert opciones["trust_env"] is False
        return clase_cliente(transport=httpx.MockTransport(responder), **opciones)

    monkeypatch.setattr("pos_tablet_access.httpx.AsyncClient", cliente_claves)

    def token(*, header=None, key_id=None, **claims):
        ahora = int(time())
        datos = {
            "iss": verificador.emisor, "aud": [AUD], "email": CORREO,
            "type": "app", "iat": ahora - 5, "nbf": ahora - 5, "exp": ahora + 600,
        }
        return jwt.encode(signer, {**datos, **claims}, header=header, key_id=key_id).decode("ascii")

    return verificador, token


def cliente_usando(app, *, ip="127.0.0.1"):
    # URL visible para el navegador y su política de cookies. El transporte ASGI
    # entra por HTTP, como lo haría cloudflared en loopback.
    async def origen_http(scope, receive, send):
        await app({**scope, "scheme": "http"}, receive, send)

    return TestClient(origen_http, base_url=ORIGEN, client=(ip, 50000))


@pytest.fixture
def remoto(laboratorio, acceso):
    app = crear_app_remota(laboratorio, host=HOST, port=8461, verificador=acceso[0])
    with cliente_usando(app) as cliente:
        yield cliente


def cabeceras(token):
    return {AFIRMACION: token, "X-Forwarded-Proto": "https", "Origin": ORIGEN}


def iniciar(cliente, headers, usuario="tablet-ventas", clave=VENTAS):
    return cliente.post("/pos-api/login", headers=headers, json={"usuario": usuario, "contrasena": clave})


@pytest.mark.parametrize("cambios", [
    {"iss": "https://otro.cloudflareaccess.com"}, {"aud": ["b" * 64]},
    {"aud": AUD}, {"email": None}, {"email": "otro@example.com"}, {"type": "org"},
    {"exp": 1}, {"iat": 4_000_000_000}, {"nbf": 4_000_000_000}, {"nbf": None},
    {"key_id": "desconocida"}, {"header": {"alg": "none"}},
])
def test_rechaza_jwt_firmado_con_datos_invalidos(acceso, firmante, cambios):
    verificador, emitir = acceso
    claves = {"clave-test": firmante[1]}
    assert verificador._valida_firma_y_datos(emitir(), claves)
    assert not verificador._valida_firma_y_datos(emitir(**cambios), claves)


def test_rechaza_acceso_sin_firma_sin_tunel_o_con_cabeceras_ambiguas(laboratorio, remoto, acceso):
    verificador, emitir = acceso
    token = emitir()
    prefijo, firma = token.rsplit(".", 1)
    modificado = prefijo + "." + ("A" if firma[0] != "A" else "B") + firma[1:]
    remoto.cookies.set("CF_Authorization", token)
    for ruta in ("/pos/", "/pos-api/simulacion/estado", "/pos-api/catalogo/productos"):
        assert remoto.get(ruta).status_code == 403
    for headers in (
        cabeceras(modificado), cabeceras("a.a.a"),
        {**cabeceras(token), "Host": "otro.example.com"},
        {**cabeceras(token), "X-Forwarded-Proto": "http"},
        [*cabeceras(token).items(), (AFIRMACION, token)],
        [*cabeceras(token).items(), ("X-Forwarded-Proto", "https")],
    ):
        assert remoto.get("/pos/", headers=headers).status_code == 403
    app = crear_app_remota(laboratorio, host=HOST, port=8461, verificador=verificador)
    with cliente_usando(app, ip="192.168.1.5") as externo:
        assert externo.get("/pos/", headers=cabeceras(token)).status_code == 403


def test_falla_cerrado_al_vencer_cache_sin_claves(remoto, acceso, monkeypatch):
    verificador, emitir = acceso
    headers = cabeceras(emitir())
    assert remoto.get("/pos/", headers=headers).status_code == 200

    async def sin_claves():
        raise httpx.ConnectError("origen de claves no disponible")

    monkeypatch.setattr(verificador, "_descargar_certificados", sin_claves)
    verificador.refrescar_en = 0
    assert remoto.get("/pos/", headers=headers).status_code == 403
    assert not verificador.certificados


def test_sesiones_y_roles_remotos(laboratorio, remoto, acceso):
    headers = cabeceras(acceso[1]())
    assert remoto.get("/pos/", headers=headers).status_code == 200
    assert remoto.get("/pos-api/catalogo/productos", headers=headers).status_code == 401
    for origen in ("", "https://otro.example.com", "http://" + HOST):
        assert iniciar(remoto, {**headers, "Origin": origen}).status_code == 403
    assert iniciar(remoto, {k: v for k, v in headers.items() if k != "Origin"}).status_code == 403
    assert iniciar(remoto, headers, clave="incorrecta").status_code == 401
    respuesta = iniciar(remoto, headers)
    assert respuesta.status_code == 200, respuesta.text
    for atributo in ("abadion_tablet_access_ventas=", "Secure", "HttpOnly", "SameSite=strict", "Path=/pos-api"):
        assert atributo in respuesta.headers["set-cookie"]
    assert remoto.get("/pos-api/yo").status_code == 403
    assert remoto.get("/pos-api/admin/verificar", headers=headers).status_code == 403
    assert remoto.get("/negocio.db", headers=headers).status_code == 404
    cookie = remoto.cookies.get("abadion_tablet_access_ventas")
    assert remoto.post("/pos-api/logout", headers=headers).status_code == 200
    remoto.cookies.set("abadion_tablet_access_ventas", cookie)
    assert remoto.get("/pos-api/yo", headers=headers).status_code == 401
    assert iniciar(remoto, headers, "tablet-admin", ADMIN).status_code == 200
    assert remoto.get("/pos-api/admin/verificar", headers=headers).status_code == 200
    with closing(abrir_base_entrenamiento(laboratorio / ARCHIVO_BASE)) as db, db:
        db.execute("UPDATE sesiones_pos SET expira_en = '2000-01-01T00:00:00+00:00'")
    assert remoto.get("/pos-api/yo", headers=headers).status_code == 401


def test_venta_remota_en_dos_cajas_e_idempotencia(remoto, acceso):
    remoto.headers.update(cabeceras(acceso[1]()))
    assert iniciar(remoto, remoto.headers).status_code == 200
    for caja in ("comidas", "bebidas_postres"):
        apertura = remoto.post(f"/pos-api/simulacion/caja-diaria/{caja}/apertura", json={
            "id_solicitud": str(uuid4()), "fecha": ahora_local()[:10], "inicial_centavos": 0,
        })
        assert apertura.status_code == 200, apertura.text
    productos = remoto.get("/pos-api/catalogo/productos").json()["productos"]
    opciones = remoto.get(f"/pos-api/catalogo/productos/{productos[0]['id_producto']}/personalizaciones")
    assert opciones.status_code == 200
    assert "Extra ficticio" in opciones.text
    pedido = {"items": [{"id_producto": p["id_producto"], "cantidad": 1} for p in productos],
              "id_solicitud": str(uuid4()), "total_esperado_centavos": 150_000, "medio_pago": "efectivo"}
    primera = remoto.post("/pos-api/simulacion/ventas", json=pedido)
    assert primera.status_code == 200, primera.text
    assert primera.json()["cajas_centavos"] == {"comidas": 100_000, "bebidas_postres": 50_000}
    assert remoto.post("/pos-api/simulacion/ventas", json=pedido).json() == primera.json()
    cajas = remoto.get("/pos-api/simulacion/caja-diaria").json()["cajas"]
    assert {caja: datos["esperado_centavos"] for caja, datos in cajas.items()} == primera.json()["cajas_centavos"]
    historial = remoto.get("/pos-api/simulacion/ventas").json()["ventas"]
    assert [venta["id_venta"] for venta in historial] == [primera.json()["id_venta"]]
