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
}

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
            "de Oreo por unidad. El azúcar impalpable se usa a ojo "
            "y no se incluye todavía en el costo cuantificado."
        ),
        "insumos": [
            ("Galletitas Oreo", 800),
            ("Dulce de leche", 900),
            ("Crema de leche", 600),
            ("Leche", 300),
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
            "y 20 g finales de Chocolinas. "
            "Ingredientes usados a ojo no se incluyen en el costo "
            "exacto hasta que se mida su consumo."
        ),
        "insumos": [
            ("Chocolinas", 1100),
            ("Queso crema", 500),
            ("Dulce de leche", 500),
            ("Café con leche preparado", 900),
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
                seccion
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
