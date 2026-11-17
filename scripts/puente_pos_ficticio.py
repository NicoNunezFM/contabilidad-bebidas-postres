"""Prepara, verifica o sirve el puente sobre SQLite ficticio."""
import argparse
import json
import os
import secrets
import sqlite3
import sys
from contextlib import closing, contextmanager
from pathlib import Path

from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pos_contabilidad import corte_contable, crear_integracion_contable
from pos_puente import leer_conciliacion
from pos_caja_diaria import caja_diaria_activa, crear_caja_diaria
from pos_simulacion import ID_SQLITE_SIMULACION, VERSION_ESQUEMA_SIMULACION


@contextmanager
def abrir_ficticia(ruta):
    if ruta.name.casefold() == "negocio.db":
        raise ValueError("Elegí un SQLite ficticio.")
    ruta = ruta.resolve(strict=True)
    if ruta.name.casefold() == "negocio.db" or not ruta.is_file():
        raise ValueError("Elegí un SQLite ficticio.")
    with closing(sqlite3.connect(ruta.as_uri() + "?mode=ro", uri=True)) as db:
        if (db.execute("PRAGMA application_id").fetchone()[0] != ID_SQLITE_SIMULACION
                or db.execute("PRAGMA user_version").fetchone()[0] != VERSION_ESQUEMA_SIMULACION):
            raise ValueError("Se requiere una base marcada como simulación POS 4.")
        yield db


def copiar_ficticia(origen, destino, *, caja_diaria=False, contabilidad=False):
    if destino.suffix.lower() != ".db" or destino.name.casefold() == "negocio.db":
        raise ValueError("Elegí un archivo .db nuevo de nombre distinto de negocio.db.")
    with abrir_ficticia(origen) as anterior:
        with destino.open("xb"):
            pass
        try:
            with closing(sqlite3.connect(destino)) as copia:
                anterior.backup(copia)
                with copia:
                    copia.execute("BEGIN IMMEDIATE")
                    if contabilidad:
                        if not caja_diaria_activa(copia) or corte_contable(copia):
                            raise ValueError("Para etapa 7, elegí una copia ficticia de etapa 6.")
                        crear_integracion_contable(copia)
                    elif caja_diaria_activa(copia):
                        raise ValueError("La fuente ya tiene el registro diario de etapa 6.")
                    if not contabilidad and not (caja_diaria and copia.execute("""
                        SELECT 1 FROM sqlite_schema WHERE name = 'pos_puente_ficticio' AND type = 'table'
                    """).fetchone()):
                        copia.execute("""
                            CREATE TABLE pos_puente_ficticio (version INTEGER PRIMARY KEY CHECK (version = 1))
                        """)
                        copia.execute("INSERT INTO pos_puente_ficticio VALUES (1)")
                    if caja_diaria:
                        crear_caja_diaria(copia)
                    if not leer_conciliacion(copia)["cuadrado"]:
                        raise ValueError("La copia tiene diferencias contables. Revisá la simulación de origen.")
        except BaseException:
            destino.unlink()
            raise


def verificar_ficticia(ruta):
    with abrir_ficticia(ruta) as db, db:
        db.execute("BEGIN")
        return leer_conciliacion(db)


def servidor_local(ruta, puerto):
    verificar_ficticia(ruta)
    ruta = ruta.resolve(strict=True)
    os.environ.update(
        NEGOCIO_DB_PATH=str(ruta),
        POS_V1_SIMULACION="1",
        ABADION_PUENTE_FICTICIO="1",
        PYTHON_DOTENV_DISABLED="1",
        ABADION_API_TOKEN=secrets.token_urlsafe(32),
        ABADION_BOT_TOKEN=secrets.token_urlsafe(32),
    )

    import uvicorn

    uvicorn.run("api:app", host="127.0.0.1", port=puerto, proxy_headers=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    comandos = parser.add_subparsers(dest="comando", required=True)
    copiar = comandos.add_parser("copiar", help="Crea y verifica una copia nueva de POS 4")
    copiar.add_argument("origen", type=Path)
    copiar.add_argument("destino", type=Path)
    modo = copiar.add_mutually_exclusive_group()
    modo.add_argument("--contabilidad", action="store_true", help="Habilita la etapa 7 desde una copia de etapa 6")
    modo.add_argument("--caja-diaria", action="store_true", help="Habilita la etapa 6 en la copia nueva")
    verificar = comandos.add_parser("conciliar", help="Emite el informe JSON en solo lectura")
    verificar.add_argument("ruta", type=Path)
    servir = comandos.add_parser("servir", help="Inicia la simulación en 127.0.0.1")
    servir.add_argument("ruta", type=Path)
    servir.add_argument("--puerto", type=int, choices=range(1, 65536), metavar="PUERTO", default=8000)
    args = parser.parse_args()

    try:
        if args.comando == "copiar":
            copiar_ficticia(args.origen, args.destino, caja_diaria=args.caja_diaria, contabilidad=args.contabilidad)
            print(f"Copia ficticia conciliada en {args.destino}")
        elif args.comando == "conciliar":
            informe = verificar_ficticia(args.ruta)
            print(json.dumps(informe, ensure_ascii=True, indent=2))
            return 0 if informe["cuadrado"] else 1
        else:
            servidor_local(args.ruta, args.puerto)
    except (OSError, sqlite3.Error, ValueError, HTTPException) as error:
        parser.error(error.detail if isinstance(error, HTTPException) else str(error))
    return 0


if __name__ == "__main__":
    sys.exit(main())
