from movimientos_caja import (
    registrar_aporte,
    registrar_retiro,
    anular_movimiento_caja,
    total_aportes,
    total_retiros,
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

def test_aporte_rechaza_monto_booleano(base_prueba):
    resultado = registrar_aporte(
        descripcion="Aporte prueba",
        monto=True
    )

    assert resultado["ok"] is False
    assert resultado["codigo"] == "DATOS_INVALIDOS"


def test_anular_movimiento_rechaza_id_booleano(base_prueba):
    movimiento = registrar_aporte(
        descripcion="Aporte para prueba",
        monto=5000
    )

    assert movimiento["ok"] is True

    resultado = anular_movimiento_caja(
        id_movimiento=True,
        motivo="Prueba"
    )

    assert resultado["ok"] is False
    assert resultado["codigo"] == "DATOS_INVALIDOS"


def test_total_aportes_excluye_aportes_anulados(base_prueba):
    aporte_activo = registrar_aporte(
        descripcion="Aporte activo",
        monto=5000
    )

    aporte_anular = registrar_aporte(
        descripcion="Aporte a anular",
        monto=3000
    )

    assert aporte_activo["ok"] is True
    assert aporte_anular["ok"] is True

    anular = anular_movimiento_caja(
        id_movimiento=aporte_anular["id_movimiento"],
        motivo="No corresponde"
    )

    assert anular["ok"] is True
    assert total_aportes() == 5000


def test_total_retiros_excluye_retiros_anulados(base_prueba):
    retiro_activo = registrar_retiro(
        descripcion="Retiro activo",
        monto=2000
    )

    retiro_anular = registrar_retiro(
        descripcion="Retiro a anular",
        monto=1500
    )

    assert retiro_activo["ok"] is True
    assert retiro_anular["ok"] is True

    anular = anular_movimiento_caja(
        id_movimiento=retiro_anular["id_movimiento"],
        motivo="No corresponde"
    )

    assert anular["ok"] is True
    assert total_retiros() == 2000