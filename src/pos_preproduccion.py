"""Exclusive identity, verified SQLite snapshots and offline recovery for preproduction."""
import hashlib
import json
import os
import sqlite3
import threading
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from pos_entrenamiento_db import bloquear_entrenamiento, comprobar_archivo

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
    from backups import _publicar_respaldo
    with BACKUP_LOCK:
        identidad = configuracion(carpeta)["id"]
        directorio = carpeta / "backups"
        directorio.mkdir(exist_ok=True)
        if directorio.resolve() != directorio.absolute():
            raise ValueError("Backups debe ser una carpeta directa.")
        destino = directorio / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ-") + etapa + ".db")
        publicados = []
        try:
            # Publish only verified snapshots; a crash before the manifest leaves no usable pair.
            with TemporaryDirectory(prefix=".backup-", dir=directorio) as temporal:
                archivo = Path(temporal) / "copia.db"
                with closing(abrir_base(carpeta, identidad, lectura=True)) as origen, closing(sqlite3.connect(archivo)) as copia:
                    origen.backup(copia)
                    verificar(copia, identidad)
                    integridad(copia)
                meta = {"modo": MODO, "id": identidad, "sha256": hashlib.sha256(archivo.read_bytes()).hexdigest()}
                manifiesto = Path(temporal) / "copia.json"
                manifiesto.write_text(json.dumps(meta), encoding="utf-8")
                for ruta in (archivo, manifiesto):
                    with ruta.open("r+b") as descriptor:
                        os.fsync(descriptor.fileno())
                _publicar_respaldo(archivo, destino)
                publicados.append(destino)
                _publicar_respaldo(manifiesto, destino.with_suffix(".json"))
                publicados.append(destino.with_suffix(".json"))
            auditar(carpeta, "backup-verificado", archivo=destino.name, sha256=meta["sha256"])
            return destino
        except BaseException:
            for publicado in publicados:
                publicado.unlink(missing_ok=True)
            raise


def validar_respaldo(carpeta, nombre):
    if Path(nombre).name != nombre or not nombre.endswith(".db"):
        raise ValueError("Elegí un nombre de backup de esta instalación.")
    origen = carpeta / "backups" / nombre
    comprobar_archivo(origen)
    comprobar_archivo(origen.with_suffix(".json"))
    if any(origen.with_name(origen.name + s).exists() or origen.with_name(origen.name + s).is_symlink()
           for s in ("-wal", "-shm", "-journal")):
        raise ValueError("El backup tiene auxiliares SQLite; no es un snapshot autónomo.")
    identidad = configuracion(carpeta)["id"]
    meta = json.loads(origen.with_suffix(".json").read_text(encoding="utf-8"))
    if meta != {"modo": MODO, "id": identidad, "sha256": hashlib.sha256(origen.read_bytes()).hexdigest()}:
        raise ValueError("El backup fue alterado o pertenece a otra instalación.")
    with closing(sqlite3.connect(origen.as_uri() + "?mode=ro", uri=True)) as db:
        verificar(db, identidad)
        integridad(db)
    return origen


def leer_catalogo_preproduccion(contenido):
    from scripts.abadion_entrenamiento import Catalogo
    catalogo = Catalogo.model_validate_json(contenido.decode("utf-8-sig"))
    if any(a.nombre == "Extra de práctica (ejemplo)" for a in catalogo.adicionales):
        raise ValueError("Retirá el adicional de ejemplo y sus referencias antes de aprobar el catálogo.")
    for producto in catalogo.productos:
        # Stock is an operational balance, never catalogue configuration.
        producto.stock_inicial = 0
    return catalogo


def plan_catalogo(db, catalogo):
    from scripts.abadion_entrenamiento import clave_producto
    existentes = {}
    for identificador, nombre, categoria, controla, precio, stock in db.execute(
        "SELECT id_producto, nombre, categoria, controla_stock, precio_venta, stock FROM productos"
    ):
        clave = clave_producto(nombre)
        if clave in existentes:
            raise ValueError(f"Productos existentes ambiguos: {nombre}.")
        existentes[clave] = (identificador, nombre, categoria, bool(controla), precio, stock)
    adicionales = {}
    for nombre, in db.execute("SELECT nombre FROM adicionales_catalogo"):
        if nombre.casefold() in adicionales:
            raise ValueError("Adicionales existentes ambiguos: " + nombre)
        adicionales[nombre.casefold()] = nombre
    for adicional in catalogo.adicionales:
        anterior = adicionales.get(adicional.nombre.casefold())
        if anterior is not None and anterior != adicional.nombre:
            raise ValueError("Conservá el nombre exacto del adicional existente: " + anterior)
    incluidos, nuevos, cambios = [], [], []
    for producto in catalogo.productos:
        anterior = existentes.get(clave_producto(producto.nombre))
        if anterior is None:
            nuevos.append(producto.nombre)
        else:
            if (producto.categoria, producto.controla_stock) != anterior[2:4]:
                raise ValueError("Cambiar categoría o control de stock requiere revisión separada: " + producto.nombre)
            incluidos.append({"id": anterior[0], "antes": anterior[1], "nombre": producto.nombre})
        cambios.append({"nombre": producto.nombre, "id": anterior[0] if anterior else None,
                        "precio_anterior": anterior[4] if anterior else None,
                        "stock_conservado": anterior[5] if anterior else 0,
                        "propuesto": producto.model_dump()})
    claves = {clave_producto(p.nombre) for p in catalogo.productos}
    return {"conservados": incluidos, "nuevos_stock_cero": nuevos, "productos": cambios,
            "adicionales_propuestos": [a.model_dump() for a in catalogo.adicionales],
            "combinar_sabores_promo": catalogo.combinar_sabores_promo,
            "fuera_menu": [v[1] for k, v in existentes.items() if k not in claves]}


def actualizar_catalogo(carpeta, archivo, *, validar=False, sha256=None):
    from scripts.abadion_entrenamiento import cargar_catalogo
    carpeta = carpeta_segura(carpeta)
    archivo = Path(archivo)
    comprobar_archivo(archivo)
    contenido = archivo.read_bytes()
    huella = hashlib.sha256(contenido).hexdigest()
    if sha256 is not None and sha256 != huella:
        raise ValueError("El catálogo cambió desde su revisión SHA-256.")
    catalogo = leer_catalogo_preproduccion(contenido)
    # Same OS lock and identity as #29. Never dispatch to the #30 launcher/schema.
    with bloquear_entrenamiento(carpeta):
        identidad = configuracion(carpeta)["id"]
        with closing(abrir_base(carpeta, identidad)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            integridad(db)
            plan = plan_catalogo(db, catalogo)
            plan["sha256"] = huella
            if validar:
                return plan
            copia = respaldo(carpeta, "pre-catalogo")
            validar_respaldo(carpeta, copia.name)
            cargar_catalogo(db, catalogo)
            integridad(db)
        auditar(carpeta, "catalogo-aplicado", previo=copia.name, **plan)
        return {"backup": copia.name, **plan}


def restaurar(carpeta, nombre, *, base_ausente=False):
    # Caller must hold the installation lock: never replace an active SQLite file.
    identidad = configuracion(carpeta)["id"]
    origen = validar_respaldo(carpeta, nombre)
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
