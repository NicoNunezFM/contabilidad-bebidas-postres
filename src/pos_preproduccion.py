"""Exclusive identity, verified SQLite snapshots and offline recovery for preproduction."""
import hashlib
import json
import os
import sqlite3
import threading
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from pos_entrenamiento_db import comprobar_archivo

ARCHIVO = "abadion-preproduccion.db"
MODO = "PREPRODUCCION-FICTICIA-V1"
BACKUP_LOCK = threading.Lock()


def carpeta_segura(carpeta):
    carpeta = Path(carpeta).absolute()
    if carpeta.resolve() != carpeta or carpeta.name != "Preproduccion" or str(carpeta).startswith("\\\\"):
        raise ValueError("Se requiere una carpeta local directa llamada Preproduccion.")
    if any(p.casefold().startswith("onedrive") for p in carpeta.parts) or any(
        v and carpeta.is_relative_to(Path(v).resolve())
        for v in (os.getenv(k) for k in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"))
    ):
        raise ValueError("Preproducción debe quedar fuera de OneDrive.")
    return carpeta


def configuracion(carpeta):
    carpeta = carpeta_segura(carpeta)
    archivo = carpeta / "instalacion.json"
    comprobar_archivo(archivo)
    datos = json.loads(archivo.read_text(encoding="utf-8"))
    if datos["modo"] != MODO or datos["carpeta"] != str(carpeta):
        raise ValueError("La instalación no coincide con su ruta o modo.")
    return datos


def verificar(db, identidad):
    from pos_simulacion import ID_SQLITE_SIMULACION, VERSION_ESQUEMA_SIMULACION
    if (db.execute("PRAGMA application_id").fetchone()[0] != ID_SQLITE_SIMULACION
            or db.execute("PRAGMA user_version").fetchone()[0] != VERSION_ESQUEMA_SIMULACION
            or db.execute("SELECT modo, instalacion FROM pos_preproduccion").fetchall() != [(MODO, identidad)]):
        raise ValueError("Base ajena o versión incompatible con PREPRODUCCIÓN.")


def abrir_base(carpeta, identidad, *, lectura=False):
    carpeta = carpeta_segura(carpeta)
    if configuracion(carpeta)["id"] != identidad:
        raise ValueError("Identidad de instalación incorrecta.")
    ruta = carpeta / ARCHIVO
    comprobar_archivo(ruta)
    for sufijo in ("-wal", "-shm", "-journal"):
        comprobar_archivo(ruta.with_name(ruta.name + sufijo))
    db = sqlite3.connect(ruta.as_uri() + ("?mode=ro" if lectura else "?mode=rw"), uri=True, timeout=15)
    try:
        verificar(db, identidad)
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA synchronous=FULL")
        return db
    except BaseException:
        db.close()
        raise


def integridad(db):
    if db.execute("PRAGMA integrity_check").fetchall() != [("ok",)] or db.execute("PRAGMA foreign_key_check").fetchall():
        raise ValueError("Falló la integridad SQLite o sus referencias.")


def auditar(carpeta, evento, **datos):
    ruta = carpeta / "auditoria.jsonl"
    comprobar_archivo(ruta)
    with ruta.open("a", encoding="utf-8") as archivo:
        archivo.write(json.dumps({"utc": datetime.now(timezone.utc).isoformat(), "evento": evento, **datos}) + "\n")
        archivo.flush()
        os.fsync(archivo.fileno())


def respaldo(carpeta, etapa="manual"):
    with BACKUP_LOCK:
        identidad = configuracion(carpeta)["id"]
        directorio = carpeta / "backups"
        directorio.mkdir(exist_ok=True)
        if directorio.resolve() != directorio.absolute():
            raise ValueError("Backups debe ser una carpeta directa.")
        destino = directorio / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ-") + etapa + ".db")
        with destino.open("xb"):
            pass
        try:
            with closing(abrir_base(carpeta, identidad, lectura=True)) as origen, closing(sqlite3.connect(destino)) as copia:
                origen.backup(copia)
                verificar(copia, identidad)
                integridad(copia)
            meta = {"modo": MODO, "id": identidad, "sha256": hashlib.sha256(destino.read_bytes()).hexdigest()}
            destino.with_suffix(".json").write_text(json.dumps(meta), encoding="utf-8")
            auditar(carpeta, "backup-verificado", archivo=destino.name, sha256=meta["sha256"])
            return destino
        except BaseException:
            destino.unlink(missing_ok=True)
            raise


def restaurar(carpeta, nombre, *, base_ausente=False):
    # Caller must hold the installation lock: never replace an active SQLite file.
    if Path(nombre).name != nombre or not nombre.endswith(".db"):
        raise ValueError("Elegí un nombre de backup de esta instalación.")
    identidad = configuracion(carpeta)["id"]
    origen = carpeta / "backups" / nombre
    comprobar_archivo(origen)
    comprobar_archivo(origen.with_suffix(".json"))
    meta = json.loads(origen.with_suffix(".json").read_text(encoding="utf-8"))
    if meta != {"modo": MODO, "id": identidad, "sha256": hashlib.sha256(origen.read_bytes()).hexdigest()}:
        raise ValueError("El backup fue alterado o pertenece a otra instalación.")
    destino = carpeta / ARCHIVO
    comprobar_archivo(destino)
    if not destino.exists() and not base_ausente:
        raise ValueError("Falta la base. Revisá la instalación y usá --base-ausente para recuperación explícita.")
    if destino.exists() and base_ausente:
        raise ValueError("--base-ausente sólo admite un destino inexistente; no sobrescribe archivos.")
    if any(destino.with_name(destino.name + s).exists() for s in ("-wal", "-shm", "-journal")):
        raise ValueError("Hay recuperación SQLite pendiente. Iniciá y detené antes de restaurar.")
    temporal = carpeta / "restore-pendiente.db"
    comprobar_archivo(temporal)
    with temporal.open("xb"):
        pass
    try:
        with closing(sqlite3.connect(origen.as_uri() + "?mode=ro", uri=True)) as fuente, closing(sqlite3.connect(temporal)) as copia:
            verificar(fuente, identidad)
            integridad(fuente)
            fuente.backup(copia)
            copia.execute("DELETE FROM sesiones_pos")
            copia.commit()
            integridad(copia)
        previo = None if base_ausente else respaldo(carpeta, "pre-restore")
        os.replace(temporal, destino)
        auditar(carpeta, "restore-verificado", archivo=nombre, previo=previo.name if previo else "base-ausente")
    finally:
        temporal.unlink(missing_ok=True)
