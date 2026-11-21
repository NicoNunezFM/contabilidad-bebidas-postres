"""Verificación de los límites del libro en la base del Issue #15."""
import sqlite3
from contextlib import closing

import pytest
from pydantic import ValidationError

from pos_cobros import PagoPos, crear_libro, estado_cuenta, registrar_movimiento


@pytest.mark.parametrize(
    "receptor, medio",
    [("comidas_efectivo_en_transito", "transferencia"), ("obligacion_reparto", "transferencia")],
)
def test_rechaza_receptor_incompatible_con_medio_de_cobro(receptor, medio):
    with pytest.raises(ValidationError):
        PagoPos(receptor=receptor, medio_pago=medio, importe_centavos=100_000)


def test_transferencia_de_terceros_no_aumenta_ingreso_ni_saldo_del_cliente():
    from uuid import uuid4

    from pos_cobros import resumen_libro, terminar_evento
    from pos_envios import MovimientoReparto, registrar_fondo_reparto, resumen_fondos_reparto

    pedido = {
        "total_centavos": 1_000_000,
        "items": [{"seccion": "comidas", "cantidad": 1, "precio_unitario_centavos": 1_000_000}],
        "envio": {"titular": "repartidor", "importe_centavos": 100_000},
    }
    with closing(sqlite3.connect(":memory:")) as db:
        db.execute("PRAGMA foreign_keys = ON")
        db.execute("CREATE TABLE usuarios_pos (id_usuario INTEGER PRIMARY KEY)")
        db.execute("CREATE TABLE pos_ventas_simuladas (id_venta INTEGER PRIMARY KEY)")
        db.execute("INSERT INTO usuarios_pos VALUES (1)")
        db.execute("INSERT INTO pos_ventas_simuladas VALUES (1)")
        crear_libro(db)
        db.execute("""
            INSERT INTO pos_eventos_simulados (id_evento, id_venta, id_usuario, solicitud, tipo, periodo)
            VALUES (1, 1, 1, '{}', 'venta', 1)
        """)
        registrar_movimiento(db, 1, 1, "comidas_banco", "transferencia", 1_000_000)
        estado = estado_cuenta(db, 1, pedido)
        terminar_evento(db, 1, estado, despues=estado)
        entrada = MovimientoReparto(
            id_solicitud=uuid4(), receptor="comidas_banco", importe_centavos=100_000,
            referencia="transferencia-ficticia", motivo="Envío cobrado para el repartidor",
        )
        usuario = {"id_usuario": 1}
        recibido = registrar_fondo_reparto(db, 1, pedido, entrada, usuario, tipo="recepcion")
        assert recibido["fondos_reparto"][0]["obligacion_centavos"] == 100_000
        assert registrar_fondo_reparto(db, 1, pedido, entrada, usuario, tipo="recepcion") == recibido
        directo = entrada.model_copy(update={
            "id_solicitud": uuid4(), "referencia": "entrega-ficticia", "receptor": "repartidor_directo",
        })
        pedido["envio"]["importe_centavos"] = 200_000
        constancia = registrar_fondo_reparto(db, 1, pedido, directo, usuario, tipo="directo")
        fila = next(f for f in constancia["fondos_reparto"] if f["receptor"] == "repartidor_directo")
        assert fila["pagado_directo_centavos"] == 100_000
        assert fila["obligacion_centavos"] == 0
        liquidacion = entrada.model_copy(update={"id_solicitud": uuid4(), "referencia": "liquidacion-ficticia"})
        registrar_fondo_reparto(db, 1, pedido, liquidacion, usuario, tipo="liquidacion")
        assert resumen_fondos_reparto(db)[0]["obligacion_centavos"] == 0
        assert estado_cuenta(db, 1, pedido) == estado
        assert estado["saldo_pendiente_centavos"] == 0
        assert resumen_libro(db)["secciones"]["comidas"]["cobrado_atribuido_centavos"] == 1_000_000


def test_cobro_en_transito_y_rendicion_no_duplican_venta():
    from uuid import uuid4

    from pos_caja_diaria import ahora_local, crear_caja_diaria
    from pos_cobros import (
        RendicionEntrada, efectivo_en_transito, registrar_pagos, registrar_rendicion, resumen_libro,
    )

    pedido = {
        "total_centavos": 1_000_000,
        "items": [{"seccion": "comidas", "cantidad": 1, "precio_unitario_centavos": 1_000_000}],
    }
    with closing(sqlite3.connect(":memory:")) as db:
        db.execute("PRAGMA foreign_keys = ON")
        db.execute("CREATE TABLE usuarios_pos (id_usuario INTEGER PRIMARY KEY, usuario TEXT, rol TEXT)")
        db.execute("CREATE TABLE pos_ventas_simuladas (id_venta INTEGER PRIMARY KEY)")
        db.execute("INSERT INTO usuarios_pos VALUES (1, 'admin-ficticio', 'admin')")
        db.execute("INSERT INTO pos_ventas_simuladas VALUES (1)")
        crear_libro(db)
        crear_caja_diaria(db)
        db.execute("INSERT INTO pos_jornadas_caja (caja, fecha) VALUES ('comidas', ?)", (ahora_local()[:10],))
        db.execute("""
            INSERT INTO pos_eventos_simulados (id_evento, id_venta, id_usuario, solicitud, tipo, periodo)
            VALUES (1, 1, 1, '{}', 'venta', 1)
        """)
        pago = PagoPos(receptor="comidas_efectivo_en_transito", medio_pago="efectivo", importe_centavos=1_000_000)
        registrar_pagos(db, 1, 1, [pago])
        assert estado_cuenta(db, 1, pedido)["saldo_pendiente_centavos"] == 0
        assert efectivo_en_transito(db, 1) == 1_000_000
        assert len(resumen_libro(db)["receptores"]) == 1
        assert db.execute("SELECT COUNT(*) FROM pos_diario_caja").fetchone()[0] == 0
        entrada = RendicionEntrada(id_solicitud=uuid4(), importe_centavos=600_000, motivo="Recepción de efectivo")
        recibo = registrar_rendicion(db, 1, entrada, {"id_usuario": 1})
        assert registrar_rendicion(db, 1, entrada, {"id_usuario": 1}) == recibo
        assert efectivo_en_transito(db, 1) == 400_000
        assert db.execute("SELECT tipo, importe_centavos FROM pos_diario_caja").fetchall() == [
            ("transferencia", 600_000),
        ]
        assert estado_cuenta(db, 1, pedido)["cobrado_centavos"] == 1_000_000
        saldos = {r["receptor"]: r["saldo_centavos"] for r in resumen_libro(db)["receptores"]}
        assert saldos == {"comidas_efectivo": 600_000, "comidas_efectivo_en_transito": 400_000}
        db.execute("""
            INSERT INTO pos_eventos_simulados (id_venta, id_usuario, solicitud, tipo, periodo)
            VALUES (1, 1, '{}', 'devolucion', 1)
        """)
        registrar_movimiento(db, 3, 1, pago.receptor, "efectivo", -500_000, revierte=1)
        assert efectivo_en_transito(db, 1) == 0
        assert estado_cuenta(db, 1, pedido)["cobrado_centavos"] == 500_000
        saldos = {r["receptor"]: r["saldo_centavos"] for r in resumen_libro(db)["receptores"]}
        assert saldos == {"comidas_efectivo": 500_000, "comidas_efectivo_en_transito": 0}


def test_envio_propio_se_devenga_por_separado_y_revierte_en_devolucion_total():
    pedido = {
        "total_centavos": 1_100_000,
        "items": [{"seccion": "bebidas_postres", "cantidad": 1, "precio_unitario_centavos": 1_000_000}],
        "envio": {"titular": "negocio", "importe_centavos": 100_000},
    }
    with closing(sqlite3.connect(":memory:")) as db:
        crear_libro(db)
        db.execute("""
            INSERT INTO pos_eventos_simulados (id_evento, id_venta, id_usuario, solicitud, tipo, periodo)
            VALUES (1, 1, 1, '{}', 'devolucion', 1)
        """)
        estado = estado_cuenta(db, 1, pedido)
        assert estado["devengado_centavos"] == {"comidas": 100_000, "bebidas_postres": 1_000_000}
        assert estado["envio_propio_vigente_centavos"] == 100_000
        db.execute("INSERT INTO pos_unidades_devueltas VALUES (1, 1, 1)")
        estado = estado_cuenta(db, 1, pedido)
        assert estado["importe_vigente_centavos"] == 0
        assert estado["envio_propio_vigente_centavos"] == 0


def test_envio_de_terceros_pago_mixto_rendicion_concurrente_y_diezmo(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from pos_caja_diaria import ahora_local
    from scripts.abadion_entrenamiento import preparar_base
    from tests.test_pos_qa_integrado import SIM, catalogo, cliente, post, solicitud

    preparar_base(tmp_path)
    ventas, admin, otro_admin = cliente(tmp_path, 0), cliente(tmp_path, 1), cliente(tmp_path, 1)
    producto = catalogo(ventas)["Clásica doble"]
    mercaderia = round(producto["precio_venta"] * 100)
    envio, efectivo = 100_000, 200_000
    venta = post(ventas, SIM + "/ventas", solicitud(
        items=[{"id_producto": producto["id_producto"], "cantidad": 1}],
        total_esperado_centavos=mercaderia,
        envio={"titular": "repartidor", "importe_centavos": envio},
        pagos=[
            {"receptor": "comidas_banco", "medio_pago": "transferencia",
             "importe_centavos": mercaderia - efectivo, "referencia": "mixto-ficticio"},
            {"receptor": "comidas_efectivo_en_transito", "medio_pago": "efectivo",
             "importe_centavos": efectivo},
        ],
    ))
    assert venta["saldo_pendiente_centavos"] == 0
    raiz = SIM + f"/ventas/{venta['id_venta']}/fondos-reparto"
    recepcion = solicitud(receptor="comidas_banco", importe_centavos=envio,
                          referencia="mixto-ficticio", motivo="Envío ajeno")
    assert ventas.post(raiz + "/recepcion", json=recepcion).status_code == 403
    raiz_cierres = SIM + "/cierres"
    ingreso = post(admin, raiz + "/recepcion", recepcion)
    assert post(admin, raiz + "/recepcion", recepcion) == ingreso
    informe = admin.get(SIM + "/contabilidad").json()
    assert informe["cobrado_neto_centavos"] == mercaderia
    assert informe["diezmo_centavos"] == mercaderia // 10

    historia = admin.get(SIM + "/ventas").json()["ventas"][0]["historial"]
    cobro = next(m["id_movimiento"] for m in historia[0]["movimientos"]
                 if m["receptor"] == "comidas_efectivo_en_transito")
    ruta_rendicion = SIM + f"/cobros/{cobro}/rendiciones"
    rendicion = solicitud(importe_centavos=efectivo, motivo="Recepción en caja")
    assert admin.post(ruta_rendicion, json=rendicion).status_code == 409
    post(admin, SIM + "/caja-diaria/comidas/apertura",
         solicitud(fecha=ahora_local()[:10], inicial_centavos=0))
    assert post(admin, ruta_rendicion, rendicion)["pendiente_centavos"] == 0
    assert post(admin, ruta_rendicion, rendicion)["pendiente_centavos"] == 0

    cierre = post(admin, raiz_cierres, solicitud(periodo=1, motivo="Cierre ficticio"))
    assert cierre["resumen"]["fondos_reparto"][0]["obligacion_centavos"] == envio
    barrera = Barrier(2, timeout=10)

    def liquidar(navegador, referencia):
        barrera.wait()
        return navegador.post(raiz + "/liquidacion", json=solicitud(
            receptor="comidas_banco", importe_centavos=envio, motivo="Liquidación ficticia",
            referencia=referencia,
        )).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        primera = pool.submit(liquidar, admin, "liq-a")
        segunda = pool.submit(liquidar, otro_admin, "liq-b")
        assert sorted((primera.result(), segunda.result())) == [200, 409]
    assert admin.get(raiz_cierres + "/1").json()["resumen"] == cierre["resumen"]
    assert admin.get(SIM + "/cajas").json()["fondos_reparto"][0]["obligacion_centavos"] == 0
    assert admin.get(SIM + "/conciliacion").json()["cuadrado"] is True


def test_preparacion_fondos_con_respaldo_e_idempotencia(tmp_path):
    from scripts.abadion_entrenamiento import activar_fondos_envio, preparar_base

    ruta = preparar_base(tmp_path)
    respaldo = activar_fondos_envio(tmp_path)
    assert respaldo.is_file()
    assert activar_fondos_envio(tmp_path) is None
    with closing(sqlite3.connect(respaldo)) as antes, closing(sqlite3.connect(ruta)) as despues:
        assert antes.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert despues.execute("PRAGMA foreign_key_check").fetchall() == []
        for tabla in ("productos", "pos_ventas_simuladas", "pos_movimientos_simulados", "pos_clientes"):
            assert antes.execute(f"SELECT * FROM {tabla}").fetchall() == despues.execute(
                f"SELECT * FROM {tabla}"
            ).fetchall()


def test_fiado_con_envio_propio_y_abono_fifo_fuera_del_local(tmp_path):
    from scripts.abadion_entrenamiento import preparar_base
    from tests.test_pos_clientes import CLIENTES, fiar, preparar_abono
    from tests.test_pos_entrenamiento import registrar_cliente_prueba
    from tests.test_pos_qa_integrado import SIM, cliente, post

    preparar_base(tmp_path)
    ventas, admin = cliente(tmp_path, 0), cliente(tmp_path, 1)
    cliente_id = registrar_cliente_prueba(ventas, "Cliente ficticio de reparto")
    primero = fiar(ventas, cliente_id, "Clásica doble")
    primero["total_esperado_centavos"] += 100_000
    primero["envio"] = {"titular": "negocio", "importe_centavos": 100_000}
    venta = post(ventas, SIM + "/ventas", primero)
    segunda = post(ventas, SIM + "/ventas", fiar(ventas, cliente_id, "Manaos Cola 600ml"))
    ruta = f"{CLIENTES}/{cliente_id}"
    monto = primero["total_esperado_centavos"] + 50_000
    previa, abono = preparar_abono(ventas, ruta, {
        "receptor": "comidas_efectivo_en_transito", "medio_pago": "efectivo", "importe_centavos": monto,
    })
    assert [(i["id_venta"], i["importe_centavos"]) for i in previa["imputaciones"]] == [
        (venta["id_venta"], primero["total_esperado_centavos"]), (segunda["id_venta"], 50_000),
    ]
    cobro = post(ventas, ruta + "/abonos", abono)
    assert post(ventas, ruta + "/abonos", abono) == cobro
    assert ventas.get(ruta).json()["saldo_centavos"] == segunda["importe_original_centavos"] - 50_000
    assert admin.get(SIM + "/contabilidad").json()["diezmo_centavos"] == monto // 10
    assert admin.get(SIM + "/conciliacion").json()["cuadrado"] is True


def test_pedido_whatsapp_fiado_entrega_confirmada_y_cancelacion_auditada(tmp_path):
    import shutil

    from scripts.abadion_entrenamiento import ARCHIVO_CATALOGO, preparar_base, respaldar_sqlite
    from tests.test_pos_clientes import fiar
    from tests.test_pos_entrenamiento import registrar_cliente_prueba
    from tests.test_pos_qa_integrado import SIM, cliente, post, solicitud

    ruta_db = preparar_base(tmp_path)
    ventas, admin = cliente(tmp_path, 0), cliente(tmp_path, 1)
    cliente_id = registrar_cliente_prueba(ventas, "Cliente ficticio")
    payload = fiar(ventas, cliente_id, "Clásica doble")
    payload["entrega"] = {"origen": "whatsapp", "modalidad": "envio", "direccion": "Calle ficticia 123"}
    venta = post(ventas, SIM + "/ventas", payload)
    assert post(ventas, SIM + "/ventas", payload)["id_venta"] == venta["id_venta"]
    lista = ventas.get(SIM + "/pedidos").json()["pedidos"]
    assert len(lista) == 1 and lista[0]["estado"] == "pendiente"
    ruta = SIM + f"/pedidos/{venta['id_venta']}/estado"
    assert ventas.post(ruta, json=solicitud(estado="cancelado", version=1, motivo="Prueba")).status_code == 403
    for version, estado in enumerate(("preparacion", "listo", "en_camino"), start=1):
        datos = solicitud(estado=estado, version=version)
        paso = post(ventas, ruta, datos)
        assert post(ventas, ruta, datos) == paso
    assert ventas.post(ruta, json=solicitud(estado="entregado", version=4)).status_code == 409
    assert ventas.post(ruta, json=solicitud(
        estado="entregado", version=4, confirmar_pendiente=True, saldo_confirmado_centavos=1,
    )).status_code == 409
    pedido = post(ventas, ruta, solicitud(
        estado="entregado", version=4, confirmar_pendiente=True,
        saldo_confirmado_centavos=venta["saldo_pendiente_centavos"],
    ))
    assert pedido["saldo_pendiente_centavos"] == venta["saldo_pendiente_centavos"]
    assert len(pedido["historial"]) == 5
    assert ventas.get(SIM + "/pedidos").json()["pedidos"] == []
    assert ventas.get(SIM + "/pedidos?finalizados=true").json()["pedidos"][0]["estado"] == "entregado"

    retiro = fiar(ventas, cliente_id, "Clásica doble")
    retiro["entrega"] = {"origen": "mostrador", "modalidad": "retiro"}
    segunda = post(ventas, SIM + "/ventas", retiro)
    cancelado = post(admin, SIM + f"/pedidos/{segunda['id_venta']}/estado",
                     solicitud(estado="cancelado", version=1, motivo="Pedido duplicado ficticio"))
    assert cancelado["saldo_pendiente_centavos"] == segunda["saldo_pendiente_centavos"]
    assert cancelado["historial"][-1]["motivo"] == "Pedido duplicado ficticio"


    respaldo = respaldar_sqlite(ruta_db, "pedido-ficticio")
    restaurada = tmp_path / "restaurada"
    restaurada.mkdir()
    shutil.copy2(respaldo, restaurada / ruta_db.name)
    shutil.copy2(tmp_path / ARCHIVO_CATALOGO, restaurada / ARCHIVO_CATALOGO)
    restaurado = cliente(restaurada, 1)
    assert restaurado.get(SIM + "/pedidos?finalizados=true").json() == admin.get(
        SIM + "/pedidos?finalizados=true"
    ).json()


def test_pedido_anonimo_conversion_concurrente_con_reprecio_y_restauracion(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from shutil import copy2
    from threading import Barrier

    from scripts.abadion_entrenamiento import ARCHIVO_CATALOGO, preparar_base, respaldar_sqlite
    from tests.test_pos_qa_integrado import SIM, catalogo, cliente, post, solicitud

    ruta_db = preparar_base(tmp_path)
    operador, otro, admin = cliente(tmp_path, 0), cliente(tmp_path, 0), cliente(tmp_path, 1)
    producto = catalogo(operador)["Oreo chico"]
    id_producto = producto["id_producto"]
    with closing(sqlite3.connect(ruta_db)) as db, db:
        db.execute("UPDATE productos SET controla_stock=1, stock=2 WHERE id_producto=?", (id_producto,))
    ruta = SIM + "/pedidos"
    entrada = solicitud(items=[{"id_producto": id_producto, "cantidad": 1, "observacion": "Nota ficticia"}],
                        entrega={"origen": "whatsapp", "modalidad": "envio", "direccion": "Calle ficticia 123"})
    pedido = post(operador, ruta, entrada)
    numero = pedido["id_pedido"]
    assert post(operador, ruta, entrada)["id_pedido"] == numero
    assert pedido["id_venta"] is None
    assert pedido["items"][0]["observacion"] == "Nota ficticia"
    detalle = f"{ruta}/{numero}"
    paso = solicitud(estado="preparacion", version=1)
    assert post(operador, detalle + "/estado", paso)["estado"] == "preparacion"
    assert post(operador, detalle + "/estado", paso)["estado"] == "preparacion"
    assert admin.get(SIM + "/contabilidad").json()["diezmo_centavos"] == 0
    with closing(sqlite3.connect(ruta_db)) as db, db:
        for tabla in ("pos_ventas_simuladas", "pos_movimientos_simulados", "pos_diario_caja"):
            assert db.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone() == (0,)
        assert db.execute("SELECT stock FROM productos WHERE id_producto=?", (id_producto,)).fetchone() == (2,)
        db.execute("UPDATE productos SET precio_venta=3500, stock=0 WHERE id_producto=?", (id_producto,))
    original = solicitud(total_esperado_centavos=300_000, medio_pago="transferencia")
    assert operador.post(detalle + "/venta", json=original).status_code == 409
    with closing(sqlite3.connect(ruta_db)) as db, db:
        db.execute("UPDATE productos SET stock=2 WHERE id_producto=?", (id_producto,))
    assert operador.get(detalle + "/cotizacion").json()["total_centavos"] == 350_000
    precio = operador.post(detalle + "/venta", json=original)
    assert precio.status_code == 409 and precio.json()["detail"]["codigo"] == "TOTAL_MODIFICADO"

    barrera = Barrier(2, timeout=10)

    def confirmar(navegador, datos):
        barrera.wait()
        return navegador.post(detalle + "/venta", json=datos)

    pagos = [solicitud(total_esperado_centavos=350_000, medio_pago="transferencia") for _ in range(2)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        tareas = [pool.submit(confirmar, navegador, datos) for navegador, datos in zip((operador, otro), pagos)]
        respuestas = [tarea.result() for tarea in tareas]
    assert sorted(r.status_code for r in respuestas) == [200, 409]
    ganadora = next(i for i, r in enumerate(respuestas) if r.status_code == 200)
    venta = respuestas[ganadora].json()
    assert post(operador, detalle + "/venta", pagos[ganadora]) == venta
    assert venta["id_pedido"] == numero and venta["saldo_pendiente_centavos"] == 0
    assert admin.get(SIM + "/contabilidad").json()["cobrado_neto_centavos"] == 350_000
    assert admin.get(SIM + "/conciliacion").json()["cuadrado"]
    with closing(sqlite3.connect(ruta_db)) as db:
        assert db.execute("SELECT stock FROM productos WHERE id_producto=?", (id_producto,)).fetchone() == (1,)
        assert db.execute("SELECT COUNT(*) FROM pos_ventas_simuladas").fetchone() == (1,)
    copia = tmp_path / "recuperada"
    copia.mkdir()
    copy2(respaldar_sqlite(ruta_db, "anonimo"), copia / ruta_db.name)
    copy2(tmp_path / ARCHIVO_CATALOGO, copia / ARCHIVO_CATALOGO)
    assert cliente(copia, 0).get(ruta).json() == operador.get(ruta).json()


def test_pedido_anonimo_cancelado_y_conversion_fiada(tmp_path):
    from scripts.abadion_entrenamiento import preparar_base
    from tests.test_pos_entrenamiento import registrar_cliente_prueba
    from tests.test_pos_qa_integrado import SIM, catalogo, cliente, post, solicitud

    preparar_base(tmp_path)
    operador, admin = cliente(tmp_path, 0), cliente(tmp_path, 1)
    producto = catalogo(operador)["Oreo chico"]
    ruta = SIM + "/pedidos"
    datos = {"items": [{"id_producto": producto["id_producto"], "cantidad": 1}],
             "entrega": {"origen": "mostrador", "modalidad": "retiro"}}
    cancelable = post(operador, ruta, solicitud(**datos))
    cancel = f"{ruta}/{cancelable['id_pedido']}"
    cambio = solicitud(estado="cancelado", motivo="Cancelación ficticia", version=1)
    assert operador.post(cancel + "/estado", json=cambio).status_code == 403
    assert post(admin, cancel + "/estado", cambio)["id_venta"] is None
    assert operador.post(cancel + "/venta", json=solicitud(total_esperado_centavos=300_000,
                         medio_pago="transferencia")).status_code == 409
    assert admin.get(SIM + "/ventas").json()["ventas"] == []

    pedido = post(operador, ruta, solicitud(**datos))
    convertir = f"{ruta}/{pedido['id_pedido']}/venta"
    pago = solicitud(fiado=True, pagos=[], total_esperado_centavos=300_000)
    assert operador.post(convertir, json=pago).status_code == 422
    identificador = registrar_cliente_prueba(operador, "Cliente ficticio de conversión")
    venta = post(operador, convertir, {**pago, "id_cliente": identificador})
    assert venta["id_venta"] != pedido["id_pedido"]
    assert venta["saldo_pendiente_centavos"] == 300_000
    assert operador.get(f"{SIM}/clientes/{identificador}").json()["saldo_centavos"] == 300_000
