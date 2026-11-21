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
def test_pr16_rechaza_receptores_fuera_de_sus_cajas(receptor, medio):
    with pytest.raises(ValidationError):
        PagoPos(receptor=receptor, medio_pago=medio, importe_centavos=100_000)


def test_pr16_suma_el_movimiento_de_terceros_como_cobro_de_venta():
    pedido = {
        "total_centavos": 1_000_000,
        "items": [{"seccion": "comidas", "cantidad": 1, "precio_unitario_centavos": 1_000_000}],
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
        assert estado_cuenta(db, 1, pedido)["estado"] == "saldado"

        # Simula la reutilización directa del libro para $1.000 ajenos
        # sin pasar por la validación de importe del endpoint de venta.
        registrar_movimiento(db, 1, 1, "comidas_banco", "transferencia", 100_000)
        saldo = estado_cuenta(db, 1, pedido)
        assert saldo["cobrado_atribuido_centavos"]["comidas"] == 1_100_000
        assert saldo["saldo_pendiente_centavos"] == -100_000


def test_cobro_en_transito_y_rendicion_no_duplican_venta():
    from uuid import uuid4

    from pos_cobros import (
        RendicionEntrada, efectivo_en_transito, registrar_pagos, registrar_rendicion, resumen_libro,
    )

    pedido = {
        "total_centavos": 1_000_000,
        "items": [{"seccion": "comidas", "cantidad": 1, "precio_unitario_centavos": 1_000_000}],
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
        pago = PagoPos(receptor="comidas_efectivo_en_transito", medio_pago="efectivo", importe_centavos=1_000_000)
        registrar_pagos(db, 1, 1, [pago])
        assert estado_cuenta(db, 1, pedido)["saldo_pendiente_centavos"] == 0
        assert efectivo_en_transito(db, 1) == 1_000_000
        assert len(resumen_libro(db)["receptores"]) == 1
        entrada = RendicionEntrada(id_solicitud=uuid4(), importe_centavos=600_000, motivo="Recepción de efectivo")
        recibo = registrar_rendicion(db, 1, entrada, {"id_usuario": 1})
        assert registrar_rendicion(db, 1, entrada, {"id_usuario": 1}) == recibo
        assert efectivo_en_transito(db, 1) == 400_000
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
