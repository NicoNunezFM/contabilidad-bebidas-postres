
from fastapi.testclient import TestClient

from api import app
from database import obtener_conexion
from pos_auth import generar_hash


def test_precio_adicional_con_permisos(base_prueba):
    conexion = obtener_conexion()

    try:
        conexion.execute(
            """
            UPDATE adicionales_catalogo
            SET precio_venta = 600,
                costo_unitario = 250
            WHERE nombre = 'huevo'
            """
        )

        id_huevo = conexion.execute(
            """
            SELECT id_adicional_catalogo
            FROM adicionales_catalogo
            WHERE nombre = 'huevo'
            """
        ).fetchone()[0]

        for nombre, rol, clave in (
            ("admin", "admin", "AdminPrueba123!"),
            ("ventas", "ventas", "VentasPrueba123!"),
        ):
            conexion.execute(
                """
                INSERT INTO usuarios_pos
                    (usuario, rol, password_hash)
                VALUES (?, ?, ?)
                """,
                (nombre, rol, generar_hash(clave))
            )

        conexion.commit()

    finally:
        conexion.close()

    cliente = TestClient(app)
    origen = {"Origin": "http://testserver"}

    ruta = f"/pos-api/admin/adicionales/{id_huevo}/precio"
    datos = {"precio_nuevo": 800}

    # Sin sesión: no autorizado.
    assert cliente.patch(
        ruta, json=datos, headers=origen
    ).status_code == 401

    # Iniciar sesión de ventas.
    cliente.post(
        "/pos-api/login",
        json={
            "usuario": "ventas",
            "contrasena": "VentasPrueba123!"
        },
        headers=origen
    )

    # Ventas no puede cambiar precios.
    assert cliente.patch(
        ruta, json=datos, headers=origen
    ).status_code == 403

    # Iniciar sesión como administrador.
    cliente.post(
        "/pos-api/login",
        json={
            "usuario": "admin",
            "contrasena": "AdminPrueba123!"
        },
        headers=origen
    )

    # Sin encabezado de origen: rechazado.
    assert cliente.patch(
        ruta, json=datos
    ).status_code == 403

    # Actualización autorizada.
    respuesta = cliente.patch(
        ruta, json=datos, headers=origen
    )

    assert respuesta.status_code == 200

    resultado = respuesta.json()

    assert resultado["ok"] is True
    assert resultado["precio_anterior"] == 600
    assert resultado["precio_nuevo"] == 800
    assert resultado["modificado_por"] == "admin"

    # No se admiten precios negativos ni decimales.
    assert cliente.patch(
        ruta,
        json={"precio_nuevo": -100},
        headers=origen
    ).status_code == 422

    assert cliente.patch(
        ruta,
        json={"precio_nuevo": 100.5},
        headers=origen
    ).status_code == 422

    conexion = obtener_conexion()

    try:
        precio, costo = conexion.execute(
            """
            SELECT precio_venta, costo_unitario
            FROM adicionales_catalogo
            WHERE id_adicional_catalogo = ?
            """,
            (id_huevo,)
        ).fetchone()

        historial = conexion.execute(
            """
            SELECT precio_anterior, precio_nuevo
            FROM historial_precios_adicionales_pos
            WHERE id_adicional_catalogo = ?
            """,
            (id_huevo,)
        ).fetchall()

        assert precio == 800
        assert costo == 250
        assert historial == [(600, 800)]

    finally:
        conexion.close()
