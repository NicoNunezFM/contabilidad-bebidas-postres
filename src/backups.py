from datetime import datetime
from pathlib import Path
import sqlite3

from database import obtener_ruta_base


RETENCION_BACKUPS_DIAS = 14


def obtener_directorio_backups():
    ruta_base = Path(obtener_ruta_base())
    return ruta_base.parent / "backups"


def crear_backup_diario(
    retencion=RETENCION_BACKUPS_DIAS
):
    ruta_base = Path(obtener_ruta_base())

    if not ruta_base.exists():
        return {
            "ok": False,
            "codigo": "BASE_NO_ENCONTRADA",
            "mensaje": (
                "No se encontró la base de datos para respaldar."
            ),
        }

    directorio = obtener_directorio_backups()
    directorio.mkdir(
        parents=True,
        exist_ok=True
    )

    fecha = datetime.now().strftime("%Y-%m-%d")
    destino = (
        directorio
        / f"{ruta_base.stem}_{fecha}.db"
    )

    if destino.exists():
        return {
            "ok": True,
            "codigo": "BACKUP_YA_EXISTE",
            "creado": False,
            "ruta": str(destino),
        }

    origen = None
    respaldo = None

    try:
        origen = sqlite3.connect(ruta_base)
        respaldo = sqlite3.connect(destino)

        origen.backup(respaldo)

    except sqlite3.Error as error:
        if destino.exists():
            try:
                destino.unlink()
            except OSError:
                pass

        return {
            "ok": False,
            "codigo": "ERROR_BACKUP",
            "mensaje": (
                f"No se pudo crear el backup: {error}"
            ),
        }

    finally:
        if respaldo is not None:
            respaldo.close()

        if origen is not None:
            origen.close()

    _aplicar_retencion(
        directorio=directorio,
        nombre_base=ruta_base.stem,
        retencion=retencion,
    )

    return {
        "ok": True,
        "codigo": "BACKUP_CREADO",
        "creado": True,
        "ruta": str(destino),
    }


def _aplicar_retencion(
    directorio,
    nombre_base,
    retencion
):
    if (
        isinstance(retencion, bool)
        or not isinstance(retencion, int)
        or retencion <= 0
    ):
        return

    archivos = sorted(
        directorio.glob(
            f"{nombre_base}_????-??-??.db"
        ),
        key=lambda archivo: archivo.name,
        reverse=True,
    )

    for archivo in archivos[retencion:]:
        try:
            archivo.unlink()
        except OSError:
            pass
