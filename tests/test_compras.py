from database import obtener_conexion
from compras import registrar_compra, anular_compra


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


def test_compra_y_anulacion_restauran_stock(
    producto_prueba
):

    id_producto = producto_prueba

    # Comenzamos con 10.
    assert obtener_stock(id_producto) == 10

    # Compramos 5.
    compra = registrar_compra(
        id_producto=id_producto,
        cantidad=5,
        precio_unitario=1500,
        fecha="2026-09-29"
    )

    assert compra["ok"] is True

    # El stock debe subir a 15.
    assert obtener_stock(id_producto) == 15

    # Anulamos la compra.
    anulacion = anular_compra(
        id_compra=compra["id_compra"],
        motivo="Prueba automática"
    )

    assert anulacion["ok"] is True

    # Debe volver a 10.
    assert obtener_stock(id_producto) == 10

    # No debe poder anularse otra vez.
    segunda_anulacion = anular_compra(
        id_compra=compra["id_compra"],
        motivo="Segunda anulación"
    )

    assert segunda_anulacion["ok"] is False

    assert obtener_stock(id_producto) == 10