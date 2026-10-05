from database import obtener_conexion


CATALOGO_PRECIOS = [
    # Bebidas
    {"nombre": "Manaos Pomelo 600ml", "categoria": "Bebidas", "precio": 1300, "controla_stock": True, "unidades_por_pack": 12},
    {"nombre": "Manaos Cola 600ml", "categoria": "Bebidas", "precio": 1300, "controla_stock": True, "unidades_por_pack": 12},
    {"nombre": "Manaos Cola 2.25l", "categoria": "Bebidas", "precio": 2000, "controla_stock": True, "unidades_por_pack": 6},
    {"nombre": "Manaos Naranja 2.25l", "categoria": "Bebidas", "precio": 2000, "controla_stock": True, "unidades_por_pack": 6},
    {"nombre": "Manaos Manzana 2.25l", "categoria": "Bebidas", "precio": 2000, "controla_stock": True, "unidades_por_pack": 6},
    {"nombre": "Manaos Pomelo 2.25l", "categoria": "Bebidas", "precio": 2000, "controla_stock": True, "unidades_por_pack": 6},
    {"nombre": "Manaos Lima 2.25l", "categoria": "Bebidas", "precio": 2000, "controla_stock": True, "unidades_por_pack": 6},
    {"nombre": "Pepsi lata", "categoria": "Bebidas", "precio": 1600, "controla_stock": True},
    {"nombre": "7up lata", "categoria": "Bebidas", "precio": 1600, "controla_stock": True},

    # Sánguches
    {"nombre": "Grande de pollo individual", "categoria": "Sanguches", "precio": 6500, "controla_stock": False},
    {"nombre": "Grande de carne individual", "categoria": "Sanguches", "precio": 7500, "controla_stock": False},
    {"nombre": "Chico de pollo + papas", "categoria": "Sanguches", "precio": 6000, "controla_stock": False},
    {"nombre": "Chico de carne + papas", "categoria": "Sanguches", "precio": 7000, "controla_stock": False},
    {"nombre": "Grande de pollo + papas", "categoria": "Sanguches", "precio": 8000, "controla_stock": False},
    {"nombre": "Grande de carne + papas", "categoria": "Sanguches", "precio": 9000, "controla_stock": False},

    # Conos
    {"nombre": "Conos", "categoria": "Conos", "precio": 2500, "controla_stock": False},
    {"nombre": "Bandeja chica", "categoria": "Conos", "precio": 3500, "controla_stock": False},
    {"nombre": "Bandeja grande", "categoria": "Conos", "precio": 4500, "controla_stock": False},

    # Al plato
    {"nombre": "Milanesa de pollo con fritas", "categoria": "Al plato", "precio": 8500, "controla_stock": False},
    {"nombre": "Milanesa de carne con fritas", "categoria": "Al plato", "precio": 9500, "controla_stock": False},
    {"nombre": "Milanesa de pollo con pure", "categoria": "Al plato", "precio": 8000, "controla_stock": False},
    {"nombre": "Milanesa de carne con pure", "categoria": "Al plato", "precio": 9000, "controla_stock": False},
    {"nombre": "Napo de pollo con fritas", "categoria": "Al plato", "precio": 9500, "controla_stock": False},
    {"nombre": "Napo de carne con fritas", "categoria": "Al plato", "precio": 10500, "controla_stock": False},
    {"nombre": "Napo de pollo con pure", "categoria": "Al plato", "precio": 9500, "controla_stock": False},
    {"nombre": "Napo de carne con pure", "categoria": "Al plato", "precio": 10500, "controla_stock": False},
    {"nombre": "Tortilla", "categoria": "Al plato", "precio": 7500, "controla_stock": False},

    # Hamburguesas
    {"nombre": "Pollo con papas simple", "categoria": "Hamburguesas", "precio": 5500, "controla_stock": False},
    {"nombre": "Big mac simple", "categoria": "Hamburguesas", "precio": 7000, "controla_stock": False},
    {"nombre": "Big mac doble", "categoria": "Hamburguesas", "precio": 9000, "controla_stock": False},
    {"nombre": "Cheddar y huevo simple", "categoria": "Hamburguesas", "precio": 7000, "controla_stock": False},
    {"nombre": "Cheddar y huevo doble", "categoria": "Hamburguesas", "precio": 9000, "controla_stock": False},
    {"nombre": "Clasica simple", "categoria": "Hamburguesas", "precio": 6500, "controla_stock": False},
    {"nombre": "Clasica doble", "categoria": "Hamburguesas", "precio": 8500, "controla_stock": False},

    # Postres
    {"nombre": "Chocotorta", "categoria": "Postres", "precio": 4500, "controla_stock": True},
    {"nombre": "Oreo", "categoria": "Postres", "precio": 4500, "controla_stock": True},
]


def asegurar_productos_catalogo():
    """
    Crea únicamente los productos del catálogo que todavía no existen.

    No modifica precios ni stock de productos ya existentes.
    Solo sincroniza unidades_por_pack cuando el catálogo define
    explícitamente ese dato operativo. Es seguro ejecutarlo en cada arranque.
    """

    conexion = obtener_conexion()
    creados = 0

    try:
        cursor = conexion.cursor()

        for item in CATALOGO_PRECIOS:
            cursor.execute(
                """
                SELECT id_producto
                FROM productos
                WHERE LOWER(nombre) = LOWER(?)
                """,
                (item["nombre"],)
            )

            existente = cursor.fetchone()

            if existente is not None:
                if "unidades_por_pack" in item:
                    cursor.execute(
                        """
                        UPDATE productos
                        SET unidades_por_pack = ?
                        WHERE id_producto = ?
                        """,
                        (
                            item["unidades_por_pack"],
                            existente[0],
                        )
                    )
                continue

            cursor.execute(
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
                    item["nombre"],
                    item["categoria"],
                    "Unidad",
                    1,
                    "unidad",
                    item.get("unidades_por_pack", 1),
                    0,
                    item["precio"],
                    int(item["controla_stock"]),
                )
            )

            creados += 1

        conexion.commit()

        return {
            "ok": True,
            "creados": creados,
            "total_catalogo": len(CATALOGO_PRECIOS),
        }

    finally:
        conexion.close()


def sincronizar_catalogo():
    """
    Crea los productos que no existan y actualiza precio/categoría/control de stock
    de los que ya existan. Nunca pisa el stock existente.
    """

    conexion = obtener_conexion()

    creados = 0
    actualizados = 0

    try:
        cursor = conexion.cursor()

        for item in CATALOGO_PRECIOS:
            cursor.execute(
                """
                SELECT id_producto
                FROM productos
                WHERE LOWER(nombre) = LOWER(?)
                """,
                (item["nombre"],)
            )

            existente = cursor.fetchone()

            if existente is None:
                cursor.execute(
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
                        item["nombre"],
                        item["categoria"],
                        "Unidad",
                        1,
                        "unidad",
                        item.get("unidades_por_pack", 1),
                        0,
                        item["precio"],
                        int(item["controla_stock"]),
                    )
                )
                creados += 1

            else:
                cursor.execute(
                    """
                    UPDATE productos
                    SET
                        categoria = ?,
                        precio_venta = ?,
                        controla_stock = ?
                    WHERE id_producto = ?
                    """,
                    (
                        item["categoria"],
                        item["precio"],
                        int(item["controla_stock"]),
                        existente[0],
                    )
                )
                actualizados += 1

        conexion.commit()

        return {
            "ok": True,
            "creados": creados,
            "actualizados": actualizados,
            "total_catalogo": len(CATALOGO_PRECIOS),
        }

    finally:
        conexion.close()
