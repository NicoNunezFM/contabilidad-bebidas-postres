import sqlite3

from backups import crear_backup_diario
from database import obtener_conexion


def test_crea_backup_diario_y_no_lo_duplica(
    base_prueba
):
    conexion = obtener_conexion()

    conexion.execute(
        """
        INSERT INTO productos (
            nombre,
            categoria,
            stock
        )
        VALUES (?, ?, ?)
        """,
        (
            "Producto backup",
            "Prueba",
            7,
        )
    )

    conexion.commit()
    conexion.close()

    primero = crear_backup_diario()

    assert primero["ok"] is True
    assert primero["creado"] is True

    ruta_backup = primero["ruta"]

    conexion_backup = sqlite3.connect(
        ruta_backup
    )

    cantidad = conexion_backup.execute(
        """
        SELECT COUNT(*)
        FROM productos
        WHERE nombre = ?
        """,
        ("Producto backup",)
    ).fetchone()[0]

    conexion_backup.close()

    assert cantidad == 1

    segundo = crear_backup_diario()

    assert segundo["ok"] is True
    assert segundo["creado"] is False
    assert segundo["ruta"] == ruta_backup
