from database import obtener_conexion
from ventas import registrar_venta, anular_venta


def obtener_stock(id_producto):

    conexion = obtener_conexion()

    cursor = conexion.execute(
        """
        SELECT stock
        FROM productos
        WHERE id_producto = ?
        """,
        (id_producto,)
    )

    resultado = cursor.fetchone()

    conexion.close()

    return resultado[0]


def test_venta_y_anulacion_restauran_stock(
    producto_prueba
):

    id_producto = producto_prueba

    # 1. El producto comienza con 10 unidades.
    stock_inicial = obtener_stock(id_producto)

    assert stock_inicial == 10

    # 2. Vendemos 2 unidades.
    venta = registrar_venta(
        id_producto=id_producto,
        cantidad=2,
        precio_unitario=3000,
        fecha="2026-09-29"
    )

    assert venta["ok"] is True

    # 3. El stock debería quedar en 8.
    stock_despues_venta = obtener_stock(
        id_producto
    )

    assert stock_despues_venta == 8

    # 4. Anulamos esa venta.
    anulacion = anular_venta(
        id_venta=venta["id_venta"],
        motivo="Prueba automática"
    )

    assert anulacion["ok"] is True

    # 5. El stock debería volver a 10.
    stock_despues_anulacion = obtener_stock(
        id_producto
    )

    assert stock_despues_anulacion == 10

    # 6. No debería permitir anularla otra vez.
    segunda_anulacion = anular_venta(
        id_venta=venta["id_venta"],
        motivo="Segunda anulación"
    )

    assert segunda_anulacion["ok"] is False

    # 7. El stock debe seguir siendo 10.
    stock_final = obtener_stock(id_producto)

    assert stock_final == 10

def test_no_permite_vender_mas_stock_del_disponible(
    producto_prueba
):

    id_producto = producto_prueba

    # El producto tiene 10 unidades.
    stock_inicial = obtener_stock(id_producto)

    assert stock_inicial == 10

    # Intentamos vender 15.
    venta = registrar_venta(
        id_producto=id_producto,
        cantidad=15,
        precio_unitario=3000,
        fecha="2026-09-29"
    )

    # La operación debe ser rechazada.
    assert venta["ok"] is False

    # El stock no debe modificarse.
    stock_final = obtener_stock(id_producto)

    assert stock_final == 10