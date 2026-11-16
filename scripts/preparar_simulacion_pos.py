import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from crear_usuarios_pos_prueba import pedir_contrasena
from database import inicializar_base_de_datos, obtener_conexion
from pos_simulacion import crear_esquema_simulacion


def main():
    parser = argparse.ArgumentParser(description="Creá una base SQLite ficticia para Abadion POS V1.")
    parser.add_argument("ruta", type=Path, help="Ruta de un archivo .db nuevo")
    ruta = parser.parse_args().ruta.absolute()
    if ruta.suffix.lower() != ".db" or ruta.name.casefold() == "negocio.db" or ruta.exists():
        parser.error("Elegí un archivo .db nuevo con un nombre distinto de negocio.db.")

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
