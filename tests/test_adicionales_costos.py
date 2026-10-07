import pytest
from fastapi.testclient import TestClient

from api import app
from database import obtener_conexion


client = TestClient(app)


def _crear_producto(
    nombre,
    categoria,
    precio,
    stock=0,
    controla_stock=False,
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


def test_configurar_y_listar_adicional(
    base_prueba
):
    respuesta = client.post(
        "/comandos",
        json={
            "mensaje": (
                "adicional huevo precio 1000 costo 300"
            )
        }
    )

    assert respuesta.status_code == 200

    datos = respuesta.json()

    assert datos["codigo"] == "COMANDO_ADICIONAL_CONFIGURADO"
    assert datos["nombre"] == "huevo"
    assert datos["precio_venta"] == 1000
    assert datos["costo_unitario"] == 300

    listado = client.post(
        "/comandos",
        json={"mensaje": "adicionales"}
    )

    assert listado.status_code == 200

    adicionales = {
        item["nombre"]: item
        for item in listado.json()["adicionales"]
    }

    assert adicionales["huevo"]["precio_venta"] == 1000
    assert adicionales["huevo"]["costo_unitario"] == 300


def test_venta_usa_precio_y_costo_configurado_del_adicional(
    base_prueba
):
    _crear_producto(
        "Producto extra",
        "Hamburguesas",
        5000,
        controla_stock=False,
    )

    configurar = client.post(
        "/comandos",
        json={
            "mensaje": (
                "adicional huevo precio 1000 costo 300"
            )
        }
    )

    assert configurar.status_code == 200

    respuesta = client.post(
        "/comandos",
        json={
            "mensaje": (
                "venta 1 producto extra con 2 huevos"
            )
        }
    )

    assert respuesta.status_code == 200

    datos = respuesta.json()

    assert datos["total"] == 7000
    assert len(datos["adicionales"]) == 1

    adicional = datos["adicionales"][0]
    adicional_detalle = datos["adicionales_detalle"][0]

    assert adicional == {
        "descripcion": "huevo",
        "cantidad": 2,
        "precio_total": 2000.0,
    }
    assert adicional_detalle["costo_unitario_snapshot"] == 300
    assert (
        adicional_detalle["fuente_costo_snapshot"]
        == "catálogo de adicionales"
    )

    conexion = obtener_conexion()

    fila = conexion.execute(
        """
        SELECT
            descripcion,
            cantidad,
            precio_total,
            costo_unitario_snapshot,
            fuente_costo_snapshot
        FROM venta_adicionales
        """
    ).fetchone()

    conexion.close()

    assert fila == (
        "huevo",
        2,
        2000.0,
        300.0,
        "catálogo de adicionales",
    )


def test_precio_explicito_del_adicional_pisa_precio_catalogo(
    base_prueba
):
    _crear_producto(
        "Producto promo",
        "Hamburguesas",
        5000,
        controla_stock=False,
    )

    assert client.post(
        "/comandos",
        json={
            "mensaje": (
                "adicional huevo precio 1000 costo 300"
            )
        }
    ).status_code == 200

    respuesta = client.post(
        "/comandos",
        json={
            "mensaje": (
                "venta 1 producto promo con 2 huevos (1500)"
            )
        }
    )

    assert respuesta.status_code == 200

    datos = respuesta.json()

    assert datos["total"] == 6500
    assert datos["adicionales"][0]["precio_total"] == 1500
    assert (
        datos["adicionales_detalle"][0]["costo_unitario_snapshot"]
        == 300
    )


def test_adicional_sin_precio_configurado_sigue_pidiendo_precio(
    base_prueba
):
    _crear_producto(
        "Producto cheddar",
        "Hamburguesas",
        5000,
        controla_stock=False,
    )

    respuesta = client.post(
        "/comandos",
        json={
            "mensaje": (
                "venta 1 producto cheddar con cheddar"
            )
        }
    )

    assert respuesta.status_code == 400

    datos = respuesta.json()

    assert datos["codigo"] == "PRECIO_ADICIONAL_REQUERIDO"


def test_rentabilidad_historica_incluye_costo_del_adicional(
    base_prueba
):
    producto = _crear_producto(
        "Bebida extra test",
        "Bebidas",
        2000,
        stock=0,
        controla_stock=True,
    )

    compra = client.post(
        "/compras",
        json={
            "id_producto": producto,
            "cantidad": 5,
            "precio_unitario": 1000,
        }
    )

    assert compra.status_code == 201

    assert client.post(
        "/comandos",
        json={
            "mensaje": (
                "adicional huevo precio 500 costo 200"
            )
        }
    ).status_code == 200

    venta = client.post(
        "/comandos",
        json={
            "mensaje": (
                "venta 1 bebida extra test con huevo"
            )
        }
    )

    assert venta.status_code == 200

    rentabilidad = client.post(
        "/comandos",
        json={
            "mensaje": "rentabilidad bebida extra test"
        }
    )

    assert rentabilidad.status_code == 200

    datos = rentabilidad.json()

    assert datos["rentabilidad_historica_exacta"] is True
    assert datos["ingresos"] == 2500
    assert datos["costo_ventas_historico"] == pytest.approx(1200)
    assert datos["ganancia_bruta_historica"] == pytest.approx(1300)
    assert datos["adicionales_sin_costo_snapshot"] == 0
