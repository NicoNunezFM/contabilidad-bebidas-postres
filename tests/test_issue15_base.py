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
