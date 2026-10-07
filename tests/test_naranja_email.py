from naranja_email import parsear_correo_compra_naranja


CUERPO_ADICIONAL = """
TU COMPRA

$

104.498,00

ALEJANDRO ALBERTO TOCC

Adicional

-
Claudia Elizabet Rotondo

Tarjeta
MASTER INTERNACIONAL

Plan
01

cuota

en

PESOS

Martes 15/SET
-
12:36
h
"""


def test_parsea_compra_adicional_del_negocio():
    resultado = parsear_correo_compra_naranja(
        asunto=(
            "Sergio Nicolas👉 Ingresó una compra "
            "en tu tarjeta crédito"
        ),
        cuerpo=CUERPO_ADICIONAL,
        fecha_email="2026-09-15T13:00:58-03:00",
    )

    assert resultado["ok"] is True
    assert resultado["importe"] == 104498
    assert resultado["comercio"] == "ALEJANDRO ALBERTO TOCC"
    assert resultado["tipo_tarjeta"] == "Adicional"
    assert resultado["titular"] == "Claudia Elizabet Rotondo"
    assert resultado["tarjeta"] == "MASTER INTERNACIONAL"
    assert resultado["plan"] == "01"
    assert resultado["moneda"] == "ARS"
    assert resultado["fecha_operacion"] == "2026-09-15T12:36"
    assert resultado["es_adicional_negocio"] is True
    assert resultado["estado_sugerido"] == "pendiente_clasificacion"


def test_tarjeta_titular_no_se_considera_negocio():
    cuerpo = CUERPO_ADICIONAL.replace(
        "Adicional\n\n-\nClaudia Elizabet Rotondo",
        "Titular\n\n-\nSergio Nicolas Nunez",
    )

    resultado = parsear_correo_compra_naranja(
        asunto=(
            "Sergio Nicolas👉 Ingresó una compra "
            "en tu tarjeta crédito"
        ),
        cuerpo=cuerpo,
        fecha_email="2026-09-15T13:00:58-03:00",
    )

    assert resultado["ok"] is True
    assert resultado["es_adicional_negocio"] is False
    assert resultado["estado_sugerido"] == "ignorado_no_negocio"


def test_rechaza_correo_que_no_es_aviso_de_compra():
    resultado = parsear_correo_compra_naranja(
        asunto="Tu resumen está disponible",
        cuerpo=CUERPO_ADICIONAL,
        fecha_email="2026-09-15T13:00:58-03:00",
    )

    assert resultado["ok"] is False
    assert resultado["codigo"] == "CORREO_NARANJA_NO_ES_COMPRA"



def test_rechaza_remitente_no_oficial_de_naranja():
    resultado = parsear_correo_compra_naranja(
        asunto=(
            "Sergio Nicolas👉 Ingresó una compra "
            "en tu tarjeta crédito"
        ),
        cuerpo=CUERPO_ADICIONAL,
        fecha_email="2026-09-15T13:00:58-03:00",
        remitente="Aviso <otro@example.com>",
    )

    assert resultado["ok"] is False
    assert (
        resultado["codigo"]
        == "REMITENTE_NARANJA_NO_CONFIABLE"
    )
