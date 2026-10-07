from fastapi.testclient import TestClient

from api import app
from database import obtener_conexion
from ventas import registrar_venta_multiple


client = TestClient(app)


def crear_producto(
    nombre,
    precio,
    stock,
    controla_stock=True,
    categoria="Bebidas",
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


def test_venta_multiple_registra_una_operacion_atomica(
    base_prueba
):
    id_pepsi = crear_producto(
        "Pepsi lata",
        precio=1600,
        stock=5,
    )

    id_oreo = crear_producto(
        "Oreo",
        precio=4500,
        stock=3,
        categoria="Postres",
    )

    id_bigmac = crear_producto(
        "Big mac doble",
        precio=9000,
        stock=0,
        controla_stock=False,
        categoria="Hamburguesas",
    )

    resultado = registrar_venta_multiple([
        {
            "id_producto": id_pepsi,
            "cantidad": 2,
        },
        {
            "id_producto": id_oreo,
            "cantidad": 1,
        },
        {
            "id_producto": id_bigmac,
            "cantidad": 2,
        },
    ])

    assert resultado["ok"] is True
    assert resultado["codigo"] == "VENTA_MULTIPLE_REGISTRADA"
    assert resultado["cantidad_items"] == 3
    assert resultado["total"] == 25700

    assert obtener_stock(id_pepsi) == 3
    assert obtener_stock(id_oreo) == 2
    assert obtener_stock(id_bigmac) == 0

    conexion = obtener_conexion()

    filas = conexion.execute(
        """
        SELECT id_operacion, COUNT(*)
        FROM ventas
        GROUP BY id_operacion
        """
    ).fetchall()

    operaciones = conexion.execute(
        """
        SELECT COUNT(*)
        FROM ventas_operaciones
        """
    ).fetchone()[0]

    conexion.close()

    assert operaciones == 1
    assert len(filas) == 1
    assert filas[0][0] == resultado["id_operacion"]
    assert filas[0][1] == 3


def test_venta_multiple_falla_completa_si_un_item_no_tiene_stock(
    base_prueba
):
    id_pepsi = crear_producto(
        "Pepsi lata",
        precio=1600,
        stock=1,
    )

    id_bigmac = crear_producto(
        "Big mac doble",
        precio=9000,
        stock=0,
        controla_stock=False,
        categoria="Hamburguesas",
    )

    resultado = registrar_venta_multiple([
        {
            "id_producto": id_bigmac,
            "cantidad": 1,
        },
        {
            "id_producto": id_pepsi,
            "cantidad": 2,
        },
    ])

    assert resultado["ok"] is False
    assert resultado["codigo"] == "STOCK_INSUFICIENTE"

    assert obtener_stock(id_pepsi) == 1
    assert obtener_stock(id_bigmac) == 0

    conexion = obtener_conexion()

    ventas = conexion.execute(
        "SELECT COUNT(*) FROM ventas"
    ).fetchone()[0]

    operaciones = conexion.execute(
        "SELECT COUNT(*) FROM ventas_operaciones"
    ).fetchone()[0]

    conexion.close()

    assert ventas == 0
    assert operaciones == 0


def test_venta_multiple_agrupa_producto_repetido(
    base_prueba
):
    id_pepsi = crear_producto(
        "Pepsi lata",
        precio=1600,
        stock=5,
    )

    resultado = registrar_venta_multiple([
        {
            "id_producto": id_pepsi,
            "cantidad": 2,
        },
        {
            "id_producto": id_pepsi,
            "cantidad": 3,
        },
    ])

    assert resultado["ok"] is True
    assert resultado["cantidad_items"] == 1
    assert resultado["items"][0]["cantidad"] == 5
    assert resultado["total"] == 8000
    assert obtener_stock(id_pepsi) == 0


def test_accion_venta_multiple_desde_json(
    base_prueba
):
    crear_producto(
        "Pepsi lata",
        precio=1600,
        stock=5,
    )

    crear_producto(
        "Oreo",
        precio=4500,
        stock=4,
        categoria="Postres",
    )

    respuesta = client.post(
        "/acciones",
        json={
            "accion": "registrar_venta",
            "datos": {
                "items": [
                    {
                        "producto": "pepsi",
                        "cantidad": 2,
                    },
                    {
                        "producto": "oreo",
                        "cantidad": 1,
                    },
                ]
            }
        }
    )

    assert respuesta.status_code == 200

    datos = respuesta.json()

    assert datos["ok"] is True
    assert (
        datos["codigo"]
        == "ACCION_VENTA_MULTIPLE_REGISTRADA"
    )
    assert datos["datos"]["cantidad_items"] == 2
    assert datos["datos"]["total"] == 7700


def test_comando_venta_multiple(
    base_prueba
):
    crear_producto(
        "Pepsi lata",
        precio=1600,
        stock=5,
    )

    crear_producto(
        "Chocotorta",
        precio=4500,
        stock=3,
        categoria="Postres",
    )

    crear_producto(
        "Big mac doble",
        precio=9000,
        stock=0,
        controla_stock=False,
        categoria="Hamburguesas",
    )

    respuesta = client.post(
        "/comandos",
        json={
            "mensaje": (
                "venta 2 pepsi, 1 chocotorta "
                "y 2 bigmac doble"
            )
        }
    )

    assert respuesta.status_code == 200

    datos = respuesta.json()

    assert datos["ok"] is True
    assert (
        datos["codigo"]
        == "COMANDO_VENTA_MULTIPLE_REGISTRADA"
    )
    assert datos["total"] == 25700
    assert len(datos["items"]) == 3
    assert "Pepsi lata" in datos["respuesta"]
    assert "Chocotorta" in datos["respuesta"]
    assert "Big mac doble" in datos["respuesta"]


def test_comando_no_separa_y_dentro_del_nombre_producto(
    base_prueba
):
    crear_producto(
        "Cheddar y huevo doble",
        precio=9000,
        stock=0,
        controla_stock=False,
        categoria="Hamburguesas",
    )

    respuesta = client.post(
        "/comandos",
        json={
            "mensaje": "venta 1 cheddar y huevo doble"
        }
    )

    assert respuesta.status_code == 200

    datos = respuesta.json()

    assert datos["ok"] is True
    assert datos["codigo"] == "COMANDO_VENTA_REGISTRADA"
    assert datos["producto"] == "Cheddar y huevo doble"
    assert datos["total"] == 9000



def test_venta_multiple_guarda_costo_snapshot(
    base_prueba
):
    id_pepsi = crear_producto(
        "Pepsi snapshot",
        precio=2000,
        stock=0,
    )

    compra = client.post(
        "/compras",
        json={
            "id_producto": id_pepsi,
            "cantidad": 6,
            "precio_unitario": 1200,
        }
    )

    assert compra.status_code == 201

    resultado = registrar_venta_multiple([
        {
            "id_producto": id_pepsi,
            "cantidad": 2,
        },
    ])

    assert resultado["ok"] is True
    assert (
        resultado["items"][0]["costo_unitario_snapshot"]
        == 1200
    )
    assert (
        resultado["items"][0]["fuente_costo_snapshot"]
        .startswith("promedio ponderado")
    )

    conexion = obtener_conexion()

    fila = conexion.execute(
        """
        SELECT
            costo_unitario_snapshot,
            fuente_costo_snapshot
        FROM ventas
        WHERE id_producto = ?
        """,
        (id_pepsi,)
    ).fetchone()

    conexion.close()

    assert fila[0] == 1200
    assert fila[1].startswith(
        "promedio ponderado"
    )
