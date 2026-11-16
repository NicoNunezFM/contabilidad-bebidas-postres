import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from threading import Event
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

import ajustes_stock
import pos_simulacion
from api import app
from database import obtener_conexion
from pos_pedidos import calcular_pedido_pos
from pos_simulacion import ID_SQLITE_SIMULACION, VentaSimuladaEntrada
from tests.test_pos_pedidos import ORIGEN, pedido_prueba
from tests.test_pos_simulacion import CAJAS, MOVIMIENTOS, VENTAS, _estado, _iniciar_sesion, venta_prueba


CIERRES = "/pos-api/simulacion/cierres"


def pago(receptor, importe, medio="transferencia", referencia=None):
    return {"receptor": receptor, "medio_pago": medio, "importe_centavos": importe, "referencia": referencia}


def solicitud(**datos):
    return {"id_solicitud": str(uuid4()), **datos}


def post(cliente, ruta, datos, estado=200):
    respuesta = cliente.post(ruta, headers=ORIGEN, json=datos)
    assert respuesta.status_code == estado, respuesta.text
    return respuesta.json()


@pytest.fixture
def mixta(venta_prueba):
    cliente, venta = venta_prueba
    venta.pop("medio_pago")
    with closing(obtener_conexion()) as db, db:
        comida = db.execute("""
            INSERT INTO productos (nombre, categoria, precio_venta, stock)
            VALUES ('Comida ficticia', 'Rotisería', 50.25, 2)
        """).lastrowid
    venta["items"].append({"id_producto": comida, "cantidad": 1})
    venta["total_esperado_centavos"] += 5025
    return cliente, venta


def test_combinado_distingue_ingreso_medio_y_receptor_y_liquida_sin_otra_venta(mixta):
    cliente, venta = mixta
    venta["pagos"] = [
        pago("bebidas_postres_efectivo", 1000, "efectivo"),
        pago("comidas_mercado_pago", 10000, "transferencia"),
        pago("comidas_mercado_pago", 17051, "mercado_pago", "mp-ficticio-1"),
    ]
    registrada = post(cliente, VENTAS, venta)
    assert registrada["estado"] == "saldado"
    assert registrada["devengado_centavos"] == {"comidas": 5025, "bebidas_postres": 23026}
    assert registrada["saldo_pendiente_centavos"] == 0
    assert post(cliente, VENTAS, venta) == registrada

    traslado = solicitud(origen="comidas_mercado_pago", destino="bebidas_postres_banco",
                         importe_centavos=22026, motivo="Distribución ficticia")
    post(cliente, CAJAS + "/transferencias", traslado, 403)
    _iniciar_sesion(cliente, "admin", "admin")
    resumen = cliente.get(CAJAS).json()
    assert resumen["secciones"]["bebidas_postres"]["por_distribuir_centavos"] == 22026
    assert resumen["secciones"]["comidas"]["por_distribuir_centavos"] == -22026
    post(cliente, CAJAS + "/transferencias", {**traslado, "importe_centavos": 22027}, 409)
    aplicado = post(cliente, CAJAS + "/transferencias", traslado)
    assert post(cliente, CAJAS + "/transferencias", traslado) == aplicado
    assert all(fila["por_distribuir_centavos"] == 0 for fila in aplicado["secciones"].values())
    assert sum(fila["saldo_centavos"] for fila in aplicado["receptores"]) == 28051
    assert _estado() == (8, 1, 0, 5)
    movimiento = cliente.get(MOVIMIENTOS, params={"caja": "comidas"}).json()["movimientos"][0]
    assert movimiento["tipo"] == "transferencia_interna"
    assert movimiento["importe_centavos"] == -22026
    assert movimiento["id_venta"] is None
    assert movimiento["motivo"] == traslado["motivo"]
    assert movimiento["id_evento"] == aplicado["id_evento"]


def test_fiado_total_parcial_abonos_propietario_y_referencias(mixta):
    cliente, venta = mixta
    venta.update(fiado=True, pagos=[], deudor="  Cliente ficticio  ")
    post(cliente, VENTAS, {**venta, "deudor": "  "}, 422)
    post(cliente, VENTAS, {**venta, "fiado": False, "deudor": None}, 422)
    post(cliente, VENTAS, {**venta, "pagos": [pago("comidas_banco", 28052)]}, 422)
    pendiente = post(cliente, VENTAS, venta)
    assert pendiente["estado"] == "pendiente"
    assert pendiente["deudor"] == "Cliente ficticio"
    assert pendiente["saldo_pendiente_centavos"] == 28051
    assert _estado() == (8, 1, 0, 0)

    ruta = f'{VENTAS}/{pendiente["id_venta"]}/abonos'
    primer_abono = solicitud(pagos=[pago("comidas_banco", 14001, referencia="abono-ficticio")])
    assert cliente.post(ruta, json=primer_abono).status_code == 403
    post(TestClient(app), ruta, primer_abono, 401)
    parcial = post(cliente, ruta, primer_abono)
    assert parcial["estado"] == "parcial"
    assert parcial["cobrado_atribuido_centavos"] == {"comidas": 2508, "bebidas_postres": 11493}
    assert parcial["saldo_pendiente_centavos"] == 14050
    assert post(cliente, ruta, primer_abono) == parcial
    post(cliente, ruta, solicitud(pagos=primer_abono["pagos"]), 409)
    post(cliente, ruta, {**primer_abono, "pagos": [pago("comidas_banco", 500)]}, 409)

    otro = TestClient(app)
    _iniciar_sesion(otro, "otra-operadora", "ventas")
    post(otro, ruta, solicitud(pagos=[pago("bebidas_postres_banco", 14050)]), 404)
    post(cliente, ruta, solicitud(pagos=[pago("bebidas_postres_banco", 14051)]), 409)
    saldo = post(cliente, ruta, solicitud(pagos=[pago("bebidas_postres_banco", 14050)]))
    assert saldo["estado"] == "saldado"
    assert saldo["cobrado_centavos"] == 28051
    historial, = cliente.get(VENTAS).json()["ventas"]
    assert [evento["tipo"] for evento in historial["historial"]] == ["venta", "abono", "abono"]
    assert [len(evento["movimientos"]) for evento in historial["historial"]] == [0, 1, 1]
    assert all(evento["fecha"] for evento in historial["historial"])


def test_devolucion_y_anulacion_posteriores_al_cierre_sin_reescribirlo(mixta):
    cliente, venta = mixta
    venta.update(fiado=True, deudor="FID-123", pagos=[
        pago("comidas_efectivo", 2050, "efectivo"), pago("comidas_banco", 24950),
    ])
    alta = post(cliente, VENTAS, venta)
    assert alta["estado"] == "parcial"
    assert alta["saldo_pendiente_centavos"] == 1051
    devoluciones = f'{VENTAS}/{alta["id_venta"]}/devoluciones'
    anulacion = f'{VENTAS}/{alta["id_venta"]}/anulacion'
    devolver = solicitud(motivo="Comida devuelta", items=[{"linea": 2, "cantidad": 1}])
    post(cliente, devoluciones, devolver, 403)

    _iniciar_sesion(cliente, "admin", "admin")
    cerrar = solicitud(periodo=1, motivo="Cierre ficticio")
    cierre = post(cliente, CIERRES, cerrar)
    assert post(cliente, CIERRES, cerrar) == cierre
    post(cliente, CIERRES, solicitud(periodo=1, motivo="Doble clic distinto"), 409)
    anterior = cliente.get(CIERRES + "/1").json()
    assert anterior["resumen"]["secciones"]["comidas"]["devengado_centavos"] == 5025
    assert anterior["resumen"]["secciones"]["bebidas_postres"]["por_cobrar_centavos"] > 0
    assert cliente.get(CAJAS).json()["periodo_abierto"] == 2

    devuelta = post(cliente, devoluciones, devolver)
    assert devuelta["reembolsado_centavos"] == 3974
    assert devuelta["estado"] == "saldado"
    assert devuelta["devengado_centavos"] == {"comidas": 0, "bebidas_postres": 23026}
    assert post(cliente, devoluciones, devolver) == devuelta
    post(cliente, devoluciones, {**devolver, "id_solicitud": str(uuid4())}, 409)

    anular = solicitud(motivo="Anulación del resto")
    revertida = post(cliente, anulacion, anular)
    assert post(cliente, anulacion, anular) == revertida
    assert revertida["reembolsado_centavos"] == 23026
    assert revertida["saldo_pendiente_centavos"] == 0
    assert revertida["estado"] == "anulada"
    assert cliente.get(CIERRES + "/1").json() == anterior
    venta_actual, = cliente.get(VENTAS).json()["ventas"]
    _, devolucion, anulacion = venta_actual["historial"]
    assert devolucion["periodo"] == anulacion["periodo"] == 2
    assert devolucion["unidades_devueltas"] == [{"linea": 2, "cantidad": 1}]
    assert devolucion["movimientos"][0]["revierte"] == venta_actual["historial"][0]["movimientos"][1]["id_movimiento"]
    assert [(m["receptor"], m["importe_centavos"]) for m in anulacion["movimientos"]] == [
        ("comidas_banco", -20976), ("comidas_efectivo", -2050)]
    with closing(obtener_conexion()) as db:
        ids = [item["id_producto"] for item in venta["items"]]
        assert db.execute("SELECT stock FROM productos WHERE id_producto IN (?, ?) ORDER BY id_producto",
                          ids).fetchall() == [(10,), (2,)]


def test_dos_abonos_concurrentes_no_sobrecobran(venta_prueba):
    cliente, venta = venta_prueba
    venta.pop("medio_pago")
    venta.update(fiado=True, deudor="Cliente de prueba", pagos=[])
    alta = post(cliente, VENTAS, venta)
    ruta = f'{VENTAS}/{alta["id_venta"]}/abonos'

    def abonar(_):
        return cliente.post(ruta, headers=ORIGEN, json=solicitud(pagos=[pago("comidas_banco", 20000)])).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(abonar, range(2))) == [200, 409]
    assert cliente.get(VENTAS).json()["ventas"][0]["saldo_pendiente_centavos"] == 3026


def test_devolucion_total_de_fiado_cancela_deuda_sin_crear_dinero(venta_prueba):
    cliente, venta = venta_prueba
    venta.pop("medio_pago")
    venta.update(fiado=True, deudor="Deudor ficticio", pagos=[])
    alta = post(cliente, VENTAS, venta)
    _iniciar_sesion(cliente, "admin", "admin")
    devuelta = post(cliente, f'{VENTAS}/{alta["id_venta"]}/devoluciones',
                    solicitud(motivo="Pedido devuelto", items=[{"linea": 1, "cantidad": 2}]))
    assert devuelta["estado"] == "devuelta"
    assert devuelta["reembolsado_centavos"] == devuelta["saldo_pendiente_centavos"] == 0
    assert cliente.get(CAJAS).json()["receptores"] == []
    assert _estado() == (10, 1, 0, 0)


@pytest.mark.parametrize("conteo, stock_final", [(False, 11), (True, 3)])
def test_ajuste_y_conteo_leen_stock_despues_de_venta_simulada(venta_prueba, monkeypatch, conteo, stock_final):
    _, venta = venta_prueba
    venta_tiene_bloqueo = Event()
    terminar_venta = Event()
    ajuste_intenta_bloqueo = Event()
    calcular = pos_simulacion.calcular_pedido_pos

    def pausar_venta(db, entrada):
        pedido = calcular(db, entrada)
        venta_tiene_bloqueo.set()
        assert terminar_venta.wait(5)
        return pedido

    def conexion_ajuste():
        db = obtener_conexion()
        db.set_trace_callback(lambda sql: ajuste_intenta_bloqueo.set() if sql == "BEGIN IMMEDIATE" else None)
        return db

    monkeypatch.setattr(pos_simulacion, "calcular_pedido_pos", pausar_venta)
    monkeypatch.setattr(ajustes_stock, "obtener_conexion", conexion_ajuste)
    producto = venta["items"][0]["id_producto"]
    with ThreadPoolExecutor(max_workers=2) as executor:
        venta_futura = executor.submit(pos_simulacion.registrar_venta_simulada,
                                      VentaSimuladaEntrada.model_validate(venta), {"id_usuario": 1})
        try:
            assert venta_tiene_bloqueo.wait(5)
            ajuste_futuro = (executor.submit(ajustes_stock.registrar_inventario_fisico, producto, 3) if conteo
                             else executor.submit(ajustes_stock.registrar_ajuste_stock, producto, 3, "Ajuste ficticio"))
            assert ajuste_intenta_bloqueo.wait(5)
        finally:
            terminar_venta.set()
        assert venta_futura.result()["estado"] == "saldado"
        ajuste = ajuste_futuro.result()
    assert (ajuste["stock_anterior"], ajuste["stock_nuevo"]) == (8, stock_final)
    assert _estado()[0] == stock_final


def test_migra_historial_v3_sin_volver_a_aplicar_stock(pedido_prueba, monkeypatch, tmp_path):
    cliente, linea = pedido_prueba
    venta = solicitud(total_esperado_centavos=23026, medio_pago="efectivo", items=[linea])
    entrada = VentaSimuladaEntrada.model_validate(venta)
    with closing(obtener_conexion()) as db, db:
        pedido = calcular_pedido_pos(db, entrada)
        pedido.update(cajas_centavos={"bebidas_postres": 23026}, medio_pago="efectivo")
        db.execute(f"PRAGMA application_id = {ID_SQLITE_SIMULACION}")
        db.execute("PRAGMA user_version = 3")
        db.execute("""
            CREATE TABLE pos_ventas_simuladas (
               id_venta INTEGER PRIMARY KEY, id_usuario, id_solicitud, solicitud, fecha, pedido
            )
        """)
        db.execute("CREATE TABLE pos_anulaciones_simuladas (id_venta, id_usuario, fecha, motivo)")
        db.execute("CREATE TABLE pos_movimientos_simulados (id_venta, caja, medio_pago, tipo, importe_centavos)")
        db.execute("INSERT INTO pos_ventas_simuladas VALUES (1, 1, ?, ?, '2026-01-01', ?)",
                   (venta["id_solicitud"], entrada.model_dump_json(exclude={"id_solicitud", "pagos", "fiado", "deudor"}),
                    json.dumps(pedido)))
        db.execute("INSERT INTO pos_anulaciones_simuladas VALUES (1, 1, '2026-01-02', 'Histórico ficticio')")
        db.execute("INSERT INTO pos_movimientos_simulados VALUES (1, 'bebidas_postres', 'efectivo', 'venta', 23026)")
        db.execute("INSERT INTO pos_movimientos_simulados VALUES (1, 'bebidas_postres', 'efectivo', 'anulacion', -23026)")
    origen = Path(os.environ["NEGOCIO_DB_PATH"])
    antes = origen.read_bytes()
    destino = tmp_path / "copia.db"
    preparar = Path(__file__).resolve().parents[1] / "scripts" / "preparar_simulacion_pos.py"
    copia = subprocess.run([sys.executable, str(preparar), str(destino), "--desde-pos3", str(origen)],
                         capture_output=True)
    assert copia.returncode == 0, copia.stderr
    assert origen.read_bytes() == antes
    monkeypatch.setenv("NEGOCIO_DB_PATH", str(destino))
    monkeypatch.setenv("POS_V1_SIMULACION", "1")
    historial, = cliente.get(VENTAS).json()["ventas"]
    assert historial["estado"] == "anulada"
    assert [evento["fecha"] for evento in historial["historial"]] == ["2026-01-01", "2026-01-02"]
    assert post(cliente, VENTAS, venta)["id_venta"] == 1
    assert _estado() == (10, 1, 0, 2)
