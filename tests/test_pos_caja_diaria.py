from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from threading import Barrier

import pytest
from fastapi.testclient import TestClient

import pos_caja_diaria
from api import app
from database import obtener_conexion
from scripts.puente_pos_ficticio import copiar_ficticia, verificar_ficticia
from tests import cliente_contabilidad
from tests.test_pos_cobros import CIERRES, mixta, pago, post, solicitud
from tests.test_pos_pedidos import ORIGEN, pedido_prueba
from tests.test_pos_simulacion import CAJAS, VENTAS, _iniciar_sesion, venta_prueba


RUTA = "/pos-api/simulacion/caja-diaria"
FECHA = "2026-11-17"
COMIDAS = "comidas"
BEBIDAS = "bebidas_postres"


@pytest.fixture
def diaria(mixta, base_prueba, monkeypatch):
    ventas, venta = mixta
    # Conservamos una venta y un corte previos en una copia real de etapa 5.
    previo = {**venta, "pagos": [pago("comidas_efectivo", 28051, "efectivo")]}
    post(ventas, VENTAS, previo)
    admin = TestClient(app)
    _iniciar_sesion(admin, "admin", "admin")
    corte = post(admin, CIERRES, solicitud(periodo=1, motivo="Corte previo"))
    etapa5 = base_prueba.with_name("pos5-ficticio.db")
    copiar_ficticia(base_prueba, etapa5)
    contenido = etapa5.read_bytes()
    destino = base_prueba.with_name("pos6-ficticio.db")
    copiar_ficticia(etapa5, destino, caja_diaria=True)
    assert etapa5.read_bytes() == contenido
    monkeypatch.setenv("NEGOCIO_DB_PATH", str(destino))
    monkeypatch.setenv("ABADION_PUENTE_FICTICIO", "1")
    monkeypatch.setattr(pos_caja_diaria, "ahora_local", lambda: FECHA + "T22:33:59.123456-03:00")
    venta = {**venta, **solicitud(), "pagos": [
        pago("comidas_efectivo", 10000, "efectivo"), pago("bebidas_postres_banco", 10000),
    ], "fiado": True, "deudor": "Fiado ficticio"}
    return ventas, admin, venta, corte, destino


def estado(cliente, caja):
    respuesta = cliente.get(RUTA)
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.headers["Cache-Control"] == "no-store"
    return respuesta.json()["cajas"][caja]


def operar(cliente, caja, accion, status=200, **datos):
    return post(cliente, f"{RUTA}/{caja}/{accion}", solicitud(**datos), status)


def abrir(cliente, caja, importe=1000):
    return operar(cliente, caja, "apertura", fecha=FECHA, inicial_centavos=importe)["id_jornada"]


def arquear(cliente, caja, importe, **datos):
    actual = estado(cliente, caja)
    return operar(cliente, caja, "arqueo", id_jornada=actual["id_jornada"],
                  revision_efectivo=actual["revision_efectivo"], contado_centavos=importe, **datos)


def test_caja_receptora_pagos_fiados_traslados_gastos_y_puente(diaria):
    ventas, admin, venta, corte, destino = diaria
    sin_sesion = TestClient(app)
    assert sin_sesion.get(RUTA).status_code == 401
    assert sin_sesion.post(f"{RUTA}/{COMIDAS}/apertura", json={}).status_code == 403
    assert estado(ventas, COMIDAS) is None
    post(ventas, VENTAS, venta, 409)

    comidas = abrir(ventas, COMIDAS)
    registrada = post(ventas, VENTAS, venta)
    assert registrada["saldo_pendiente_centavos"] == 8051
    assert estado(ventas, COMIDAS)["esperado_centavos"] == 11000
    assert estado(ventas, BEBIDAS) is None

    ruta_traslado = CAJAS + "/transferencias"
    traslado = solicitud(origen="comidas_efectivo", destino="bebidas_postres_efectivo",
                         importe_centavos=1000, motivo="Distribución de prueba")
    post(admin, ruta_traslado, traslado, 409)
    assert estado(ventas, COMIDAS)["esperado_centavos"] == 11000
    bebidas = abrir(ventas, BEBIDAS, 0)
    post(admin, ruta_traslado, {**traslado, "destino": "bebidas_postres_banco"}, 422)
    aplicado = post(admin, ruta_traslado, traslado)
    assert post(admin, ruta_traslado, traslado) == aplicado
    assert estado(ventas, BEBIDAS)["esperado_centavos"] == 1000

    ruta_venta = f"{VENTAS}/{registrada['id_venta']}"
    post(ventas, ruta_venta + "/abonos", solicitud(pagos=[pago("bebidas_postres_efectivo", 500, "efectivo")]))
    post(admin, ruta_venta + "/devoluciones", solicitud(motivo="Devolución ficticia",
         items=[{"linea": 1, "cantidad": 2}]))
    operar(ventas, COMIDAS, "movimientos", 403, id_jornada=comidas, tipo="gasto",
           importe_centavos=200, motivo="Pago físico")
    operar(admin, COMIDAS, "movimientos", id_jornada=comidas, tipo="gasto",
           importe_centavos=200, motivo="Pago físico")
    operar(admin, BEBIDAS, "movimientos", id_jornada=bebidas, tipo="aporte",
           importe_centavos=250, motivo="Fondo extra")
    operar(admin, BEBIDAS, "movimientos", id_jornada=bebidas, tipo="retiro",
           importe_centavos=50, motivo="Retiro de prueba")
    legado = cliente_contabilidad(app)
    assert legado.post("/gastos", json={"categoria": "Servicios", "descripcion": "Sin medio",
                                       "valor": 500, "seccion": COMIDAS}).status_code == 201

    saldo_comidas = estado(ventas, COMIDAS)
    assert saldo_comidas["movimientos_centavos"] == {
        "apertura": 1000, "cobro": 10000, "transferencia": -1000, "reembolso": -4975, "gasto": -200,
    }
    assert saldo_comidas["esperado_centavos"] == 4825
    assert estado(ventas, BEBIDAS)["movimientos_centavos"] == {
        "apertura": 0, "transferencia": 1000, "cobro": 500, "reembolso": -500, "aporte": 250, "retiro": -50,
    }
    arqueo = arquear(ventas, COMIDAS, 5025, motivo="Sobrante pendiente de investigar")
    assert arqueo["diferencia_centavos"] == 200
    operar(admin, COMIDAS, "cierre", id_jornada=comidas, id_arqueo=arqueo["id_evento"])
    informe = verificar_ficticia(destino)
    assert admin.get("/pos-api/simulacion/conciliacion").json() == informe
    assert informe["cuadrado"]
    assert informe["caja_diaria_centavos"]["cajas"][COMIDAS]["cerrada"]
    assert not informe["caja_diaria_centavos"]["cajas"][BEBIDAS]["cerrada"]
    assert admin.get(CIERRES + "/1").json()["resumen"] == corte["resumen"]
    assert len(admin.get(VENTAS).json()["ventas"]) == 2
    with closing(obtener_conexion()) as db, db:
        db.execute("UPDATE pos_diario_caja SET importe_centavos = 0 WHERE id_movimiento_pos IS NOT NULL")
    assert "MOVIMIENTO_FISICO_SIN_CONCILIAR" in {
        diferencia["codigo"] for diferencia in verificar_ficticia(destino)["diferencias"]
    }


def test_arqueo_vigente_autorizacion_reintento_y_auditoria(diaria, monkeypatch):
    ventas, admin, venta, _, _ = diaria
    jornada = abrir(ventas, COMIDAS)
    operar(ventas, COMIDAS, "apertura", 409, fecha=FECHA, inicial_centavos=0)
    entero = arquear(ventas, COMIDAS, 1000)
    operar(admin, COMIDAS, "movimientos", id_jornada=jornada, tipo="aporte",
           importe_centavos=200, motivo="Cambio")
    operar(admin, COMIDAS, "movimientos", id_jornada=jornada, tipo="retiro",
           importe_centavos=200, motivo="Devolución de cambio")
    operar(ventas, COMIDAS, "cierre", 409, id_jornada=jornada, id_arqueo=entero["id_evento"])
    arquear(ventas, COMIDAS, 999, status=422)
    conteo = arquear(ventas, COMIDAS, 999, motivo="Faltó un centavo")
    cierre = solicitud(id_jornada=jornada, id_arqueo=conteo["id_evento"])
    ruta = f"{RUTA}/{COMIDAS}/cierre"
    post(ventas, ruta, cierre, 403)
    confirmado = post(admin, ruta, cierre)
    assert confirmado["autorizado_por"] != confirmado["arqueo"]["id_usuario"]
    assert confirmado["arqueo"]["usuario"] == "cajero"
    assert confirmado["arqueo"]["motivo"] == "Faltó un centavo"
    assert confirmado["arqueo"]["resultado"]["diferencia_centavos"] == -1
    assert post(admin, ruta, cierre) == confirmado
    post(admin, ruta, {**cierre, "id_arqueo": entero["id_evento"]}, 409)
    post(admin, ruta, {**cierre, **solicitud()}, 409)
    post(ventas, VENTAS, venta, 409)

    manana = "2026-11-18"
    monkeypatch.setattr(pos_caja_diaria, "ahora_local", lambda: manana + "T08:00:00-03:00")
    operar(ventas, COMIDAS, "apertura", 409, fecha=FECHA, inicial_centavos=0)
    operar(ventas, COMIDAS, "apertura", fecha=manana, inicial_centavos=0)
    assert post(admin, ruta, cierre) == confirmado
    historial = f"{RUTA}/{COMIDAS}/historial"
    primera = ventas.get(historial, params={"limite": 1}).json()
    assert primera["jornadas"][0]["fecha"] == manana
    pasada = ventas.get(historial, params={"antes_de": primera["siguiente_antes_de"]}).json()["jornadas"][0]
    assert pasada["cierre"]["usuario"] == "admin"
    assert pasada["cierre"]["id_usuario"] == confirmado["autorizado_por"]
    assert pasada["cierre"]["fecha_hora"].endswith("-03:00")
    eventos = ventas.get(f"{historial}/{jornada}").json()["eventos"]
    assert [evento["tipo"] for evento in eventos] == ["cierre", "arqueo", "retiro", "aporte", "arqueo", "apertura"]


def test_cierre_concurrente_con_cobro(diaria):
    ventas, _, venta, _, _ = diaria
    jornada = abrir(ventas, COMIDAS)
    arqueo = arquear(ventas, COMIDAS, 1000)
    cierre = solicitud(id_jornada=jornada, id_arqueo=arqueo["id_evento"])
    barrera = Barrier(2, timeout=5)

    def enviar(ruta, datos):
        cliente = TestClient(app, cookies=dict(ventas.cookies))
        barrera.wait()
        return cliente.post(ruta, headers=ORIGEN, json=datos).status_code

    with ThreadPoolExecutor(max_workers=2) as ejecutor:
        cobro = ejecutor.submit(enviar, VENTAS, venta)
        cerrar = ejecutor.submit(enviar, f"{RUTA}/{COMIDAS}/cierre", cierre)
        cobro_estado, cierre_estado = cobro.result(timeout=10), cerrar.result(timeout=10)
    assert sorted([cobro_estado, cierre_estado]) == [200, 409]
    actual = estado(ventas, COMIDAS)
    assert actual["cerrada"] == (cierre_estado == 200)
    assert actual["esperado_centavos"] == (11000 if cobro_estado == 200 else 1000)


def test_caja_diaria_solo_en_copia_marcada_y_cobro_digital_sin_apertura(diaria, monkeypatch, base_prueba):
    ventas, _, venta, _, destino = diaria
    monkeypatch.setenv("NEGOCIO_DB_PATH", str(base_prueba))
    assert ventas.get(RUTA).status_code == 404
    monkeypatch.setenv("NEGOCIO_DB_PATH", str(destino))
    venta["pagos"] = [pago("comidas_banco", 15000), pago("bebidas_postres_banco", 5000)]
    registrada = post(ventas, VENTAS, venta)
    assert registrada["saldo_pendiente_centavos"] == 8051
    assert estado(ventas, COMIDAS) is None
    assert estado(ventas, BEBIDAS) is None
    monkeypatch.delenv("POS_V1_SIMULACION")
    assert ventas.get(RUTA).status_code == 404


def test_jornada_vencida_permite_cerrar_y_exige_apertura_de_hoy(diaria, monkeypatch):
    ventas, _, venta, _, _ = diaria
    jornada = abrir(ventas, COMIDAS, 0)
    manana = "2026-11-18"
    monkeypatch.setattr(pos_caja_diaria, "ahora_local", lambda: manana + "T00:01:00-03:00")
    post(ventas, VENTAS, venta, 409)
    operar(ventas, COMIDAS, "apertura", 409, fecha=manana, inicial_centavos=0)
    arqueo = arquear(ventas, COMIDAS, 0)
    datos = solicitud(id_jornada=jornada, id_arqueo=arqueo["id_evento"])
    ruta = f"{RUTA}/{COMIDAS}/cierre"
    with ThreadPoolExecutor(max_workers=2) as ejecutor:
        llamadas = [
            ejecutor.submit(post, TestClient(app, cookies=dict(ventas.cookies)), ruta, datos)
            for _ in range(2)
        ]
        resultados = [llamada.result(timeout=10) for llamada in llamadas]
    assert resultados[0] == resultados[1]
    assert resultados[0]["fecha_hora"].startswith(manana)
    assert estado(ventas, COMIDAS) is None
    assert operar(ventas, COMIDAS, "apertura", fecha=manana, inicial_centavos=0)["id_jornada"] != jornada
    post(ventas, VENTAS, venta)
