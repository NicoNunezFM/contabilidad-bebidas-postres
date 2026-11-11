
import getpass
import os
import sys
import tempfile
from pathlib import Path

RUTA_PROYECTO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RUTA_PROYECTO / "src"))

from database import crear_tabla_usuarios_pos, obtener_conexion
from pos_auth import generar_hash


RUTA_ESPERADA = (
    Path(tempfile.gettempdir())
    / "AbadionPOSPruebas"
    / "negocio_pos_test.db"
).resolve()


def pedir_contrasena(usuario):
    primera = getpass.getpass(f"Contraseña para {usuario}: ")
    segunda = getpass.getpass("Repetir contraseña: ")

    if primera != segunda:
        raise ValueError("Las contraseñas no coinciden.")

    return generar_hash(primera)


def main():
    ruta_configurada = os.environ.get("NEGOCIO_DB_PATH")

    if not ruta_configurada:
        raise SystemExit("ERROR: NEGOCIO_DB_PATH no está configurada.")

    ruta = Path(ruta_configurada).resolve()

    if ruta != RUTA_ESPERADA or not ruta.is_file():
        raise SystemExit(
            "ERROR: solo se permite la base de pruebas existente."
        )

    crear_tabla_usuarios_pos()

    print("Creación de usuarios POS (solo pruebas)")
    hash_admin = pedir_contrasena("admin")
    hash_ventas = pedir_contrasena("ventas")

    conexion = obtener_conexion()

    try:
        conexion.execute("BEGIN IMMEDIATE")

        cantidad = conexion.execute(
            "SELECT COUNT(*) FROM usuarios_pos"
        ).fetchone()[0]

        if cantidad != 0:
            conexion.rollback()
            raise SystemExit(
                "Ya existen usuarios POS. No se modificó ninguna cuenta."
            )

        for usuario, rol, password_hash in (
            ("admin", "admin", hash_admin),
            ("ventas", "ventas", hash_ventas),
        ):
            conexion.execute(
                """
                INSERT INTO usuarios_pos
                    (usuario, rol, password_hash)
                VALUES (?, ?, ?)
                """,
                (usuario, rol, password_hash)
            )

        conexion.commit()
        print("Se crearon correctamente las cuentas admin y ventas.")

    except Exception:
        conexion.rollback()
        raise
    finally:
        conexion.close()


if __name__ == "__main__":
    main()
