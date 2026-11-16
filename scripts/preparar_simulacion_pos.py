import argparse
import os
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from crear_usuarios_pos_prueba import pedir_contrasena
from database import inicializar_base_de_datos, obtener_conexion
from pos_simulacion import ID_SQLITE_SIMULACION, crear_esquema_simulacion, migrar_esquema_simulacion_v3


def copiar_simulacion_anterior(origen, destino):
    origen = origen.resolve(strict=True)
    if origen.name.casefold() == "negocio.db":
        raise ValueError("Elegí una base ficticia POS 3.")
    with closing(sqlite3.connect(origen.as_uri() + "?mode=ro", uri=True)) as anterior:
        if (anterior.execute("PRAGMA application_id").fetchone()[0] != ID_SQLITE_SIMULACION
                or anterior.execute("PRAGMA user_version").fetchone()[0] != 3):
            raise ValueError("Se requiere una base ficticia marcada con el esquema POS 3.")
        with destino.open("xb"):
            pass
        os.environ["NEGOCIO_DB_PATH"] = str(destino)
        with closing(obtener_conexion()) as copia:
            anterior.backup(copia)
            migrar_esquema_simulacion_v3(copia)


def main():
    parser = argparse.ArgumentParser(description="Creá una base SQLite ficticia para Abadion POS V1.")
    parser.add_argument("ruta", type=Path, help="Ruta de un archivo .db nuevo")
    parser.add_argument("--desde-pos3", type=Path, help="Copiá y actualizá una base ficticia de la versión anterior")
    args = parser.parse_args()
    ruta = args.ruta.absolute()
    if ruta.suffix.lower() != ".db" or ruta.name.casefold() == "negocio.db" or ruta.exists():
        parser.error("Elegí un archivo .db nuevo con un nombre distinto de negocio.db.")

    if args.desde_pos3:
        try:
            copiar_simulacion_anterior(args.desde_pos3, ruta)
        except (OSError, sqlite3.Error, ValueError) as error:
            parser.error(str(error))
        print(f"Copia ficticia actualizada en {ruta}")
        return

    usuarios = [(rol, rol, pedir_contrasena(rol)) for rol in ("admin", "ventas")]
    with ruta.open("xb"):
        pass
    os.environ["NEGOCIO_DB_PATH"] = str(ruta)
    inicializar_base_de_datos()
    conexion = obtener_conexion()
    try:
        with conexion:
            conexion.execute("BEGIN")
            crear_esquema_simulacion(conexion)
            conexion.executemany(
                "INSERT INTO usuarios_pos (usuario, rol, password_hash) VALUES (?, ?, ?)", usuarios
            )
            conexion.executemany(
                "INSERT INTO productos (nombre, categoria, stock, precio_venta) VALUES (?, ?, ?, ?)",
                [("Bebida ficticia", "Bebidas", 20, 1500), ("Comida ficticia", "Comidas", 10, 2500)],
            )
    finally:
        conexion.close()
    print(f"Base ficticia creada en {ruta}")


if __name__ == "__main__":
    main()
