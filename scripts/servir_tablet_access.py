"""Inicia el POS ficticio en loopback para Cloudflare Access administrado."""
import argparse
from getpass import getpass
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pos_entrenamiento_db import bloquear_entrenamiento
from pos_tablet_access import VerificadorAccess, crear_app_remota
from scripts.servir_tablet_https import preparar_laboratorio


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True, help="Hostname público de la aplicación Access")
    parser.add_argument("--equipo", required=True, help="Nombre de equipo en cloudflareaccess.com")
    parser.add_argument("--audiencia", required=True, help="AUD de la aplicación Access")
    parser.add_argument("--port", type=int, default=8461)
    args = parser.parse_args()
    try:
        verificador = VerificadorAccess(
            equipo=args.equipo, audiencia=args.audiencia,
            correo=input("Correo individual autorizado por Access: ").strip(),
        )
        clave_ventas = getpass("Contraseña nueva de tablet-ventas (mínimo 12 caracteres): ")
        clave_admin = getpass("Contraseña distinta de tablet-admin (mínimo 12 caracteres): ")
        with TemporaryDirectory(prefix="abadion-tablet-access-") as temporal:
            carpeta = Path(temporal).resolve()
            if any(parte.casefold().startswith("onedrive") for parte in carpeta.parts):
                raise ValueError("La carpeta temporal debe estar fuera de OneDrive.")
            preparar_laboratorio(carpeta, clave_ventas=clave_ventas, clave_admin=clave_admin)
            with bloquear_entrenamiento(carpeta):
                app = crear_app_remota(carpeta, host=args.host, port=args.port, verificador=verificador)
                config = uvicorn.Config(
                    app, host="127.0.0.1", port=args.port, proxy_headers=False,
                    server_header=False, access_log=False, ws="none",
                )
                print(f"LABORATORIO FICTICIO: https://{args.host}/pos/?tablet=1")
                uvicorn.Server(config).run()
    except (ValueError, OSError, EOFError) as error:
        parser.exit(1, f"No se inició el laboratorio: {error}\n")


if __name__ == "__main__":
    main()
