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

def test_compra_rechaza_cantidad_booleano(base_prueba, producto_prueba):
    resultado = registrar_compra(
        id_producto=producto_prueba,
        cantidad=True,
        precio_unitario=1000
    )

    assert resultado["ok"] is False
    assert resultado["codigo"] == "DATOS_INVALIDOS"

def test_compra_rechaza_precio_booleano(base_prueba, producto_prueba):
    resultado = registrar_compra(
        id_producto=producto_prueba,
        cantidad=2,
        precio_unitario=True
    )

    assert resultado["ok"] is False
    assert resultado["codigo"] == "DATOS_INVALIDOS"

def test_compra_rechaza_id_producto_booleano(base_prueba, producto_prueba):
    resultado = registrar_compra(
        id_producto=True,
        cantidad=2,
        precio_unitario=1000
    )

    assert resultado["ok"] is False
    assert resultado["codigo"] == "DATOS_INVALIDOS"

def test_no_permite_anular_compra_sin_stock_suficiente(
    producto_prueba
):
    id_producto = producto_prueba

    compra = registrar_compra(
        id_producto=id_producto,
        cantidad=5,
        precio_unitario=1000,
        fecha="2026-09-29"
    )

    assert compra["ok"] is True

    conexion = obtener_conexion()

    conexion.execute(
        """
        UPDATE productos
        SET stock = 4
        WHERE id_producto = ?
        """,
        (id_producto,)
    )

    conexion.commit()
    conexion.close()

    anulacion = anular_compra(
        id_compra=compra["id_compra"],
        motivo="Stock insuficiente para prueba"
    )

    assert anulacion["ok"] is False
    assert anulacion["codigo"] == (
        "STOCK_INSUFICIENTE_PARA_ANULAR_COMPRA"
    )

    assert obtener_stock(id_producto) == 4