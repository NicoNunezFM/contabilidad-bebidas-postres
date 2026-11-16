import re

from fastapi.testclient import TestClient

from api import app
from database import obtener_conexion
from pos_auth import crear_sesion_pos
from tests import TOKEN_BOT_FICTICIO, TOKEN_INTEGRACION_FICTICIO


def test_rutas_contables_exigen_credencial_de_servicio(base_prueba):
    cliente = TestClient(app)
    for ruta, operaciones in app.openapi()["paths"].items():
        if ruta == "/" or ruta.startswith("/pos-api/"):
            continue
        url = re.sub(r"\{[^}]+\}", "1", ruta)
        for metodo in operaciones:
            respuesta = cliente.request(metodo, url)
            assert respuesta.status_code == 401, (metodo, ruta)
            assert respuesta.headers["WWW-Authenticate"] == "Bearer"
            if ruta != "/comandos":
                respuesta = cliente.request(
                    metodo, url, headers={"Authorization": f"Bearer {TOKEN_BOT_FICTICIO}"}
                )
                assert respuesta.status_code == 401, (metodo, ruta)


def test_bot_autenticado_conserva_comando_y_reintento(base_prueba):
    cliente = TestClient(app, headers={"Authorization": f"Bearer {TOKEN_BOT_FICTICIO}"})
    comando = {"mensaje": "stock", "id_mensaje": "mensaje-ficticio-1", "canal": "whatsapp"}
    primera = cliente.post("/comandos", json=comando)
    segunda = cliente.post("/comandos", json=comando)
    assert primera.status_code == segunda.status_code == 200
    assert segunda.json() == {**primera.json(), "repetido": True}


def test_claves_ausentes_cortas_o_compartidas_fallan_cerrado(base_prueba, monkeypatch):
    cliente = TestClient(app)
    for clave in ("", "corta", TOKEN_BOT_FICTICIO):
        monkeypatch.setenv("ABADION_API_TOKEN", clave)
        respuesta = cliente.get("/caja", headers={"Authorization": f"Bearer {clave}"})
        assert respuesta.status_code == 401

    monkeypatch.delenv("ABADION_API_TOKEN")
    respuesta = cliente.get("/caja", headers={"Authorization": f"Bearer {TOKEN_INTEGRACION_FICTICIO}"})
    assert respuesta.status_code == 401


def test_sesion_pos_puede_leer_catalogo_y_no_da_acceso_contable(producto_prueba):
    conexion = obtener_conexion()
    try:
        with conexion:
            usuario = conexion.execute(
                "INSERT INTO usuarios_pos (usuario, rol, password_hash) VALUES (?, ?, ?)",
                ("vendedor ficticio", "ventas", "hash de prueba"),
            ).lastrowid
    finally:
        conexion.close()

    cliente = TestClient(app)
    assert cliente.get("/pos-api/catalogo/productos").status_code == 401
    cliente.cookies.set("abadion_pos_ventas", crear_sesion_pos(usuario), path="/pos-api")
    assert cliente.get("/pos-api/catalogo/productos").json()["productos"][0]["id_producto"] == producto_prueba
    assert cliente.get("/caja").status_code == 401
