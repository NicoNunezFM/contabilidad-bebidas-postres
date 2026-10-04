from fastapi.testclient import TestClient

from ajustes_stock import (
    obtener_ajustes_stock,
    registrar_consumo_interno,
    registrar_inventario_fisico,
    registrar_merma,
)
from api import app
from database import obtener_conexion


client = TestClient(app)


def crear_producto_stock(
    nombre="Pepsi lata",
    stock=10,
    precio=1600,
    controla_stock=True
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
            "Bebidas",
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


def obtener_stock(id_producto):
    conexion = obtener_conexion()

    stock = conexion.execute(
        """
        SELECT stock
        FROM productos
        WHERE id_producto = ?
        """,
        (id_producto,)
    ).fetchone()[0]

    conexion.close()

    return stock


def test_merma_descuenta_stock_y_guarda_tipo(
    base_prueba
):
    id_producto = crear_producto_stock(stock=10)

    resultado = registrar_merma(
        id_producto=id_producto,
        cantidad=2,
        motivo="Rotura",
        fecha="2026-10-04"
    )

    assert resultado["ok"] is True
    assert resultado["tipo"] == "Merma"
    assert resultado["stock_anterior"] == 10
    assert resultado["stock_nuevo"] == 8
    assert obtener_stock(id_producto) == 8

    ajustes = obtener_ajustes_stock(id_producto=id_producto)

    assert len(ajustes) == 1
    assert ajustes[0]["tipo"] == "Merma"
    assert ajustes[0]["motivo"] == "Rotura"


def test_consumo_interno_descuenta_stock(
    base_prueba
):
    id_producto = crear_producto_stock(
        nombre="Oreo",
        stock=4,
        precio=4500
    )

    resultado = registrar_consumo_interno(
        id_producto=id_producto,
        cantidad=1,
        motivo="Consumo familiar",
        fecha="2026-10-04"
    )

    assert resultado["ok"] is True
    assert resultado["tipo"] == "Consumo interno"
    assert resultado["stock_nuevo"] == 3
    assert obtener_stock(id_producto) == 3


def test_inventario_clasifica_ajuste(
    base_prueba
):
    id_producto = crear_producto_stock(stock=10)

    resultado = registrar_inventario_fisico(
        id_producto=id_producto,
        cantidad_real=7,
        fecha="2026-10-04"
    )

    assert resultado["ok"] is True
    assert resultado["tipo"] == "Inventario"
    assert resultado["ajuste"] == -3
    assert resultado["stock_nuevo"] == 7

    ajustes = obtener_ajustes_stock(
        id_producto=id_producto,
        tipo="Inventario"
    )

    assert len(ajustes) == 1


def test_merma_rechaza_producto_sin_control_stock(
    base_prueba
):
    id_producto = crear_producto_stock(
        nombre="Big mac doble",
        stock=0,
        precio=9000,
        controla_stock=False
    )

    resultado = registrar_merma(
        id_producto=id_producto,
        cantidad=1
    )

    assert resultado["ok"] is False
    assert resultado["codigo"] == "PRODUCTO_SIN_CONTROL_STOCK"


def test_accion_merma_con_motivo(
    base_prueba
):
    crear_producto_stock(stock=5)

    respuesta = client.post(
        "/acciones",
        json={
            "accion": "registrar_merma",
            "datos": {
                "producto": "pepsi",
                "cantidad": 2,
                "motivo": "Botellas dañadas",
            }
        }
    )

    assert respuesta.status_code == 200

    datos = respuesta.json()

    assert datos["ok"] is True
    assert datos["codigo"] == "ACCION_MERMA_REGISTRADA"
    assert datos["datos"]["motivo"] == "Botellas dañadas"
    assert datos["datos"]["stock_nuevo"] == 3


def test_comando_merma(
    base_prueba
):
    crear_producto_stock(stock=6)

    respuesta = client.post(
        "/comandos",
        json={
            "mensaje": "merma 2 pepsi"
        }
    )

    assert respuesta.status_code == 200

    datos = respuesta.json()

    assert datos["ok"] is True
    assert datos["codigo"] == "ACCION_MERMA_REGISTRADA"
    assert datos["stock_nuevo"] == 4
    assert "Merma registrada" in datos["respuesta"]


def test_comando_consumo_interno(
    base_prueba
):
    crear_producto_stock(
        nombre="Oreo",
        stock=3,
        precio=4500
    )

    respuesta = client.post(
        "/comandos",
        json={
            "mensaje": "consumo 1 oreo"
        }
    )

    assert respuesta.status_code == 200

    datos = respuesta.json()

    assert datos["ok"] is True
    assert datos["codigo"] == "ACCION_CONSUMO_INTERNO_REGISTRADO"
    assert datos["stock_nuevo"] == 2


def test_comando_inventario(
    base_prueba
):
    crear_producto_stock(stock=9)

    respuesta = client.post(
        "/comandos",
        json={
            "mensaje": "inventario pepsi 7"
        }
    )

    assert respuesta.status_code == 200

    datos = respuesta.json()

    assert datos["ok"] is True
    assert datos["codigo"] == "ACCION_INVENTARIO_REGISTRADO"
    assert datos["stock_nuevo"] == 7
    assert datos["ajuste"] == -2
