from datetime import datetime
import json
import sqlite3

from database import obtener_conexion


LIMITE_PROCESANDO_SEGUNDOS = 300


def asegurar_tabla_mensajes_procesados():
    conexion = obtener_conexion()

    conexion.execute(
        """
        CREATE TABLE IF NOT EXISTS mensajes_procesados (
            id_registro INTEGER PRIMARY KEY AUTOINCREMENT,
            canal TEXT NOT NULL,
            id_externo TEXT NOT NULL,
            fecha_recepcion TEXT NOT NULL,
            fecha_actualizacion TEXT,
            mensaje TEXT NOT NULL,
            estado TEXT NOT NULL DEFAULT 'Procesando',
            respuesta_json TEXT,
            UNIQUE(canal, id_externo)
        )
        """
    )

    cursor = conexion.cursor()
    cursor.execute("PRAGMA table_info(mensajes_procesados)")
    columnas = cursor.fetchall()
    nombres = [columna[1] for columna in columnas]

    if "fecha_actualizacion" not in nombres:
        cursor.execute(
            """
            ALTER TABLE mensajes_procesados
            ADD COLUMN fecha_actualizacion TEXT
            """
        )

    conexion.commit()
    conexion.close()


def iniciar_procesamiento(
    canal,
    id_externo,
    mensaje
):
    if (
        not isinstance(canal, str)
        or not canal.strip()
        or not isinstance(id_externo, str)
        or not id_externo.strip()
    ):
        return {
            "ok": False,
            "codigo": "DATOS_INVALIDOS",
            "mensaje": "Canal e ID externo son obligatorios."
        }

    asegurar_tabla_mensajes_procesados()

    conexion = obtener_conexion()

    try:
        cursor = conexion.cursor()

        cursor.execute(
            """
            INSERT INTO mensajes_procesados (
                canal,
                id_externo,
                fecha_recepcion,
                fecha_actualizacion,
                mensaje,
                estado
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                canal.strip(),
                id_externo.strip(),
                datetime.now().isoformat(timespec="seconds"),
                datetime.now().isoformat(timespec="seconds"),
                str(mensaje or ""),
                "Procesando",
            )
        )

        conexion.commit()

        return {
            "ok": True,
            "nuevo": True,
        }

    except sqlite3.IntegrityError:
        conexion.rollback()
        cursor = conexion.cursor()

        cursor.execute(
            """
            SELECT
                estado,
                respuesta_json,
                COALESCE(
                    fecha_actualizacion,
                    fecha_recepcion
                )
            FROM mensajes_procesados
            WHERE canal = ?
              AND id_externo = ?
            """,
            (
                canal.strip(),
                id_externo.strip(),
            )
        )

        fila = cursor.fetchone()

        if fila is None:
            return {
                "ok": False,
                "codigo": "ERROR_BASE_DATOS",
                "mensaje": "No se pudo recuperar el mensaje duplicado."
            }

        estado = fila[0]
        respuesta_json = fila[1]
        fecha_estado = fila[2]

        if estado == "Completado" and respuesta_json:
            try:
                resultado = json.loads(respuesta_json)
            except json.JSONDecodeError:
                return {
                    "ok": False,
                    "codigo": "ERROR_BASE_DATOS",
                    "mensaje": "La respuesta guardada del mensaje no es válida."
                }

            resultado["repetido"] = True

            return {
                "ok": True,
                "nuevo": False,
                "resultado": resultado,
            }

        if estado == "Procesando":
            ahora = datetime.now()

            try:
                fecha_proceso = datetime.fromisoformat(
                    fecha_estado
                )
                antiguedad = (
                    ahora - fecha_proceso
                ).total_seconds()
            except (TypeError, ValueError):
                antiguedad = (
                    LIMITE_PROCESANDO_SEGUNDOS + 1
                )

            if antiguedad <= LIMITE_PROCESANDO_SEGUNDOS:
                return {
                    "ok": False,
                    "codigo": "MENSAJE_EN_PROCESO",
                    "mensaje": (
                        "Este mensaje ya fue recibido y todavía "
                        "está marcado como en proceso."
                    )
                }

            cursor.execute(
                """
                UPDATE mensajes_procesados
                SET
                    estado = 'Requiere_revision',
                    fecha_actualizacion = ?
                WHERE canal = ?
                  AND id_externo = ?
                """,
                (
                    ahora.isoformat(timespec="seconds"),
                    canal.strip(),
                    id_externo.strip(),
                )
            )
            conexion.commit()

        return {
            "ok": False,
            "codigo": "MENSAJE_REQUIERE_REVISION",
            "mensaje": (
                "Este mensaje quedó interrumpido durante una "
                "ejecución anterior. No se volverá a ejecutar "
                "automáticamente para evitar duplicar movimientos."
            )
        }

    except sqlite3.Error as error:
        conexion.rollback()

        return {
            "ok": False,
            "codigo": "ERROR_BASE_DATOS",
            "mensaje": f"Error registrando idempotencia: {error}"
        }

    finally:
        conexion.close()


def finalizar_procesamiento(
    canal,
    id_externo,
    resultado
):
    asegurar_tabla_mensajes_procesados()

    conexion = obtener_conexion()

    try:
        conexion.execute(
            """
            UPDATE mensajes_procesados
            SET
                estado = 'Completado',
                respuesta_json = ?,
                fecha_actualizacion = ?
            WHERE canal = ?
              AND id_externo = ?
            """,
            (
                json.dumps(
                    resultado,
                    ensure_ascii=False
                ),
                datetime.now().isoformat(timespec="seconds"),
                canal.strip(),
                id_externo.strip(),
            )
        )

        conexion.commit()

        return {
            "ok": True,
        }

    except sqlite3.Error as error:
        conexion.rollback()

        return {
            "ok": False,
            "codigo": "ERROR_BASE_DATOS",
            "mensaje": f"Error finalizando idempotencia: {error}"
        }

    finally:
        conexion.close()
