"""Laboratorio HTTPS efímero con SQLite exclusivamente ficticio, sin importar bases."""
import argparse
from contextlib import closing
from getpass import getpass
from pathlib import Path
import ssl
import sys
from tempfile import TemporaryDirectory

import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pos_auth import generar_hash
from pos_entrenamiento_db import ARCHIVO_BASE, abrir_base_entrenamiento, bloquear_entrenamiento
from pos_tablet_laboratorio import crear_app_tablet, ipv4_local
from scripts.abadion_entrenamiento import Catalogo, construir_base


def preparar_laboratorio(carpeta, *, clave_ventas, clave_admin):
    """Solo directorios vacíos: sin lectura, copia o migración de bases instaladas."""
    if any(carpeta.iterdir()):
        raise ValueError("El laboratorio requiere un directorio vacío y nuevo.")
    if clave_ventas == clave_admin:
        raise ValueError("Usá contraseñas distintas para ventas y administración.")
    hashes = (generar_hash(clave_ventas), generar_hash(clave_admin))
    catalogo = Catalogo.model_validate({
        "aviso": "LABORATORIO FICTICIO - SIN VALIDEZ CONTABLE",
        "productos": [
            {"nombre": nombre, "categoria": categoria, "precio_centavos": precio,
             "controla_stock": True, "stock_inicial": 100, "adicionales": ["Extra ficticio"]}
            for nombre, categoria, precio in (
                ("Comida ficticia", "Comidas", 100_000),
                ("Bebida ficticia", "Bebidas", 20_000),
                ("Postre ficticio", "Postres", 30_000),
            )
        ],
        "adicionales": [{"nombre": "Extra ficticio", "precio_centavos": 10_000}],
    })
    ruta = carpeta / ARCHIVO_BASE
    nueva = carpeta / "nueva-ficticia.db"
    construir_base(nueva, catalogo)
    nueva.rename(ruta)
    with closing(abrir_base_entrenamiento(ruta)) as db, db:
        # Las credenciales públicas del entrenamiento nunca quedan utilizables por red.
        db.execute("DELETE FROM usuarios_pos")
        db.executemany("INSERT INTO usuarios_pos (usuario, rol, password_hash) VALUES (?, ?, ?)", (
            ("tablet-ventas", "ventas", hashes[0]), ("tablet-admin", "admin", hashes[1]),
        ))
        db.execute("CREATE TABLE pos_tablet_laboratorio (identidad TEXT PRIMARY KEY)")
        db.execute("INSERT INTO pos_tablet_laboratorio VALUES ('ficticio-efimero-v1')")
    return ruta


def configurar_tls(app, *, host, port, cert, key):
    # Validar el par antes de iniciar el servidor. No hay listener HTTP alternativo.
    contexto = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    contexto.minimum_version = ssl.TLSVersion.TLSv1_2
    contexto.load_cert_chain(cert, key)
    config = uvicorn.Config(app, host=host, port=port, proxy_headers=False,
                            server_header=False, access_log=False, ws="none",
                            ssl_certfile=str(cert), ssl_keyfile=str(key),
                            ssl_version=ssl.PROTOCOL_TLS_SERVER)
    config.load()
    config.ssl.minimum_version = ssl.TLSVersion.TLSv1_2
    return config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bind", default="127.0.0.1", type=ipv4_local)
    parser.add_argument("--allow", action="append", type=ipv4_local, default=[])
    parser.add_argument("--port", type=int, default=8460)
    parser.add_argument("--cert", required=True, type=Path, help="Certificado PEM con SAN del bind")
    parser.add_argument("--key", required=True, type=Path, help="Clave privada PEM local")
    args = parser.parse_args()
    if args.bind != "127.0.0.1" and not args.allow:
        parser.error("Para red privada indicá --allow con la IP observada del dispositivo.")
    try:
        clave_ventas = getpass("Contraseña nueva de tablet-ventas (mínimo 12 caracteres): ")
        clave_admin = getpass("Contraseña distinta de tablet-admin (mínimo 12 caracteres): ")
        with TemporaryDirectory(prefix="abadion-tablet-https-") as temporal:
            carpeta = Path(temporal).resolve()
            if any(parte.casefold().startswith("onedrive") for parte in carpeta.parts):
                raise ValueError("La carpeta temporal debe estar fuera de OneDrive.")
            preparar_laboratorio(carpeta, clave_ventas=clave_ventas, clave_admin=clave_admin)
            with bloquear_entrenamiento(carpeta):
                app = crear_app_tablet(carpeta, host=args.bind, port=args.port,
                                      clientes=args.allow or ["127.0.0.1"])
                config = configurar_tls(app, host=args.bind, port=args.port, cert=args.cert, key=args.key)
                print(f"LABORATORIO FICTICIO: https://{args.bind}:{args.port}/pos/?tablet=1")
                print("Base temporal nueva. Ctrl+C detiene y elimina las prácticas. Sin listener HTTP.")
                print("Verificá certificado confiable y SAN correcto en cada navegador; no omitas advertencias.")
                uvicorn.Server(config).run()
    except (OSError, ValueError, EOFError) as error:
        parser.exit(1, f"No se inició el laboratorio: {error}\n")


if __name__ == "__main__":
    main()
