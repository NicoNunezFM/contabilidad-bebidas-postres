from datetime import datetime

from database import obtener_conexion
from deudas_negocio import registrar_compra_deuda_en_cursor


def _parse_fecha(valor):
    if not valor:
        return None

    texto = str(valor).strip()

    try:
        return datetime.fromisoformat(
            texto.replace("Z", "+00:00")
        ).replace(tzinfo=None)
    except ValueError:
        return None


def _fila_a_dict(fila):
    if fila is None:
        return None

    return {
        "id_importacion": fila[0],
        "fuente": fila[1],
        "id_externo": fila[2],
        "id_cuenta_deuda": fila[3],
        "fecha_operacion": fila[4],
        "fecha_importacion": fila[5],
        "importe": float(fila[6]),
        "moneda": fila[7],
        "comercio": fila[8],
        "titular": fila[9],
        "tipo_tarjeta": fila[10],
        "plan": fila[11],
        "estado": fila[12],
        "id_movimiento_deuda": fila[13],
        "asunto": fila[14],
    }


def _buscar_importacion(
    cursor,
    fuente,
    id_externo,
):
    fila = cursor.execute(
        """
        SELECT
            id_importacion,
            fuente,
            id_externo,
            id_cuenta_deuda,
            fecha_operacion,
            fecha_importacion,
            importe,
            moneda,
            comercio,
            titular,
            tipo_tarjeta,
            plan,
            estado,
            id_movimiento_deuda,
            asunto
        FROM importaciones_deuda
        WHERE fuente = ?
          AND id_externo = ?
        """,
        (
            fuente,
            id_externo,
        )
    ).fetchone()

    return _fila_a_dict(
        fila
    )


def registrar_importacion_deuda(
    *,
    fuente,
    id_externo,
    importe,
    fecha_operacion=None,
    moneda="ARS",
    comercio=None,
    titular=None,
    tipo_tarjeta=None,
    plan=None,
    asunto=None,
    cuenta_deuda="naranja",
    aplica_deuda=True,
    fecha_corte=None,
):
    fuente = str(fuente or "").strip()
    id_externo = str(id_externo or "").strip()
    moneda = str(moneda or "ARS").strip().upper()

    if not fuente or not id_externo:
        return {
            "ok": False,
            "codigo": "IMPORTACION_DEUDA_INVALIDA",
            "mensaje": (
                "La importación necesita fuente e id externo."
            ),
        }

    if (
        isinstance(importe, bool)
        or not isinstance(importe, (int, float))
        or importe <= 0
    ):
        return {
            "ok": False,
            "codigo": "IMPORTE_IMPORTACION_INVALIDO",
            "mensaje": (
                "El importe importado debe ser mayor que cero."
            ),
        }

    fecha_operacion_dt = _parse_fecha(
        fecha_operacion
    )
    fecha_corte_dt = _parse_fecha(
        fecha_corte
    )

    estado_final = (
        "pendiente_clasificacion"
        if aplica_deuda
        else "ignorado_no_negocio"
    )

    if (
        aplica_deuda
        and fecha_corte_dt is not None
        and fecha_operacion_dt is not None
        and fecha_operacion_dt < fecha_corte_dt
    ):
        estado_final = "historico_no_aplicado"

    if (
        aplica_deuda
        and moneda != "ARS"
    ):
        estado_final = "requiere_revision_moneda"

    genera_deuda = (
        estado_final
        == "pendiente_clasificacion"
    )

    conexion = obtener_conexion()

    try:
        conexion.execute(
            "BEGIN IMMEDIATE"
        )
        cursor = conexion.cursor()

        existente = _buscar_importacion(
            cursor,
            fuente,
            id_externo,
        )

        if existente is not None:
            conexion.rollback()

            return {
                "ok": True,
                "codigo": "IMPORTACION_DEUDA_YA_EXISTENTE",
                "duplicada": True,
                **existente,
            }

        fecha_importacion = datetime.now().isoformat(
            timespec="seconds"
        )

        cursor.execute(
            """
            INSERT INTO importaciones_deuda (
                fuente,
                id_externo,
                fecha_operacion,
                fecha_importacion,
                importe,
                moneda,
                comercio,
                titular,
                tipo_tarjeta,
                plan,
                estado,
                asunto
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'procesando', ?)
            """,
            (
                fuente,
                id_externo,
                fecha_operacion,
                fecha_importacion,
                float(importe),
                moneda,
                comercio,
                titular,
                tipo_tarjeta,
                plan,
                asunto,
            )
        )

        id_importacion = cursor.lastrowid
        id_cuenta_deuda = None
        id_movimiento_deuda = None
        saldo_deuda = None

        if genera_deuda:
            descripcion = (
                "Compra importada"
                + (
                    f" - {comercio}"
                    if comercio
                    else ""
                )
            )

            deuda = registrar_compra_deuda_en_cursor(
                cursor=cursor,
                nombre=cuenta_deuda,
                monto=float(importe),
                descripcion=descripcion,
                fecha_hora=(
                    fecha_operacion
                    or fecha_importacion
                ),
            )

            id_cuenta_deuda = deuda[
                "id_cuenta"
            ]
            id_movimiento_deuda = deuda[
                "id_movimiento_deuda"
            ]
            saldo_deuda = deuda[
                "saldo"
            ]

        cursor.execute(
            """
            UPDATE importaciones_deuda
            SET
                id_cuenta_deuda = ?,
                id_movimiento_deuda = ?,
                estado = ?
            WHERE id_importacion = ?
            """,
            (
                id_cuenta_deuda,
                id_movimiento_deuda,
                estado_final,
                id_importacion,
            )
        )

        importacion = _buscar_importacion(
            cursor,
            fuente,
            id_externo,
        )

        conexion.commit()

        return {
            "ok": True,
            "codigo": "IMPORTACION_DEUDA_REGISTRADA",
            "duplicada": False,
            "genera_deuda": genera_deuda,
            "saldo_deuda": saldo_deuda,
            **importacion,
        }

    except Exception as error:
        conexion.rollback()

        return {
            "ok": False,
            "codigo": "ERROR_IMPORTACION_DEUDA",
            "mensaje": (
                "No se pudo registrar la importación: "
                f"{error}"
            ),
        }

    finally:
        conexion.close()


def listar_importaciones_deuda(
    estado=None,
    limite=50,
):
    if (
        isinstance(limite, bool)
        or not isinstance(limite, int)
        or limite <= 0
    ):
        limite = 50

    conexion = obtener_conexion()

    try:
        if estado:
            filas = conexion.execute(
                """
                SELECT
                    id_importacion,
                    fuente,
                    id_externo,
                    id_cuenta_deuda,
                    fecha_operacion,
                    fecha_importacion,
                    importe,
                    moneda,
                    comercio,
                    titular,
                    tipo_tarjeta,
                    plan,
                    estado,
                    id_movimiento_deuda,
                    asunto
                FROM importaciones_deuda
                WHERE estado = ?
                ORDER BY id_importacion DESC
                LIMIT ?
                """,
                (
                    estado,
                    limite,
                )
            ).fetchall()
        else:
            filas = conexion.execute(
                """
                SELECT
                    id_importacion,
                    fuente,
                    id_externo,
                    id_cuenta_deuda,
                    fecha_operacion,
                    fecha_importacion,
                    importe,
                    moneda,
                    comercio,
                    titular,
                    tipo_tarjeta,
                    plan,
                    estado,
                    id_movimiento_deuda,
                    asunto
                FROM importaciones_deuda
                ORDER BY id_importacion DESC
                LIMIT ?
                """,
                (limite,)
            ).fetchall()

        return [
            _fila_a_dict(fila)
            for fila in filas
        ]

    finally:
        conexion.close()



def obtener_importacion_deuda(
    id_importacion,
):
    if (
        isinstance(id_importacion, bool)
        or not isinstance(id_importacion, int)
        or id_importacion <= 0
    ):
        return {
            "ok": False,
            "codigo": "ID_IMPORTACION_INVALIDO",
            "mensaje": (
                "El ID de importación debe ser "
                "un entero mayor que cero."
            ),
        }

    conexion = obtener_conexion()

    try:
        fila = conexion.execute(
            """
            SELECT
                id_importacion,
                fuente,
                id_externo,
                id_cuenta_deuda,
                fecha_operacion,
                fecha_importacion,
                importe,
                moneda,
                comercio,
                titular,
                tipo_tarjeta,
                plan,
                estado,
                id_movimiento_deuda,
                asunto
            FROM importaciones_deuda
            WHERE id_importacion = ?
            """,
            (id_importacion,)
        ).fetchone()

        if fila is None:
            return {
                "ok": False,
                "codigo": "IMPORTACION_DEUDA_NO_ENCONTRADA",
                "mensaje": (
                    "No existe esa importación de deuda."
                ),
            }

        return {
            "ok": True,
            "codigo": "IMPORTACION_DEUDA_ENCONTRADA",
            "importacion": _fila_a_dict(
                fila
            ),
        }

    finally:
        conexion.close()
