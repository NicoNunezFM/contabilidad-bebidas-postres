import pytest
from fastapi.testclient import TestClient

from api import app
from costos_postres import inicializar_costos_postres
from database import obtener_conexion


client = TestClient(app)


def _crear_postre(
    nombre,
    stock=0,
    precio=4500,
):
    conexion = obtener_conexion()

    conexion.execute(
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
            "Postres",
            "Unidad",
            1,
            "unidad",
            1,
            stock,
            precio,
            1,
        )
    )

    conexion.commit()
    conexion.close()


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
            json={
                "mensaje": mensaje,
            }
        )

        assert respuesta.status_code == 200


def test_produccion_oreo_suma_stock_y_guarda_costo(
    base_prueba
):
    inicializar_costos_postres()
    _crear_postre(
        "Oreo",
        stock=2,
    )
    _cargar_costos_oreo()

    respuesta = client.post(
        "/comandos",
        json={
            "mensaje": "produccion 10 oreos",
            "canal": "whatsapp",
            "usuario_numero": "operador-produccion",
            "grupo_id": "grupo-produccion",
            "id_mensaje": "prod-1",
        }
    )

    assert respuesta.status_code == 200

    datos = respuesta.json()

    assert (
        datos["codigo"]
        == "COMANDO_PRODUCCION_POSTRE_REGISTRADA"
    )
    assert datos["producto"] == "Oreo"
    assert datos["cantidad_producida"] == 10
    assert datos["version_receta"] == 2
    assert datos["costo_insumos"] == pytest.approx(26300)
    assert datos["costo_fijo"] == pytest.approx(5000)
    assert datos["costo_total"] == pytest.approx(31300)
    assert datos["costo_unitario"] == pytest.approx(3130)
    assert datos["stock_anterior"] == 2
    assert datos["stock_nuevo"] == 12

    conexion = obtener_conexion()

    stock = conexion.execute(
        """
        SELECT stock
        FROM productos
        WHERE nombre = 'Oreo'
        """
    ).fetchone()[0]

    produccion = conexion.execute(
        """
        SELECT
            cantidad_producida,
            version_receta,
            costo_total,
            costo_unitario,
            canal_origen,
            usuario_origen,
            grupo_origen,
            id_mensaje_origen
        FROM producciones_postres
        """
    ).fetchone()

    cantidad_snapshots = conexion.execute(
        """
        SELECT COUNT(*)
        FROM produccion_postres_insumos
        """
    ).fetchone()[0]

    conexion.close()

    assert stock == 12
    assert produccion == (
        10,
        2,
        31300.0,
        3130.0,
        "whatsapp",
        "operador-produccion",
        "grupo-produccion",
        "prod-1",
    )
    assert cantidad_snapshots == 5


def test_produccion_incompleta_no_modifica_stock(
    base_prueba
):
    inicializar_costos_postres()
    _crear_postre(
        "Oreo",
        stock=4,
    )

    respuesta = client.post(
        "/comandos",
        json={
            "mensaje": "produccion 10 oreo"
        }
    )

    assert respuesta.status_code == 400

    datos = respuesta.json()

    assert (
        datos["codigo"]
        == "COSTO_PRODUCCION_INCOMPLETO"
    )
    assert "Galletitas Oreo" in datos["faltantes"]
    assert "Pote" in datos["faltantes"]

    conexion = obtener_conexion()

    stock = conexion.execute(
        """
        SELECT stock
        FROM productos
        WHERE nombre = 'Oreo'
        """
    ).fetchone()[0]

    producciones = conexion.execute(
        """
        SELECT COUNT(*)
        FROM producciones_postres
        """
    ).fetchone()[0]

    conexion.close()

    assert stock == 4
    assert producciones == 0


def test_produccion_escala_receta_y_costo(
    base_prueba
):
    inicializar_costos_postres()
    _crear_postre(
        "Oreo",
        stock=0,
    )
    _cargar_costos_oreo()

    respuesta = client.post(
        "/comandos",
        json={
            "mensaje": "produccion 5 oreo"
        }
    )

    assert respuesta.status_code == 200

    datos = respuesta.json()

    assert datos["cantidad_producida"] == 5
    assert datos["costo_insumos"] == pytest.approx(13150)
    assert datos["costo_fijo"] == pytest.approx(2500)
    assert datos["costo_total"] == pytest.approx(15650)
    assert datos["costo_unitario"] == pytest.approx(3130)
    assert datos["stock_nuevo"] == 5


def test_historial_produccion_muestra_tandas(
    base_prueba
):
    inicializar_costos_postres()
    _crear_postre(
        "Oreo",
        stock=0,
    )
    _cargar_costos_oreo()

    creada = client.post(
        "/comandos",
        json={
            "mensaje": "produccion 10 oreo"
        }
    )

    assert creada.status_code == 200

    respuesta = client.post(
        "/comandos",
        json={
            "mensaje": "historial produccion"
        }
    )

    assert respuesta.status_code == 200

    datos = respuesta.json()

    assert (
        datos["codigo"]
        == "COMANDO_HISTORIAL_PRODUCCIONES_POSTRES"
    )
    assert len(datos["producciones"]) == 1

    produccion = datos["producciones"][0]

    assert produccion["producto"] == "Oreo"
    assert produccion["cantidad_producida"] == 10
    assert produccion["version_receta"] == 2
    assert produccion["costo_total"] == pytest.approx(31300)
    assert produccion["costo_unitario"] == pytest.approx(3130)
