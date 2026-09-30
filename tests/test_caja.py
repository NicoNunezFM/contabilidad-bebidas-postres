from movimientos_caja import (
    registrar_aporte,
    registrar_retiro,
    anular_movimiento_caja
)

from caja import obtener_estado_caja

def test_aporte_y_retiro_modifican_caja(
    base_prueba
):

    aporte = registrar_aporte(
        descripcion="Aporte de prueba",
        monto=5000,
        fecha="2026-09-29"
    )

    assert aporte["ok"] is True

    retiro = registrar_retiro(
        descripcion="Retiro de prueba",
        monto=1500,
        fecha="2026-09-29"
    )

    assert retiro["ok"] is True

    caja = obtener_estado_caja()

    assert caja["aportes"] == 5000
    assert caja["retiros"] == 1500
    assert caja["saldo_caja"] == 3500
    assert caja["saldo_fisico"] == 3500
    assert caja["saldo_disponible"] == 3500


def test_anular_retiro_restaurar_caja(
    base_prueba
):

    registrar_aporte(
        descripcion="Aporte de prueba",
        monto=5000,
        fecha="2026-09-29"
    )

    retiro = registrar_retiro(
        descripcion="Retiro a anular",
        monto=1500,
        fecha="2026-09-29"
    )

    assert retiro["ok"] is True

    assert obtener_estado_caja()["saldo_caja"] == 3500

    anulacion = anular_movimiento_caja(
        id_movimiento=retiro["id_movimiento"],
        motivo="Prueba automática"
    )

    assert anulacion["ok"] is True

    caja_final = obtener_estado_caja()

    assert caja_final["aportes"] == 5000
    assert caja_final["retiros"] == 0
    assert caja_final["saldo_caja"] == 5000