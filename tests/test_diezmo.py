from compras import registrar_compra
from ventas import registrar_venta
from gastos import registrar_gasto

from cierres import registrar_cierre_mensual

from diezmo import (
    estado_diezmo_mes,
    registrar_reserva_diezmo,
    registrar_entrega_diezmo
)


def preparar_mes_con_diezmo(id_producto):

    registrar_compra(
        id_producto=id_producto,
        cantidad=10,
        precio_unitario=1000,
        fecha="2026-08-10"
    )

    registrar_venta(
        id_producto=id_producto,
        cantidad=6,
        precio_unitario=3000,
        fecha="2026-08-10"
    )

    registrar_gasto(
        categoria="Transporte",
        descripcion_gasto="Gasto de prueba",
        valor_final=2000,
        fecha="2026-08-10"
    )

    cierre = registrar_cierre_mensual(
        anio=2026,
        mes=8
    )

    assert cierre["ok"] is True

    return cierre


def test_estado_diezmo_despues_del_cierre(
    producto_prueba
):

    preparar_mes_con_diezmo(
        producto_prueba
    )

    estado = estado_diezmo_mes(
        anio=2026,
        mes=8
    )

    assert estado["ok"] is True
    assert estado["cerrado"] is True

    assert estado["resultado_negocio"] == 6000
    assert estado["diezmo_correspondiente"] == 600

    assert estado["reservado"] == 0
    assert estado["pendiente_reservar"] == 600

    assert estado["entregado"] == 0
    assert estado["pendiente_entregar"] == 600

def test_reservas_diezmo_respetan_limite(
    producto_prueba
):

    preparar_mes_con_diezmo(
        producto_prueba
    )

    primera_reserva = registrar_reserva_diezmo(
        anio=2026,
        mes=8,
        monto=500,
        descripcion="Reserva automática"
    )

    assert primera_reserva["ok"] is True

    estado = estado_diezmo_mes(
        anio=2026,
        mes=8
    )

    assert estado["reservado"] == 500
    assert estado["pendiente_reservar"] == 100

    # Intentamos reservar 200 cuando solamente faltan 100.
    reserva_excesiva = registrar_reserva_diezmo(
        anio=2026,
        mes=8,
        monto=200,
        descripcion="Reserva excesiva"
    )

    assert reserva_excesiva["ok"] is False

    # El rechazo no debe modificar lo ya reservado.
    estado = estado_diezmo_mes(
        anio=2026,
        mes=8
    )

    assert estado["reservado"] == 500
    assert estado["pendiente_reservar"] == 100

    segunda_reserva = registrar_reserva_diezmo(
        anio=2026,
        mes=8,
        monto=100,
        descripcion="Completar reserva"
    )

    assert segunda_reserva["ok"] is True

    estado_final = estado_diezmo_mes(
        anio=2026,
        mes=8
    )

    assert estado_final["reservado"] == 600
    assert estado_final["pendiente_reservar"] == 0

def test_entrega_diezmo_respeta_limite(
    producto_prueba
):

    preparar_mes_con_diezmo(
        producto_prueba
    )

    reserva = registrar_reserva_diezmo(
        anio=2026,
        mes=8,
        monto=600,
        descripcion="Reserva completa"
    )

    assert reserva["ok"] is True

    # El diezmo oficial es 600.
    # Intentamos entregar 700.
    entrega_excesiva = registrar_entrega_diezmo(
        anio=2026,
        mes=8,
        monto=700,
        descripcion="Entrega excesiva"
    )

    assert entrega_excesiva["ok"] is False

    estado = estado_diezmo_mes(
        anio=2026,
        mes=8
    )

    assert estado["entregado"] == 0
    assert estado["pendiente_entregar"] == 600

    entrega = registrar_entrega_diezmo(
        anio=2026,
        mes=8,
        monto=600,
        descripcion="Entrega completa"
    )

    assert entrega["ok"] is True

    estado_final = estado_diezmo_mes(
        anio=2026,
        mes=8
    )

    assert estado_final["entregado"] == 600
    assert estado_final["pendiente_entregar"] == 0