from contextlib import closing
from datetime import datetime
import os
from pathlib import Path
import sqlite3
from tempfile import NamedTemporaryFile

from database import obtener_ruta_base


RETENCION_BACKUPS_DIAS = 14


def _publicar_respaldo(temporal, destino):
    # En Windows rename rechaza un destino existente. En POSIX lo reemplaza.
    if os.name == "nt":
        temporal.rename(destino)
    else:
        os.link(temporal, destino)


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

    temporal = None
    try:
        with NamedTemporaryFile(dir=directorio, suffix=".tmp", delete=False) as archivo:
            temporal = Path(archivo.name)
        uri_origen = ruta_base.resolve().as_uri() + "?mode=ro"
        with closing(sqlite3.connect(uri_origen, uri=True)) as origen:
            with closing(sqlite3.connect(temporal)) as respaldo:
                origen.backup(respaldo)
                if respaldo.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                    raise sqlite3.DatabaseError("El respaldo no pasó integrity_check.")
        try:
            _publicar_respaldo(temporal, destino)
        except FileExistsError:
            return {
                "ok": True,
                "codigo": "BACKUP_YA_EXISTE",
                "creado": False,
                "ruta": str(destino),
            }
    except (sqlite3.Error, OSError) as error:

        return {
            "ok": False,
            "codigo": "ERROR_BACKUP",
            "mensaje": (
                f"No se pudo crear el backup: {error}"
            ),
        }

    finally:
        if temporal is not None:
            try:
                temporal.unlink(missing_ok=True)
            except OSError:
                pass

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
