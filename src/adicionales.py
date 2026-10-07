from datetime import datetime
import unicodedata

from database import obtener_conexion


ALIASES_ADICIONALES = {
    "huevos": "huevo",
    "huevo": "huevo",
    "cheddar": "cheddar",
    "cheddar extra": "cheddar",
    "doble porcion": "doble porcion",
    "doble porción": "doble porcion",
    "extra papa": "extra papa",
    "extra de papa": "extra papa",
    "papas extra": "extra papa",
}


def _normalizar(texto):
    valor = str(
        texto or ""
    ).strip().lower()

    valor = "".join(
        caracter
        for caracter in unicodedata.normalize(
            "NFD",
            valor,
        )
        if unicodedata.category(caracter) != "Mn"
    )

    return " ".join(
        valor.split()
    )


def resolver_adicional(nombre):
    consulta = _normalizar(
        nombre
    )
    consulta = ALIASES_ADICIONALES.get(
        consulta,
        consulta,
    )

    conexion = obtener_conexion()

    try:
        filas = conexion.execute(
            """
            SELECT
                id_adicional_catalogo,
                nombre,
                precio_venta,
                costo_unitario,
                activo
            FROM adicionales_catalogo
            WHERE activo = 1
            ORDER BY nombre
            """
        ).fetchall()

    finally:
        conexion.close()

    for fila in filas:
        if _normalizar(
            fila[1]
        ) == consulta:
            return {
                "ok": True,
                "adicional": {
                    "id_adicional_catalogo": fila[0],
                    "nombre": fila[1],
                    "precio_venta": (
                        float(fila[2])
                        if fila[2] is not None
                        else None
                    ),
                    "costo_unitario": (
                        float(fila[3])
                        if fila[3] is not None
                        else None
                    ),
                },
            }

    return {
        "ok": False,
        "codigo": "ADICIONAL_NO_ENCONTRADO",
        "mensaje": (
            f"No conozco el adicional '{nombre}'."
        ),
    }


def configurar_adicional(
    nombre,
    precio_venta=None,
    costo_unitario=None,
):
    if not isinstance(nombre, str) or not nombre.strip():
        return {
            "ok": False,
            "codigo": "ADICIONAL_INVALIDO",
            "mensaje": "Indicá el nombre del adicional.",
        }

    if precio_venta is None and costo_unitario is None:
        return {
            "ok": False,
            "codigo": "ADICIONAL_SIN_CAMBIOS",
            "mensaje": (
                "Indicá precio de venta, costo unitario "
                "o ambos."
            ),
        }

    for etiqueta, valor in (
        ("precio", precio_venta),
        ("costo", costo_unitario),
    ):
        if valor is None:
            continue

        if (
            isinstance(valor, bool)
            or not isinstance(valor, (int, float))
            or valor < 0
        ):
            return {
                "ok": False,
                "codigo": "ADICIONAL_VALOR_INVALIDO",
                "mensaje": (
                    f"El {etiqueta} debe ser un número "
                    "mayor o igual a cero."
                ),
            }

    nombre_normalizado = _normalizar(nombre)
    nombre_normalizado = ALIASES_ADICIONALES.get(
        nombre_normalizado,
        nombre_normalizado,
    )

    fecha_actualizacion = datetime.now().isoformat(
        timespec="seconds"
    )

    conexion = obtener_conexion()

    try:
        cursor = conexion.cursor()

        fila = cursor.execute(
            """
            SELECT
                id_adicional_catalogo,
                precio_venta,
                costo_unitario
            FROM adicionales_catalogo
            WHERE LOWER(nombre) = LOWER(?)
            """,
            (nombre_normalizado,)
        ).fetchone()

        if fila is None:
            cursor.execute(
                """
                INSERT INTO adicionales_catalogo (
                    nombre,
                    precio_venta,
                    costo_unitario,
                    activo,
                    fecha_actualizacion
                )
                VALUES (?, ?, ?, 1, ?)
                """,
                (
                    nombre_normalizado,
                    float(precio_venta)
                    if precio_venta is not None
                    else None,
                    float(costo_unitario)
                    if costo_unitario is not None
                    else None,
                    fecha_actualizacion,
                )
            )
            id_adicional = cursor.lastrowid
            precio_final = (
                float(precio_venta)
                if precio_venta is not None
                else None
            )
            costo_final = (
                float(costo_unitario)
                if costo_unitario is not None
                else None
            )

        else:
            id_adicional = fila[0]
            precio_final = (
                float(precio_venta)
                if precio_venta is not None
                else (
                    float(fila[1])
                    if fila[1] is not None
                    else None
                )
            )
            costo_final = (
                float(costo_unitario)
                if costo_unitario is not None
                else (
                    float(fila[2])
                    if fila[2] is not None
                    else None
                )
            )

            cursor.execute(
                """
                UPDATE adicionales_catalogo
                SET
                    precio_venta = ?,
                    costo_unitario = ?,
                    activo = 1,
                    fecha_actualizacion = ?
                WHERE id_adicional_catalogo = ?
                """,
                (
                    precio_final,
                    costo_final,
                    fecha_actualizacion,
                    id_adicional,
                )
            )

        conexion.commit()

        return {
            "ok": True,
            "codigo": "ADICIONAL_CONFIGURADO",
            "id_adicional_catalogo": id_adicional,
            "nombre": nombre_normalizado,
            "precio_venta": precio_final,
            "costo_unitario": costo_final,
            "fecha_actualizacion": fecha_actualizacion,
        }

    except Exception as error:
        conexion.rollback()
        return {
            "ok": False,
            "codigo": "ERROR_BASE_DATOS",
            "mensaje": (
                "Error al configurar adicional: "
                f"{error}"
            ),
        }

    finally:
        conexion.close()


def listar_adicionales():
    conexion = obtener_conexion()

    try:
        filas = conexion.execute(
            """
            SELECT
                id_adicional_catalogo,
                nombre,
                precio_venta,
                costo_unitario,
                activo,
                fecha_actualizacion
            FROM adicionales_catalogo
            WHERE activo = 1
            ORDER BY nombre
            """
        ).fetchall()

        return [
            {
                "id_adicional_catalogo": fila[0],
                "nombre": fila[1],
                "precio_venta": (
                    float(fila[2])
                    if fila[2] is not None
                    else None
                ),
                "costo_unitario": (
                    float(fila[3])
                    if fila[3] is not None
                    else None
                ),
                "activo": bool(fila[4]),
                "fecha_actualizacion": fila[5],
            }
            for fila in filas
        ]

    finally:
        conexion.close()
