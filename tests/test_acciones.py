from fastapi.testclient import TestClient

from api import app
from database import obtener_conexion


client = TestClient(app)


def crear_producto(
    nombre,
    categoria,
    precio,
    stock,
    controla_stock
):
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
            stock,
            precio_venta,
            controla_stock
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            nombre,
            categoria,
            "Unidad",
            1,
            "unidad",
            1,
            stock,
            precio,
            int(controla_stock),
        )
    )

    id_producto = cursor.lastrowid

    conexion.commit()
    conexion.close()

    return id_producto


def test_accion_registrar_venta_estructurada(
    base_prueba
):
    id_producto = crear_producto(
        nombre="Manaos Cola 600ml",
        categoria="Bebidas",
        precio=1300,
        stock=6,
        controla_stock=True,
    )

    respuesta = client.post(
        "/acciones",
        json={
            "accion": "registrar_venta",
            "datos": {
                "producto": "manaos cola 600",
                "cantidad": 2,
            }
        }
    )

    assert respuesta.status_code == 200

    datos = respuesta.json()

    assert datos["ok"] is True
    assert datos["codigo"] == "ACCION_VENTA_REGISTRADA"
    assert datos["datos"]["producto"] == "Manaos Cola 600ml"
    assert datos["datos"]["cantidad"] == 2
    assert datos["datos"]["precio_unitario"] == 1300
    assert datos["datos"]["total"] == 2600
    assert datos["datos"]["stock_restante"] == 4

    conexion = obtener_conexion()

    stock = conexion.execute(
        "SELECT stock FROM productos WHERE id_producto = ?",
        (id_producto,)
    ).fetchone()[0]

    conexion.close()

    assert stock == 4


def test_accion_consultar_stock(
    base_prueba
):
    crear_producto(
        nombre="Pepsi lata",
        categoria="Bebidas",
        precio=1600,
        stock=8,
        controla_stock=True,
    )

    crear_producto(
        nombre="Big mac doble",
        categoria="Hamburguesas",
        precio=9000,
        stock=0,
        controla_stock=False,
    )

    respuesta = client.post(
        "/acciones",
        json={
            "accion": "consultar_stock",
            "datos": {}
        }
    )

    assert respuesta.status_code == 200

    productos = respuesta.json()["datos"]["productos"]

    nombres = [
        producto["nombre"]
        for producto in productos
    ]

    assert "Pepsi lata" in nombres
    assert "Big mac doble" not in nombres


def test_accion_consultar_precio_producto(
    base_prueba
):
    crear_producto(
        nombre="Oreo",
        categoria="Postres",
        precio=4500,
        stock=3,
        controla_stock=True,
    )

    respuesta = client.post(
        "/acciones",
        json={
            "accion": "consultar_precios",
            "datos": {
                "producto": "postre oreo"
            }
        }
    )

    assert respuesta.status_code == 200

    producto = (
        respuesta
        .json()["datos"]["productos"][0]
    )

    assert producto["nombre"] == "Oreo"
    assert producto["precio_venta"] == 4500


def test_accion_inexistente_devuelve_400(
    base_prueba
):
    respuesta = client.post(
        "/acciones",
        json={
            "accion": "hacer_magia",
            "datos": {}
        }
    )

    assert respuesta.status_code == 400

    datos = respuesta.json()

    assert datos["ok"] is False
    assert datos["codigo"] == "ACCION_NO_RECONOCIDA"


def test_accion_manaos_cola_sin_tamano_asume_grande(
    base_prueba
):
    crear_producto(
        nombre="Manaos Cola 600ml",
        categoria="Bebidas",
        precio=1300,
        stock=10,
        controla_stock=True,
    )

    crear_producto(
        nombre="Manaos Cola 2.25l",
        categoria="Bebidas",
        precio=2000,
        stock=10,
        controla_stock=True,
    )

    respuesta = client.post(
        "/acciones",
        json={
            "accion": "registrar_venta",
            "datos": {
                "producto": "manaos cola",
                "cantidad": 1,
            }
        }
    )

    assert respuesta.status_code == 200

    datos = respuesta.json()

    assert datos["ok"] is True
    assert datos["codigo"] == "ACCION_VENTA_REGISTRADA"
    assert datos["datos"]["producto"] == "Manaos Cola 2.25l"
    assert datos["datos"]["precio_unitario"] == 2000
    assert datos["datos"]["stock_restante"] == 9
