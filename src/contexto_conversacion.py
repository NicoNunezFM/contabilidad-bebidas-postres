from datetime import datetime, timedelta

from database import obtener_conexion


DURACION_CONTEXTO_MINUTOS = 15


def _asegurar_tabla():
    conexion = obtener_conexion()

    conexion.execute(
        """
        CREATE TABLE IF NOT EXISTS contextos_conversacion (
            id_contexto INTEGER PRIMARY KEY AUTOINCREMENT,
            canal TEXT NOT NULL,
            clave_contexto TEXT NOT NULL,
            tipo_contexto TEXT NOT NULL,
            fecha_actualizacion TEXT NOT NULL,
            UNIQUE(canal, clave_contexto)
        )
        """
    )

    conexion.commit()
    conexion.close()


def _clave_contexto(contexto):
    if not isinstance(contexto, dict):
        return None, None

    canal = str(
        contexto.get("canal") or "api"
    ).strip()

    usuario = (
        contexto.get("usuario_numero")
        or contexto.get("usuario_id")
    )

    grupo = contexto.get("grupo_id")

    if not usuario and not grupo:
        return canal, None

    if grupo and usuario:
        clave = f"{grupo}|{usuario}"
    elif grupo:
        clave = str(grupo)
    else:
        clave = str(usuario)

    return canal, clave.strip()


def activar_contexto(
    contexto,
    tipo_contexto
):
    canal, clave = _clave_contexto(contexto)

    if not clave:
        return False

    _asegurar_tabla()

    conexion = obtener_conexion()

    try:
        conexion.execute(
            """
            INSERT INTO contextos_conversacion (
                canal,
                clave_contexto,
                tipo_contexto,
                fecha_actualizacion
            )
            VALUES (?, ?, ?, ?)
            ON CONFLICT(canal, clave_contexto)
            DO UPDATE SET
                tipo_contexto = excluded.tipo_contexto,
                fecha_actualizacion = excluded.fecha_actualizacion
            """,
            (
                canal,
                clave,
                tipo_contexto,
                datetime.now().isoformat(
                    timespec="seconds"
                ),
            )
        )

        conexion.commit()
        return True

    finally:
        conexion.close()


def obtener_contexto_activo(contexto):
    canal, clave = _clave_contexto(contexto)

    if not clave:
        return None

    _asegurar_tabla()

    conexion = obtener_conexion()

    try:
        fila = conexion.execute(
            """
            SELECT
                tipo_contexto,
                fecha_actualizacion
            FROM contextos_conversacion
            WHERE canal = ?
              AND clave_contexto = ?
            """,
            (
                canal,
                clave,
            )
        ).fetchone()

        if fila is None:
            return None

        try:
            fecha = datetime.fromisoformat(
                fila[1]
            )
        except (TypeError, ValueError):
            conexion.execute(
                """
                DELETE FROM contextos_conversacion
                WHERE canal = ?
                  AND clave_contexto = ?
                """,
                (canal, clave)
            )
            conexion.commit()
            return None

        if (
            datetime.now() - fecha
            > timedelta(
                minutes=DURACION_CONTEXTO_MINUTOS
            )
        ):
            conexion.execute(
                """
                DELETE FROM contextos_conversacion
                WHERE canal = ?
                  AND clave_contexto = ?
                """,
                (canal, clave)
            )
            conexion.commit()
            return None

        return fila[0]

    finally:
        conexion.close()


def tocar_contexto(contexto):
    tipo = obtener_contexto_activo(contexto)

    if not tipo:
        return None

    activar_contexto(
        contexto,
        tipo
    )

    return tipo


def limpiar_contexto(contexto):
    canal, clave = _clave_contexto(contexto)

    if not clave:
        return False

    _asegurar_tabla()

    conexion = obtener_conexion()

    try:
        conexion.execute(
            """
            DELETE FROM contextos_conversacion
            WHERE canal = ?
              AND clave_contexto = ?
            """,
            (
                canal,
                clave,
            )
        )

        conexion.commit()
        return True

    finally:
        conexion.close()
