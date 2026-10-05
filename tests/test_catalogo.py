from catalogo import asegurar_productos_catalogo
from database import obtener_conexion


def test_catalogo_agrega_manaos_lima_si_falta(
    base_prueba
):
    resultado = asegurar_productos_catalogo()

    assert resultado["ok"] is True

    conexion = obtener_conexion()

    fila = conexion.execute(
        """
        SELECT
            nombre,
            categoria,
            precio_venta,
            controla_stock,
            stock
        FROM productos
        WHERE nombre = ?
        """,
        ("Manaos Lima 2.25l",)
    ).fetchone()

    conexion.close()

    assert fila == (
        "Manaos Lima 2.25l",
        "Bebidas",
        2000,
        1,
        0,
    )


def test_catalogo_no_pisa_producto_existente(
    base_prueba
):
    conexion = obtener_conexion()

    conexion.execute(
        """
        INSERT INTO productos (
            nombre,
            categoria,
            presentacion,
            contenido,
            unidad_medida,
            unidades_por_pack,
            stock,
            precio_venta,
            controla_stock
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "Manaos Cola 2.25l",
            "Bebidas",
            "Unidad",
            1,
            "unidad",
            1,
            7,
            2500,
            1,
        )
    )

    conexion.commit()
    conexion.close()

    asegurar_productos_catalogo()

    conexion = obtener_conexion()

    fila = conexion.execute(
        """
        SELECT stock, precio_venta, unidades_por_pack
        FROM productos
        WHERE nombre = ?
        """,
        ("Manaos Cola 2.25l",)
    ).fetchone()

    conexion.close()

    assert fila == (
        7,
        2500,
        6,
    )
