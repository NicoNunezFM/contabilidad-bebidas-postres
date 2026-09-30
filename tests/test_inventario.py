from database import obtener_conexion
from ajustes_stock import registrar_inventario_fisico


def obtener_stock(id_producto):

    conexion = obtener_conexion()

    resultado = conexion.execute(
        """
        SELECT stock
        FROM productos
        WHERE id_producto = ?
        """,
        (id_producto,)
    ).fetchone()

    conexion.close()

    return resultado[0]


def contar_ajustes():

    conexion = obtener_conexion()

    cantidad = conexion.execute(
        """
        SELECT COUNT(*)
        FROM ajustes_stock
        """
    ).fetchone()[0]

    conexion.close()

    return cantidad


def test_inventario_fisico_ajusta_stock(
    producto_prueba
):

    id_producto = producto_prueba

    assert obtener_stock(id_producto) == 10

    resultado = registrar_inventario_fisico(
        id_producto=id_producto,
        cantidad_real=7,
        fecha="2026-09-29"
    )

    assert resultado["ok"] is True
    assert obtener_stock(id_producto) == 7
    assert contar_ajustes() == 1


def test_inventario_igual_no_genera_otro_ajuste(
    producto_prueba
):

    id_producto = producto_prueba

    primer_resultado = registrar_inventario_fisico(
        id_producto=id_producto,
        cantidad_real=7,
        fecha="2026-09-29"
    )

    assert primer_resultado["ok"] is True
    assert contar_ajustes() == 1

    segundo_resultado = registrar_inventario_fisico(
        id_producto=id_producto,
        cantidad_real=7,
        fecha="2026-09-29"
    )

    assert segundo_resultado["ok"] is True

    assert obtener_stock(id_producto) == 7
    assert contar_ajustes() == 1