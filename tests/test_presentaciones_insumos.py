from fastapi.testclient import TestClient

from api import app
from costos_postres import inicializar_costos_postres
from database import obtener_conexion


client = TestClient(app)


def test_compra_oreo_tres_paquetes_118g_convierte_a_354g(
    base_prueba
):
    inicializar_costos_postres()

    respuesta = client.post(
        "/comandos",
        json={
            "mensaje": (
                "insumo oreo 3 paquetes 118g "
                "4288 Carrefour"
            )
        }
    )

    assert respuesta.status_code == 200

    datos = respuesta.json()

    assert (
        datos["codigo"]
        == "COMANDO_COMPRA_INSUMO_PAQUETES_REGISTRADA"
    )
    assert datos["insumo"] == "Galletitas Oreo"
    assert datos["cantidad_paquetes"] == 3
    assert datos["presentacion"] == "118g"
    assert datos["contenido_por_paquete"] == 118
    assert datos["cantidad_base_total"] == 354
    assert datos["costo_total"] == 4288

    conexion = obtener_conexion()

    compra = conexion.execute(
        """
        SELECT cantidad_base, costo_total, observaciones
        FROM compras_insumos
        """
    ).fetchone()

    conexion.close()

    assert compra[0] == 354
    assert compra[1] == 4288
    assert "3 paquete(s) x 118g" in compra[2]


def test_compra_oreo_x4_convierte_a_258g(
    base_prueba
):
    inicializar_costos_postres()

    respuesta = client.post(
        "/comandos",
        json={
            "mensaje": (
                "insumo oreo 1 pack x4 "
                "3406 Carrefour"
            )
        }
    )

    assert respuesta.status_code == 200

    datos = respuesta.json()

    assert datos["presentacion"] == "258g x4"
    assert datos["cantidad_base_total"] == 258
    assert datos["contenido_por_paquete"] == 258


def test_compra_chocolinas_admite_170_y_250g(
    base_prueba
):
    inicializar_costos_postres()

    compra_250 = client.post(
        "/comandos",
        json={
            "mensaje": (
                "insumo chocolinas 4 paquetes 250g "
                "12000 Carrefour"
            )
        }
    )

    assert compra_250.status_code == 200
    assert (
        compra_250.json()["cantidad_base_total"]
        == 1000
    )

    compra_170 = client.post(
        "/comandos",
        json={
            "mensaje": (
                "insumo chocolinas 2 paquetes 170g "
                "3000 Carrefour"
            )
        }
    )

    assert compra_170.status_code == 200
    assert (
        compra_170.json()["cantidad_base_total"]
        == 340
    )


def test_presentacion_incorrecta_no_registra_compra(
    base_prueba
):
    inicializar_costos_postres()

    respuesta = client.post(
        "/comandos",
        json={
            "mensaje": (
                "insumo chocolinas 2 paquetes 118g "
                "3000 Carrefour"
            )
        }
    )

    assert respuesta.status_code == 400

    datos = respuesta.json()

    assert (
        datos["codigo"]
        == "PRESENTACION_INSUMO_NO_ENCONTRADA"
    )
    assert {
        item["nombre"]
        for item in datos["presentaciones"]
    } == {
        "170g",
        "250g",
    }

    conexion = obtener_conexion()

    cantidad = conexion.execute(
        """
        SELECT COUNT(*)
        FROM compras_insumos
        """
    ).fetchone()[0]

    conexion.close()

    assert cantidad == 0
