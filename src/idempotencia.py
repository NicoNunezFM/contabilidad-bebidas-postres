from datetime import datetime
import json
import sqlite3

from database import obtener_conexion


def asegurar_tabla_mensajes_procesados():
    conexion = obtener_conexion()

    conexion.execute(
        """
        CREATE TABLE IF NOT EXISTS mensajes_procesados (
            id_registro INTEGER PRIMARY KEY AUTOINCREMENT,
            canal TEXT NOT NULL,
            id_externo TEXT NOT NULL,
            fecha_recepcion TEXT NOT NULL,
            mensaje TEXT NOT NULL,
            estado TEXT NOT NULL DEFAULT 'Procesando',
            respuesta_json TEXT,
            UNIQUE(canal, id_externo)
        )
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
                mensaje,
                estado
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                canal.strip(),
                id_externo.strip(),
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
        cursor = conexion.cursor()

        cursor.execute(
            """
            SELECT
                estado,
                respuesta_json
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

        return {
            "ok": False,
            "codigo": "MENSAJE_EN_PROCESO",
            "mensaje": (
                "Este mensaje ya fue recibido y todavía "
                "está marcado como en proceso."
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
                respuesta_json = ?
            WHERE canal = ?
              AND id_externo = ?
            """,
            (
                json.dumps(
                    resultado,
                    ensure_ascii=False
                ),
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
