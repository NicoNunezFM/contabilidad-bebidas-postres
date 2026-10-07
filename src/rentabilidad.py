from database import obtener_conexion
from costos_postres import estimar_costo_receta


CATEGORIAS_RENTABILIDAD = {
    "bebidas": {"bebidas"},
    "postres": {"postres"},
}


def _costo_unitario_bebida(
    id_producto,
    compras_a_promediar=3,
):
    conexion = obtener_conexion()

    try:
        filas = conexion.execute(
            """
            SELECT
                cantidad,
                precio_unitario
            FROM compras
            WHERE id_producto = ?
              AND anulada = 0
            ORDER BY fecha DESC, id_compra DESC
            LIMIT ?
            """,
            (
                id_producto,
                compras_a_promediar,
            )
        ).fetchall()

    finally:
        conexion.close()

    if not filas:
        return None

    unidades = sum(
        int(fila[0])
        for fila in filas
    )

    if unidades <= 0:
        return None

    costo_total = sum(
        int(fila[0]) * float(fila[1])
        for fila in filas
    )

    return {
        "costo_unitario": (
            costo_total / unidades
        ),
        "fuente": (
            f"promedio ponderado de las últimas "
            f"{len(filas)} compras"
        ),
        "compras_consideradas": len(filas),
    }


def _costo_unitario_postre(
    nombre_producto,
):
    conexion = obtener_conexion()

    try:
        fila = conexion.execute(
            """
            SELECT
                costo_unitario,
                id_produccion,
                version_receta,
                fecha_hora
            FROM producciones_postres
            WHERE LOWER(producto) = LOWER(?)
            ORDER BY id_produccion DESC
            LIMIT 1
            """,
            (nombre_producto,)
        ).fetchone()

    finally:
        conexion.close()

    if fila is not None:
        return {
            "costo_unitario": float(
                fila[0]
            ),
            "fuente": "última producción registrada",
            "id_produccion": fila[1],
            "version_receta": fila[2],
            "fecha_costo": fila[3],
        }

    estimacion = estimar_costo_receta(
        producto=nombre_producto,
        cantidad_objetivo=1,
    )

    if (
        not estimacion["ok"]
        or estimacion.get(
            "costo_total_estimado"
        ) is None
    ):
        return {
            "costo_unitario": None,
            "fuente": "receta actual",
            "faltantes": estimacion.get(
                "faltantes",
                [],
            ),
        }

    return {
        "costo_unitario": float(
            estimacion[
                "costo_total_estimado"
            ]
        ),
        "fuente": (
            "estimación de la receta actual"
        ),
        "version_receta": estimacion.get(
            "version_receta"
        ),
    }


def costo_unitario_para_venta(
    id_producto,
):
    conexion = obtener_conexion()

    try:
        producto = conexion.execute(
            """
            SELECT
                nombre,
                categoria
            FROM productos
            WHERE id_producto = ?
            """,
            (id_producto,)
        ).fetchone()

    finally:
        conexion.close()

    if producto is None:
        return {
            "costo_unitario": None,
            "fuente": None,
        }

    categoria = str(
        producto[1] or ""
    ).strip().lower()

    if categoria == "bebidas":
        costo = _costo_unitario_bebida(
            id_producto
        )
    elif categoria == "postres":
        costo = _costo_unitario_postre(
            producto[0]
        )
    else:
        costo = None

    if not costo:
        return {
            "costo_unitario": None,
            "fuente": None,
        }

    return {
        "costo_unitario": costo.get(
            "costo_unitario"
        ),
        "fuente": costo.get("fuente"),
        "metadata": {
            clave: costo[clave]
            for clave in (
                "id_produccion",
                "version_receta",
                "fecha_costo",
                "compras_consideradas",
            )
            if clave in costo
        },
    }


def _ventas_producto(
    id_producto,
):
    conexion = obtener_conexion()

    try:
        fila = conexion.execute(
            """
            SELECT
                COALESCE(
                    SUM(ventas.cantidad),
                    0
                ),
                COALESCE(
                    SUM(
                        ventas.cantidad
                        * ventas.precio_unitario
                        + COALESCE(
                            (
                                SELECT SUM(
                                    precio_total
                                )
                                FROM venta_adicionales
                                WHERE
                                    venta_adicionales.id_venta
                                    = ventas.id_venta
                            ),
                            0
                        )
                    ),
                    0
                ),
                COALESCE(
                    SUM(
                        CASE
                            WHEN ventas.costo_unitario_snapshot
                                IS NOT NULL
                            THEN
                                ventas.cantidad
                                * ventas.costo_unitario_snapshot
                            ELSE 0
                        END
                    ),
                    0
                ),
                COALESCE(
                    SUM(
                        CASE
                            WHEN ventas.costo_unitario_snapshot
                                IS NULL
                            THEN ventas.cantidad
                            ELSE 0
                        END
                    ),
                    0
                )
            FROM ventas
            WHERE id_producto = ?
              AND anulada = 0
            """,
            (id_producto,)
        ).fetchone()

    finally:
        conexion.close()

    return {
        "unidades_vendidas": int(
            fila[0] or 0
        ),
        "ingresos": float(
            fila[1] or 0
        ),
        "costo_ventas_historico_conocido": float(
            fila[2] or 0
        ),
        "unidades_sin_snapshot": int(
            fila[3] or 0
        ),
    }


def rentabilidad_producto(
    id_producto,
):
    conexion = obtener_conexion()

    try:
        producto = conexion.execute(
            """
            SELECT
                id_producto,
                nombre,
                categoria,
                precio_venta,
                stock
            FROM productos
            WHERE id_producto = ?
            """,
            (id_producto,)
        ).fetchone()

    finally:
        conexion.close()

    if producto is None:
        return {
            "ok": False,
            "codigo": "PRODUCTO_NO_ENCONTRADO",
            "mensaje": "Producto no encontrado.",
        }

    categoria = str(
        producto[2] or ""
    ).strip().lower()

    if categoria == "bebidas":
        costo = _costo_unitario_bebida(
            id_producto
        )
    elif categoria == "postres":
        costo = _costo_unitario_postre(
            producto[1]
        )
    else:
        return {
            "ok": False,
            "codigo": "RENTABILIDAD_NO_SOPORTADA",
            "mensaje": (
                "Por ahora la rentabilidad detallada "
                "está disponible para Bebidas y Postres."
            ),
        }

    precio_venta = (
        float(producto[3])
        if producto[3] is not None
        else None
    )
    ventas = _ventas_producto(
        id_producto
    )
    costo_unitario = (
        costo.get("costo_unitario")
        if costo
        else None
    )

    if (
        costo_unitario is None
        or precio_venta is None
    ):
        return {
            "ok": True,
            "codigo": "RENTABILIDAD_PARCIAL",
            "completo": False,
            "id_producto": producto[0],
            "producto": producto[1],
            "categoria": producto[2],
            "stock": int(
                producto[4] or 0
            ),
            "precio_venta": precio_venta,
            "costo_unitario": costo_unitario,
            "fuente_costo": (
                costo.get("fuente")
                if costo
                else None
            ),
            "faltantes_costo": (
                costo.get("faltantes", [])
                if costo
                else []
            ),
            "rentabilidad_historica_exacta": (
                ventas["unidades_sin_snapshot"] == 0
            ),
            "costo_ventas_historico": (
                ventas[
                    "costo_ventas_historico_conocido"
                ]
                if ventas["unidades_sin_snapshot"] == 0
                else None
            ),
            "ganancia_bruta_historica": (
                ventas["ingresos"]
                - ventas[
                    "costo_ventas_historico_conocido"
                ]
                if ventas["unidades_sin_snapshot"] == 0
                else None
            ),
            **ventas,
        }

    ganancia_unitaria = (
        precio_venta
        - costo_unitario
    )
    margen_sobre_venta = (
        (
            ganancia_unitaria
            / precio_venta
        )
        * 100
        if precio_venta > 0
        else None
    )
    markup_sobre_costo = (
        (
            ganancia_unitaria
            / costo_unitario
        )
        * 100
        if costo_unitario > 0
        else None
    )
    costo_ventas_estimado = (
        ventas["unidades_vendidas"]
        * costo_unitario
    )
    ganancia_bruta_estimada = (
        ventas["ingresos"]
        - costo_ventas_estimado
    )

    rentabilidad_historica_exacta = (
        ventas["unidades_sin_snapshot"]
        == 0
    )

    if rentabilidad_historica_exacta:
        costo_ventas_historico = (
            ventas[
                "costo_ventas_historico_conocido"
            ]
        )
        ganancia_bruta_historica = (
            ventas["ingresos"]
            - costo_ventas_historico
        )
    else:
        costo_ventas_historico = None
        ganancia_bruta_historica = None

    resultado = {
        "ok": True,
        "codigo": "RENTABILIDAD_PRODUCTO",
        "completo": True,
        "id_producto": producto[0],
        "producto": producto[1],
        "categoria": producto[2],
        "stock": int(
            producto[4] or 0
        ),
        "precio_venta": precio_venta,
        "costo_unitario": costo_unitario,
        "ganancia_unitaria": ganancia_unitaria,
        "margen_sobre_venta_pct": (
            margen_sobre_venta
        ),
        "markup_sobre_costo_pct": (
            markup_sobre_costo
        ),
        "fuente_costo": costo["fuente"],
        "unidades_vendidas": (
            ventas["unidades_vendidas"]
        ),
        "ingresos": ventas["ingresos"],
        "costo_ventas_estimado": (
            costo_ventas_estimado
        ),
        "ganancia_bruta_estimada": (
            ganancia_bruta_estimada
        ),
        "rentabilidad_historica_exacta": (
            rentabilidad_historica_exacta
        ),
        "costo_ventas_historico": (
            costo_ventas_historico
        ),
        "ganancia_bruta_historica": (
            ganancia_bruta_historica
        ),
        "costo_ventas_historico_conocido": (
            ventas[
                "costo_ventas_historico_conocido"
            ]
        ),
        "unidades_sin_snapshot": (
            ventas["unidades_sin_snapshot"]
        ),
    }

    for clave in (
        "id_produccion",
        "version_receta",
        "fecha_costo",
        "compras_consideradas",
    ):
        if clave in costo:
            resultado[clave] = costo[clave]

    return resultado


def rentabilidad_categoria(
    categoria,
):
    categoria_normalizada = str(
        categoria or ""
    ).strip().lower()

    if categoria_normalizada not in {
        "bebidas",
        "postres",
        "bebidas_postres",
        "bebidas postres",
        "bebidas y postres",
    }:
        return {
            "ok": False,
            "codigo": "CATEGORIA_RENTABILIDAD_INVALIDA",
            "mensaje": (
                "La categoría debe ser bebidas, "
                "postres o bebidas_postres."
            ),
        }

    if categoria_normalizada == "bebidas":
        categorias = {"bebidas"}
        nombre = "Bebidas"
    elif categoria_normalizada == "postres":
        categorias = {"postres"}
        nombre = "Postres"
    else:
        categorias = {
            "bebidas",
            "postres",
        }
        nombre = "Bebidas + Postres"

    conexion = obtener_conexion()

    try:
        placeholders = ",".join(
            "?"
            for _ in categorias
        )

        filas = conexion.execute(
            f"""
            SELECT id_producto
            FROM productos
            WHERE LOWER(categoria)
                IN ({placeholders})
            ORDER BY categoria, nombre
            """,
            tuple(sorted(categorias))
        ).fetchall()

    finally:
        conexion.close()

    productos = [
        rentabilidad_producto(
            fila[0]
        )
        for fila in filas
    ]

    con_ventas = [
        item
        for item in productos
        if item.get(
            "unidades_vendidas",
            0,
        ) > 0
    ]
    faltantes_costo = [
        item["producto"]
        for item in con_ventas
        if not item.get(
            "completo",
            False,
        )
    ]

    ingresos = sum(
        item.get("ingresos", 0)
        for item in productos
    )
    costo_conocido = sum(
        item.get(
            "costo_ventas_estimado",
            0,
        )
        for item in productos
        if item.get("completo")
    )

    completo = (
        len(faltantes_costo) == 0
    )

    if completo:
        ganancia = (
            ingresos
            - costo_conocido
        )
        margen = (
            (
                ganancia / ingresos
            ) * 100
            if ingresos > 0
            else None
        )
    else:
        ganancia = None
        margen = None

    historico_exacto = all(
        item.get(
            "rentabilidad_historica_exacta",
            True,
        )
        for item in con_ventas
    )

    costo_historico_conocido = sum(
        item.get(
            "costo_ventas_historico_conocido",
            0,
        )
        for item in con_ventas
    )

    if historico_exacto:
        costo_historico = (
            costo_historico_conocido
        )
        ganancia_historica = (
            ingresos - costo_historico
        )
        margen_historico = (
            (
                ganancia_historica / ingresos
            ) * 100
            if ingresos > 0
            else None
        )
    else:
        costo_historico = None
        ganancia_historica = None
        margen_historico = None

    return {
        "ok": True,
        "codigo": "RENTABILIDAD_CATEGORIA",
        "categoria": categoria_normalizada,
        "nombre": nombre,
        "completo": completo,
        "productos": productos,
        "ingresos": ingresos,
        "costo_ventas_estimado": (
            costo_conocido
            if completo
            else None
        ),
        "costo_ventas_conocido": (
            costo_conocido
        ),
        "ganancia_bruta_estimada": (
            ganancia
        ),
        "margen_bruto_pct": margen,
        "faltantes_costo": faltantes_costo,
        "rentabilidad_historica_exacta": (
            historico_exacto
        ),
        "costo_ventas_historico": (
            costo_historico
        ),
        "costo_ventas_historico_conocido": (
            costo_historico_conocido
        ),
        "ganancia_bruta_historica": (
            ganancia_historica
        ),
        "margen_bruto_historico_pct": (
            margen_historico
        ),
    }
