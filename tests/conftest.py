import sys
from pathlib import Path

import pytest


RUTA_SRC = Path(__file__).resolve().parents[1] / "src"

if str(RUTA_SRC) not in sys.path:
    sys.path.insert(0, str(RUTA_SRC))


from database import (
    inicializar_base_de_datos,
    obtener_conexion,
)


@pytest.fixture
def base_prueba(tmp_path, monkeypatch):

    ruta_db = tmp_path / "negocio_test.db"

    monkeypatch.setenv(
        "NEGOCIO_DB_PATH",
        str(ruta_db)
    )

    inicializar_base_de_datos()

    return ruta_db


@pytest.fixture
def producto_prueba(base_prueba):

    conexion = obtener_conexion()

    cursor = conexion.execute(
        """
        INSERT INTO productos (
            nombre,
            categoria,
            presentacion,
            contenido,
            unidad_medida,
            unidades_por_pack,
            stock
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "Coca prueba",
            "Bebidas",
            "Botella",
            2.0,
            "Litros",
            6,
            10
        )
    )

    id_producto = cursor.lastrowid

    conexion.commit()
    conexion.close()

    return id_producto