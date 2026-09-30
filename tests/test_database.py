import sqlite3

import pytest

from database import obtener_conexion


def test_sqlite_exige_claves_foraneas(base_prueba):
    conexion = obtener_conexion()

    estado_fk = conexion.execute(
        "PRAGMA foreign_keys"
    ).fetchone()[0]

    assert estado_fk == 1

    with pytest.raises(sqlite3.IntegrityError):
        conexion.execute(
            """
            INSERT INTO ventas (
                id_producto,
                fecha,
                cantidad,
                precio_unitario
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                999999,
                "2026-09-30",
                1,
                1000,
            ),
        )
        conexion.commit()

    conexion.close()