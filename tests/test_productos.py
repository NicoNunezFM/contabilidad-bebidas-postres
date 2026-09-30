from database import obtener_conexion
from productos import (
    buscar_producto_por_id,
    eliminar_producto,
)
from productos import agregar_producto


def test_no_permite_eliminar_producto_con_ajuste_stock(
    base_prueba,
    producto_prueba,
):
    conexion = obtener_conexion()

    conexion.execute(
        """
        INSERT INTO ajustes_stock (
            id_producto,
            fecha,
            cantidad_ajuste,
            motivo,
            stock_anterior,
            stock_nuevo
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            producto_prueba,
            "2026-09-30",
            2,
            "Inventario físico",
            10,
            12,
        ),
    )

    conexion.commit()
    conexion.close()

    resultado = eliminar_producto(producto_prueba)

    assert resultado["ok"] is False
    assert resultado["mensaje"] == (
        "No se puede eliminar el producto porque tiene "
        "compras, ventas o ajustes de stock registrados."
    )
    assert buscar_producto_por_id(producto_prueba) is not None

def test_agregar_producto_rechaza_contenido_booleano(base_prueba):
    resultado = agregar_producto(
        "Producto prueba",
        "Bebidas",
        "Botella",
        True,
        "Litros",
        6,
    )

    assert resultado["ok"] is False
    assert resultado["mensaje"] == "El contenido debe ser un número."