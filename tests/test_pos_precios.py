from fastapi.testclient import TestClient
from api import app
from pos_auth import generar_hash
from database import obtener_conexion


def test_actualizacion_precio_pos(producto_prueba):
    conexion = obtener_conexion()

    try:
        conexion.execute(
            """
            UPDATE productos
            SET precio_venta = 8000
            WHERE id_producto = ?
            """,
            (producto_prueba,)
        )

        # Una venta histórica de prueba.
        cursor = conexion.execute(
            """
            INSERT INTO ventas (
                id_producto, fecha, cantidad, precio_unitario
            )
            VALUES (?, ?, ?, ?)
            """,
            (producto_prueba, "2026-11-11", 1, 8000)
        )
        id_venta = cursor.lastrowid

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

    ruta = f"/pos-api/admin/productos/{producto_prueba}/precio"
    datos = {"precio_nuevo": 8500}

    # Sin sesión: acceso rechazado.
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

    # Ventas no puede modificar precios.
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

    # El administrador puede actualizarlo.
    respuesta = cliente.patch(
        ruta, json=datos, headers=origen
    )

    assert respuesta.status_code == 200
    assert respuesta.json()["precio_anterior"] == 8000
    assert respuesta.json()["precio_nuevo"] == 8500
    assert respuesta.json()["modificado_por"] == "admin"

    conexion = obtener_conexion()

    try:
        precio_actual = conexion.execute(
            """
            SELECT precio_venta
            FROM productos
            WHERE id_producto = ?
            """,
            (producto_prueba,)
        ).fetchone()[0]

        historial = conexion.execute(
            """
            SELECT precio_anterior, precio_nuevo
            FROM historial_precios_pos
            WHERE id_producto = ?
            """,
            (producto_prueba,)
        ).fetchone()

        precio_venta_anterior = conexion.execute(
            """
            SELECT precio_unitario
            FROM ventas
            WHERE id_venta = ?
            """,
            (id_venta,)
        ).fetchone()[0]

        assert precio_actual == 8500
        assert historial == (8000, 8500)

        # La venta histórica mantiene su precio.
        assert precio_venta_anterior == 8000

    finally:
        conexion.close()


def test_historial_precios_pos(base_prueba):
    conexion = obtener_conexion()

    try:
        tabla = conexion.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name = 'historial_precios_pos'
            """
        ).fetchone()

        assert tabla is not None

        columnas = conexion.execute(
            "PRAGMA table_info(historial_precios_pos)"
        ).fetchall()

        nombres = {columna[1] for columna in columnas}

        assert {
            "id_producto",
            "id_usuario",
            "precio_anterior",
            "precio_nuevo",
            "fecha_hora"
        }.issubset(nombres)

        cambios = conexion.execute(
            "SELECT COUNT(*) FROM historial_precios_pos"
        ).fetchone()[0]

        assert cambios == 0

    finally:
        conexion.close()

