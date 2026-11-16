import sqlite3
from uuid import uuid4

import pytest

from database import obtener_conexion
from pos_auth import crear_sesion_pos
from pos_simulacion import crear_esquema_simulacion
from tests.test_pos_pedidos import ORIGEN, pedido_prueba


VENTAS = "/pos-api/simulacion/ventas"
CAJAS = "/pos-api/simulacion/cajas"


@pytest.fixture
def venta_prueba(pedido_prueba, monkeypatch):
    cliente, linea = pedido_prueba
    conexion = obtener_conexion()
    try:
        with conexion:
            crear_esquema_simulacion(conexion)
    finally:
        conexion.close()
    monkeypatch.setenv("POS_V1_SIMULACION", "1")
    return cliente, {
        "id_solicitud": str(uuid4()),
        "total_esperado_centavos": 23026,
        "medio_pago": "efectivo",
        "items": [linea],
    }


def _iniciar_sesion_administrador(cliente):
    conexion = obtener_conexion()
    try:
        with conexion:
            id_usuario = conexion.execute(
                "INSERT INTO usuarios_pos (usuario, rol, password_hash) VALUES ('admin', 'admin', 'prueba')"
            ).lastrowid
    finally:
        conexion.close()
    cliente.cookies.set("abadion_pos_admin", crear_sesion_pos(id_usuario), path="/pos-api")


def _estado():
    conexion = obtener_conexion()
    try:
        return (
            conexion.execute("SELECT stock FROM productos ORDER BY id_producto").fetchone()[0],
            conexion.execute("SELECT COUNT(*) FROM pos_ventas_simuladas").fetchone()[0],
            conexion.execute("SELECT COUNT(*) FROM ventas_operaciones").fetchone()[0],
            conexion.execute("SELECT COUNT(*) FROM pos_movimientos_simulados").fetchone()[0],
        )
    finally:
        conexion.close()


def test_simulacion_deshabilitada_sin_marca(pedido_prueba, monkeypatch):
    cliente, linea = pedido_prueba
    monkeypatch.setenv("POS_V1_SIMULACION", "1")
    respuesta = cliente.post(VENTAS, headers=ORIGEN, json={
        "id_solicitud": str(uuid4()), "total_esperado_centavos": 23026,
        "medio_pago": "efectivo", "items": [linea],
    })
    assert respuesta.status_code == 404


def test_simulacion_es_atomica_e_idempotente(venta_prueba):
    cliente, venta = venta_prueba
    respuesta = cliente.post(VENTAS, headers=ORIGEN, json=venta)
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["simulacion"] is True
    assert cliente.post(VENTAS, headers=ORIGEN, json=venta).json() == respuesta.json()
    assert cliente.post(VENTAS, headers=ORIGEN, json={**venta, "total_esperado_centavos": 1}).status_code == 409
    assert _estado() == (8, 1, 0, 1)


def test_revalida_total_y_revierte_si_falla_el_stock(venta_prueba):
    cliente, venta = venta_prueba
    respuesta = cliente.post(VENTAS, headers=ORIGEN, json={**venta, "total_esperado_centavos": 1})
    assert respuesta.status_code == 409
    assert _estado() == (10, 0, 0, 0)

    conexion = obtener_conexion()
    try:
        with conexion:
            conexion.execute("""
                CREATE TRIGGER error_stock BEFORE UPDATE OF stock ON productos
                BEGIN SELECT RAISE(ABORT, 'error de prueba'); END
            """)
    finally:
        conexion.close()
    with pytest.raises(sqlite3.IntegrityError):
        cliente.post(VENTAS, headers=ORIGEN, json=venta)
    assert _estado() == (10, 0, 0, 0)


def test_cajas_diferenciadas_y_medios_de_pago(venta_prueba):
    cliente, venta = venta_prueba
    conexion = obtener_conexion()
    try:
        with conexion:
            comida = conexion.execute("""
                INSERT INTO productos (nombre, categoria, precio_venta, stock)
                VALUES ('Comida prueba', 'Rotisería', 50.25, 2)
            """).lastrowid
    finally:
        conexion.close()

    invalida = cliente.post(VENTAS, headers=ORIGEN, json={**venta, "medio_pago": "tarjeta"})
    assert invalida.status_code == 422
    assert cliente.get(CAJAS).status_code == 403
    venta_mixta = cliente.post(VENTAS, headers=ORIGEN, json={
        **venta, "medio_pago": "transferencia", "total_esperado_centavos": 28051,
        "items": [*venta["items"], {"id_producto": comida, "cantidad": 1}],
    })
    assert venta_mixta.status_code == 200, venta_mixta.text
    assert venta_mixta.json()["cajas_centavos"] == {"bebidas_postres": 23026, "comidas": 5025}
    efectivo = cliente.post(VENTAS, headers=ORIGEN, json={**venta, "id_solicitud": str(uuid4())})
    assert efectivo.status_code == 200
    _iniciar_sesion_administrador(cliente)
    assert cliente.get(CAJAS).json()["saldos"] == [
        {"caja": "bebidas_postres", "medio_pago": "efectivo", "saldo_centavos": 23026},
        {"caja": "bebidas_postres", "medio_pago": "transferencia", "saldo_centavos": 23026},
        {"caja": "comidas", "medio_pago": "transferencia", "saldo_centavos": 5025},
    ]
