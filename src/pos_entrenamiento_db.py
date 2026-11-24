"""Identidad y exclusión mutua del SQLite de entrenamiento."""
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

ARCHIVO_BASE = "abadion-entrenamiento.db"
IDENTIDAD = "abadion-entrenamiento-lo-de-clau-v1"
DESCUENTO_POSTRE_CENTAVOS = 50_000


def clientes_activos(db):
    return db.execute(
        "SELECT 1 FROM sqlite_schema WHERE type = 'table' AND name = 'pos_clientes'"
    ).fetchone() is not None


def consultar_catalogo_entrenamiento(db):
    # Las bases instaladas antes de la actualización todavía pueden abrirse.
    if not db.execute("""
        SELECT 1 FROM sqlite_schema WHERE type = 'table' AND name = 'pos_catalogo_entrenamiento'
    """).fetchone():
        return {}
    return {
        id_producto: (estado, grupo)
        for id_producto, estado, grupo in db.execute(
            "SELECT id_producto, estado, grupo_promo FROM pos_catalogo_entrenamiento"
        )
    }


def carpeta_local():
    if os.name == "nt":
        local = os.getenv("LOCALAPPDATA")
        if not local or not Path(local).is_absolute() or Path(local).drive.startswith("\\\\"):
            raise ValueError("Se requiere un directorio LocalAppData en un disco local.")
        raiz = Path(local)
    else:
        raiz = Path.home() / ".local" / "share"
    carpeta = (raiz / "Abadion" / "Entrenamiento").resolve()
    sincronizadas = (os.getenv(nombre) for nombre in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"))
    if any(valor and carpeta.is_relative_to(Path(valor).resolve()) for valor in sincronizadas) or any(
        parte.casefold().startswith("onedrive") for parte in carpeta.parts
    ):
        raise ValueError("El directorio de entrenamiento debe quedar fuera de OneDrive.")
    return carpeta


def comprobar_archivo(ruta):
    if ruta.resolve() != ruta.absolute() or ruta.is_symlink() or (
        ruta.exists() and (not ruta.is_file() or ruta.stat().st_nlink != 1)
    ):
        raise ValueError(f"Se requiere un archivo local directo: {ruta.name}.")


def abrir_base_entrenamiento(ruta, *, solo_lectura=False):
    from pos_simulacion import ID_SQLITE_SIMULACION, VERSION_ESQUEMA_SIMULACION

    if ruta.name != ARCHIVO_BASE:
        raise ValueError(f"Se requiere el archivo {ARCHIVO_BASE}.")
    comprobar_archivo(ruta)
    for sufijo in ("-wal", "-shm", "-journal"):
        auxiliar = ruta.with_name(ruta.name + sufijo)
        if auxiliar.is_symlink() or (auxiliar.exists() and (solo_lectura or sufijo != "-journal")):
            raise ValueError("SQLite tiene archivos auxiliares; se requiere revisar la base de entrenamiento.")
    modo = "ro&immutable=1" if solo_lectura else "rw"
    db = sqlite3.connect(ruta.as_uri() + "?mode=" + modo, uri=True)
    try:
        if db.execute("SELECT 1 FROM sqlite_schema WHERE name='pos_preproduccion'").fetchone():
            raise ValueError("Preproducción no puede abrirse como Entrenamiento.")
        if (
            db.execute("PRAGMA application_id").fetchone()[0] != ID_SQLITE_SIMULACION
            or db.execute("PRAGMA user_version").fetchone()[0] != VERSION_ESQUEMA_SIMULACION
            or not db.execute("""
                SELECT 1 FROM sqlite_schema WHERE type = 'table' AND name = 'pos_entrenamiento'
            """).fetchone()
            or db.execute("SELECT identidad FROM pos_entrenamiento").fetchall() != [(IDENTIDAD,)]
        ):
            raise ValueError("El archivo no tiene el marcador de Abadion Entrenamiento para esta versión.")
        return db
    except BaseException:
        db.close()
        raise


@contextmanager
def bloquear_entrenamiento(carpeta):
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / "uso.lock"
    comprobar_archivo(ruta)
    with ruta.open("a+b") as archivo:
        if os.name == "nt":
            import msvcrt

            def bloquear():
                archivo.seek(0)
                msvcrt.locking(archivo.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            def bloquear():
                fcntl.flock(archivo, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            bloquear()
        except OSError as error:
            raise ValueError("Entrenamiento está en uso. Cerrá el servidor con Ctrl+C y volvé a intentar.") from error
        yield
