
from database import obtener_conexion

from fastapi.testclient import TestClient
from api import app
from pos_auth import generar_hash


def test_consultar_personalizaciones_pos(producto_prueba):
    conexion = obtener_conexion()

    try:
        # Configurar precios y disponibilidad de prueba.
        conexion.execute(
            """
            UPDATE adicionales_catalogo
            SET precio_venta = 600
            WHERE nombre = 'huevo'
            """
        )

        conexion.execute(
            """
            UPDATE adicionales_catalogo
            SET activo = 0
            WHERE nombre = 'cheddar'
            """
        )

        filas = conexion.execute(
            """
            SELECT id_adicional_catalogo, nombre
            FROM adicionales_catalogo
            WHERE nombre IN ('huevo', 'cheddar')
            """
        ).fetchall()

        ids = {nombre: identificador for identificador, nombre in filas}

        # Asociar dos ingredientes al producto.
        for ingrediente in ("Tomate", "Lechuga"):
            conexion.execute(
                """
                INSERT INTO pos_ingredientes_producto
                    (id_producto, ingrediente)
                VALUES (?, ?)
                """,
                (producto_prueba, ingrediente)
            )

        # Asociar dos extras, uno de ellos inactivo.
        for nombre in ("huevo", "cheddar"):
            conexion.execute(
                """
                INSERT INTO pos_adicionales_producto
                    (id_producto, id_adicional_catalogo)
                VALUES (?, ?)
                """,
                (producto_prueba, ids[nombre])
            )

        conexion.commit()

    finally:
        conexion.close()

    cliente = TestClient(app)

    ruta = (
        f"/pos-api/catalogo/productos/"
        f"{producto_prueba}/personalizaciones"
    )

    respuesta = cliente.get(ruta)

    assert respuesta.status_code == 200

    datos = respuesta.json()

    assert datos["ok"] is True
    assert datos["id_producto"] == producto_prueba

    assert datos["ingredientes"] == [
        "Lechuga",
        "Tomate"
    ]

    # Huevo aparece con su precio configurado.
    assert datos["adicionales"] == [
        {
            "id_adicional_catalogo": ids["huevo"],
            "nombre": "huevo",
            "precio_venta": 600
        }
    ]

    # Un producto inexistente devuelve 404.
    respuesta = cliente.get(
        "/pos-api/catalogo/productos/999999/personalizaciones"
    )

    assert respuesta.status_code == 404



def test_personalizaciones_por_producto(producto_prueba):
    conexion = obtener_conexion()

    try:
        # Buscar el ID real del adicional "huevo".
        adicional = conexion.execute(
            """
            SELECT id_adicional_catalogo
            FROM adicionales_catalogo
            WHERE nombre = 'huevo'
            """
        ).fetchone()

        assert adicional is not None

        id_huevo = adicional[0]

        # Definir ingredientes de un producto de prueba.
        conexion.execute(
            """
            INSERT INTO pos_ingredientes_producto
                (id_producto, ingrediente)
            VALUES (?, ?)
            """,
            (producto_prueba, "Tomate")
        )

        conexion.execute(
            """
            INSERT INTO pos_ingredientes_producto
                (id_producto, ingrediente)
            VALUES (?, ?)
            """,
            (producto_prueba, "Lechuga")
        )

        # Asociar el adicional huevo al mismo producto.
        conexion.execute(
            """
            INSERT INTO pos_adicionales_producto
                (id_producto, id_adicional_catalogo)
            VALUES (?, ?)
            """,
            (producto_prueba, id_huevo)
        )

        conexion.commit()

        ingredientes = conexion.execute(
            """
            SELECT ingrediente
            FROM pos_ingredientes_producto
            WHERE id_producto = ?
            ORDER BY ingrediente
            """,
            (producto_prueba,)
        ).fetchall()

        adicionales = conexion.execute(
            """
            SELECT id_adicional_catalogo
            FROM pos_adicionales_producto
            WHERE id_producto = ?
            """,
            (producto_prueba,)
        ).fetchall()

        assert ingredientes == [
            ("Lechuga",),
            ("Tomate",)
        ]

        assert adicionales == [(id_huevo,)]

    finally:
        conexion.close()


def test_admin_configura_personalizaciones(producto_prueba):
    conexion = obtener_conexion()

    try:
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

        id_huevo = conexion.execute(
            """
            SELECT id_adicional_catalogo
            FROM adicionales_catalogo
            WHERE nombre = 'huevo'
            """
        ).fetchone()[0]

        conexion.commit()

    finally:
        conexion.close()

    cliente = TestClient(app)
    origen = {"Origin": "http://testserver"}

    ruta = (
        f"/pos-api/admin/productos/"
        f"{producto_prueba}/personalizaciones"
    )

    datos = {
        "ingredientes": ["Tomate", "Lechuga"],
        "ids_adicionales": [id_huevo]
    }

    # Sin sesión: 401.
    assert cliente.put(
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

    # Ventas no puede modificar.
    assert cliente.put(
        ruta, json=datos, headers=origen
    ).status_code == 403

    # Iniciar sesión administrativa.
    cliente.post(
        "/pos-api/login",
        json={
            "usuario": "admin",
            "contrasena": "AdminPrueba123!"
        },
        headers=origen
    )

    respuesta = cliente.put(
        ruta, json=datos, headers=origen
    )

    assert respuesta.status_code == 200
    assert respuesta.json()["modificado_por"] == "admin"

    # Comprobar que quedaron guardadas las opciones.
    consulta = cliente.get(
        f"/pos-api/catalogo/productos/"
        f"{producto_prueba}/personalizaciones"
    )

    assert consulta.status_code == 200

    configuracion = consulta.json()

    assert configuracion["ingredientes"] == [
        "Lechuga",
        "Tomate"
    ]

    assert len(configuracion["adicionales"]) == 1
    assert configuracion["adicionales"][0]["nombre"] == "huevo"

    # Un extra inexistente debe ser rechazado.
    invalida = cliente.put(
        ruta,
        json={
            "ingredientes": [],
            "ids_adicionales": [999999]
        },
        headers=origen
    )

    assert invalida.status_code == 422

    # El rechazo no debe borrar la configuración anterior.
    consulta = cliente.get(
        f"/pos-api/catalogo/productos/"
        f"{producto_prueba}/personalizaciones"
    )

    assert consulta.json()["ingredientes"] == [
        "Lechuga",
        "Tomate"
    ]
