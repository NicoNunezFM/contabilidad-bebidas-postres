import pytest
from fastapi.testclient import TestClient

from api import app
from costos_postres import inicializar_costos_postres
from database import obtener_conexion


client = TestClient(app)


def _crear_producto(
    nombre,
    categoria,
    precio,
    stock=0,
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


def _asegurar_oreo():
    conexion = obtener_conexion()

    fila = conexion.execute(
        """
        SELECT id_producto
        FROM productos
        WHERE LOWER(nombre) = 'oreo'
        """
    ).fetchone()

    if fila is None:
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
                "Oreo",
                "Postres",
                "Unidad",
                1,
                "unidad",
                1,
                0,
                4500,
                1,
            )
        )
        id_producto = cursor.lastrowid
    else:
        id_producto = fila[0]

        conexion.execute(
            """
            UPDATE productos
            SET
                precio_venta = 4500,
                stock = 0,
                controla_stock = 1
            WHERE id_producto = ?
            """,
            (id_producto,)
        )

    conexion.commit()
    conexion.close()

    return id_producto


def _cargar_costos_oreo():
    mensajes = [
        "insumo galletitas oreo 800 g 8000 Carrefour",
        "insumo dulce de leche 900 g 9000 Carrefour",
        "insumo crema de leche 600 ml 6000 Carrefour",
        "insumo leche 300 ml 300 Carrefour",
        "insumo pote 10 unidades 3000 Papelera",
    ]

    for mensaje in mensajes:
        respuesta = client.post(
            "/comandos",
            json={"mensaje": mensaje}
        )

        assert respuesta.status_code == 200


def test_rentabilidad_bebida_usa_promedio_ponderado_ultimas_compras(
    base_prueba
):
    producto = _crear_producto(
        "Bebida rentabilidad",
        "Bebidas",
        2000,
        stock=0,
    )

    assert client.post(
        "/compras",
        json={
            "id_producto": producto,
            "cantidad": 10,
            "precio_unitario": 1000,
        }
    ).status_code == 201

    assert client.post(
        "/compras",
        json={
            "id_producto": producto,
            "cantidad": 5,
            "precio_unitario": 1200,
        }
    ).status_code == 201

    assert client.post(
        "/ventas",
        json={
            "id_producto": producto,
            "cantidad": 3,
            "precio_unitario": 2000,
        }
    ).status_code == 201

    respuesta = client.post(
        "/comandos",
        json={
            "mensaje": "rentabilidad bebida rentabilidad"
        }
    )

    assert respuesta.status_code == 200

    datos = respuesta.json()

    assert datos["codigo"] == "COMANDO_RENTABILIDAD_PRODUCTO"
    assert datos["completo"] is True
    assert datos["costo_unitario"] == pytest.approx(
        16000 / 15
    )
    assert datos["ganancia_unitaria"] == pytest.approx(
        2000 - (16000 / 15)
    )
    assert datos["margen_sobre_venta_pct"] == pytest.approx(
        ((2000 - (16000 / 15)) / 2000) * 100
    )
    assert datos["unidades_vendidas"] == 3
    assert datos["ingresos"] == 6000
    assert datos["fuente_costo"].startswith(
        "promedio ponderado"
    )
    assert datos["rentabilidad_historica_exacta"] is True
    assert datos["costo_ventas_historico"] == pytest.approx(
        3 * (16000 / 15)
    )
    assert datos["unidades_sin_snapshot"] == 0


def test_rentabilidad_postre_usa_ultima_produccion(
    base_prueba
):
    inicializar_costos_postres()
    producto = _asegurar_oreo()
    _cargar_costos_oreo()

    produccion = client.post(
        "/comandos",
        json={
            "mensaje": "produccion 10 oreo"
        }
    )

    assert produccion.status_code == 200

    venta = client.post(
        "/ventas",
        json={
            "id_producto": producto,
            "cantidad": 2,
            "precio_unitario": 4500,
        }
    )

    assert venta.status_code == 201

    respuesta = client.post(
        "/comandos",
        json={
            "mensaje": "ganancia oreo"
        }
    )

    assert respuesta.status_code == 200

    datos = respuesta.json()

    assert datos["completo"] is True
    assert datos["costo_unitario"] == pytest.approx(3130)
    assert datos["precio_venta"] == 4500
    assert datos["ganancia_unitaria"] == pytest.approx(1370)
    assert datos["margen_sobre_venta_pct"] == pytest.approx(
        (1370 / 4500) * 100
    )
    assert datos["fuente_costo"] == "última producción registrada"
    assert datos["unidades_vendidas"] == 2
    assert datos["ingresos"] == 9000
    assert datos["costo_ventas_estimado"] == pytest.approx(6260)
    assert datos["ganancia_bruta_estimada"] == pytest.approx(2740)
    assert datos["rentabilidad_historica_exacta"] is True
    assert datos["costo_ventas_historico"] == pytest.approx(6260)
    assert datos["ganancia_bruta_historica"] == pytest.approx(2740)

    conexion = obtener_conexion()

    snapshot = conexion.execute(
        """
        SELECT
            costo_unitario_snapshot,
            fuente_costo_snapshot
        FROM ventas
        WHERE id_producto = ?
        """,
        (producto,)
    ).fetchone()

    conexion.close()

    assert snapshot[0] == pytest.approx(3130)
    assert snapshot[1] == "última producción registrada"


def test_rentabilidad_postre_sin_produccion_usa_receta_actual(
    base_prueba
):
    inicializar_costos_postres()
    _asegurar_oreo()
    _cargar_costos_oreo()

    respuesta = client.post(
        "/comandos",
        json={
            "mensaje": "rentabilidad oreo"
        }
    )

    assert respuesta.status_code == 200

    datos = respuesta.json()

    assert datos["completo"] is True
    assert datos["costo_unitario"] == pytest.approx(3130)
    assert (
        datos["fuente_costo"]
        == "estimación de la receta actual"
    )


def test_rentabilidad_bebida_sin_compras_informa_costo_incompleto(
    base_prueba
):
    _crear_producto(
        "Bebida sin costo",
        "Bebidas",
        1800,
        stock=5,
    )

    respuesta = client.post(
        "/comandos",
        json={
            "mensaje": "rentabilidad bebida sin costo"
        }
    )

    assert respuesta.status_code == 200

    datos = respuesta.json()

    assert datos["completo"] is False
    assert datos["costo_unitario"] is None
    assert "sin datos suficientes" in datos["respuesta"].lower()


def test_rentabilidad_categoria_bebidas_lista_productos(
    base_prueba
):
    producto = _crear_producto(
        "Bebida categoria rentabilidad",
        "Bebidas",
        2500,
        stock=0,
    )

    assert client.post(
        "/compras",
        json={
            "id_producto": producto,
            "cantidad": 6,
            "precio_unitario": 1500,
        }
    ).status_code == 201

    respuesta = client.post(
        "/comandos",
        json={
            "mensaje": "rentabilidad bebidas"
        }
    )

    assert respuesta.status_code == 200

    datos = respuesta.json()

    assert datos["codigo"] == "COMANDO_RENTABILIDAD_CATEGORIA"

    nombres = {
        item["producto"]
        for item in datos["productos"]
    }

    assert "Bebida categoria rentabilidad" in nombres



def test_costo_historico_venta_no_cambia_con_compra_posterior(
    base_prueba
):
    producto = _crear_producto(
        "Bebida snapshot",
        "Bebidas",
        2000,
        stock=0,
    )

    assert client.post(
        "/compras",
        json={
            "id_producto": producto,
            "cantidad": 10,
            "precio_unitario": 1000,
        }
    ).status_code == 201

    venta = client.post(
        "/ventas",
        json={
            "id_producto": producto,
            "cantidad": 2,
            "precio_unitario": 2000,
        }
    )

    assert venta.status_code == 201
    assert (
        venta.json()["datos"]["costo_unitario_snapshot"]
        == pytest.approx(1000)
    )

    assert client.post(
        "/compras",
        json={
            "id_producto": producto,
            "cantidad": 10,
            "precio_unitario": 2000,
        }
    ).status_code == 201

    respuesta = client.post(
        "/comandos",
        json={
            "mensaje": "rentabilidad bebida snapshot"
        }
    )

    assert respuesta.status_code == 200

    datos = respuesta.json()

    assert datos["costo_unitario"] == pytest.approx(1500)
    assert datos["costo_ventas_estimado"] == pytest.approx(3000)

    assert datos["rentabilidad_historica_exacta"] is True
    assert datos["costo_ventas_historico"] == pytest.approx(2000)
    assert datos["ganancia_bruta_historica"] == pytest.approx(2000)
    assert datos["unidades_sin_snapshot"] == 0

    assert "costo congelado" in datos["respuesta"].lower()
