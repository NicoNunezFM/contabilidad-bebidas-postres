"""Sirve una práctica local del POS con una base SQLite nueva y temporal."""
import argparse
from pathlib import Path
from tempfile import TemporaryDirectory

import uvicorn

from abadion_entrenamiento import bloquear_entrenamiento, crear_app_entrenamiento, preparar_base


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--puerto", type=int, default=8076)
    args = parser.parse_args()
    if not 1024 <= args.puerto <= 65535:
        parser.error("El puerto debe estar entre 1024 y 65535.")
    with TemporaryDirectory(prefix="abadion-pos-edge-") as temporal:
        carpeta = Path(temporal)
        preparar_base(carpeta)
        with bloquear_entrenamiento(carpeta):
            app = crear_app_entrenamiento(carpeta)
            uvicorn.run(app, host="127.0.0.1", port=args.puerto, proxy_headers=False)


if __name__ == "__main__":
    main()
