from datetime import datetime
import re
import unicodedata

from database import obtener_conexion
from gastos import registrar_gasto


INSUMOS_BASE = [
    ("Galletitas Oreo", "g"),
    ("Dulce de leche", "g"),
    ("Crema de leche", "ml"),
    ("Leche", "ml"),
    ("Chocolinas", "g"),
    ("Queso crema", "g"),
    ("Café con leche preparado", "ml"),
    ("Café", "g"),
    ("Azúcar impalpable", "g"),
    ("Pote", "un"),
]

ALIASES_INSUMOS = {
    "oreo": "galletitas oreo",
    "galletita oreo": "galletitas oreo",
    "galletitas oreo": "galletitas oreo",
    "dulce": "dulce de leche",
    "ddl": "dulce de leche",
    "dulce de leche": "dulce de leche",
    "crema": "crema de leche",
    "crema de leche": "crema de leche",
    "leche": "leche",
    "chocolina": "chocolinas",
    "chocolinas": "chocolinas",
    "queso": "queso crema",
    "queso crema": "queso crema",
    "cafe": "cafe",
    "cafe molido": "cafe",
    "cafe con leche": "cafe con leche preparado",
    "cafe con leche preparado": "cafe con leche preparado",
    "azucar impalpable": "azucar impalpable",
    "pote": "pote",
    "potes": "pote",
    "envase": "pote",
    "envases": "pote",
}

PRESENTACIONES_INSUMOS_BASE = [
    {
        "insumo": "Galletitas Oreo",
        "nombre": "118g",
        "contenido_base": 118,
    },
    {
        "insumo": "Galletitas Oreo",
        "nombre": "258g x4",
        "contenido_base": 258,
    },
    {
        "insumo": "Galletitas Oreo",
        "nombre": "354g tripack",
        "contenido_base": 354,
    },
    {
        "insumo": "Chocolinas",
        "nombre": "170g",
        "contenido_base": 170,
    },
    {
        "insumo": "Chocolinas",
        "nombre": "250g",
        "contenido_base": 250,
    },
]


RECETAS_BASE = [
    {
        "nombre": "Oreo - receta histórica",
        "producto": "Oreo",
        "version": 1,
        "rendimiento": 10,
        "costo_fijo_por_unidad": 500,
        "activa": False,
        "notas": (
            "Versión anterior conservada para historial."
        ),
        "insumos": [
            ("Galletitas Oreo", 700),
            ("Dulce de leche", 900),
            ("Crema de leche", 500),
            ("Leche", 400),
        ],
    },
    {
        "nombre": "Oreo - receta actual",
        "producto": "Oreo",
        "version": 2,
        "rendimiento": 10,
        "costo_fijo_por_unidad": 500,
        "activa": True,
        "notas": (
            "Para 10 unidades: 700 g de Oreo en el armado "
            "+ 100 g adicionales para decoración. "
            "Por unidad: 70 g de Oreo base, 30 ml de leche, "
            "90 g de dulce de leche y 60 ml de crema. "
            "Los 100 g de decoración equivalen a unos 10 g extra "
            "de Oreo por unidad. Se usa 1 pote por postre. "
            "El azúcar impalpable se usa a ojo y no se incluye "
            "todavía en el costo cuantificado."
        ),
        "insumos": [
            ("Galletitas Oreo", 800),
            ("Dulce de leche", 900),
            ("Crema de leche", 600),
            ("Leche", 300),
            ("Pote", 10),
        ],
    },
    {
        "nombre": "Chocotorta - receta histórica",
        "producto": "Chocotorta",
        "version": 1,
        "rendimiento": 10,
        "costo_fijo_por_unidad": 500,
        "activa": False,
        "notas": (
            "Versión anterior conservada para historial."
        ),
        "insumos": [
            ("Chocolinas", 1100),
            ("Queso crema", 500),
            ("Dulce de leche", 500),
            ("Café con leche preparado", 1000),
        ],
    },
    {
        "nombre": "Chocotorta - receta actual",
        "producto": "Chocotorta",
        "version": 2,
        "rendimiento": 10,
        "costo_fijo_por_unidad": 500,
        "activa": True,
        "notas": (
            "Para 10 unidades: 1100 g de Chocolinas, "
            "1000 g de relleno de dulce de leche + queso crema "
            "y 900 ml de café con leche preparado. "
            "El relleno se mantiene 50/50: 500 g de dulce de leche "
            "+ 500 g de queso crema. "
            "Armado orientativo por unidad: 45 g Chocolinas + "
            "45 ml café, 50 g relleno, otra capa igual, "
            "y 20 g finales de Chocolinas. Se usa 1 pote por postre. "
            "Ingredientes usados a ojo no se incluyen en el costo "
            "exacto hasta que se mida su consumo."
        ),
        "insumos": [
            ("Chocolinas", 1100),
            ("Queso crema", 500),
            ("Dulce de leche", 500),
            ("Café con leche preparado", 900),
            ("Pote", 10),
        ],
    },
]


def _normalizar(texto):
    texto = str(texto or "").strip().lower()
    texto = "".join(
        c
        for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    )
    return " ".join(texto.split())


def inicializar_costos_postres():
    conexion = obtener_conexion()
    cursor = conexion.cursor()

    try:
        for nombre, unidad in INSUMOS_BASE:
            cursor.execute(
                """
                INSERT OR IGNORE INTO insumos (
                    nombre,
                    unidad_base,
                    seccion,
                    activo
                )
                VALUES (?, ?, 'bebidas_postres', 1)
                """,
                (nombre, unidad)
            )

        cursor.execute(
            """
            UPDATE insumos
            SET controla_stock = 0
            WHERE nombre = 'Café con leche preparado'
            """
        )

        for presentacion in PRESENTACIONES_INSUMOS_BASE:
            cursor.execute(
                """
                SELECT id_insumo
                FROM insumos
                WHERE nombre = ?
                """,
                (presentacion["insumo"],)
            )

            fila_insumo = cursor.fetchone()

            if fila_insumo is None:
                continue

            cursor.execute(
                """
                INSERT INTO presentaciones_insumos (
                    id_insumo,
                    nombre,
                    contenido_base,
                    activa
                )
                VALUES (?, ?, ?, 1)
                ON CONFLICT(id_insumo, nombre)
                DO UPDATE SET
                    contenido_base = excluded.contenido_base,
                    activa = 1
                """,
                (
                    fila_insumo[0],
                    presentacion["nombre"],
                    presentacion["contenido_base"],
                )
            )

        for receta in RECETAS_BASE:
            cursor.execute(
                """
                SELECT id_receta
                FROM recetas
                WHERE producto = ?
                  AND version = ?
                """,
                (
                    receta["producto"],
                    receta["version"],
                )
            )
            fila = cursor.fetchone()

            if fila is None:
                cursor.execute(
                    """
                    INSERT INTO recetas (
                        nombre,
                        producto,
                        version,
                        rendimiento,
                        costo_fijo_por_unidad,
                        activa,
                        notas
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        receta["nombre"],
                        receta["producto"],
                        receta["version"],
                        receta["rendimiento"],
                        receta["costo_fijo_por_unidad"],
                        int(receta.get("activa", True)),
                        receta.get("notas"),
                    )
                )
                id_receta = cursor.lastrowid
            else:
                id_receta = fila[0]

                cursor.execute(
                    """
                    UPDATE recetas
                    SET
                        nombre = ?,
                        rendimiento = ?,
                        costo_fijo_por_unidad = ?,
                        activa = ?,
                        notas = ?
                    WHERE id_receta = ?
                    """,
                    (
                        receta["nombre"],
                        receta["rendimiento"],
                        receta["costo_fijo_por_unidad"],
                        int(receta.get("activa", True)),
                        receta.get("notas"),
                        id_receta,
                    )
                )

            for nombre_insumo, cantidad in receta["insumos"]:
                cursor.execute(
                    """
                    SELECT id_insumo
                    FROM insumos
                    WHERE nombre = ?
                    """,
                    (nombre_insumo,)
                )
                id_insumo = cursor.fetchone()[0]

                cursor.execute(
                    """
                    INSERT INTO receta_insumos (
                        id_receta,
                        id_insumo,
                        cantidad_base
                    )
                    VALUES (?, ?, ?)
                    ON CONFLICT(id_receta, id_insumo)
                    DO UPDATE SET
                        cantidad_base = excluded.cantidad_base
                    """,
                    (
                        id_receta,
                        id_insumo,
                        cantidad,
                    )
                )

        conexion.commit()

        return {
            "ok": True,
            "codigo": "COSTOS_POSTRES_INICIALIZADOS",
        }

    finally:
        conexion.close()


def resolver_insumo(nombre):
    consulta = _normalizar(nombre)
    consulta = ALIASES_INSUMOS.get(
        consulta,
        consulta
    )

    conexion = obtener_conexion()

    try:
        filas = conexion.execute(
            """
            SELECT
                id_insumo,
                nombre,
                unidad_base,
                seccion,
                stock_base,
                controla_stock
            FROM insumos
            WHERE activo = 1
            ORDER BY nombre
            """
        ).fetchall()

    finally:
        conexion.close()

    candidatos = []

    for fila in filas:
        normalizado = _normalizar(fila[1])

        if consulta == normalizado:
            return {
                "ok": True,
                "insumo": {
                    "id_insumo": fila[0],
                    "nombre": fila[1],
                    "unidad_base": fila[2],
                    "seccion": fila[3],
                    "stock_base": float(fila[4] or 0),
                    "controla_stock": bool(fila[5]),
                },
            }

        if consulta in normalizado or normalizado in consulta:
            candidatos.append(fila)

    if len(candidatos) == 1:
        fila = candidatos[0]
        return {
            "ok": True,
            "insumo": {
                "id_insumo": fila[0],
                "nombre": fila[1],
                "unidad_base": fila[2],
                "seccion": fila[3],
            },
        }

    if len(candidatos) > 1:
        return {
            "ok": False,
            "codigo": "INSUMO_AMBIGUO",
            "mensaje": "El insumo coincide con más de una opción.",
            "candidatos": [fila[1] for fila in candidatos],
        }

    return {
        "ok": False,
        "codigo": "INSUMO_NO_ENCONTRADO",
        "mensaje": f"No conozco el insumo '{nombre}'.",
    }


def convertir_a_base(
    cantidad,
    unidad,
    unidad_base
):
    if isinstance(cantidad, bool) or not isinstance(
        cantidad,
        (int, float)
    ):
        raise ValueError("Cantidad inválida.")

    if cantidad <= 0:
        raise ValueError("La cantidad debe ser mayor que cero.")

    u = _normalizar(unidad)
    base = _normalizar(unidad_base)

    aliases = {
        "gramo": "g",
        "gramos": "g",
        "gr": "g",
        "g": "g",
        "kg": "kg",
        "kilo": "kg",
        "kilos": "kg",
        "ml": "ml",
        "mililitro": "ml",
        "mililitros": "ml",
        "l": "l",
        "lt": "l",
        "litro": "l",
        "litros": "l",
        "unidad": "un",
        "unidades": "un",
        "u": "un",
        "un": "un",
    }

    u = aliases.get(u, u)
    base = aliases.get(base, base)

    if base == "g":
        if u == "g":
            return float(cantidad)
        if u == "kg":
            return float(cantidad) * 1000

    if base == "ml":
        if u == "ml":
            return float(cantidad)
        if u == "l":
            return float(cantidad) * 1000

    if base == "un" and u == "un":
        return float(cantidad)

    raise ValueError(
        f"No puedo convertir {unidad} a {unidad_base}."
    )


def registrar_compra_insumo(
    nombre_insumo,
    cantidad,
    unidad,
    costo_total,
    comercio=None,
    fecha=None,
    observaciones=None,
):
    resolucion = resolver_insumo(
        nombre_insumo
    )

    if not resolucion["ok"]:
        return resolucion

    insumo = resolucion["insumo"]

    try:
        cantidad_base = convertir_a_base(
            cantidad,
            unidad,
            insumo["unidad_base"],
        )
    except ValueError as error:
        return {
            "ok": False,
            "codigo": "UNIDAD_INSUMO_INVALIDA",
            "mensaje": str(error),
        }

    if isinstance(costo_total, bool) or not isinstance(
        costo_total,
        (int, float)
    ):
        return {
            "ok": False,
            "codigo": "COSTO_INSUMO_INVALIDO",
            "mensaje": "El costo debe ser numérico.",
        }

    if costo_total <= 0:
        return {
            "ok": False,
            "codigo": "COSTO_INSUMO_INVALIDO",
            "mensaje": "El costo debe ser mayor que cero.",
        }

    if fecha is None:
        fecha = datetime.now().strftime(
            "%Y-%m-%d"
        )

    descripcion = (
        f"{insumo['nombre']} "
        f"{cantidad:g} {unidad}"
    )

    if comercio:
        descripcion += f" - {comercio}"

    if observaciones:
        descripcion += f" ({observaciones})"

    gasto = registrar_gasto(
        categoria="Materia prima",
        descripcion_gasto=descripcion,
        valor_final=float(costo_total),
        fecha=fecha,
        seccion="bebidas_postres",
        subseccion="postres",
    )

    if not gasto["ok"]:
        return gasto

    conexion = obtener_conexion()

    try:
        cursor = conexion.cursor()

        cursor.execute(
            """
            INSERT INTO compras_insumos (
                id_insumo,
                fecha,
                cantidad_base,
                costo_total,
                comercio,
                id_gasto,
                observaciones
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                insumo["id_insumo"],
                fecha,
                cantidad_base,
                float(costo_total),
                comercio.strip()
                if isinstance(comercio, str)
                and comercio.strip()
                else None,
                gasto["id_gasto"],
                observaciones,
            )
        )

        id_compra_insumo = cursor.lastrowid

        stock_anterior = float(
            cursor.execute(
                """
                SELECT stock_base
                FROM insumos
                WHERE id_insumo = ?
                """,
                (insumo["id_insumo"],)
            ).fetchone()[0] or 0
        )

        if insumo.get("controla_stock", True):
            cursor.execute(
                """
                UPDATE insumos
                SET stock_base = stock_base + ?
                WHERE id_insumo = ?
                """,
                (
                    cantidad_base,
                    insumo["id_insumo"],
                )
            )
            stock_nuevo = stock_anterior + cantidad_base
        else:
            stock_nuevo = stock_anterior

        conexion.commit()

    except Exception:
        conexion.rollback()
        raise

    finally:
        conexion.close()

    return {
        "ok": True,
        "codigo": "COMPRA_INSUMO_REGISTRADA",
        "id_compra_insumo": id_compra_insumo,
        "id_gasto": gasto["id_gasto"],
        "insumo": insumo["nombre"],
        "cantidad_base": cantidad_base,
        "unidad_base": insumo["unidad_base"],
        "costo_total": float(costo_total),
        "comercio": comercio,
        "fecha": fecha,
        "controla_stock": insumo.get("controla_stock", True),
        "stock_anterior": stock_anterior,
        "stock_nuevo": stock_nuevo,
    }


def _costo_unitario_reciente(
    conexion,
    id_insumo,
    limite=3
):
    filas = conexion.execute(
        """
        SELECT
            compras_insumos.cantidad_base,
            compras_insumos.costo_total
        FROM compras_insumos
        LEFT JOIN gastos
            ON compras_insumos.id_gasto = gastos.id_gasto
        WHERE compras_insumos.id_insumo = ?
          AND (
              compras_insumos.id_gasto IS NULL
              OR COALESCE(gastos.anulado, 0) = 0
          )
        ORDER BY
            compras_insumos.fecha DESC,
            compras_insumos.id_compra_insumo DESC
        LIMIT ?
        """,
        (
            id_insumo,
            limite,
        )
    ).fetchall()

    if not filas:
        return None

    cantidad = sum(
        float(fila[0])
        for fila in filas
    )
    costo = sum(
        float(fila[1])
        for fila in filas
    )

    if cantidad <= 0:
        return None

    return costo / cantidad


def obtener_receta(producto):
    consulta = _normalizar(producto)

    aliases = {
        "oreo": "oreo",
        "oreos": "oreo",
        "choco oreo": "oreo",
        "chocotorta": "chocotorta",
        "choco": "chocotorta",
        "chocolina": "chocotorta",
    }

    consulta = aliases.get(
        consulta,
        consulta
    )

    conexion = obtener_conexion()

    try:
        recetas = conexion.execute(
            """
            SELECT
                id_receta,
                nombre,
                producto,
                version,
                rendimiento,
                costo_fijo_por_unidad,
                notas
            FROM recetas
            WHERE activa = 1
            ORDER BY version DESC
            """
        ).fetchall()

        receta = None

        for fila in recetas:
            if _normalizar(fila[2]) == consulta:
                receta = fila
                break

        if receta is None:
            return {
                "ok": False,
                "codigo": "RECETA_NO_ENCONTRADA",
                "mensaje": (
                    f"No encontré una receta activa para '{producto}'."
                ),
            }

        insumos = conexion.execute(
            """
            SELECT
                insumos.id_insumo,
                insumos.nombre,
                insumos.unidad_base,
                receta_insumos.cantidad_base
            FROM receta_insumos
            INNER JOIN insumos
                ON receta_insumos.id_insumo = insumos.id_insumo
            WHERE receta_insumos.id_receta = ?
            ORDER BY receta_insumos.id_receta_insumo
            """,
            (receta[0],)
        ).fetchall()

        return {
            "ok": True,
            "receta": {
                "id_receta": receta[0],
                "nombre": receta[1],
                "producto": receta[2],
                "version": receta[3],
                "rendimiento": float(receta[4]),
                "costo_fijo_por_unidad": float(receta[5]),
                "notas": receta[6],
                "insumos": [
                    {
                        "id_insumo": fila[0],
                        "nombre": fila[1],
                        "unidad_base": fila[2],
                        "cantidad_base": float(fila[3]),
                    }
                    for fila in insumos
                ],
            },
        }

    finally:
        conexion.close()


def estimar_costo_receta(
    producto,
    cantidad_objetivo,
    compras_a_promediar=3,
):
    if (
        isinstance(cantidad_objetivo, bool)
        or not isinstance(
            cantidad_objetivo,
            (int, float)
        )
        or cantidad_objetivo <= 0
    ):
        return {
            "ok": False,
            "codigo": "CANTIDAD_RECETA_INVALIDA",
            "mensaje": (
                "La cantidad a producir debe ser mayor que cero."
            ),
        }

    receta_resultado = obtener_receta(
        producto
    )

    if not receta_resultado["ok"]:
        return receta_resultado

    receta = receta_resultado["receta"]
    factor = (
        float(cantidad_objetivo)
        / receta["rendimiento"]
    )

    conexion = obtener_conexion()

    try:
        detalle = []
        faltantes = []
        costo_insumos = 0.0

        for insumo in receta["insumos"]:
            cantidad_necesaria = (
                insumo["cantidad_base"]
                * factor
            )

            costo_unitario = _costo_unitario_reciente(
                conexion,
                insumo["id_insumo"],
                limite=compras_a_promediar,
            )

            if costo_unitario is None:
                faltantes.append(
                    insumo["nombre"]
                )
                costo_estimado = None
            else:
                costo_estimado = (
                    cantidad_necesaria
                    * costo_unitario
                )
                costo_insumos += costo_estimado

            detalle.append({
                "insumo": insumo["nombre"],
                "cantidad": cantidad_necesaria,
                "unidad": insumo["unidad_base"],
                "costo_unitario_base": costo_unitario,
                "costo_estimado": costo_estimado,
            })

        costo_fijo = (
            float(cantidad_objetivo)
            * receta["costo_fijo_por_unidad"]
        )

        total_parcial = (
            costo_insumos
            + costo_fijo
        )

        completo = len(faltantes) == 0

        return {
            "ok": True,
            "codigo": (
                "COSTO_RECETA_ESTIMADO"
                if completo
                else "COSTO_RECETA_PARCIAL"
            ),
            "producto": receta["producto"],
            "version_receta": receta["version"],
            "notas_receta": receta.get("notas"),
            "cantidad_objetivo": float(cantidad_objetivo),
            "rendimiento_base": receta["rendimiento"],
            "detalle": detalle,
            "costo_insumos": costo_insumos,
            "costo_fijo": costo_fijo,
            "costo_total_estimado": (
                total_parcial
                if completo
                else None
            ),
            "costo_parcial_conocido": total_parcial,
            "faltantes": faltantes,
            "compras_a_promediar": compras_a_promediar,
        }

    finally:
        conexion.close()


def historial_gastos_postres(
    limite=10
):
    conexion = obtener_conexion()

    try:
        filas = conexion.execute(
            """
            SELECT
                id_gasto,
                fecha,
                descripcion_gasto,
                valor_final,
                categoria
            FROM gastos
            WHERE anulado = 0
              AND seccion = 'bebidas_postres'
              AND subseccion = 'postres'
            ORDER BY id_gasto DESC
            LIMIT ?
            """,
            (limite,)
        ).fetchall()

        return [
            {
                "id_gasto": fila[0],
                "fecha": fila[1],
                "descripcion": fila[2],
                "monto": float(fila[3]),
                "categoria": fila[4],
            }
            for fila in filas
        ]

    finally:
        conexion.close()


def _normalizar_contexto_produccion(contexto):
    if not isinstance(contexto, dict):
        contexto = {}

    usuario_numero = contexto.get("usuario_numero")
    usuario_id = contexto.get("usuario_id")

    usuario_origen = (
        str(usuario_numero).strip()
        if usuario_numero
        else (
            str(usuario_id).strip()
            if usuario_id
            else None
        )
    )

    return {
        "canal": (
            str(contexto.get("canal")).strip()
            if contexto.get("canal")
            else None
        ),
        "usuario_origen": usuario_origen,
        "grupo_origen": (
            str(contexto.get("grupo_id")).strip()
            if contexto.get("grupo_id")
            else None
        ),
        "id_mensaje": (
            str(contexto.get("id_mensaje")).strip()
            if contexto.get("id_mensaje")
            else None
        ),
    }


def registrar_produccion_postre(
    producto,
    cantidad,
    contexto=None,
):
    if (
        isinstance(cantidad, bool)
        or not isinstance(cantidad, int)
        or cantidad <= 0
    ):
        return {
            "ok": False,
            "codigo": "CANTIDAD_PRODUCCION_INVALIDA",
            "mensaje": (
                "La cantidad producida debe ser un entero "
                "mayor que cero."
            ),
        }

    costo = estimar_costo_receta(
        producto=producto,
        cantidad_objetivo=cantidad,
    )

    if not costo["ok"]:
        return costo

    if costo["costo_total_estimado"] is None:
        return {
            "ok": False,
            "codigo": "COSTO_PRODUCCION_INCOMPLETO",
            "mensaje": (
                "No puedo registrar la producción todavía porque "
                "faltan precios de insumos. Cargá primero: "
                + ", ".join(costo["faltantes"])
                + "."
            ),
            "faltantes": costo["faltantes"],
            "costo_parcial_conocido": costo[
                "costo_parcial_conocido"
            ],
        }

    receta_resultado = obtener_receta(
        producto
    )

    if not receta_resultado["ok"]:
        return receta_resultado

    receta = receta_resultado["receta"]
    contexto_normalizado = _normalizar_contexto_produccion(
        contexto
    )

    conexion = obtener_conexion()

    try:
        conexion.execute("BEGIN IMMEDIATE")
        cursor = conexion.cursor()

        producto_db = cursor.execute(
            """
            SELECT
                id_producto,
                nombre,
                stock,
                controla_stock
            FROM productos
            WHERE LOWER(nombre) = LOWER(?)
            """,
            (receta["producto"],)
        ).fetchone()

        if producto_db is None:
            conexion.rollback()
            return {
                "ok": False,
                "codigo": "PRODUCTO_NO_ENCONTRADO",
                "mensaje": (
                    "El postre de la receta no existe en el catálogo "
                    "de productos."
                ),
            }

        if not bool(producto_db[3]):
            conexion.rollback()
            return {
                "ok": False,
                "codigo": "PRODUCTO_SIN_CONTROL_STOCK",
                "mensaje": (
                    "El producto de esta receta no controla stock "
                    "y no puede recibir producción."
                ),
            }

        insumos_produccion = []
        faltantes_stock = []

        for item in costo["detalle"]:
            if (
                item["costo_unitario_base"] is None
                or item["costo_estimado"] is None
            ):
                conexion.rollback()
                return {
                    "ok": False,
                    "codigo": "COSTO_PRODUCCION_INCOMPLETO",
                    "mensaje": (
                        "La producción tiene un insumo "
                        "sin costo conocido."
                    ),
                }

            insumo_db = cursor.execute(
                """
                SELECT
                    id_insumo,
                    stock_base,
                    controla_stock
                FROM insumos
                WHERE nombre = ?
                """,
                (item["insumo"],)
            ).fetchone()

            if insumo_db is None:
                conexion.rollback()
                return {
                    "ok": False,
                    "codigo": "INSUMO_NO_ENCONTRADO",
                    "mensaje": (
                        f"No encontré el insumo "
                        f"'{item['insumo']}'."
                    ),
                }

            stock_disponible = float(
                insumo_db[1] or 0
            )
            controla_stock = bool(
                insumo_db[2]
            )
            cantidad_necesaria = float(
                item["cantidad"]
            )

            if (
                controla_stock
                and stock_disponible + 1e-9
                < cantidad_necesaria
            ):
                faltantes_stock.append({
                    "insumo": item["insumo"],
                    "necesario": cantidad_necesaria,
                    "disponible": stock_disponible,
                    "faltante": (
                        cantidad_necesaria
                        - stock_disponible
                    ),
                    "unidad": item["unidad"],
                })

            insumos_produccion.append({
                **item,
                "id_insumo": insumo_db[0],
                "controla_stock": controla_stock,
                "stock_anterior": stock_disponible,
            })

        if faltantes_stock:
            conexion.rollback()
            return {
                "ok": False,
                "codigo": "STOCK_INSUMOS_INSUFICIENTE",
                "mensaje": (
                    "No hay suficiente stock de insumos para "
                    "registrar la producción."
                ),
                "faltantes_stock": faltantes_stock,
            }

        stock_anterior = int(
            producto_db[2] or 0
        )
        fecha_hora = datetime.now().isoformat(
            timespec="seconds"
        )
        costo_total = float(
            costo["costo_total_estimado"]
        )
        costo_unitario = (
            costo_total
            / cantidad
        )

        cursor.execute(
            """
            INSERT INTO producciones_postres (
                fecha_hora,
                id_producto,
                producto,
                cantidad_producida,
                id_receta,
                version_receta,
                costo_insumos,
                costo_fijo,
                costo_total,
                costo_unitario,
                canal_origen,
                usuario_origen,
                grupo_origen,
                id_mensaje_origen
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                fecha_hora,
                producto_db[0],
                producto_db[1],
                cantidad,
                receta["id_receta"],
                receta["version"],
                float(costo["costo_insumos"]),
                float(costo["costo_fijo"]),
                costo_total,
                costo_unitario,
                contexto_normalizado["canal"],
                contexto_normalizado["usuario_origen"],
                contexto_normalizado["grupo_origen"],
                contexto_normalizado["id_mensaje"],
            )
        )

        id_produccion = cursor.lastrowid
        detalle_consumo = []

        for item in insumos_produccion:
            if item["controla_stock"]:
                stock_nuevo_insumo = (
                    item["stock_anterior"]
                    - float(item["cantidad"])
                )

                cursor.execute(
                    """
                    UPDATE insumos
                    SET stock_base = ?
                    WHERE id_insumo = ?
                    """,
                    (
                        stock_nuevo_insumo,
                        item["id_insumo"],
                    )
                )
            else:
                stock_nuevo_insumo = (
                    item["stock_anterior"]
                )

            cursor.execute(
                """
                INSERT INTO produccion_postres_insumos (
                    id_produccion,
                    id_insumo,
                    insumo,
                    cantidad_base,
                    unidad_base,
                    costo_unitario_base,
                    costo_estimado,
                    controla_stock,
                    stock_anterior,
                    stock_nuevo
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    id_produccion,
                    item["id_insumo"],
                    item["insumo"],
                    float(item["cantidad"]),
                    item["unidad"],
                    float(item["costo_unitario_base"]),
                    float(item["costo_estimado"]),
                    int(item["controla_stock"]),
                    item["stock_anterior"],
                    stock_nuevo_insumo,
                )
            )

            detalle_consumo.append({
                "insumo": item["insumo"],
                "cantidad": float(item["cantidad"]),
                "unidad": item["unidad"],
                "controla_stock": item["controla_stock"],
                "stock_anterior": item["stock_anterior"],
                "stock_nuevo": stock_nuevo_insumo,
                "costo_estimado": float(
                    item["costo_estimado"]
                ),
            })

        cursor.execute(
            """
            UPDATE productos
            SET stock = stock + ?
            WHERE id_producto = ?
            """,
            (
                cantidad,
                producto_db[0],
            )
        )

        stock_nuevo = (
            stock_anterior
            + cantidad
        )

        conexion.commit()

        return {
            "ok": True,
            "codigo": "PRODUCCION_POSTRE_REGISTRADA",
            "id_produccion": id_produccion,
            "fecha_hora": fecha_hora,
            "producto": producto_db[1],
            "cantidad_producida": cantidad,
            "version_receta": receta["version"],
            "costo_insumos": float(
                costo["costo_insumos"]
            ),
            "costo_fijo": float(
                costo["costo_fijo"]
            ),
            "costo_total": costo_total,
            "costo_unitario": costo_unitario,
            "stock_anterior": stock_anterior,
            "stock_nuevo": stock_nuevo,
            "detalle_insumos": detalle_consumo,
        }

    except Exception as error:
        conexion.rollback()
        return {
            "ok": False,
            "codigo": "ERROR_BASE_DATOS",
            "mensaje": (
                "Error al registrar la producción: "
                f"{error}"
            ),
        }

    finally:
        conexion.close()


def historial_producciones_postres(
    limite=10
):
    if (
        isinstance(limite, bool)
        or not isinstance(limite, int)
        or limite <= 0
    ):
        limite = 10

    conexion = obtener_conexion()

    try:
        filas = conexion.execute(
            """
            SELECT
                id_produccion,
                fecha_hora,
                producto,
                cantidad_producida,
                version_receta,
                costo_total,
                costo_unitario
            FROM producciones_postres
            ORDER BY id_produccion DESC
            LIMIT ?
            """,
            (limite,)
        ).fetchall()

        return [
            {
                "id_produccion": fila[0],
                "fecha_hora": fila[1],
                "producto": fila[2],
                "cantidad_producida": fila[3],
                "version_receta": fila[4],
                "costo_total": float(fila[5]),
                "costo_unitario": float(fila[6]),
            }
            for fila in filas
        ]

    finally:
        conexion.close()



def resolver_presentacion_insumo(
    nombre_insumo,
    presentacion
):
    resolucion = resolver_insumo(
        nombre_insumo
    )

    if not resolucion["ok"]:
        return resolucion

    insumo = resolucion["insumo"]
    consulta = _normalizar(
        presentacion
    )

    aliases = {
        "118": 118,
        "118g": 118,
        "118 g": 118,
        "258": 258,
        "258g": 258,
        "258 g": 258,
        "x4": 258,
        "x 4": 258,
        "258g x4": 258,
        "258 g x 4": 258,
        "354": 354,
        "354g": 354,
        "354 g": 354,
        "x3": 354,
        "x 3": 354,
        "tripack": 354,
        "354g tripack": 354,
        "354 g tripack": 354,
        "170": 170,
        "170g": 170,
        "170 g": 170,
        "250": 250,
        "250g": 250,
        "250 g": 250,
    }

    contenido_buscado = aliases.get(
        consulta
    )

    conexion = obtener_conexion()

    try:
        filas = conexion.execute(
            """
            SELECT
                id_presentacion,
                nombre,
                contenido_base
            FROM presentaciones_insumos
            WHERE id_insumo = ?
              AND activa = 1
            ORDER BY contenido_base
            """,
            (insumo["id_insumo"],)
        ).fetchall()

    finally:
        conexion.close()

    if contenido_buscado is not None:
        candidatos = [
            fila
            for fila in filas
            if float(fila[2]) == float(contenido_buscado)
        ]
    else:
        candidatos = [
            fila
            for fila in filas
            if _normalizar(fila[1]) == consulta
        ]

    if len(candidatos) == 1:
        fila = candidatos[0]
        return {
            "ok": True,
            "insumo": insumo,
            "presentacion": {
                "id_presentacion": fila[0],
                "nombre": fila[1],
                "contenido_base": float(fila[2]),
            },
        }

    if contenido_buscado is not None or consulta:
        return {
            "ok": False,
            "codigo": "PRESENTACION_INSUMO_NO_ENCONTRADA",
            "mensaje": (
                f"Esa presentación no está configurada para "
                f"{insumo['nombre']}. Opciones: "
                + ", ".join(
                    fila[1]
                    for fila in filas
                )
                + "."
            ),
            "presentaciones": [
                {
                    "nombre": fila[1],
                    "contenido_base": float(fila[2]),
                }
                for fila in filas
            ],
        }

    if len(filas) > 1:
        return {
            "ok": False,
            "codigo": "PRESENTACION_INSUMO_AMBIGUA",
            "mensaje": (
                f"Indicá la presentación de {insumo['nombre']}. "
                "Opciones: "
                + ", ".join(
                    fila[1]
                    for fila in filas
                )
                + "."
            ),
            "presentaciones": [
                {
                    "nombre": fila[1],
                    "contenido_base": float(fila[2]),
                }
                for fila in filas
            ],
        }

    if len(filas) == 1:
        fila = filas[0]
        return {
            "ok": True,
            "insumo": insumo,
            "presentacion": {
                "id_presentacion": fila[0],
                "nombre": fila[1],
                "contenido_base": float(fila[2]),
            },
        }

    return {
        "ok": False,
        "codigo": "PRESENTACION_INSUMO_NO_CONFIGURADA",
        "mensaje": (
            f"No hay presentaciones por paquete configuradas "
            f"para {insumo['nombre']}."
        ),
    }


def registrar_compra_insumo_paquetes(
    nombre_insumo,
    cantidad_paquetes,
    presentacion,
    costo_total,
    comercio=None,
    fecha=None,
):
    if (
        isinstance(cantidad_paquetes, bool)
        or not isinstance(cantidad_paquetes, int)
        or cantidad_paquetes <= 0
    ):
        return {
            "ok": False,
            "codigo": "CANTIDAD_PAQUETES_INVALIDA",
            "mensaje": (
                "La cantidad de paquetes debe ser un entero "
                "mayor que cero."
            ),
        }

    resolucion = resolver_presentacion_insumo(
        nombre_insumo,
        presentacion,
    )

    if not resolucion["ok"]:
        return resolucion

    insumo = resolucion["insumo"]
    presentacion_resuelta = resolucion["presentacion"]

    cantidad_base_total = (
        cantidad_paquetes
        * presentacion_resuelta["contenido_base"]
    )

    observaciones = (
        f"{cantidad_paquetes} paquete(s) x "
        f"{presentacion_resuelta['nombre']}"
    )

    resultado = registrar_compra_insumo(
        nombre_insumo=insumo["nombre"],
        cantidad=cantidad_base_total,
        unidad=insumo["unidad_base"],
        costo_total=costo_total,
        comercio=comercio,
        fecha=fecha,
        observaciones=observaciones,
    )

    if not resultado["ok"]:
        return resultado

    resultado.update({
        "cantidad_paquetes": cantidad_paquetes,
        "presentacion": presentacion_resuelta["nombre"],
        "contenido_por_paquete": (
            presentacion_resuelta["contenido_base"]
        ),
        "cantidad_base_total": cantidad_base_total,
        "costo_por_paquete": (
            float(costo_total)
            / cantidad_paquetes
        ),
    })

    return resultado



def obtener_stock_insumos():
    conexion = obtener_conexion()

    try:
        filas = conexion.execute(
            """
            SELECT
                id_insumo,
                nombre,
                unidad_base,
                stock_base,
                controla_stock
            FROM insumos
            WHERE activo = 1
            ORDER BY nombre
            """
        ).fetchall()

        return [
            {
                "id_insumo": fila[0],
                "nombre": fila[1],
                "unidad_base": fila[2],
                "stock_base": float(fila[3] or 0),
                "controla_stock": bool(fila[4]),
            }
            for fila in filas
        ]

    finally:
        conexion.close()


def registrar_inventario_insumo(
    nombre_insumo,
    cantidad_real,
    unidad,
    contexto=None,
):
    resolucion = resolver_insumo(
        nombre_insumo
    )

    if not resolucion["ok"]:
        return resolucion

    insumo = resolucion["insumo"]

    if not insumo.get("controla_stock", True):
        return {
            "ok": False,
            "codigo": "INSUMO_NO_INVENTARIABLE",
            "mensaje": (
                f"{insumo['nombre']} es una preparación "
                "y no controla stock físico."
            ),
        }

    try:
        cantidad_base = convertir_a_base(
            cantidad_real,
            unidad,
            insumo["unidad_base"],
        )
    except ValueError as error:
        return {
            "ok": False,
            "codigo": "UNIDAD_INSUMO_INVALIDA",
            "mensaje": str(error),
        }

    contexto_normalizado = _normalizar_contexto_produccion(
        contexto
    )
    conexion = obtener_conexion()

    try:
        conexion.execute("BEGIN IMMEDIATE")
        cursor = conexion.cursor()

        fila = cursor.execute(
            """
            SELECT stock_base
            FROM insumos
            WHERE id_insumo = ?
            """,
            (insumo["id_insumo"],)
        ).fetchone()

        stock_anterior = float(
            fila[0] or 0
        )
        diferencia = (
            cantidad_base
            - stock_anterior
        )
        fecha_hora = datetime.now().isoformat(
            timespec="seconds"
        )

        cursor.execute(
            """
            UPDATE insumos
            SET stock_base = ?
            WHERE id_insumo = ?
            """,
            (
                cantidad_base,
                insumo["id_insumo"],
            )
        )

        cursor.execute(
            """
            INSERT INTO ajustes_stock_insumos (
                id_insumo,
                fecha_hora,
                tipo,
                cantidad_anterior,
                cantidad_nueva,
                diferencia,
                canal_origen,
                usuario_origen,
                grupo_origen,
                id_mensaje_origen
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                insumo["id_insumo"],
                fecha_hora,
                "Inventario físico",
                stock_anterior,
                cantidad_base,
                diferencia,
                contexto_normalizado["canal"],
                contexto_normalizado["usuario_origen"],
                contexto_normalizado["grupo_origen"],
                contexto_normalizado["id_mensaje"],
            )
        )

        conexion.commit()

        return {
            "ok": True,
            "codigo": "INVENTARIO_INSUMO_REGISTRADO",
            "insumo": insumo["nombre"],
            "unidad_base": insumo["unidad_base"],
            "stock_anterior": stock_anterior,
            "stock_nuevo": cantidad_base,
            "diferencia": diferencia,
            "fecha_hora": fecha_hora,
        }

    except Exception as error:
        conexion.rollback()
        return {
            "ok": False,
            "codigo": "ERROR_BASE_DATOS",
            "mensaje": (
                "Error al registrar inventario de insumo: "
                f"{error}"
            ),
        }

    finally:
        conexion.close()


def necesidades_produccion(
    producto,
    cantidad,
):
    if (
        isinstance(cantidad, bool)
        or not isinstance(cantidad, int)
        or cantidad <= 0
    ):
        return {
            "ok": False,
            "codigo": "CANTIDAD_PRODUCCION_INVALIDA",
            "mensaje": (
                "La cantidad debe ser un entero mayor que cero."
            ),
        }

    receta_resultado = obtener_receta(
        producto
    )

    if not receta_resultado["ok"]:
        return receta_resultado

    receta = receta_resultado["receta"]
    factor = (
        cantidad
        / receta["rendimiento"]
    )
    conexion = obtener_conexion()

    try:
        detalle = []
        faltantes = []

        for item in receta["insumos"]:
            fila = conexion.execute(
                """
                SELECT
                    stock_base,
                    controla_stock
                FROM insumos
                WHERE id_insumo = ?
                """,
                (item["id_insumo"],)
            ).fetchone()

            stock = float(
                fila[0] or 0
            )
            controla_stock = bool(
                fila[1]
            )
            necesario = (
                float(item["cantidad_base"])
                * factor
            )

            if controla_stock:
                faltante = max(
                    0.0,
                    necesario - stock,
                )
                suficiente = (
                    faltante <= 1e-9
                )
            else:
                faltante = 0.0
                suficiente = True

            registro = {
                "insumo": item["nombre"],
                "necesario": necesario,
                "unidad": item["unidad_base"],
                "controla_stock": controla_stock,
                "disponible": (
                    stock
                    if controla_stock
                    else None
                ),
                "faltante": faltante,
                "suficiente": suficiente,
            }
            detalle.append(registro)

            if controla_stock and not suficiente:
                faltantes.append(registro)

        return {
            "ok": True,
            "codigo": "NECESIDADES_PRODUCCION",
            "producto": receta["producto"],
            "cantidad": cantidad,
            "version_receta": receta["version"],
            "detalle": detalle,
            "faltantes": faltantes,
            "puede_producir": (
                len(faltantes) == 0
            ),
        }

    finally:
        conexion.close()
