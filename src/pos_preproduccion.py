"""Almacenamiento exclusivo para ensayos persistentes; no habilita producción."""
import hashlib
import json
import os
import shutil
import sqlite3
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from pos_entrenamiento_db import bloquear_entrenamiento, comprobar_archivo

ARCHIVO = "abadion-preproduccion.db"
MODO = "PREPRODUCCION-FICTICIA-V1"


def carpeta_segura(carpeta):
    carpeta = Path(carpeta)
    if (not carpeta.is_absolute() or carpeta.resolve() != carpeta.absolute()
            or str(carpeta).startswith("\\\\") or carpeta.name != "Preproduccion"):
        raise ValueError("Elegí una ruta local absoluta directa llamada Preproduccion.")
    sincronizadas = (os.getenv(k) for k in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"))
    if any(p.casefold().startswith("onedrive") for p in carpeta.parts) or any(
        v and carpeta.is_relative_to(Path(v).resolve()) for v in sincronizadas
    ):
        raise ValueError("Los datos deben quedar fuera de OneDrive.")
    return carpeta


def carpeta_local():
    local = os.getenv("LOCALAPPDATA")
    if not local:
        raise ValueError("Se requiere LOCALAPPDATA o --carpeta explícita.")
    return carpeta_segura(Path(local) / "Abadion" / "Preproduccion")


def configuracion(carpeta):
    carpeta = carpeta_segura(carpeta)
    archivo = carpeta / "instalacion.json"
    comprobar_archivo(archivo)
    datos = json.loads(archivo.read_text(encoding="utf-8"))
    if datos["modo"] != MODO or datos["carpeta"] != str(carpeta):
        raise ValueError("Configuración ajena a esta instalación.")
    return datos


def verificar(db, identidad):
    from pos_simulacion import ID_SQLITE_SIMULACION, VERSION_ESQUEMA_SIMULACION
    if (db.execute("PRAGMA application_id").fetchone()[0] != ID_SQLITE_SIMULACION
            or db.execute("PRAGMA user_version").fetchone()[0] != VERSION_ESQUEMA_SIMULACION
            or db.execute("SELECT modo, identidad FROM pos_preproduccion").fetchall() != [(MODO, identidad)]):
        raise ValueError("Identidad o versión de preproducción incorrecta.")


def integridad(db):
    if db.execute("PRAGMA integrity_check").fetchall() != [("ok",)] or db.execute("PRAGMA foreign_key_check").fetchall():
        raise ValueError("Falló la integridad SQLite o sus referencias.")


def abrir_base(carpeta, *, lectura=False):
    datos = configuracion(carpeta)
    ruta = carpeta / ARCHIVO
    comprobar_archivo(ruta)
    for sufijo in ("-wal", "-shm", "-journal"):
        comprobar_archivo(ruta.with_name(ruta.name + sufijo))
    db = sqlite3.connect(ruta.as_uri() + ("?mode=ro" if lectura else "?mode=rw"), uri=True, timeout=15)
    try:
        verificar(db, datos["id"])
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA synchronous=FULL")
        return db
    except BaseException:
        db.close()
        raise


@contextmanager
def mantenimiento(carpeta):
    configuracion(carpeta)
    with bloquear_entrenamiento(carpeta):
        yield


def catalogo_sin_stock(archivo):
    from scripts.abadion_entrenamiento import leer_catalogo
    catalogo = leer_catalogo(archivo)
    ejemplo = "Extra de práctica (ejemplo)"
    catalogo.adicionales = [a for a in catalogo.adicionales if a.nombre != ejemplo]
    catalogo.aviso = "Catálogo de preproducción para ensayos; revisar precios y disponibilidad."
    for producto in catalogo.productos:
        producto.stock_inicial = 0
        producto.adicionales = [a for a in producto.adicionales if a != ejemplo]
    return catalogo


def preparar(carpeta, catalogo, admin, ventas):
    from scripts.abadion_entrenamiento import construir_base
    from pos_auth import generar_hash
    carpeta = carpeta_segura(carpeta)
    if carpeta.exists():
        raise FileExistsError("La carpeta ya existe; no se reemplaza ninguna instalación.")
    hashes = (generar_hash(admin), generar_hash(ventas))
    from scripts.abadion_entrenamiento import USUARIOS
    if admin == ventas or any(clave in {u[2] for u in USUARIOS} for clave in (admin, ventas)):
        raise ValueError("Usá dos contraseñas privadas diferentes de las de práctica.")
    catalogo = catalogo_sin_stock(catalogo)
    carpeta.parent.mkdir(parents=True, exist_ok=True)
    identidad = str(uuid4())
    with TemporaryDirectory(prefix=".preproduccion-", dir=carpeta.parent) as temporal:
        nueva = Path(temporal) / "instalacion"
        nueva.mkdir()
        ruta = nueva / "construccion.db"
        # El constructor opera sólo sobre el archivo nuevo dentro del temporal privado.
        construir_base(ruta, catalogo)
        with closing(sqlite3.connect(ruta)) as db, db:
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("DELETE FROM usuarios_pos")
            db.executemany("INSERT INTO usuarios_pos (id_usuario, usuario, rol, password_hash) VALUES (?, ?, ?, ?)",
                           [(1, "admin-preproduccion", "admin", hashes[0]),
                            (2, "ventas-preproduccion", "ventas", hashes[1])])
            db.execute("DROP TABLE pos_entrenamiento")
            db.execute("CREATE TABLE pos_preproduccion (modo TEXT NOT NULL, identidad TEXT NOT NULL)")
            db.execute("INSERT INTO pos_preproduccion VALUES (?, ?)", (MODO, identidad))
            verificar(db, identidad)
            integridad(db)
        ruta.rename(nueva / ARCHIVO)
        (nueva / "instalacion.json").write_text(json.dumps(
            {"modo": MODO, "id": identidad, "carpeta": str(carpeta)}, indent=2), encoding="utf-8")
        (nueva / "catalogo.json").write_text(catalogo.model_dump_json(indent=2), encoding="utf-8")
        nueva.rename(carpeta)
    return carpeta / ARCHIVO


def respaldo(carpeta):
    identidad = configuracion(carpeta)["id"]
    directorio = carpeta / "backups"
    directorio.mkdir(exist_ok=True)
    if directorio.resolve() != directorio.absolute():
        raise ValueError("La carpeta de copias debe ser directa.")
    nombre = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ-") + uuid4().hex
    destino = directorio / (nombre + ".db")
    # Los temporales incompletos nunca son reconocidos como copias publicadas.
    with TemporaryDirectory(prefix=".backup-", dir=directorio) as temporal:
        archivo = Path(temporal) / "copia.db"
        with closing(abrir_base(carpeta, lectura=True)) as origen, closing(sqlite3.connect(archivo)) as copia:
            origen.backup(copia)
            verificar(copia, identidad)
            integridad(copia)
        meta = {"modo": MODO, "id": identidad, "sha256": hashlib.sha256(archivo.read_bytes()).hexdigest()}
        archivo.rename(destino)
        destino.with_suffix(".json").write_text(json.dumps(meta), encoding="utf-8")
    return destino


def validar_respaldo(carpeta, archivo):
    comprobar_archivo(archivo)
    manifiesto = archivo.with_suffix(".json")
    comprobar_archivo(manifiesto)
    meta = json.loads(manifiesto.read_text(encoding="utf-8"))
    if (meta["modo"] != MODO or meta["id"] != configuracion(carpeta)["id"]
            or meta["sha256"] != hashlib.sha256(archivo.read_bytes()).hexdigest()):
        raise ValueError("El respaldo no coincide con su hash o instalación.")
    for sufijo in ("-wal", "-shm", "-journal"):
        if archivo.with_name(archivo.name + sufijo).exists():
            raise ValueError("El respaldo tiene auxiliares SQLite.")
    with closing(sqlite3.connect(archivo.as_uri() + "?mode=ro", uri=True)) as db:
        verificar(db, meta["id"])
        integridad(db)


def restaurar(carpeta, archivo):
    with mantenimiento(carpeta):
        validar_respaldo(carpeta, archivo)
        ruta = carpeta / ARCHIVO
        for sufijo in ("-wal", "-shm", "-journal"):
            if ruta.with_name(ruta.name + sufijo).exists():
                raise ValueError("Revisá los auxiliares SQLite antes de restaurar.")
        anterior = respaldo(carpeta)
        with TemporaryDirectory(prefix=".restore-", dir=carpeta) as temporal:
            nueva = Path(temporal) / "nueva.db"
            shutil.copyfile(archivo, nueva)
            if hashlib.sha256(nueva.read_bytes()).hexdigest() != json.loads(
                archivo.with_suffix(".json").read_text(encoding="utf-8")
            )["sha256"]:
                raise ValueError("La copia cambió durante la restauración.")
            with closing(sqlite3.connect(nueva)) as db, db:
                verificar(db, configuracion(carpeta)["id"])
                integridad(db)
                db.execute("UPDATE sesiones_pos SET revocada=1")
            os.replace(nueva, ruta)
        return anterior


def actualizar_catalogo(carpeta, archivo):
    from scripts.abadion_entrenamiento import cargar_catalogo
    catalogo = catalogo_sin_stock(archivo)
    with mantenimiento(carpeta):
        copia = respaldo(carpeta)
        with closing(abrir_base(carpeta)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            cargar_catalogo(db, catalogo)
            integridad(db)
        return copia
