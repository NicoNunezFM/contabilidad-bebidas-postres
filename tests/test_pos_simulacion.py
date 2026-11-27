import json
import os
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from api import app
from database import obtener_conexion
from pos_auth import crear_sesion_pos
from pos_simulacion import crear_esquema_simulacion
from tests.test_pos_pedidos import ORIGEN, pedido_prueba


VENTAS = "/pos-api/simulacion/ventas"
CAJAS = "/pos-api/simulacion/cajas"
MOVIMIENTOS = f"{CAJAS}/movimientos"
ESTADO = "/pos-api/simulacion/estado"


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


def _iniciar_sesion(cliente, usuario, rol):
    conexion = obtener_conexion()
    try:
        with conexion:
            id_usuario = conexion.execute(
                "INSERT INTO usuarios_pos (usuario, rol, password_hash) VALUES (?, ?, 'prueba')",
                (usuario, rol),
            ).lastrowid
    finally:
        conexion.close()
    cliente.cookies.set(f"abadion_pos_{rol}", crear_sesion_pos(id_usuario), path="/pos-api")


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
    assert cliente.get(ESTADO).status_code == 404


def test_simulacion_es_atomica_e_idempotente(venta_prueba):
    cliente, venta = venta_prueba
    respuesta = cliente.post(VENTAS, headers=ORIGEN, json=venta)
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["simulacion"] is True
    assert cliente.post(VENTAS, headers=ORIGEN, json=venta).json() == respuesta.json()
    assert cliente.post(VENTAS, headers=ORIGEN, json={**venta, "total_esperado_centavos": 1}).status_code == 409
    assert _estado() == (8, 1, 0, 1)


def test_recupera_venta_tras_caida_antes_del_commit(venta_prueba):
    cliente, venta = venta_prueba
    usuario = cliente.get("/pos-api/yo").json()["usuario"]
    comando = """
import json, os, sys
import pos_simulacion

def salir(*args, **kwargs):
    os._exit(73)

pos_simulacion.terminar_evento = salir
venta, usuario = json.loads(sys.argv[1])
pos_simulacion.registrar_venta_simulada(pos_simulacion.VentaSimuladaEntrada.model_validate(venta), usuario)
"""
    src = Path(__file__).resolve().parents[1] / "src"
    proceso = subprocess.run(
        [sys.executable, "-c", comando, json.dumps([venta, usuario])],
        env={**os.environ, "PYTHONPATH": str(src)},
        capture_output=True,
        timeout=20,
    )
    assert proceso.returncode == 73, proceso.stderr.decode(errors="replace")
    assert _estado() == (10, 0, 0, 0)
    with closing(obtener_conexion()) as db:
        assert db.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
        assert not db.execute("PRAGMA foreign_key_check").fetchall()
    respuesta = cliente.post(VENTAS, headers=ORIGEN, json=venta)
    assert respuesta.status_code == 200, respuesta.text
    assert cliente.post(VENTAS, headers=ORIGEN, json=venta).json() == respuesta.json()
    assert _estado() == (8, 1, 0, 1)


def test_estado_simulacion_y_reintentos_ligados_a_la_cuenta(venta_prueba):
    cliente, venta = venta_prueba
    estado = TestClient(app).get(ESTADO)
    assert estado.json() == {"ok": True, "simulacion": True}
    assert estado.headers["Cache-Control"] == "no-store"

    id_ventas = cliente.get("/pos-api/yo").json()["usuario"]["id_usuario"]
    headers = {**ORIGEN, "X-POS-Usuario": str(id_ventas)}
    registrada = cliente.post(VENTAS, headers=headers, json=venta)
    assert registrada.status_code == 200
    _iniciar_sesion(cliente, "admin", "admin")
    cambiada = cliente.post(VENTAS, headers=headers, json=venta)
    assert cambiada.status_code == 409
    assert cambiada.json()["detail"]["codigo"] == "SESION_CAMBIADA"
    url = f'{VENTAS}/{registrada.json()["id_venta"]}/anulacion'
    assert cliente.post(url, headers=headers, json={"motivo": "Prueba"}).status_code == 409
    assert _estado() == (8, 1, 0, 1)
    cliente.cookies.delete("abadion_pos_admin", path="/pos-api")
    assert cliente.post(VENTAS, headers=headers, json=venta).json() == registrada.json()


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
    respuesta = cliente.post(VENTAS, headers=ORIGEN, json=venta)
    assert respuesta.status_code == 500
    assert respuesta.json() == {"detail": "No se pudo completar la operación."}
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
    _iniciar_sesion(cliente, "admin", "admin")
    assert cliente.get(CAJAS).json()["saldos"] == [
        {"caja": "bebidas_postres", "medio_pago": "efectivo", "saldo_centavos": 23026},
        {"caja": "bebidas_postres", "medio_pago": "transferencia", "saldo_centavos": 23026},
        {"caja": "comidas", "medio_pago": "transferencia", "saldo_centavos": 5025},
    ]


def test_anulacion_auditada_restaura_stock_y_caja_una_vez(venta_prueba):
    cliente, venta = venta_prueba
    registrada = cliente.post(VENTAS, headers=ORIGEN, json=venta).json()
    url = f'{VENTAS}/{registrada["id_venta"]}/anulacion'
    assert cliente.post(url, headers=ORIGEN, json={"motivo": "Error de prueba"}).status_code == 403
    _iniciar_sesion(cliente, "admin", "admin")
    assert cliente.post(url, json={"motivo": "Error de prueba"}).status_code == 403
    assert cliente.post(url, headers=ORIGEN, json={"motivo": "  "}).status_code == 422

    respuesta = cliente.post(url, headers=ORIGEN, json={"motivo": "  Error de prueba  "})
    assert respuesta.status_code == 200, respuesta.text
    assert cliente.post(url, headers=ORIGEN, json={"motivo": "Duplicada"}).status_code == 409
    assert _estado() == (10, 1, 0, 2)

    assert cliente.get(CAJAS).json()["saldos"][0]["saldo_centavos"] == 0

    historial = cliente.get(VENTAS).json()["ventas"][0]
    assert historial["items"] == registrada["items"]
    assert historial["anulada"] is True
    assert historial["anulacion"]["motivo"] == "Error de prueba"
    assert historial["anulacion"]["id_usuario"] != historial["id_usuario"]

    cliente.cookies.delete("abadion_pos_admin", path="/pos-api")
    reintento = cliente.post(VENTAS, headers=ORIGEN, json=venta).json()
    assert reintento["id_venta"] == registrada["id_venta"]
    assert reintento["anulada"] is True
    assert _estado() == (10, 1, 0, 2)


def test_movimientos_paginados_por_caja_y_auditados(venta_prueba):
    cliente, venta = venta_prueba
    params = {"caja": "bebidas_postres", "limite": 1}
    assert TestClient(app).get(MOVIMIENTOS, params=params).status_code == 401
    assert cliente.get(MOVIMIENTOS, params=params).status_code == 403
    id_venta = cliente.post(VENTAS, headers=ORIGEN, json=venta).json()["id_venta"]
    _iniciar_sesion(cliente, "admin", "admin")
    assert cliente.post(
        f"{VENTAS}/{id_venta}/anulacion", headers=ORIGEN, json={"motivo": "Prueba"}
    ).status_code == 200
    respuesta = cliente.get(MOVIMIENTOS, params=params)
    assert respuesta.headers["Cache-Control"] == "no-store"
    primera = respuesta.json()
    anulacion, = primera["movimientos"]
    segunda = cliente.get(MOVIMIENTOS, params={**params, "antes_de": primera["siguiente_antes_de"]}).json()
    registro, = segunda["movimientos"]
    assert anulacion["id_venta"] == registro["id_venta"] == id_venta
    assert anulacion["id_usuario"] != registro["id_usuario"]
    assert anulacion["fecha"] and registro["fecha"]
    assert anulacion["tipo"] == "anulacion" and registro["tipo"] == "venta"
    assert anulacion["medio_pago"] == registro["medio_pago"] == "efectivo"
    assert anulacion["importe_centavos"] == -registro["importe_centavos"] == -23026
    assert segunda["siguiente_antes_de"] is None
    assert cliente.get(MOVIMIENTOS, params={"caja": "comidas"}).json()["movimientos"] == []
    assert cliente.get(MOVIMIENTOS, params={"caja": "otra"}).status_code == 422


def test_historial_limitado_por_usuario_y_paginado(venta_prueba):
    cliente, venta = venta_prueba
    primera = cliente.post(VENTAS, headers=ORIGEN, json=venta).json()["id_venta"]
    _iniciar_sesion(cliente, "otra_caja", "ventas")
    assert cliente.get(VENTAS).json()["ventas"] == []
    segunda = cliente.post(VENTAS, headers=ORIGEN, json=venta).json()["id_venta"]
    assert [fila["id_venta"] for fila in cliente.get(VENTAS).json()["ventas"]] == [segunda]

    _iniciar_sesion(cliente, "admin", "admin")
    respuesta = cliente.get(VENTAS, params={"limite": 1})
    assert respuesta.headers["Cache-Control"] == "no-store"
    primera_pagina = respuesta.json()
    assert primera_pagina["siguiente_antes_de"] == segunda
    ultima_pagina = cliente.get(VENTAS, params={"limite": 1, "antes_de": segunda}).json()
    assert [fila["id_venta"] for fila in ultima_pagina["ventas"]] == [primera]
    assert ultima_pagina["siguiente_antes_de"] is None


def test_ventas_concurrentes_no_superan_el_stock(venta_prueba):
    cliente, venta = venta_prueba
    venta["items"][0]["cantidad"] = 6
    venta["total_esperado_centavos"] = 69078

    def registrar(id_solicitud):
        return cliente.post(VENTAS, headers=ORIGEN, json={**venta, "id_solicitud": str(id_solicitud)})

    with ThreadPoolExecutor(max_workers=2) as executor:
        respuestas = list(executor.map(registrar, [uuid4(), uuid4()]))

    assert sorted(respuesta.status_code for respuesta in respuestas) == [200, 409]
    assert _estado() == (4, 1, 0, 1)


def test_simulacion_deshabilitada_por_defecto(venta_prueba, monkeypatch):
    cliente, venta = venta_prueba
    monkeypatch.delenv("POS_V1_SIMULACION")
    assert cliente.post(VENTAS, headers=ORIGEN, json=venta).status_code == 404
    assert cliente.get(VENTAS).status_code == 404
    assert _estado() == (10, 0, 0, 0)


def test_rechaza_version_anterior_del_esquema(venta_prueba):
    cliente, venta = venta_prueba
    conexion = obtener_conexion()
    try:
        with conexion:
            conexion.execute("PRAGMA user_version = 0")
    finally:
        conexion.close()
    assert cliente.post(VENTAS, headers=ORIGEN, json=venta).status_code == 409
    assert _estado() == (10, 0, 0, 0)


def test_arranque_simulado_rechaza_una_base_sin_marca_sin_escribir(base_prueba, monkeypatch):
    monkeypatch.setenv("POS_V1_SIMULACION", "1")
    antes = base_prueba.read_bytes()
    with pytest.raises(RuntimeError, match="Simulación POS deshabilitada"):
        with TestClient(app):
            pytest.fail("La API arrancó con una base sin marca de simulación")
    assert base_prueba.read_bytes() == antes
    assert not (base_prueba.parent / "backups").exists()


def test_arranque_simulado_conserva_el_catalogo_ficticio(producto_prueba, base_prueba, monkeypatch):
    conexion = obtener_conexion()
    try:
        with conexion:
            crear_esquema_simulacion(conexion)
    finally:
        conexion.close()

    monkeypatch.setenv("POS_V1_SIMULACION", "1")
    antes = base_prueba.read_bytes()
    with TestClient(app) as cliente:
        productos = cliente.get("/pos-api/catalogo/productos").json()["productos"]
        assert [producto["id_producto"] for producto in productos] == [producto_prueba]
    assert base_prueba.read_bytes() == antes
    assert not (base_prueba.parent / "backups").exists()
