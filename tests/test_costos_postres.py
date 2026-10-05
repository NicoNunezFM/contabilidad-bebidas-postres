from fastapi.testclient import TestClient

from api import app
from costos_postres import inicializar_costos_postres
from database import obtener_conexion


client = TestClient(app)


def test_gasto_postres_queda_en_caja_seccion(
    base_prueba
):
    inicializar_costos_postres()

    respuesta = client.post(
        "/comandos",
        json={
            "mensaje": "gasto postres Carrefour 20000"
        }
    )

    assert respuesta.status_code == 200

    datos = respuesta.json()

    assert datos["ok"] is True
    assert datos["seccion"] == "bebidas_postres"
    assert datos["monto"] == 20000

    caja = client.post(
        "/comandos",
        json={
            "mensaje": "caja bebidas postres"
        }
    ).json()

    assert caja["gastos_seccion"] == 20000
    assert caja["saldo_operativo"] == -20000


def test_compra_insumos_oreo_alimenta_estimacion(
    base_prueba
):
    inicializar_costos_postres()

    compras = [
        "insumo galletitas oreo 700 g 7000 Carrefour",
        "insumo dulce de leche 900 g 9000 Carrefour",
        "insumo crema de leche 500 ml 5000 Carrefour",
        "insumo leche 400 ml 400 Carrefour",
    ]

    for mensaje in compras:
        respuesta = client.post(
            "/comandos",
            json={"mensaje": mensaje}
        )

        assert respuesta.status_code == 200
        assert respuesta.json()["ok"] is True

    costo = client.post(
        "/comandos",
        json={
            "mensaje": "cuanto me vale hacer 10 oreos"
        }
    )

    assert costo.status_code == 200

    datos = costo.json()

    assert datos["codigo"] == "COSTO_RECETA_ESTIMADO"
    assert datos["costo_insumos"] == 21400
    assert datos["costo_fijo"] == 5000
    assert datos["costo_total_estimado"] == 26400
    assert datos["faltantes"] == []


def test_costo_oreo_incompleto_informa_faltantes(
    base_prueba
):
    inicializar_costos_postres()

    respuesta = client.post(
        "/comandos",
        json={
            "mensaje": "costo 10 oreos"
        }
    )

    assert respuesta.status_code == 200

    datos = respuesta.json()

    assert datos["codigo"] == "COSTO_RECETA_PARCIAL"
    assert datos["costo_total_estimado"] is None
    assert "Galletitas Oreo" in datos["faltantes"]
    assert "Dulce de leche" in datos["faltantes"]
    assert "Crema de leche" in datos["faltantes"]
    assert "Leche" in datos["faltantes"]


def test_receta_oreo_se_guarda_en_base(
    base_prueba
):
    inicializar_costos_postres()

    respuesta = client.post(
        "/comandos",
        json={
            "mensaje": "receta oreo"
        }
    )

    assert respuesta.status_code == 200

    datos = respuesta.json()

    assert datos["codigo"] == "COMANDO_RECETA_POSTRE"
    receta = datos["receta"]

    assert receta["producto"] == "Oreo"
    assert receta["rendimiento"] == 10
    assert receta["costo_fijo_por_unidad"] == 500

    ingredientes = {
        item["nombre"]: item["cantidad_base"]
        for item in receta["insumos"]
    }

    assert ingredientes == {
        "Galletitas Oreo": 700,
        "Dulce de leche": 900,
        "Crema de leche": 500,
        "Leche": 400,
    }


def test_historial_gastos_postres_muestra_insumos(
    base_prueba
):
    inicializar_costos_postres()

    client.post(
        "/comandos",
        json={
            "mensaje": (
                "gasto postres crema de leche "
                "500 ml 5000 en Carrefour"
            )
        }
    )

    respuesta = client.post(
        "/comandos",
        json={
            "mensaje": "historial gastos postres"
        }
    )

    assert respuesta.status_code == 200

    datos = respuesta.json()

    assert datos["codigo"] == "COMANDO_HISTORIAL_GASTOS_POSTRES"
    assert len(datos["gastos"]) == 1
    assert datos["gastos"][0]["monto"] == 5000

    conexion = obtener_conexion()

    compra = conexion.execute(
        """
        SELECT COUNT(*)
        FROM compras_insumos
        """
    ).fetchone()[0]

    conexion.close()

    assert compra == 1



def test_insumos_habituales_de_postres_se_reconocen(
    base_prueba
):
    from costos_postres import resolver_insumo

    inicializar_costos_postres()

    nombres = [
        "crema de leche",
        "dulce de leche",
        "galletitas oreo",
        "chocolinas",
        "queso crema",
        "azucar impalpable",
    ]

    for nombre in nombres:
        resultado = resolver_insumo(nombre)

        assert resultado["ok"] is True
        assert (
            resultado["insumo"]["seccion"]
            == "bebidas_postres"
        )
