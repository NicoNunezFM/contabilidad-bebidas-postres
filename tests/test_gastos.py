from gastos import registrar_gasto, anular_gasto
from reportes import resumen_por_periodo


def test_gasto_y_anulacion_actualizan_resultado(
    base_prueba
):

    gasto = registrar_gasto(
        categoria="Transporte",
        descripcion_gasto="Gasto de prueba",
        valor_final=2000,
        fecha="2026-09-29"
    )

    assert gasto["ok"] is True

    resumen = resumen_por_periodo(
        "2026-09-29",
        "2026-09-29"
    )

    assert resumen["gastos"] == 2000
    assert resumen["resultado_negocio"] == -2000

    anulacion = anular_gasto(
        id_gasto=gasto["id_gasto"],
        motivo="Prueba automática"
    )

    assert anulacion["ok"] is True

    resumen_despues = resumen_por_periodo(
        "2026-09-29",
        "2026-09-29"
    )

    assert resumen_despues["gastos"] == 0
    assert resumen_despues["resultado_negocio"] == 0


def test_no_permite_anular_gasto_dos_veces(
    base_prueba
):

    gasto = registrar_gasto(
        categoria="Transporte",
        descripcion_gasto="Gasto de prueba",
        valor_final=1000,
        fecha="2026-09-29"
    )

    primera = anular_gasto(
        id_gasto=gasto["id_gasto"],
        motivo="Primera anulación"
    )

    assert primera["ok"] is True

    segunda = anular_gasto(
        id_gasto=gasto["id_gasto"],
        motivo="Segunda anulación"
    )

    assert segunda["ok"] is False