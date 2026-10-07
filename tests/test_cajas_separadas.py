from fastapi.testclient import TestClient

from api import app


client = TestClient(app)


def test_saldos_iniciales_separan_las_dos_cajas(
    base_prueba
):
    rotiseria = client.post(
        "/comandos",
        json={
            "mensaje": "inicio caja rotiseria 56000"
        },
    )
    bebidas = client.post(
        "/comandos",
        json={
            "mensaje": "inicio caja bebidas postres 46120"
        },
    )

    assert rotiseria.status_code == 200
    assert bebidas.status_code == 200
    assert rotiseria.json()["monto"] == 56000
    assert bebidas.json()["monto"] == 46120

    caja = client.post(
        "/comandos",
        json={"mensaje": "caja"},
    )

    assert caja.status_code == 200

    datos = caja.json()

    assert datos["cajas_separadas_activas"] is True
    assert (
        datos["caja_rotiseria"]["saldo_actual"]
        == 56000
    )
    assert (
        datos["caja_bebidas_postres"]["saldo_actual"]
        == 46120
    )
    assert datos["total_cajas_actuales"] == 102120
    assert "Rotisería: $56.000,00" in datos["respuesta"]
    assert (
        "Bebidas + Postres: $46.120,00"
        in datos["respuesta"]
    )


def test_movimiento_seccion_afecta_solo_su_caja(
    base_prueba
):
    client.post(
        "/comandos",
        json={
            "mensaje": "inicio caja rotiseria 56000"
        },
    )
    client.post(
        "/comandos",
        json={
            "mensaje": "inicio caja bebidas postres 46120"
        },
    )

    aporte = client.post(
        "/comandos",
        json={
            "mensaje": "aporte rotiseria 4000"
        },
    )

    assert aporte.status_code == 200
    assert aporte.json()["seccion"] == "rotiseria"

    caja_rotiseria = client.post(
        "/comandos",
        json={"mensaje": "caja rotiseria"},
    ).json()
    caja_bebidas = client.post(
        "/comandos",
        json={"mensaje": "caja bebidas postres"},
    ).json()

    assert caja_rotiseria["saldo_actual"] == 60000
    assert caja_bebidas["saldo_actual"] == 46120
