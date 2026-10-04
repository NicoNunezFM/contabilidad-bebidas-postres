from acciones import ejecutar_accion
from database import obtener_conexion


def crear_producto(
    nombre,
    precio,
    stock,
    controla_stock=True
):
    conexion = obtener_conexion()

    cursor = conexion.execute(
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
            nombre,
            "Bebidas",
            "Unidad",
            1,
            "unidad",
            1,
            stock,
            precio,
            int(controla_stock),
        )
    )

    id_producto = cursor.lastrowid

    conexion.commit()
    conexion.close()

    return id_producto


def test_venta_simple_queda_cobrada_por_defecto(
    base_prueba
):
    crear_producto(
        nombre="Pepsi lata",
        precio=1600,
        stock=5,
    )

    resultado = ejecutar_accion({
        "accion": "registrar_venta",
        "datos": {
            "producto": "pepsi",
            "cantidad": 1,
        },
    })

    assert resultado["ok"] is True
    assert resultado["datos"]["estado_pago"] == "Cobrado"

    id_operacion = resultado["datos"]["id_operacion"]

    conexion = obtener_conexion()

    estado = conexion.execute(
        """
        SELECT estado_pago
        FROM ventas_operaciones
        WHERE id_operacion = ?
        """,
        (id_operacion,)
    ).fetchone()[0]

    conexion.close()

    assert estado == "Cobrado"


def test_venta_multiple_queda_cobrada_por_defecto(
    base_prueba
):
    crear_producto(
        nombre="Pepsi lata",
        precio=1600,
        stock=5,
    )

    crear_producto(
        nombre="Oreo",
        precio=4500,
        stock=3,
    )

    resultado = ejecutar_accion({
        "accion": "registrar_venta",
        "datos": {
            "items": [
                {
                    "producto": "pepsi",
                    "cantidad": 1,
                },
                {
                    "producto": "oreo",
                    "cantidad": 1,
                },
            ]
        },
    })

    assert resultado["ok"] is True
    assert resultado["datos"]["estado_pago"] == "Cobrado"

    id_operacion = resultado["datos"]["id_operacion"]

    conexion = obtener_conexion()

    estado = conexion.execute(
        """
        SELECT estado_pago
        FROM ventas_operaciones
        WHERE id_operacion = ?
        """,
        (id_operacion,)
    ).fetchone()[0]

    conexion.close()

    assert estado == "Cobrado"
