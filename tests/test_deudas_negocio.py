from fastapi.testclient import TestClient

from api import app
from database import obtener_conexion


client = TestClient(app)


def test_saldo_inicial_y_consulta_deuda(
    base_prueba
):
    respuesta = client.post(
        "/comandos",
        json={
            "mensaje": (
                "saldo inicial deuda naranja 100000"
            )
        }
    )

    assert respuesta.status_code == 200

    detalle = client.post(
        "/comandos",
        json={"mensaje": "deuda naranja"}
    )

    assert detalle.status_code == 200

    datos = detalle.json()

    assert datos["cuenta"].lower() == "naranja"
    assert datos["saldo"] == 100000

    resumen = client.post(
        "/comandos",
        json={"mensaje": "deudas negocio"}
    )

    assert resumen.status_code == 200
    assert resumen.json()["total_ars"] == 100000


def test_pago_deuda_reduce_saldo_y_caja(
    base_prueba
):
    assert client.post(
        "/comandos",
        json={
            "mensaje": (
                "saldo inicial deuda naranja 100000"
            )
        }
    ).status_code == 200

    pago = client.post(
        "/comandos",
        json={
            "mensaje": "pago deuda naranja 30000"
        }
    )

    assert pago.status_code == 200

    datos = pago.json()

    assert datos["saldo_anterior"] == 100000
    assert datos["saldo"] == 70000
    assert datos["afecta_caja"] is True
    assert datos["id_movimiento_caja"] is not None

    conexion = obtener_conexion()

    retiro = conexion.execute(
        """
        SELECT tipo, descripcion, monto, anulado
        FROM movimientos_caja
        """
    ).fetchone()

    conexion.close()

    assert retiro[0] == "Retiro"
    assert "naranja" in retiro[1].lower()
    assert retiro[2] == 30000
    assert retiro[3] == 0


def test_pago_no_puede_superar_deuda(
    base_prueba
):
    assert client.post(
        "/comandos",
        json={
            "mensaje": (
                "saldo inicial deuda bbva 20000"
            )
        }
    ).status_code == 200

    respuesta = client.post(
        "/comandos",
        json={
            "mensaje": "pago deuda bbva 25000"
        }
    )

    assert respuesta.status_code == 400
    assert respuesta.json()["codigo"] == "PAGO_DEUDA_EXCESIVO"

    detalle = client.post(
        "/comandos",
        json={"mensaje": "deuda bbva"}
    ).json()

    assert detalle["saldo"] == 20000


def test_compra_financiada_manual_aumenta_deuda(
    base_prueba
):
    assert client.post(
        "/comandos",
        json={
            "mensaje": (
                "saldo inicial deuda naranja 10000"
            )
        }
    ).status_code == 200

    compra = client.post(
        "/comandos",
        json={
            "mensaje": (
                "compra deuda naranja 25000 reposicion bebidas"
            )
        }
    )

    assert compra.status_code == 200
    assert compra.json()["saldo"] == 35000

    historial = client.post(
        "/comandos",
        json={
            "mensaje": "historial deuda naranja"
        }
    )

    assert historial.status_code == 200

    movimientos = historial.json()["movimientos"]

    assert movimientos[0]["tipo"] == "Compra"
    assert movimientos[0]["importe"] == 25000
    assert movimientos[1]["tipo"] == "Saldo inicial"


def test_vencimiento_y_deuda_que_vence_primero(
    base_prueba
):
    assert client.post(
        "/comandos",
        json={
            "mensaje": "saldo inicial deuda naranja 50000"
        }
    ).status_code == 200

    assert client.post(
        "/comandos",
        json={
            "mensaje": "saldo inicial deuda bbva 30000"
        }
    ).status_code == 200

    assert client.post(
        "/comandos",
        json={
            "mensaje": (
                "vencimiento deuda naranja 2026-10-20"
            )
        }
    ).status_code == 200

    assert client.post(
        "/comandos",
        json={
            "mensaje": (
                "vencimiento deuda bbva 2026-10-15"
            )
        }
    ).status_code == 200

    respuesta = client.post(
        "/comandos",
        json={
            "mensaje": "que deuda vence primero"
        }
    )

    assert respuesta.status_code == 200

    datos = respuesta.json()

    assert datos["nombre"].lower() == "bbva"
    assert datos["saldo"] == 30000
    assert datos["proximo_vencimiento"] == "2026-10-15"


def test_saldo_inicial_no_se_duplica(
    base_prueba
):
    assert client.post(
        "/comandos",
        json={
            "mensaje": "deuda inicial naranja 10000"
        }
    ).status_code == 200

    repetido = client.post(
        "/comandos",
        json={
            "mensaje": "deuda inicial naranja 10000"
        }
    )

    assert repetido.status_code == 400
    assert (
        repetido.json()["codigo"]
        == "SALDO_INICIAL_YA_REGISTRADO"
    )
