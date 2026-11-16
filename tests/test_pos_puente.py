import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from threading import Barrier, Event

import pytest
from fastapi.testclient import TestClient

import pos_puente
from api import app
from database import obtener_conexion
from scripts.puente_pos_ficticio import copiar_ficticia, verificar_ficticia
from tests import TOKEN_BOT_FICTICIO, cliente_contabilidad
from tests.test_pos_cobros import CIERRES, mixta, pago, post, solicitud
from tests.test_pos_pedidos import ORIGEN, pedido_prueba
from tests.test_pos_simulacion import CAJAS, VENTAS, _iniciar_sesion, venta_prueba


PUENTE = "/pos-api/simulacion/conciliacion"
BOT = {"Authorization": f"Bearer {TOKEN_BOT_FICTICIO}"}


def bot(cliente, mensaje, id_mensaje="mensaje-ficticio"):
    return cliente.post("/comandos", headers=BOT, json={
        "mensaje": mensaje, "canal": "whatsapp", "id_mensaje": id_mensaje,
    })


@pytest.fixture
def puente(mixta, base_prueba, monkeypatch):
    cliente, venta = mixta
    copia = base_prueba.with_name("pos5-ficticio.db")
    copiar_ficticia(base_prueba, copia)
    monkeypatch.setenv("NEGOCIO_DB_PATH", str(copia))
    monkeypatch.setenv("ABADION_PUENTE_FICTICIO", "1")
    return cliente, venta, copia


def test_copia_con_historial_verifica_y_conserva_original(mixta, base_prueba):
    cliente, venta = mixta
    venta.update(fiado=True, pagos=[], deudor="Ficticia 1")
    post(cliente, VENTAS, venta)
    _iniciar_sesion(cliente, "admin", "admin")
    post(cliente, CIERRES, solicitud(periodo=1, motivo="Corte anterior a la copia"))

    contenido = base_prueba.read_bytes()
    destino = base_prueba.with_name("ensayo.db")
    copiar_ficticia(base_prueba, destino)
    informe = verificar_ficticia(destino)
    assert informe["cuadrado"]
    assert informe["pos_centavos"]["periodo_abierto"] == 2
    assert informe["pos_centavos"]["secciones"]["comidas"]["por_cobrar_centavos"] == 5025
    with pytest.raises(FileExistsError):
        copiar_ficticia(base_prueba, destino)
    assert base_prueba.read_bytes() == contenido
    with closing(sqlite3.connect(destino)) as db:
        productos = [item["id_producto"] for item in venta["items"]]
        assert db.execute("""
            SELECT stock FROM productos WHERE id_producto IN (?, ?) ORDER BY id_producto
        """, productos).fetchall() == [(8,), (1,)]


def test_puente_exige_modo_marca_y_autorizacion(puente, base_prueba, monkeypatch):
    cliente, _, _ = puente
    sin_sesion = TestClient(app)
    assert sin_sesion.get(PUENTE).status_code == 401
    assert sin_sesion.get(PUENTE, headers=BOT).status_code == 401
    assert sin_sesion.post("/comandos", json={"mensaje": "conciliacion pos"}).status_code == 401
    assert cliente.get(PUENTE).status_code == 403
    _iniciar_sesion(cliente, "admin", "admin")
    assert cliente.get(PUENTE).headers["Cache-Control"] == "no-store"

    monkeypatch.delenv("POS_V1_SIMULACION")
    assert bot(sin_sesion, "conciliacion pos").status_code == 404
    with pytest.raises(RuntimeError):
        with TestClient(app):
            pass
    monkeypatch.setenv("POS_V1_SIMULACION", "1")
    monkeypatch.setenv("NEGOCIO_DB_PATH", str(base_prueba))
    assert bot(sin_sesion, "conciliacion pos").status_code == 404
    monkeypatch.delenv("ABADION_PUENTE_FICTICIO")
    assert bot(sin_sesion, "conciliacion pos").status_code == 404
    with pytest.raises(ValueError, match="ficticio"):
        copiar_ficticia(Path("negocio.db"), base_prueba.with_name("prohibido.db"))


def test_reconcilia_pagos_abono_reembolso_cierre_y_comandos_legados(puente):
    cliente, venta, copia = puente
    cliente_legado = cliente_contabilidad(app)
    producto = venta["items"][0]["id_producto"]
    compra = {"id_producto": producto, "cantidad": 1, "precio_unitario": 3}
    gasto = {"categoria": "Servicios", "descripcion": "Gasto ficticio", "valor": 2, "seccion": "comidas"}
    assert cliente_legado.post("/compras", json=compra).status_code == 201
    assert cliente_legado.post("/gastos", json=gasto).status_code == 201
    assert cliente_legado.post("/ventas", json={**compra, "precio_unitario": 11}).status_code == 201
    assert cliente_legado.post("/cierres/semanales", json={
        "fecha_desde": "2025-01-06", "fecha_hasta": "2025-01-12",
    }).status_code == 201
    base_legada = cliente_legado.get("/caja").json()
    assert (base_legada["ventas"], base_legada["compras"], base_legada["gastos"]) == (11, 3, 2)

    venta.update(fiado=True, deudor="Deudora ficticia", pagos=[
        pago("comidas_efectivo", 1000, "efectivo"),
        pago("comidas_banco", 13000, referencia="transferencia-ficticia"),
    ])
    alta = post(cliente, VENTAS, venta)
    assert post(cliente, VENTAS, venta) == alta
    _iniciar_sesion(cliente, "admin", "admin")
    transferir = solicitud(origen="comidas_banco", destino="bebidas_postres_banco",
                            importe_centavos=5000, motivo="Distribución ficticia")
    post(cliente, CAJAS + "/transferencias", transferir)
    cierre = post(cliente, CIERRES, solicitud(periodo=1, motivo="Corte ficticio"))
    ruta = f'{VENTAS}/{alta["id_venta"]}'
    post(cliente, ruta + "/abonos", solicitud(pagos=[pago("bebidas_postres_mercado_pago", 14051, "mercado_pago")]))
    post(cliente, ruta + "/devoluciones", solicitud(motivo="Devolución ficticia", items=[
        {"linea": 2, "cantidad": 1},
    ]))
    with closing(obtener_conexion()) as db, db:
        db.execute("UPDATE productos SET categoria = 'Comidas', precio_venta = 1 WHERE id_producto = ?", (producto,))

    informe = cliente.get(PUENTE).json()
    assert informe == verificar_ficticia(copia)
    assert informe["cuadrado"]
    assert informe["legado_pesos"]["caja_general"] == base_legada
    assert informe["legado_pesos"]["secciones"]["comidas"]["gastos_seccion"] == 2
    assert informe["legado_pesos"]["cierres_semanales"] == 1
    assert informe["pos_centavos"]["secciones"]["bebidas_postres"]["devengado_centavos"] == 23026
    receptores = {fila["receptor"]: fila for fila in informe["pos_centavos"]["receptores"]}
    assert receptores["bebidas_postres_mercado_pago"]["recibido_neto_centavos"] == 9026
    assert cliente.get(CIERRES + "/1").json()["resumen"] == cierre["resumen"]

    with closing(obtener_conexion()) as db:
        cambios = "\n".join(db.iterdump())
    respuesta = bot(cliente, "Conciliación POS")
    assert respuesta.status_code == 200
    assert "Bebidas y Postres · venta $230,26" in respuesta.json()["respuesta"]
    assert "Deudora ficticia" not in respuesta.text
    assert bot(cliente, "conciliacion pos").json() == respuesta.json()
    with closing(obtener_conexion()) as db:
        assert "\n".join(db.iterdump()) == cambios
    assert bot(cliente, "caja", "caja-ficticia").status_code == 200


def test_conciliacion_detecta_una_diferencia_sin_reparar_el_libro(puente):
    cliente, venta, copia = puente
    venta["pagos"] = [pago("comidas_banco", 28051)]
    alta = post(cliente, VENTAS, venta)
    _iniciar_sesion(cliente, "admin", "admin")
    post(cliente, CIERRES, solicitud(periodo=1, motivo="Corte ficticio"))
    with closing(obtener_conexion()) as db, db:
        db.execute("UPDATE pos_eventos_simulados SET devengado_comidas = 0 WHERE tipo = 'venta'")

    informe = verificar_ficticia(copia)
    assert informe["cuadrado"] is False
    assert informe["diferencias"] == [
        {"codigo": "VENTA_POS_DESCUADRADA", "id_venta": alta["id_venta"]},
        {"codigo": "CIERRE_POS_DESCUADRADO", "periodo": 1},
    ]
    assert "con diferencias" in bot(cliente, "conciliacion pos").json()["respuesta"]


def test_stock_compartido_serializa_venta_pos_y_bot(puente):
    cliente, venta, _ = puente
    venta["pagos"] = [pago("comidas_banco", 28051)]
    producto = venta["items"][0]["id_producto"]
    with closing(obtener_conexion()) as db, db:
        db.execute("UPDATE productos SET nombre = 'Pepsi', stock = 2 WHERE id_producto = ?", (producto,))
    inicio = Barrier(2, timeout=5)

    def vender_pos():
        inicio.wait()
        return cliente.post(VENTAS, headers=ORIGEN, json=venta)

    def vender_bot():
        inicio.wait()
        return bot(TestClient(app), "venta 2 pepsi")

    with ThreadPoolExecutor(max_workers=2) as pool:
        pos = pool.submit(vender_pos)
        legado = pool.submit(vender_bot)
        respuestas = [r.result(timeout=10) for r in (pos, legado)]

    assert sum(respuesta.json().get("ok") is True for respuesta in respuestas) == 1
    with closing(obtener_conexion()) as db:
        assert db.execute("SELECT stock FROM productos WHERE id_producto = ?", (producto,)).fetchone()[0] == 0
        assert db.execute("""
            SELECT (SELECT COUNT(*) FROM ventas) + (SELECT COUNT(*) FROM pos_ventas_simuladas)
        """).fetchone()[0] == 1


def test_lectura_usa_el_mismo_corte_con_escrituras_concurrentes(puente, monkeypatch):
    cliente, venta, _ = puente
    _iniciar_sesion(cliente, "admin", "admin")
    with closing(obtener_conexion()) as db:
        db.execute("PRAGMA journal_mode = WAL")
    leyendo = Event()
    confirmar = Event()
    obtener_estado = pos_puente.obtener_estado_caja

    def esperar_escrituras(*, conexion):
        leyendo.set()
        assert confirmar.wait(10)
        return obtener_estado(conexion=conexion)

    monkeypatch.setattr(pos_puente, "obtener_estado_caja", esperar_escrituras)
    with ThreadPoolExecutor(max_workers=1) as pool:
        primera = pool.submit(cliente.get, PUENTE)
        assert leyendo.wait(10)
        try:
            venta.update(pagos=[pago("comidas_banco", 28051)])
            post(cliente, VENTAS, venta)
            assert cliente_contabilidad(app).post("/ventas", json={
                "id_producto": venta["items"][0]["id_producto"], "cantidad": 1, "precio_unitario": 5,
            }).status_code == 201
        finally:
            confirmar.set()
        anterior = primera.result(timeout=10).json()

    posterior = cliente.get(PUENTE).json()
    assert anterior["legado_pesos"]["caja_general"]["ventas"] == 0
    assert anterior["pos_centavos"]["secciones"]["comidas"]["devengado_centavos"] == 0
    assert posterior["legado_pesos"]["caja_general"]["ventas"] == 5
    assert posterior["pos_centavos"]["secciones"]["comidas"]["devengado_centavos"] == 5025
