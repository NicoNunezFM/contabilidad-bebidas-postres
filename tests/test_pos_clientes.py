import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from threading import Barrier

import pytest
from fastapi import HTTPException

import pos_clientes
from pos_caja_diaria import ahora_local
from pos_entrenamiento_db import ARCHIVO_BASE, bloquear_entrenamiento
from scripts.abadion_entrenamiento import activar_clientes, preparar_base
from tests.test_pos_entrenamiento import registrar_cliente_prueba
from tests.test_pos_qa_integrado import SIM, catalogo, cliente, post, solicitud


CLIENTES = SIM + "/clientes"


def fiar(navegador, id_cliente, nombre, *, pagos=()):
    producto = catalogo(navegador)[nombre]
    return solicitud(id_cliente=id_cliente, fiado=True, pagos=list(pagos),
                     items=[{"id_producto": producto["id_producto"], "cantidad": 1}],
                     total_esperado_centavos=round(producto["precio_venta"] * 100))


def pago(importe, referencia="comprobante ficticio", **campos):
    return {"importe_centavos": importe, "referencia": referencia,
            "receptor": "comidas_banco", "medio_pago": "transferencia", **campos}


def preparar_abono(navegador, ruta, datos):
    previa = post(navegador, ruta + "/abonos/vista-previa", datos)
    return previa, solicitud(pago=datos, vista_previa=previa["vista_previa"])


def test_clientes_homonimos_fifo_caja_real_y_correccion(tmp_path):
    ruta_db = preparar_base(tmp_path)
    ventas, admin = cliente(tmp_path, 0), cliente(tmp_path, 1)
    datos = solicitud(nombre="Alex", telefono="555-0199", referencia="Puerta azul")
    alta = post(ventas, CLIENTES, datos)
    assert post(ventas, CLIENTES, datos) == alta
    assert ventas.post(CLIENTES, json={**datos, "nombre": "Otro"}).status_code == 409
    alex = alta["id_cliente"]
    homonimo = registrar_cliente_prueba(ventas, "Alex", referencia="Puerta roja")
    for termino in ("555-0199", "AZUL", str(alex)):
        assert [c["id_cliente"] for c in ventas.get(CLIENTES, params={"q": termino}).json()["clientes"]] == [alex]
    assert {c["id_cliente"] for c in ventas.get(CLIENTES, params={"q": "alex"}).json()["clientes"]} == {alex, homonimo}
    compra = fiar(ventas, alex, "Clásica doble", pagos=[pago(100_000, "entrega")])
    assert ventas.post(SIM + "/ventas", json={**compra, "id_cliente": None, "deudor": "Alex"}).status_code == 422
    comida = post(ventas, SIM + "/ventas", compra)
    bebida = post(admin, SIM + "/ventas", fiar(admin, alex, "Manaos Cola 600ml"))
    post(ventas, SIM + "/ventas", fiar(ventas, homonimo, "Clásica doble"))
    with closing(sqlite3.connect(ruta_db)) as db, db:
        # Fecha anterior gana al orden de ID. La tercera venta queda en otra cuenta.
        db.execute("UPDATE pos_ventas_simuladas SET fecha = '2026-01-01 00:00:00' WHERE id_venta = ?",
                   (bebida["id_venta"],))

    ruta = CLIENTES + f"/{alex}"
    ficha = ventas.get(ruta).json()
    assert ficha["saldo_por_seccion_centavos"] == {"comidas": 800_000, "bebidas_postres": 130_000}
    post(ventas, SIM + "/caja-diaria/bebidas_postres/apertura",
         solicitud(fecha=ahora_local()[:10], inicial_centavos=0))
    efectivo = pago(200_000, receptor="bebidas_postres_efectivo", medio_pago="efectivo")
    previa, abono = preparar_abono(ventas, ruta, efectivo)
    reparto = previa["imputaciones"]
    assert [(p["id_venta"], p["importe_centavos"]) for p in reparto] == [
        (bebida["id_venta"], 130_000), (comida["id_venta"], 70_000)]
    assert reparto[1]["por_seccion_centavos"] == {"comidas": 70_000, "bebidas_postres": 0}
    cobro = post(ventas, ruta + "/abonos", abono)
    assert post(ventas, ruta + "/abonos", abono) == cobro
    assert ventas.get(ruta).json()["saldo_centavos"] == 730_000
    assert ventas.get(CLIENTES + f"/{homonimo}").json()["saldo_centavos"] == 900_000
    informe = admin.get(SIM + "/contabilidad").json()
    assert informe["devengado_centavos"] == 1_930_000
    assert informe["cobrado_neto_centavos"] == 300_000
    assert informe["diezmo_centavos"] == 30_000
    assert admin.get(SIM + "/conciliacion").json()["cuadrado"] is True
    with closing(sqlite3.connect(ruta_db)) as db:
        assert db.execute("""
            SELECT SUM(importe_centavos), COUNT(referencia) FROM pos_movimientos_simulados
            WHERE receptor = 'bebidas_postres_efectivo'
        """).fetchone() == (200_000, 1)

    correccion = ruta + "/abonos/" + abono["id_solicitud"] + "/correccion"
    rectificar = solicitud(motivo="Reembolso ficticio por importe incorrecto")
    assert ventas.post(correccion, json=rectificar).status_code == 403
    resultado = post(admin, correccion, rectificar)
    assert post(admin, correccion, rectificar) == resultado
    assert admin.post(correccion, json=solicitud(motivo="Duplicado")).status_code == 409
    restaurada = ventas.get(ruta).json()
    assert restaurada["saldo_centavos"] == 930_000
    assert restaurada["operaciones"][0]["motivo"] == rectificar["motivo"]
    assert admin.get(SIM + "/contabilidad").json()["diezmo_centavos"] == 10_000
    assert admin.get(SIM + "/conciliacion").json()["cuadrado"] is True


def test_fifo_rollback_concurrencia_vista_desactualizada_y_devolucion(tmp_path, monkeypatch):
    preparar_base(tmp_path)
    ventas, admin = cliente(tmp_path, 0), cliente(tmp_path, 1)
    titular = registrar_cliente_prueba(ventas, "Titular ficticio")
    ruta = CLIENTES + f"/{titular}"
    primera = fiar(ventas, titular, "Manaos Cola 600ml")
    primera["items"][0]["cantidad"] = 2
    primera["total_esperado_centavos"] *= 2
    una = post(ventas, SIM + "/ventas", primera)
    otra = post(ventas, SIM + "/ventas", fiar(ventas, titular, "Manaos Cola 600ml"))
    antes = ventas.get(ruta).json()
    _, viejo = preparar_abono(ventas, ruta, pago(150_000, "viejo"))
    post(admin, SIM + f"/ventas/{una['id_venta']}/devoluciones",
         solicitud(motivo="Devolución de una unidad", items=[{"linea": 1, "cantidad": 1}]))
    assert ventas.post(ruta + "/abonos", json=viejo).status_code == 409
    assert ventas.post(ruta + "/abonos/vista-previa", json=pago(260_001)).status_code == 409
    previa, abono = preparar_abono(ventas, ruta, pago(150_000))
    assert [p["id_venta"] for p in previa["imputaciones"]] == [una["id_venta"], otra["id_venta"]]
    assert antes["saldo_centavos"] == 390_000

    previo = ventas.get(ruta).json()
    original = pos_clientes.registrar_pagos

    def fallar_segundo(db, evento, venta, pagos):
        if venta == otra["id_venta"]:
            raise HTTPException(409, "Fallo ficticio intermedio")
        original(db, evento, venta, pagos)

    with monkeypatch.context() as cambio:
        cambio.setattr(pos_clientes, "registrar_pagos", fallar_segundo)
        assert ventas.post(ruta + "/abonos", json=abono).status_code == 409
    assert ventas.get(ruta).json() == previo

    barrera = Barrier(2)

    def confirmar(datos):
        barrera.wait(timeout=10)
        return ventas.post(ruta + "/abonos", json=datos)

    with ThreadPoolExecutor(max_workers=2) as ejecutor:
        respuestas = list(ejecutor.map(confirmar, [abono, abono]))
    assert [r.status_code for r in respuestas] == [200, 200]
    assert respuestas[0].json() == respuestas[1].json()
    assert ventas.get(ruta).json()["saldo_centavos"] == 110_000

    _, siguiente = preparar_abono(ventas, ruta, pago(80_000, "otra ref"))
    with ThreadPoolExecutor(max_workers=2) as ejecutor:
        respuestas = list(ejecutor.map(confirmar, [siguiente, {**siguiente, **solicitud()}]))
    assert sorted(r.status_code for r in respuestas) == [200, 409]
    assert ventas.get(ruta).json()["saldo_centavos"] == 30_000


def test_migracion_clientes_respaldo_restauracion_y_fiado_historico(tmp_path):
    carpeta = tmp_path / "practica"
    ruta_db = preparar_base(carpeta)
    ventas = cliente(carpeta, 0)
    id_cliente = registrar_cliente_prueba(ventas, "Alex")
    datos = fiar(ventas, id_cliente, "Manaos Cola 600ml", pagos=[pago(30_000)])
    venta = post(ventas, SIM + "/ventas", datos)
    ruta_venta = SIM + f"/ventas/{venta['id_venta']}"
    post(ventas, ruta_venta + "/abonos", solicitud(pagos=[pago(20_000, "abono antiguo")]))
    # Recrea la forma exacta de la venta y del esquema anteriores a Clientes.
    with closing(sqlite3.connect(ruta_db)) as db, db:
        pedido, solicitud_guardada = db.execute("SELECT pedido, solicitud FROM pos_ventas_simuladas").fetchone()
        pedido, solicitud_guardada = json.loads(pedido), json.loads(solicitud_guardada)
        del pedido["id_cliente"]
        del solicitud_guardada["id_cliente"]
        solicitud_guardada["deudor"] = "Alex"
        db.execute("UPDATE pos_ventas_simuladas SET pedido = ?, solicitud = ?",
                   (json.dumps(pedido), json.dumps(solicitud_guardada, separators=(",", ":"))))
        for tabla in ("pos_eventos_clientes", "pos_solicitudes_clientes", "pos_ventas_clientes", "pos_clientes"):
            db.execute(f"DROP TABLE {tabla}")

    historial = ventas.get(SIM + "/ventas").json()
    assert historial["ventas"][0]["fiado_historico"]
    assert historial["ventas"][0]["saldo_pendiente_centavos"] == 80_000
    with bloquear_entrenamiento(carpeta), pytest.raises(ValueError, match="en uso"):
        activar_clientes(carpeta)
    respaldo = activar_clientes(carpeta)
    assert activar_clientes(carpeta) is None
    assert list(carpeta.glob("*.pre-clientes-*.db")) == [respaldo]
    assert ventas.get(SIM + "/ventas").json() == historial
    nuevo = registrar_cliente_prueba(ventas, "Alex")
    assert ventas.get(CLIENTES + f"/{nuevo}").json()["saldo_centavos"] == 0
    reintento = {k: v for k, v in datos.items() if k != "id_cliente"}
    assert post(ventas, SIM + "/ventas", {**reintento, "deudor": "Alex"})["id_venta"] == venta["id_venta"]
    assert post(ventas, ruta_venta + "/abonos", solicitud(pagos=[pago(80_000, "abono posterior")]))[
        "saldo_pendiente_centavos"] == 0

    restaurada = tmp_path / "restaurada"
    restaurada.mkdir()
    with closing(sqlite3.connect(respaldo)) as copia, closing(sqlite3.connect(restaurada / ARCHIVO_BASE)) as db:
        assert copia.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert copia.execute("PRAGMA foreign_key_check").fetchall() == []
        copia.backup(db)
    anterior = cliente(restaurada, 0)
    assert anterior.get(SIM + "/ventas").json() == historial
    assert anterior.get(CLIENTES).status_code == 404
