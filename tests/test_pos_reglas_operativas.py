import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from threading import Barrier

from scripts.abadion_entrenamiento import preparar_base
from tests.test_jornada_contable import BEBIDAS, COMIDAS, existencias, obtener, operar, preparar_productos
from tests.test_pos_qa_integrado import SIM, cliente, post, solicitud


def test_propuesta_apertura_y_alertas_por_caja(tmp_path, monkeypatch):
    preparar_base(tmp_path)
    ventas, admin = cliente(tmp_path, 0), cliente(tmp_path, 1)
    ruta = SIM + "/caja-diaria"

    def hora(fecha, momento):
        monkeypatch.setattr("pos_caja_diaria.ahora_local", lambda: f"{fecha}T{momento}:00-03:00")

    anterior, hoy = "2040-02-05", "2040-02-06"
    hora(anterior, "11:00")
    for caja, inicial, contado in ((COMIDAS, 1000, 900), (BEBIDAS, 700, 750)):
        jornada = operar(ventas, caja, "apertura", fecha=anterior, inicial_centavos=inicial)
        revision = jornada["id_evento"]
        base = dict(id_jornada=jornada["id_jornada"], revision_efectivo=revision, contado_centavos=contado)
        assert ventas.post(f"{ruta}/{caja}/arqueo", json=solicitud(**base, motivo="   ")).status_code == 422
        arqueo = operar(ventas, caja, "arqueo", **base, motivo="Conteo de prueba")
        cierre = operar(ventas, caja, "cierre", id_jornada=jornada["id_jornada"], id_arqueo=arqueo["id_evento"])
        assert cierre["alerta_administracion"]
    assert ventas.get(ruta + "/alertas").status_code == 403
    alertas = obtener(admin, ruta + "/alertas", limite=1)
    assert alertas["alertas"][0]["diferencia_centavos"] == 50
    siguiente = obtener(admin, ruta + "/alertas", antes_de=alertas["siguiente_antes_de"])
    assert siguiente["alertas"][0]["diferencia_centavos"] == -100

    for momento in ("09:59", "12:00"):
        hora(hoy, momento)
        assert obtener(ventas, ruta)["propuestas_apertura"] == {}
    for momento in ("10:00", "11:59"):
        hora(hoy, momento)
        propuestas = obtener(ventas, ruta)["propuestas_apertura"]
        assert propuestas[COMIDAS]["contado_centavos"] == 900
        assert propuestas[BEBIDAS]["contado_centavos"] == 750
    hora(hoy, "10:00")
    apertura = operar(ventas, COMIDAS, "apertura", fecha=hoy, inicial_centavos=800)
    assert apertura["diferencia_centavos"] == -100
    assert obtener(ventas, ruta)["cajas"][COMIDAS]["esperado_centavos"] == 800
    hora(hoy, "12:00")
    otra = operar(admin, BEBIDAS, "apertura", fecha=hoy, inicial_centavos=800)
    assert otra["diferencia_centavos"] == 50
    assert obtener(cliente(tmp_path, 1), ruta + "/alertas")["alertas"][0]["observacion"] == "Conteo de prueba"

    movimientos = f"{ruta}/{COMIDAS}/movimientos"
    for navegador in (admin, ventas):
        datos = solicitud(id_jornada=apertura["id_jornada"], tipo="aporte", importe_centavos=100, motivo="Cambio")
        assert post(navegador, movimientos, datos) == post(navegador, movimientos, datos)
        assert navegador.post(movimientos, json=solicitud(
            id_jornada=apertura["id_jornada"], tipo="retiro", importe_centavos=100, motivo=" ",
        )).status_code == 422
        operar(navegador, COMIDAS, "movimientos", id_jornada=apertura["id_jornada"],
               tipo="retiro", importe_centavos=100, motivo="Retorno de cambio")
    assert obtener(ventas, ruta)["cajas"][COMIDAS]["esperado_centavos"] == 800
    assert obtener(ventas, ruta)["cajas"][BEBIDAS]["esperado_centavos"] == 800


def test_faltante_reintento_devoluciones_y_concurrencia(tmp_path):
    ruta = preparar_base(tmp_path)
    ids, _ = preparar_productos(ruta)
    producto = ids["Comida"]
    with closing(sqlite3.connect(ruta)) as db, db:
        db.execute("UPDATE productos SET stock = 2 WHERE id_producto = ?", (producto,))
    ventas, admin = cliente(tmp_path, 0), cliente(tmp_path, 1)
    items = [{"id_producto": producto, "cantidad": 1}, {"id_producto": producto, "cantidad": 3}]
    faltantes = {str(producto): 2}
    cotizacion = post(ventas, "/pos-api/pedidos/validar?advertir_faltantes=true", {"items": items})
    assert cotizacion["faltantes_stock"] == faltantes
    base = solicitud(items=items, total_esperado_centavos=4000, medio_pago="transferencia")
    endpoint = SIM + "/ventas"
    assert ventas.post(endpoint, json=base).json()["detail"]["faltantes_stock"] == faltantes
    assert existencias(ruta, ids)["Comida"] == 2
    confirmada = {**base, "confirmar_faltantes": faltantes}
    competidora = {**confirmada, **solicitud()}
    barrera = Barrier(2, timeout=10)

    def vender(navegador, datos):
        barrera.wait()
        return navegador.post(endpoint, json=datos)

    with ThreadPoolExecutor(max_workers=2) as equipo:
        tareas = [equipo.submit(vender, navegador, datos)
                  for navegador, datos in ((ventas, confirmada), (admin, competidora))]
        respuestas = [tarea.result() for tarea in tareas]
    assert sorted(r.status_code for r in respuestas) == [200, 409]
    ganadora = next(i for i, r in enumerate(respuestas) if r.status_code == 200)
    original = respuestas[ganadora].json()
    assert respuestas[1 - ganadora].json()["detail"]["faltantes_stock"] == {str(producto): 4}
    assert post((ventas, admin)[ganadora], endpoint, (confirmada, competidora)[ganadora]) == original
    assert existencias(ruta, ids)["Comida"] == 0
    assert [i["stock_descontado"] for i in original["items"]] == [1, 1]
    identificador = original["id_venta"]
    with closing(sqlite3.connect(ruta)) as db:
        usuario, pedido = db.execute("SELECT id_usuario, pedido FROM pos_ventas_simuladas").fetchone()
        assert usuario and json.loads(pedido)["faltantes_stock"] == faltantes
    devolver = f"{endpoint}/{identificador}/devoluciones"
    parcial = solicitud(motivo="Devuelve unidades faltantes", items=[{"linea": 2, "cantidad": 2}])
    primera = post(admin, devolver, parcial)
    assert post(admin, devolver, parcial) == primera
    assert primera["reembolsado_centavos"] == 2000
    assert existencias(ruta, ids)["Comida"] == 0
    anulacion = solicitud(motivo="Revierte unidades restantes")
    anular = f"{endpoint}/{identificador}/anulacion"
    final = post(admin, anular, anulacion)
    assert post(admin, anular, anulacion) == final
    assert final["reembolsado_centavos"] == 2000
    assert existencias(ruta, ids)["Comida"] == 2
    assert obtener(admin, SIM + "/conciliacion")["cuadrado"]
