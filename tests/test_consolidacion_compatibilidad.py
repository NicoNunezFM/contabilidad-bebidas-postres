"""Frontera con cajas legadas: no son una instalación POS ni se migran al leer."""
from contextlib import closing
import hashlib
import sqlite3

from fastapi import HTTPException
import pytest

from database import obtener_conexion
from pos_simulacion import transaccion_simulacion


@pytest.mark.parametrize("con_aperturas", [False, True])
def test_pos_rechaza_base_legada_sin_reinterpretar_aperturas(base_prueba, monkeypatch, con_aperturas):
    # Reproduce sólo el contrato estructural de la rama lateral, con valores inventados.
    with closing(obtener_conexion()) as db, db:
        if con_aperturas:
            db.execute("""CREATE TABLE saldos_iniciales_caja (
                id_saldo_inicial INTEGER PRIMARY KEY, seccion TEXT NOT NULL,
                monto REAL NOT NULL, fecha_hora TEXT NOT NULL,
                id_venta_corte INTEGER NOT NULL DEFAULT 0,
                id_compra_corte INTEGER NOT NULL DEFAULT 0,
                id_gasto_corte INTEGER NOT NULL DEFAULT 0,
                id_movimiento_caja_corte INTEGER NOT NULL DEFAULT 0)""")
            db.executemany("INSERT INTO saldos_iniciales_caja VALUES (?,?,?,'2026-01-01',0,0,0,0)",
                           [(1, "rotiseria", 123), (2, "bebidas_postres", 456)])
    antes = hashlib.sha256(base_prueba.read_bytes()).hexdigest()
    monkeypatch.setenv("POS_V1_SIMULACION", "1")
    with pytest.raises(HTTPException) as error:
        with transaccion_simulacion(escritura=True):
            pytest.fail("Una base legada no debe admitirse como POS")
    assert error.value.status_code == 404
    assert hashlib.sha256(base_prueba.read_bytes()).hexdigest() == antes
    with closing(sqlite3.connect(base_prueba.as_uri() + "?mode=ro", uri=True)) as db:
        assert db.execute("PRAGMA application_id").fetchone()[0] == 0
        assert not db.execute("SELECT 1 FROM sqlite_schema WHERE name='pos_saldos_iniciales'").fetchone()
        if con_aperturas:
            assert db.execute("SELECT SUM(monto) FROM saldos_iniciales_caja").fetchone()[0] == 579
