import pytest
from fastapi.testclient import TestClient

from api import app
from database import obtener_conexion


client = TestClient(app)


def _crear_bebida(
    nombre,
    precio_venta,
    unidades_por_pack,
    stock=0,
):
    conexion = obtener_conexion()

    conexion.execute(
        """
        INSERT INTO productos (
            nombre,
            categoria,
            presentacion,
            contenido,
            unidad_medida,
            unidades_por_pack,
            stock,
            precio_venta,
            controla_stock
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            nombre,
            "Bebidas",
            "Unidad",
            1,
            "unidad",
            unidades_por_pack,
            stock,
            precio_venta,
            1,
        )
    )

    conexion.commit()
    conexion.close()


def test_compra_dos_packs_manaos_grande_suma_12_unidades(
    base_prueba
):
    _crear_bebida(
        "Manaos Cola 2.25l",
        2000,
        6,
        stock=3,
    )

    respuesta = client.post(
        "/comandos",
        json={
            "mensaje": (
                "compra 2 packs manaos cola por 17000"
            )
        }
    )

    assert respuesta.status_code == 200

    datos = respuesta.json()

    assert datos["ok"] is True
    assert (
        datos["codigo"]
        == "COMANDO_COMPRA_PACK_REGISTRADA"
    )
    assert datos["producto"] == "Manaos Cola 2.25l"
    assert datos["cantidad_packs"] == 2
    assert datos["unidades_por_pack"] == 6
    assert datos["cantidad_unidades"] == 12
    assert datos["total"] == 17000
    assert datos["stock_actual"] == 15

    conexion = obtener_conexion()

    compra = conexion.execute(
        """
        SELECT cantidad, precio_unitario
        FROM compras
        WHERE anulada = 0
        """
    ).fetchone()

    stock = conexion.execute(
        """
        SELECT stock
        FROM productos
        WHERE nombre = ?
        """,
        ("Manaos Cola 2.25l",)
    ).fetchone()[0]

    conexion.close()

    assert compra[0] == 12
    assert compra[1] == pytest.approx(
        17000 / 12
    )
    assert stock == 15

    caja = client.get("/caja").json()

    assert caja["compras"] == pytest.approx(
        17000
    )


def test_compra_pack_manaos_chica_suma_12_unidades(
    base_prueba
):
    _crear_bebida(
        "Manaos Cola 600ml",
        1300,
        12,
        stock=0,
    )

    respuesta = client.post(
        "/comandos",
        json={
            "mensaje": (
                "compra 1 pack manaos cola chica "
                "a 8500 cada pack"
            )
        }
    )

    assert respuesta.status_code == 200

    datos = respuesta.json()

    assert datos["producto"] == "Manaos Cola 600ml"
    assert datos["cantidad_packs"] == 1
    assert datos["unidades_por_pack"] == 12
    assert datos["cantidad_unidades"] == 12
    assert datos["total"] == 8500
    assert datos["stock_actual"] == 12


def test_compra_pack_sin_costo_no_modifica_stock(
    base_prueba
):
    _crear_bebida(
        "Manaos Cola 2.25l",
        2000,
        6,
        stock=4,
    )

    respuesta = client.post(
        "/comandos",
        json={
            "mensaje": "compra 2 packs manaos cola"
        }
    )

    assert respuesta.status_code == 400

    datos = respuesta.json()

    assert datos["ok"] is False
    assert (
        datos["codigo"]
        == "COSTO_COMPRA_REQUERIDO"
    )

    conexion = obtener_conexion()

    stock = conexion.execute(
        """
        SELECT stock
        FROM productos
        WHERE nombre = ?
        """,
        ("Manaos Cola 2.25l",)
    ).fetchone()[0]

    compras = conexion.execute(
        "SELECT COUNT(*) FROM compras"
    ).fetchone()[0]

    conexion.close()

    assert stock == 4
    assert compras == 0
