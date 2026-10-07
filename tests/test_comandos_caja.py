from fastapi.testclient import TestClient

from api import app


client = TestClient(app)


def test_comando_aporte_registra_movimiento_en_caja(
    base_prueba
):
    respuesta = client.post(
        "/comandos",
        json={
            "mensaje": (
                "aporte 100000 "
                "dinero recibido para pagar deuda naranja"
            )
        }
    )

    assert respuesta.status_code == 200

    datos = respuesta.json()

    assert datos["ok"] is True
    assert datos["tipo"] == "Aporte"
    assert datos["monto"] == 100000
    assert (
        datos["descripcion"]
        == "dinero recibido para pagar deuda naranja"
    )

    caja = client.get("/caja").json()

    assert caja["aportes"] == 100000
    assert caja["saldo_fisico"] == 100000
    assert caja["saldo_disponible"] == 100000


def test_comando_retiro_registra_movimiento_en_caja(
    base_prueba
):
    assert client.post(
        "/comandos",
        json={
            "mensaje": "aporte 100000"
        }
    ).status_code == 200

    respuesta = client.post(
        "/comandos",
        json={
            "mensaje": "retiro 25000 prueba"
        }
    )

    assert respuesta.status_code == 200

    datos = respuesta.json()

    assert datos["tipo"] == "Retiro"
    assert datos["monto"] == 25000

    caja = client.get("/caja").json()

    assert caja["aportes"] == 100000
    assert caja["retiros"] == 25000
    assert caja["saldo_fisico"] == 75000
    assert caja["saldo_disponible"] == 75000


def test_aporte_mas_reserva_deuda_deja_dinero_no_disponible(
    base_prueba
):
    assert client.post(
        "/comandos",
        json={
            "mensaje": (
                "saldo inicial deuda naranja 389.547,18"
            )
        }
    ).status_code == 200

    assert client.post(
        "/comandos",
        json={
            "mensaje": "aporte 100000"
        }
    ).status_code == 200

    reserva = client.post(
        "/comandos",
        json={
            "mensaje": "reservar deuda naranja 100000"
        }
    )

    assert reserva.status_code == 200

    caja = client.post(
        "/comandos",
        json={"mensaje": "caja"}
    )

    assert caja.status_code == 200

    datos = caja.json()

    assert datos["deuda_reservada"] == 100000
    assert datos["saldo_fisico"] == 100000
    assert datos["saldo_disponible"] == 0
    assert "Deuda reservada: $100.000,00" in datos["respuesta"]
