from fastapi.testclient import TestClient

from api import app
from database import obtener_conexion


client = TestClient(app)


def _crear_producto(
    nombre,
    categoria,
    precio,
    stock=20,
    controla_stock=True,
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


def test_caja_bebidas_postres_separa_recaudacion_y_compras(
    base_prueba
):
    bebida = _crear_producto(
        "Bebida prueba",
        "Bebidas",
        2000,
    )
    postre = _crear_producto(
        "Postre prueba",
        "Postres",
        4500,
    )
    comida = _crear_producto(
        "Comida prueba",
        "Hamburguesas",
        8000,
        controla_stock=False,
    )

    assert client.post(
        "/ventas",
        json={
            "id_producto": bebida,
            "cantidad": 2,
            "precio_unitario": 2000,
        }
    ).status_code == 201

    assert client.post(
        "/ventas",
        json={
            "id_producto": postre,
            "cantidad": 1,
            "precio_unitario": 4500,
        }
    ).status_code == 201

    assert client.post(
        "/ventas",
        json={
            "id_producto": comida,
            "cantidad": 1,
            "precio_unitario": 8000,
        }
    ).status_code == 201

    assert client.post(
        "/compras",
        json={
            "id_producto": bebida,
            "cantidad": 6,
            "precio_unitario": 1000,
        }
    ).status_code == 201

    respuesta = client.post(
        "/comandos",
        json={
            "mensaje": "caja bebidas postres"
        }
    )

    assert respuesta.status_code == 200

    datos = respuesta.json()

    assert datos["seccion"] == "bebidas_postres"
    assert datos["recaudado_bebidas"] == 4000
    assert datos["recaudado_postres"] == 4500
    assert datos["ventas"] == 8500
    assert datos["compras_directas"] == 6000
    assert datos["saldo_operativo"] == 2500


def test_recaudado_por_categoria_no_mezcla_secciones(
    base_prueba
):
    bebida = _crear_producto(
        "Bebida prueba",
        "Bebidas",
        2000,
    )
    postre = _crear_producto(
        "Postre prueba",
        "Postres",
        4500,
    )
    comida = _crear_producto(
        "Comida prueba",
        "Sanguches",
        6000,
        controla_stock=False,
    )

    for id_producto, precio in (
        (bebida, 2000),
        (postre, 4500),
        (comida, 6000),
    ):
        respuesta = client.post(
            "/ventas",
            json={
                "id_producto": id_producto,
                "cantidad": 1,
                "precio_unitario": precio,
            }
        )

        assert respuesta.status_code == 201

    bebidas = client.post(
        "/comandos",
        json={
            "mensaje": "recaudado bebidas"
        }
    ).json()

    postres = client.post(
        "/comandos",
        json={
            "mensaje": "cuanta plata recaude en postres"
        }
    ).json()

    comidas = client.post(
        "/comandos",
        json={
            "mensaje": "ventas comidas"
        }
    ).json()

    assert bebidas["total"] == 2000
    assert postres["total"] == 4500
    assert comidas["total"] == 6000


def test_caja_comidas_excluye_bebidas_y_postres(
    base_prueba
):
    bebida = _crear_producto(
        "Bebida prueba",
        "Bebidas",
        2000,
    )
    comida = _crear_producto(
        "Comida prueba",
        "Al plato",
        9500,
        controla_stock=False,
    )

    client.post(
        "/ventas",
        json={
            "id_producto": bebida,
            "cantidad": 1,
            "precio_unitario": 2000,
        }
    )

    client.post(
        "/ventas",
        json={
            "id_producto": comida,
            "cantidad": 2,
            "precio_unitario": 9500,
        }
    )

    respuesta = client.get(
        "/caja/secciones/comidas"
    )

    assert respuesta.status_code == 200

    datos = respuesta.json()["datos"]

    assert datos["seccion"] == "comidas"
    assert datos["ventas"] == 19000
    assert datos["recaudado_comidas"] == 19000
