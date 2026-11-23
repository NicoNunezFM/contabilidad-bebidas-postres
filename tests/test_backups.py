import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path

import backups

from backups import crear_backup_diario
from database import obtener_conexion


def test_respaldo_wal_restaurable_y_publicado_una_vez(base_prueba, tmp_path):
    with closing(obtener_conexion()) as origen:
        assert origen.execute("PRAGMA journal_mode=WAL").fetchone() == ("wal",)
        origen.execute("INSERT INTO productos (nombre, categoria, stock) VALUES ('Ficticio', 'Bebidas', 5)")
        origen.commit()
        assert base_prueba.with_name(base_prueba.name + "-wal").exists()

        with ThreadPoolExecutor(max_workers=2) as pool:
            resultados = list(pool.map(lambda _: crear_backup_diario(), range(2)))
        assert all(resultado["ok"] for resultado in resultados), resultados
        assert sum(resultado["creado"] for resultado in resultados) == 1

        respaldo = Path(resultados[0]["ruta"])
        assert not list(respaldo.parent.glob("*.tmp"))
        with closing(sqlite3.connect(respaldo)) as copia, closing(
            sqlite3.connect(tmp_path / "restaurada-ficticia.db")
        ) as restaurada:
            copia.backup(restaurada)
            assert restaurada.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
            assert not restaurada.execute("PRAGMA foreign_key_check").fetchall()
            assert restaurada.execute("SELECT stock FROM productos").fetchall() == [(5,)]


def test_error_de_publicacion_permite_reintentar(base_prueba, monkeypatch):
    def bloquear_publicacion(*args):
        raise PermissionError("Fallo simulado al publicar")

    with monkeypatch.context() as m:
        m.setattr(backups, "_publicar_respaldo", bloquear_publicacion)
        assert crear_backup_diario()["codigo"] == "ERROR_BACKUP"
        assert not list(backups.obtener_directorio_backups().iterdir())
    assert crear_backup_diario()["creado"] is True


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
