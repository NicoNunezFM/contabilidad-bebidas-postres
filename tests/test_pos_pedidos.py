import pytest
from fastapi.testclient import TestClient

from api import app
from database import obtener_conexion
from pos_auth import crear_sesion_pos


ORIGEN = {"Origin": "http://testserver"}
VALIDAR = "/pos-api/pedidos/validar"


@pytest.fixture
def pedido_prueba(producto_prueba):
    conexion = obtener_conexion()
    try:
        with conexion:
            conexion.execute("UPDATE productos SET precio_venta = 100.125")
            id_extra = conexion.execute(
                "INSERT INTO adicionales_catalogo (nombre, precio_venta) VALUES ('Queso', 15)"
            ).lastrowid
            conexion.execute(
                "INSERT INTO pos_adicionales_producto VALUES (?, ?)", (producto_prueba, id_extra)
            )
            conexion.execute(
                "INSERT INTO pos_ingredientes_producto (id_producto, ingrediente) VALUES (?, 'Limón')",
                (producto_prueba,),
            )
            id_usuario = conexion.execute(
                "INSERT INTO usuarios_pos (usuario, rol, password_hash) VALUES ('cajero', 'ventas', 'prueba')"
            ).lastrowid
    finally:
        conexion.close()

    with TestClient(app) as cliente:
        cliente.cookies.set("abadion_pos_ventas", crear_sesion_pos(id_usuario), path="/pos-api")
        yield cliente, {
            "id_producto": producto_prueba,
            "cantidad": 2,
            "ingredientes_quitados": ["  LIMÓN  "],
            "ids_adicionales": [id_extra],
        }


def test_valida_precio_actual_y_no_escribe(pedido_prueba, base_prueba):
    cliente, linea = pedido_prueba
    antes = base_prueba.read_bytes()
    respuesta = cliente.post(VALIDAR, headers=ORIGEN, json={"items": [linea]})
    assert respuesta.status_code == 200, respuesta.text
    resultado = respuesta.json()
    assert resultado["items"][0]["precio_base_centavos"] == 10013
    assert resultado["items"][0]["ingredientes_quitados"] == ["Limón"]
    assert resultado["total_centavos"] == 23026
    assert base_prueba.read_bytes() == antes


def test_valida_stock_sumando_lineas_y_respeta_productos_sin_control(pedido_prueba):
    cliente, linea = pedido_prueba
    json = {"items": [{**linea, "cantidad": 6}, {**linea, "cantidad": 5}]}
    respuesta = cliente.post(VALIDAR, headers=ORIGEN, json=json)
    assert respuesta.status_code == 409
    assert respuesta.json()["detail"]["cantidad_solicitada"] == 11
    conexion = obtener_conexion()
    try:
        with conexion:
            conexion.execute("UPDATE productos SET controla_stock = 0, stock = 0")
    finally:
        conexion.close()
    assert cliente.post(VALIDAR, headers=ORIGEN, json=json).status_code == 200


@pytest.mark.parametrize("cambio", [
    {"cantidad": True}, {"cantidad": "2"}, {"cantidad": 0}, {"precio_base": 1},
    {"ingredientes_quitados": ["inventado"]}, {"ingredientes_quitados": ["Limón", "limón"]},
    {"ids_adicionales": [999]}, {"ids_adicionales": [1, 1]},
    {"id_producto": 2**63},
])
def test_rechaza_lineas_invalidas(pedido_prueba, cambio):
    cliente, linea = pedido_prueba
    respuesta = cliente.post(VALIDAR, headers=ORIGEN, json={"items": [{**linea, **cambio}]})
    assert respuesta.status_code == 422


def test_exige_origen_y_sesion(pedido_prueba):
    cliente, linea = pedido_prueba
    pedido = {"items": [linea]}
    assert cliente.post(VALIDAR, json=pedido).status_code == 403
    cliente.cookies.clear()
    assert cliente.post(VALIDAR, headers=ORIGEN, json=pedido).status_code == 401


def test_rechaza_extra_desactivado_y_producto_inexistente(pedido_prueba):
    cliente, linea = pedido_prueba
    conexion = obtener_conexion()
    try:
        with conexion:
            conexion.execute("UPDATE adicionales_catalogo SET activo = 0")
    finally:
        conexion.close()
    assert cliente.post(VALIDAR, headers=ORIGEN, json={"items": [linea]}).status_code == 422
    linea["id_producto"] = 999
    assert cliente.post(VALIDAR, headers=ORIGEN, json={"items": [linea]}).status_code == 404
