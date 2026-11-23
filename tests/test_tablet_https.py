"""Aislamiento, autenticación y TLS real en loopback; nunca abre la LAN."""
import base64
from contextlib import closing
from datetime import datetime, timedelta, timezone
import hashlib
from ipaddress import ip_address
import os
import socket
import ssl
from threading import Thread
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
import uvicorn

from pos_entrenamiento_db import ARCHIVO_BASE, abrir_base_entrenamiento
from pos_caja_diaria import ahora_local
from pos_tablet_laboratorio import crear_app_tablet, ipv4_local
from scripts.abadion_entrenamiento import preparar_base
from scripts.servir_tablet_https import configurar_tls, preparar_laboratorio
from tests.test_pos_web import abrir_navegador, controles_pos, esperar


VENTAS = "ventas-ficticias-8460"
ADMIN = "admin-ficticio-8460"
ORIGEN = "https://127.0.0.1:8460"


@pytest.fixture
def laboratorio(tmp_path, monkeypatch):
    sentinela = tmp_path / "negocio.db"
    contenido = b"SENTINELA FICTICIA - NO USAR COMO SQLITE"
    sentinela.write_bytes(contenido)
    monkeypatch.setenv("NEGOCIO_DB_PATH", str(sentinela))
    carpeta = tmp_path / "laboratorio"
    carpeta.mkdir()
    preparar_laboratorio(carpeta, clave_ventas=VENTAS, clave_admin=ADMIN)
    yield carpeta
    assert sentinela.read_bytes() == contenido


def cliente_lab(carpeta, origen=ORIGEN, **kwargs):
    return TestClient(crear_app_tablet(carpeta), base_url=origen,
                      client=("127.0.0.1", 50000), **kwargs)


def login(cliente, clave=VENTAS, usuario="tablet-ventas"):
    return cliente.post("/pos-api/login", headers={"Origin": ORIGEN},
                        json={"usuario": usuario, "contrasena": clave})


@pytest.mark.parametrize("valor", ["0.0.0.0", "8.8.8.8", "169.254.1.1", "::1", "localhost", "192.168.1.0/24"])
def test_bind_rechaza_comodines_redes_y_destinos_no_privados(valor):
    with pytest.raises(ValueError):
        ipv4_local(valor)


def test_no_admite_entrenamiento_existente_ni_reutiliza_directorio(tmp_path, laboratorio):
    with pytest.raises(ValueError):
        preparar_laboratorio(laboratorio, clave_ventas=VENTAS, clave_admin=ADMIN)
    otra = tmp_path / "instalacion"
    otra.mkdir()
    preparar_base(otra)
    with pytest.raises(ValueError, match="pos_tablet_laboratorio"):
        crear_app_tablet(otra)


@pytest.mark.parametrize("ruta", ["/pos-api/catalogo/productos", "/pos-api/yo"])
def test_api_exige_sesion(laboratorio, ruta):
    with cliente_lab(laboratorio) as cliente:
        respuesta = cliente.get(ruta)
        assert respuesta.status_code == 401
        assert respuesta.headers["cache-control"] == "no-store"


def test_estado_publico_solo_informa_modo(laboratorio):
    with cliente_lab(laboratorio) as cliente:
        estado = cliente.get("/pos-api/simulacion/estado").json()
        assert estado == {"ok": True, "simulacion": True, "caja_diaria": True,
                          "contabilidad": True, "clientes": True}


def test_rechaza_http_host_proxy_cliente_y_origen(laboratorio):
    with cliente_lab(laboratorio, origen="http://127.0.0.1:8460") as cliente:
        assert cliente.get("/pos/", headers={"X-Forwarded-Proto": "https"}).status_code == 403
    with cliente_lab(laboratorio) as cliente:
        assert cliente.get("/pos/", headers={"Host": "malicioso.local:8460"}).status_code == 400
        for cabecera in ("Forwarded", "X-Forwarded-For", "X-Forwarded-Proto", "X-Forwarded-Host"):
            assert cliente.get("/pos/", headers={cabecera: "127.0.0.1"}).status_code == 400
        for origen in ("https://otro.local", "null", "http://127.0.0.1:8460", ""):
            assert cliente.post("/pos-api/login", headers={"Origin": origen}, json={
                "usuario": "tablet-ventas", "contrasena": VENTAS}).status_code == 403
    with TestClient(crear_app_tablet(laboratorio), base_url=ORIGEN, client=("192.168.2.2", 50000)) as cliente:
        assert cliente.get("/pos/").status_code == 403


def test_login_cookie_aislada_roles_logout_y_credenciales_publicas(laboratorio):
    with cliente_lab(laboratorio) as cliente:
        assert login(cliente, "Ventas-Prueba-8060", "ventas-prueba").status_code == 401
        assert login(cliente, "clave-incorrecta").status_code == 401
        respuesta = login(cliente)
        assert respuesta.status_code == 200
        cookie = respuesta.headers["set-cookie"]
        for atributo in ("abadion_tablet_lab_ventas=", "HttpOnly", "Secure", "SameSite=strict", "Path=/pos-api"):
            assert atributo in cookie
        assert cliente.get("/pos-api/yo").json()["usuario"]["rol"] == "ventas"
        assert cliente.get("/pos-api/admin/verificar").status_code == 403
        assert cliente.get("/caja").status_code == 404
        assert cliente.post("/comandos", headers={"Origin": ORIGEN}, json={}).status_code == 404
        assert cliente.get("/negocio.db").status_code == 404
        assert cliente.get("/docs").status_code == 404
        productos = cliente.get("/pos-api/catalogo/productos").json()["productos"]
        assert {p["nombre"] for p in productos} == {"Comida ficticia", "Bebida ficticia", "Postre ficticio"}
        assert cliente.post("/pos-api/logout", headers={"Origin": ORIGEN}).status_code == 200
        assert cliente.get("/pos-api/yo").status_code == 401
        assert login(cliente, ADMIN, "tablet-admin").status_code == 200
        assert cliente.get("/pos-api/admin/verificar").status_code == 200


def test_venta_ficticia_separa_cajas_y_reintento_no_duplica(laboratorio):
    with cliente_lab(laboratorio, headers={"Origin": ORIGEN}) as cliente:
        assert login(cliente).status_code == 200
        for caja in ("comidas", "bebidas_postres"):
            respuesta = cliente.post(f"/pos-api/simulacion/caja-diaria/{caja}/apertura", json={
                "id_solicitud": str(uuid4()), "fecha": ahora_local()[:10], "inicial_centavos": 0,
            })
            assert respuesta.status_code == 200, respuesta.text
        productos = cliente.get("/pos-api/catalogo/productos").json()["productos"]
        pedido = {"items": [{"id_producto": p["id_producto"], "cantidad": 1} for p in productos],
                  "id_solicitud": str(uuid4()), "total_esperado_centavos": 150_000, "medio_pago": "efectivo"}
        primera = cliente.post("/pos-api/simulacion/ventas", json=pedido)
        assert primera.status_code == 200, primera.text
        assert primera.json()["cajas_centavos"] == {"comidas": 100_000, "bebidas_postres": 50_000}
        assert cliente.post("/pos-api/simulacion/ventas", json=pedido).json() == primera.json()
        cajas = cliente.get("/pos-api/simulacion/caja-diaria").json()["cajas"]
        assert cajas["comidas"]["esperado_centavos"] == 100_000
        assert cajas["bebidas_postres"]["esperado_centavos"] == 50_000
    with closing(abrir_base_entrenamiento(laboratorio / ARCHIVO_BASE, solo_lectura=True)) as db:
        assert db.execute("SELECT COUNT(*) FROM pos_tablet_laboratorio").fetchone()[0] == 1


def test_login_limita_intentos_por_dispositivo(laboratorio):
    with cliente_lab(laboratorio) as cliente:
        for _ in range(10):
            assert login(cliente, "incorrecta").status_code == 401
        assert login(cliente).status_code == 429


@pytest.fixture
def certificado(tmp_path):
    # Certificado y clave nuevos en cada prueba, nunca se publican ni instalan.
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Abadion test loopback")])
    ahora = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(ahora - timedelta(minutes=1))
            .not_valid_after(ahora + timedelta(hours=1))
            .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ip_address("127.0.0.1"))]), critical=False)
            .sign(key, hashes.SHA256()))
    ruta_cert, ruta_key = tmp_path / "test.pem", tmp_path / "test-key.pem"
    ruta_cert.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    ruta_key.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                         serialization.NoEncryption()))
    spki = key.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    return ruta_cert, ruta_key, base64.b64encode(hashlib.sha256(spki).digest()).decode()


def test_tls_real_certificado_verificado_y_http_sin_acceso(laboratorio, certificado):
    with socket.socket() as red:
        red.bind(("127.0.0.1", 0))
        port = red.getsockname()[1]
        origen = f"https://127.0.0.1:{port}"
        app = crear_app_tablet(laboratorio, port=port)
        config = configurar_tls(app, host="127.0.0.1", port=port, cert=certificado[0], key=certificado[1])
        assert config.proxy_headers is False
        assert config.ssl.minimum_version == ssl.TLSVersion.TLSv1_2
        server = uvicorn.Server(config)
        hilo = Thread(target=server.run, kwargs={"sockets": [red]}, daemon=True)
        hilo.start()
        try:
            esperar(lambda: server.started)
            contexto = ssl.create_default_context(cafile=str(certificado[0]))
            with httpx.Client(base_url=origen, verify=contexto, trust_env=False) as cliente:
                assert cliente.get("/pos/").status_code == 200
                assert cliente.post("/pos-api/login", headers={"Origin": origen}, json={
                    "usuario": "tablet-ventas", "contrasena": VENTAS}).status_code == 200
                assert cliente.get("/pos-api/catalogo/productos").status_code == 200
            with pytest.raises(httpx.TransportError):
                httpx.get(origen + "/pos/", trust_env=False)
            with pytest.raises(httpx.TransportError):
                httpx.get(f"http://127.0.0.1:{port}/pos/", trust_env=False, timeout=2)
        finally:
            server.should_exit = True
            hilo.join(timeout=10)


@pytest.fixture
def navegador_pos(laboratorio, certificado, tmp_path, request):
    ejecutable = os.getenv("POS_TEST_BROWSER")
    if not ejecutable:
        pytest.skip("Configurá POS_TEST_BROWSER con Microsoft Edge.")
    import websocket
    yield from abrir_navegador(None, ejecutable, tmp_path, websocket, viewport=request.param,
                              tls=certificado, app_factory=lambda port: crear_app_tablet(laboratorio, port=port))


@pytest.mark.parametrize("navegador_pos", [(1024, 600), (600, 1024)], indirect=True)
def test_edge_https_login_catalogo_y_logout(controles_pos):
    evaluar, clic, texto, _ = controles_pos
    texto("#entrenamientoAviso", "SIN VALIDEZ CONTABLE")
    assert evaluar("window.isSecureContext && location.protocol === 'https:'")
    clic("#adminAccess")
    evaluar(f"document.querySelector('#usuarioPos').value = 'tablet-ventas'; document.querySelector('#claveAdmin').value = '{VENTAS}';")
    clic("#accept")
    texto("#adminAccess", "tablet-ventas")
    texto("#cardsReal", "Comida ficticia")
    assert evaluar("document.documentElement.scrollWidth <= innerWidth")
    assert not evaluar("document.cookie.includes('abadion_tablet_lab_ventas')")
    evaluar("window.__labResultado = null; fetch('/pos-api/yo').then(r => r.json()).then(r => window.__labResultado = r.usuario.rol)")
    esperar(lambda: evaluar("window.__labResultado === 'ventas'"))
    evaluar("window.__labResultado = null; fetch('/pos-api/logout', {method:'POST'}).then(r => window.__labResultado = r.status)")
    esperar(lambda: evaluar("window.__labResultado === 200"))
    evaluar("window.__labResultado = null; fetch('/pos-api/yo').then(r => window.__labResultado = r.status)")
    esperar(lambda: evaluar("window.__labResultado === 401"))
