from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import date, timedelta
from threading import Barrier

import pytest
from fastapi.testclient import TestClient

from api import app
from database import obtener_conexion
from pos_contabilidad import fecha_local
from scripts.puente_pos_ficticio import copiar_ficticia, verificar_ficticia
from tests import cliente_contabilidad
from tests.test_pos_caja_diaria import COMIDAS, BEBIDAS, arquear, estado, operar
from tests.test_pos_cobros import mixta, pago, post, solicitud
from tests.test_pos_puente import bot
from tests.test_pos_pedidos import pedido_prueba
from tests.test_pos_simulacion import CAJAS, VENTAS, _iniciar_sesion, venta_prueba


INFORME = "/pos-api/simulacion/contabilidad"
SEMANAL = "/cierres/semanales"


@pytest.fixture
def integrada(mixta, base_prueba, monkeypatch):
    ventas, venta = mixta
    legado = cliente_contabilidad(app)
    producto = venta["items"][0]["id_producto"]
    assert legado.post("/ventas", json={"id_producto": producto, "cantidad": 1, "precio_unitario": 800}).status_code == 201
    historico = legado.post(SEMANAL, json={"fecha_desde": "2025-01-06", "fecha_hasta": "2025-01-12"}).json()
    etapa6 = base_prueba.with_name("pos6-integrada.db")
    copiar_ficticia(base_prueba, etapa6, caja_diaria=True)
    original = etapa6.read_bytes()
    destino = base_prueba.with_name("pos7-integrada.db")
    copiar_ficticia(etapa6, destino, contabilidad=True)
    assert etapa6.read_bytes() == original
    monkeypatch.setenv("NEGOCIO_DB_PATH", str(destino))
    monkeypatch.setenv("ABADION_PUENTE_FICTICIO", "1")
    admin = TestClient(app)
    _iniciar_sesion(admin, "admin", "admin")
    return ventas, admin, legado, venta, destino, historico


def informe(admin):
    respuesta = admin.get(INFORME)
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.headers["Cache-Control"] == "no-store"
    return respuesta.json()


def test_libro_unificado_combinado_stock_y_bot(integrada, monkeypatch):
    ventas, admin, legado, venta, destino, historico = integrada
    assert TestClient(app).get(INFORME).status_code == 401
    assert ventas.get(INFORME).status_code == 403
    monkeypatch.delenv("ABADION_PUENTE_FICTICIO")
    assert admin.get(INFORME).status_code == 404
    monkeypatch.setenv("ABADION_PUENTE_FICTICIO", "1")
    assert admin.get(INFORME, params={"desde": "2040-01-02", "hasta": "2040-01-01"}).status_code == 422

    producto = venta["items"][0]["id_producto"]
    datos_legado = {"id_producto": producto, "cantidad": 1, "precio_unitario": 3}
    assert legado.post("/ventas", json=datos_legado).json()["codigo"] == "VENTAS_SOLO_POS"
    assert legado.post("/compras", json=datos_legado).status_code == 201
    with closing(obtener_conexion()) as db:
        stock = db.execute("SELECT stock FROM productos WHERE id_producto = ?", (producto,)).fetchone()[0]

    jornadas = {
        caja: operar(ventas, caja, "apertura", fecha=fecha_local(), inicial_centavos=1000)["id_jornada"]
        for caja in (COMIDAS, BEBIDAS)
    }
    venta.update(fiado=True, deudor="Cliente ficticio", pagos=[
        pago("comidas_efectivo", 10000, "efectivo"),
        pago("bebidas_postres_mercado_pago", 8000, "mercado_pago"),
    ])
    alta = post(ventas, VENTAS, venta)
    assert post(ventas, VENTAS, venta) == alta
    assert alta["saldo_pendiente_centavos"] == 10051
    with closing(obtener_conexion()) as db:
        assert db.execute("SELECT COUNT(*) FROM ventas").fetchone() == (1,)
        assert db.execute("SELECT COUNT(*) FROM pos_ventas_simuladas").fetchone() == (1,)
        cantidad = venta["items"][0]["cantidad"]
        assert db.execute("SELECT stock FROM productos WHERE id_producto = ?", (producto,)).fetchone() == (stock - cantidad,)

    traslado = solicitud(origen="comidas_efectivo", destino="bebidas_postres_efectivo",
                         importe_centavos=1000, motivo="Distribución ficticia")
    post(admin, CAJAS + "/transferencias", traslado)
    gasto = solicitud(id_jornada=jornadas[COMIDAS], tipo="gasto", importe_centavos=200, motivo="Pago físico")
    ruta_gasto = "/pos-api/simulacion/caja-diaria/comidas/movimientos"
    assert post(admin, ruta_gasto, gasto) == post(admin, ruta_gasto, gasto)
    mensaje = "gasto servicios telefonia 4.25"
    respuesta = bot(TestClient(app), mensaje, "gasto-unico-ficticio")
    assert respuesta.status_code == 200, respuesta.text
    repetido = bot(TestClient(app), mensaje, "gasto-unico-ficticio").json()
    assert repetido == {**respuesta.json(), "repetido": True}
    resultado = informe(admin)
    assert resultado["devengado_centavos"] == 28051
    assert resultado["cobrado_neto_centavos"] == 18000
    assert resultado["fiado_al_cierre_centavos"] == 10051
    assert resultado["compras_centavos"] == 300
    assert resultado["gastos_con_receptor_centavos"] == 200
    assert resultado["gastos_sin_receptor_centavos"] == 425
    assert resultado["resultado_base_diezmo_centavos"] == 17075
    assert resultado["diezmo_centavos"] == 1708
    assert {caja: valores["cobrado_atribuido_centavos"]
            for caja, valores in resultado["secciones"].items()} == {
        COMIDAS: 3224, BEBIDAS: 14776,
    }
    assert estado(ventas, COMIDAS)["esperado_centavos"] == 9800
    assert estado(ventas, BEBIDAS)["esperado_centavos"] == 2000
    assert legado.get("/caja").json()["caja_diaria_centavos"]["cajas"][COMIDAS]["esperado_centavos"] == 9800
    assert legado.get("/reportes/hoy").json()["contabilidad_centavos"]["diezmo_centavos"] == 1708
    hoy = date.fromisoformat(fecha_local())
    assert legado.get(f"/diezmo/{hoy.year}/{hoy.month}").json()["diezmo_estimado"] == 17.08
    assert "Cobros netos" in bot(TestClient(app), "resumen hoy").json()["respuesta"]
    assert "Caja diaria ficticia" in bot(TestClient(app), "caja", "consulta-caja").json()["respuesta"]
    assert verificar_ficticia(destino)["cuadrado"]
    assert legado.get(SEMANAL).json()["cierres"][0]["id_cierre"] == historico["id_cierre"]
    assert "contabilidad_centavos" not in legado.get(SEMANAL).json()["cierres"][0]


def test_cierres_congelados_y_cobros_en_el_periodo_del_pago(integrada):
    ventas, admin, legado, venta, _, _ = integrada
    hoy = date.fromisoformat(fecha_local())
    pasado = (hoy.replace(day=1) - timedelta(days=1)).isoformat()
    jornada = operar(ventas, COMIDAS, "apertura", fecha=hoy.isoformat(), inicial_centavos=0)
    venta.update(pagos=[], fiado=True, deudor="Cliente de prueba")
    alta = post(ventas, VENTAS, venta)
    ruta = f"{VENTAS}/{alta['id_venta']}"
    assert informe(admin)["diezmo_centavos"] == 0
    gasto = legado.post("/gastos", json={"categoria": "Servicios", "descripcion": "Prueba", "valor": 3}).json()
    # Llevamos las altas ficticias a un mes terminado para probar cortes y ajustes posteriores.
    with closing(obtener_conexion()) as db, db:
        db.execute("UPDATE pos_inicio_contable SET fecha = ?", (pasado,))
        db.execute("UPDATE pos_eventos_simulados SET fecha = ?", (pasado + " 15:00:00",))
        db.execute("UPDATE pos_costos_contables SET fecha = ?", (pasado,))
        db.execute("UPDATE pos_jornadas_caja SET fecha = ?", (pasado,))
    periodo = {"fecha_desde": pasado, "fecha_hasta": pasado}
    assert legado.post(SEMANAL, json=periodo).status_code == 409
    conteo = arquear(ventas, COMIDAS, 0)
    cierre_diario = operar(ventas, COMIDAS, "cierre", id_jornada=jornada["id_jornada"], id_arqueo=conteo["id_evento"])

    barrera = Barrier(2)

    def cerrar():
        barrera.wait()
        return legado.post(SEMANAL, json=periodo)

    with ThreadPoolExecutor(max_workers=2) as grupo:
        respuestas = list(grupo.map(lambda _: cerrar(), range(2)))
    assert sorted(r.status_code for r in respuestas) == [201, 409]
    semanal = next(r.json() for r in respuestas if r.status_code == 201)
    solapado = {"fecha_desde": (date.fromisoformat(pasado) - timedelta(days=1)).isoformat(),
                 "fecha_hasta": pasado}
    assert legado.post(SEMANAL, json=solapado).status_code == 409
    en_curso = {"fecha_desde": pasado, "fecha_hasta": hoy.isoformat()}
    assert legado.post(SEMANAL, json=en_curso).status_code == 409
    assert legado.post("/cierres/mensuales", json={"anio": hoy.year, "mes": hoy.month}).status_code == 409
    detalle = semanal["contabilidad_centavos"]
    assert detalle["devengado_centavos"] == 28051
    assert detalle["cobrado_neto_centavos"] == 0
    assert detalle["resultado_base_diezmo_centavos"] == -300
    assert detalle["diezmo_centavos"] == 0
    assert detalle["jornadas"][0]["id_cierre_diario"] == cierre_diario["id_evento"]

    mes = date.fromisoformat(pasado)
    mensual = legado.post("/cierres/mensuales", json={"anio": mes.year, "mes": mes.month})
    assert mensual.status_code == 201, mensual.text
    assert mensual.json()["contabilidad_centavos"] == detalle

    parcial = solicitud(pagos=[pago("comidas_banco", 8051, referencia="abono-parcial")])
    assert post(ventas, ruta + "/abonos", parcial) == post(ventas, ruta + "/abonos", parcial)
    actual = informe(admin)
    assert actual["devengado_centavos"] == 0
    assert actual["cobrado_neto_centavos"] == 8051
    assert actual["diezmo_centavos"] == 805
    assert actual["fiado_al_cierre_centavos"] == 20000

    post(ventas, ruta + "/abonos", solicitud(pagos=[pago("bebidas_postres_banco", 20000)]))
    actual = informe(admin)
    assert actual["fiado_al_cierre_centavos"] == 0
    assert actual["cobrado_neto_centavos"] == 28051
    assert actual["diezmo_centavos"] == 2805
    assert legado.patch(f"/gastos/{gasto['id_gasto']}/anular", json={"motivo": "Corrección ficticia"}).status_code == 200
    assert informe(admin)["resultado_base_diezmo_centavos"] == 28351
    reversion = solicitud(motivo="Reembolso ficticio")
    assert post(admin, ruta + "/anulacion", reversion) == post(admin, ruta + "/anulacion", reversion)
    assert informe(admin)["cobrado_neto_centavos"] == 0
    assert informe(admin)["devengado_centavos"] == -28051
    assert legado.get(SEMANAL).json()["cierres"][0]["contabilidad_centavos"] == detalle
    assert legado.get("/cierres/mensuales").json()["cierres"][0]["contabilidad_centavos"] == detalle


def test_fiado_anterior_al_corte_conserva_saldo_y_reconoce_solo_el_abono(mixta, base_prueba, monkeypatch):
    ventas, venta = mixta
    venta.update(pagos=[], fiado=True, deudor="Saldo inicial ficticio")
    alta = post(ventas, VENTAS, venta)
    etapa6 = base_prueba.with_name("pos6-saldo.db")
    copiar_ficticia(base_prueba, etapa6, caja_diaria=True)
    etapa7 = base_prueba.with_name("pos7-saldo.db")
    copiar_ficticia(etapa6, etapa7, contabilidad=True)
    monkeypatch.setenv("NEGOCIO_DB_PATH", str(etapa7))
    monkeypatch.setenv("ABADION_PUENTE_FICTICIO", "1")
    admin = TestClient(app)
    _iniciar_sesion(admin, "admin", "admin")

    antes = informe(admin)
    assert (antes["devengado_centavos"], antes["cobrado_neto_centavos"], antes["diezmo_centavos"]) == (0, 0, 0)
    assert antes["fiado_al_cierre_centavos"] == 28051
    ruta = f"{VENTAS}/{alta['id_venta']}/abonos"
    post(ventas, ruta, solicitud(pagos=[pago("comidas_banco", 28051)]))
    despues = informe(admin)
    assert despues["devengado_centavos"] == 0
    assert despues["cobrado_neto_centavos"] == 28051
    assert despues["fiado_al_cierre_centavos"] == 0
    assert despues["diezmo_centavos"] == 2805
