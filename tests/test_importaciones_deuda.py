from fastapi.testclient import TestClient

from api import app
from database import obtener_conexion
from deudas_negocio import detalle_deuda
from gmail_naranja import procesar_mensaje_naranja
from importaciones_deuda import registrar_importacion_deuda


client = TestClient(app)

CUERPO = """
TU COMPRA
$ 35.000,00
DISTRIBUIDORA DE AHORR
Adicional - Claudia Elizabet Rotondo
Tarjeta MASTER INTERNACIONAL
Plan 01
cuota en PESOS
Miércoles 07/OCT - 18:00 h
"""


def test_importacion_adicional_aumenta_deuda_una_sola_vez(
    base_prueba
):
    primero = procesar_mensaje_naranja(
        gmail_message_id="gmail-1",
        asunto=(
            "Sergio Nicolas👉 Ingresó una compra "
            "en tu tarjeta crédito"
        ),
        cuerpo=CUERPO,
        fecha_email="2026-10-07T18:01:00-03:00",
        fecha_corte="2026-10-07T17:30:00",
    )

    assert primero["ok"] is True
    assert primero["genera_deuda"] is True
    assert primero["estado"] == "pendiente_clasificacion"
    assert primero["importe"] == 35000
    assert primero["id_movimiento_deuda"] is not None

    deuda = detalle_deuda("naranja")

    assert deuda["ok"] is True
    assert deuda["saldo"] == 35000

    repetido = procesar_mensaje_naranja(
        gmail_message_id="gmail-1",
        asunto=(
            "Sergio Nicolas👉 Ingresó una compra "
            "en tu tarjeta crédito"
        ),
        cuerpo=CUERPO,
        fecha_email="2026-10-07T18:01:00-03:00",
        fecha_corte="2026-10-07T17:30:00",
    )

    assert repetido["ok"] is True
    assert repetido["duplicada"] is True

    deuda_final = detalle_deuda("naranja")

    assert deuda_final["saldo"] == 35000


def test_importacion_titular_personal_no_aumenta_deuda(
    base_prueba
):
    cuerpo_personal = CUERPO.replace(
        "Adicional - Claudia Elizabet Rotondo",
        "Titular - Sergio Nicolas Nunez",
    )

    resultado = procesar_mensaje_naranja(
        gmail_message_id="gmail-personal-1",
        asunto=(
            "Sergio Nicolas👉 Ingresó una compra "
            "en tu tarjeta crédito"
        ),
        cuerpo=cuerpo_personal,
        fecha_email="2026-10-07T18:01:00-03:00",
        fecha_corte="2026-10-07T17:30:00",
    )

    assert resultado["ok"] is True
    assert resultado["genera_deuda"] is False
    assert resultado["estado"] == "ignorado_no_negocio"

    conexion = obtener_conexion()

    cantidad = conexion.execute(
        """
        SELECT COUNT(*)
        FROM movimientos_deuda_negocio
        """
    ).fetchone()[0]

    conexion.close()

    assert cantidad == 0


def test_importacion_anterior_al_corte_no_aumenta_deuda(
    base_prueba
):
    resultado = registrar_importacion_deuda(
        fuente="gmail_naranja",
        id_externo="historico-1",
        importe=104498,
        fecha_operacion="2026-09-15T12:36:00",
        moneda="ARS",
        comercio="ALEJANDRO ALBERTO TOCC",
        titular="Claudia Elizabet Rotondo",
        tipo_tarjeta="Adicional",
        plan="01",
        cuenta_deuda="naranja",
        aplica_deuda=True,
        fecha_corte="2026-10-07T17:30:00",
    )

    assert resultado["ok"] is True
    assert resultado["genera_deuda"] is False
    assert resultado["estado"] == "historico_no_aplicado"

    conexion = obtener_conexion()

    cantidad = conexion.execute(
        """
        SELECT COUNT(*)
        FROM movimientos_deuda_negocio
        """
    ).fetchone()[0]

    conexion.close()

    assert cantidad == 0


def test_moneda_no_ars_requiere_revision_y_no_aumenta_deuda(
    base_prueba
):
    resultado = registrar_importacion_deuda(
        fuente="gmail_naranja",
        id_externo="usd-1",
        importe=100,
        fecha_operacion="2026-10-07T18:00:00",
        moneda="USD",
        comercio="COMERCIO PRUEBA",
        titular="Claudia Elizabet Rotondo",
        tipo_tarjeta="Adicional",
        plan="01",
        cuenta_deuda="naranja",
        aplica_deuda=True,
        fecha_corte="2026-10-07T17:30:00",
    )

    assert resultado["ok"] is True
    assert resultado["genera_deuda"] is False
    assert resultado["estado"] == "requiere_revision_moneda"



def test_comando_lista_compras_naranja_pendientes(
    base_prueba
):
    importacion = registrar_importacion_deuda(
        fuente="gmail_naranja",
        id_externo="pendiente-1",
        importe=28000,
        fecha_operacion="2026-10-08T10:15:00",
        moneda="ARS",
        comercio="DISTRIBUIDORA PRUEBA",
        titular="Claudia Elizabet Rotondo",
        tipo_tarjeta="Adicional",
        plan="01",
        cuenta_deuda="naranja",
        aplica_deuda=True,
        fecha_corte="2026-10-07T13:25:00",
    )

    assert importacion["ok"] is True

    respuesta = client.post(
        "/comandos",
        json={
            "mensaje": "compras naranja pendientes"
        }
    )

    assert respuesta.status_code == 200

    datos = respuesta.json()

    assert datos["ok"] is True
    assert len(datos["importaciones"]) == 1
    assert datos["importaciones"][0]["importe"] == 28000
    assert "DISTRIBUIDORA PRUEBA" in datos["respuesta"]
    assert (
        f"#{importacion['id_importacion']}"
        in datos["respuesta"]
    )


def test_comando_detalle_importacion_naranja(
    base_prueba
):
    importacion = registrar_importacion_deuda(
        fuente="gmail_naranja",
        id_externo="detalle-1",
        importe=44500,
        fecha_operacion="2026-10-08T11:30:00",
        moneda="ARS",
        comercio="COMERCIO DETALLE",
        titular="Claudia Elizabet Rotondo",
        tipo_tarjeta="Adicional",
        plan="01",
        cuenta_deuda="naranja",
        aplica_deuda=True,
        fecha_corte="2026-10-07T13:25:00",
    )

    respuesta = client.post(
        "/comandos",
        json={
            "mensaje": (
                "importacion "
                f"{importacion['id_importacion']}"
            )
        }
    )

    assert respuesta.status_code == 200

    datos = respuesta.json()

    assert datos["ok"] is True
    assert datos["importe"] == 44500
    assert datos["comercio"] == "COMERCIO DETALLE"
    assert datos["estado"] == "pendiente_clasificacion"
    assert (
        datos["id_movimiento_deuda"]
        == importacion["id_movimiento_deuda"]
    )
