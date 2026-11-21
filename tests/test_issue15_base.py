"""Verificación de los límites del libro en la base del Issue #15."""
import sqlite3
from contextlib import closing

import pytest
from pydantic import ValidationError

from pos_cobros import PagoPos, crear_libro, estado_cuenta, registrar_movimiento


@pytest.mark.parametrize(
    "receptor, medio",
    [("efectivo_en_transito", "efectivo"), ("obligacion_reparto", "transferencia")],
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
        db.execute("CREATE TABLE usuarios_pos (id_usuario INTEGER PRIMARY KEY)")
        db.execute("CREATE TABLE pos_ventas_simuladas (id_venta INTEGER PRIMARY KEY)")
        db.execute("INSERT INTO usuarios_pos VALUES (1)")
        db.execute("INSERT INTO pos_ventas_simuladas VALUES (1)")
        db.execute("PRAGMA foreign_keys = ON")
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
