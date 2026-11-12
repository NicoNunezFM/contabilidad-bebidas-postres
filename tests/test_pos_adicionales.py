
from fastapi.testclient import TestClient

from api import app
from database import obtener_conexion


def test_consultar_adicionales_pos(base_prueba):
    conexion = obtener_conexion()

    try:
        conexion.execute(
            """
            UPDATE adicionales_catalogo
            SET precio_venta = ?, costo_unitario = ?
            WHERE nombre = ?
            """,
            (600, 250, "huevo")
        )

        conexion.execute(
            """
            UPDATE adicionales_catalogo
            SET activo = 0
            WHERE nombre = ?
            """,
            ("cheddar",)
        )

        conexion.commit()

    finally:
        conexion.close()

    cliente = TestClient(app)

    respuesta = cliente.get(
        "/pos-api/catalogo/adicionales"
    )

    assert respuesta.status_code == 200

    datos = respuesta.json()

    assert datos["ok"] is True
    assert datos["cantidad"] == len(datos["adicionales"])

    nombres = [
        adicional["nombre"]
        for adicional in datos["adicionales"]
    ]

    assert "huevo" in nombres
    assert "cheddar" not in nombres

    huevo = next(
        adicional
        for adicional in datos["adicionales"]
        if adicional["nombre"] == "huevo"
    )

    assert huevo["precio_venta"] == 600

    # No exponer costos internos ni otros datos.
    assert set(huevo) == {
        "id_adicional_catalogo",
        "nombre",
        "precio_venta"
    }
