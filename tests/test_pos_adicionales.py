
from fastapi.testclient import TestClient

from api import app
from database import obtener_conexion
from pos_auth import crear_sesion_pos


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

        id_usuario = conexion.execute(
            "INSERT INTO usuarios_pos(usuario,rol,password_hash) VALUES('lector ficticio','ventas','prueba')"
        ).lastrowid
        conexion.commit()

    finally:
        conexion.close()

    cliente = TestClient(app)
    assert cliente.get('/pos-api/catalogo/adicionales').status_code == 401
    cliente.cookies.set('abadion_pos_ventas', crear_sesion_pos(id_usuario), path='/pos-api')

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
