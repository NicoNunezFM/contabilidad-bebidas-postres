from datetime import date

from compras import registrar_compra
from ventas import registrar_venta
from gastos import registrar_gasto

from cierres import (
    registrar_cierre_semanal,
    registrar_cierre_mensual
)


def crear_movimientos_prueba(id_producto):

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


def test_cierre_semanal_calcula_resultado_y_diezmo(
    producto_prueba
):

    id_producto = producto_prueba

    crear_movimientos_prueba(id_producto)

    cierre = registrar_cierre_semanal(
        fecha_desde="2026-08-10",
        fecha_hasta="2026-08-16"
    )

    assert cierre["ok"] is True

    assert cierre["resultado_negocio"] == 6000
    assert cierre["diezmo_estimado"] == 600
    assert cierre["resultado_despues_diezmo"] == 5400


def test_no_permite_cierre_semanal_duplicado(
    producto_prueba
):

    id_producto = producto_prueba

    crear_movimientos_prueba(id_producto)

    primero = registrar_cierre_semanal(
        fecha_desde="2026-08-10",
        fecha_hasta="2026-08-16"
    )

    assert primero["ok"] is True

    segundo = registrar_cierre_semanal(
        fecha_desde="2026-08-10",
        fecha_hasta="2026-08-16"
    )

    assert segundo["ok"] is False


def test_cierre_mensual_calcula_diezmo_oficial(
    producto_prueba
):

    id_producto = producto_prueba

    crear_movimientos_prueba(id_producto)

    cierre = registrar_cierre_mensual(
        anio=2026,
        mes=8
    )

    assert cierre["ok"] is True
    assert cierre["resultado_negocio"] == 6000
    assert cierre["diezmo_correspondiente"] == 600


def test_no_permite_cierre_mensual_duplicado(
    producto_prueba
):

    id_producto = producto_prueba

    crear_movimientos_prueba(id_producto)

    primero = registrar_cierre_mensual(
        anio=2026,
        mes=8
    )

    assert primero["ok"] is True

    segundo = registrar_cierre_mensual(
        anio=2026,
        mes=8
    )

    assert segundo["ok"] is False


def test_no_permite_cerrar_mes_actual(
    base_prueba
):

    hoy = date.today()

    cierre = registrar_cierre_mensual(
        anio=hoy.year,
        mes=hoy.month
    )

    assert cierre["ok"] is False