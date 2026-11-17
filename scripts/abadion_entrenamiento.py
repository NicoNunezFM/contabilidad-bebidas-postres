"""Prepara, sirve y reinicia el POS local de entrenamiento de Lo de Clau."""
import argparse
import json
import os
import secrets
import sqlite3
import sys
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

import uvicorn
from pydantic import BaseModel, ConfigDict, Field, model_validator

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from catalogo import CATALOGO_PRECIOS
from database import inicializar_base_de_datos, obtener_conexion
from pos_auth import generar_hash
from pos_caja_diaria import crear_caja_diaria
from pos_entrenamiento_db import (
    ARCHIVO_BASE, IDENTIDAD, abrir_base_entrenamiento, bloquear_entrenamiento,
    carpeta_local, comprobar_archivo,
)
from pos_entrenamiento_web import crear_app_entrenamiento
from pos_simulacion import crear_esquema_simulacion


ARCHIVO_CATALOGO = "catalogo-entrenamiento.json"
CONFIRMACION = "REINICIAR ENTRENAMIENTO"
USUARIOS = (
    ("ventas-prueba", "ventas", "Ventas-Prueba-8060"),
    ("admin-prueba", "admin", "Admin-Prueba-8060"),
)


class FilaCatalogo(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    nombre: str = Field(min_length=1, max_length=120)
    precio_centavos: int = Field(strict=True, ge=0, le=10_000_000_000)


class Producto(FilaCatalogo):
    categoria: str = Field(min_length=1, max_length=60)
    precio_centavos: int = Field(strict=True, gt=0, le=10_000_000_000)
    controla_stock: bool = Field(strict=True)
    stock_inicial: int = Field(strict=True, ge=0, le=100_000)
    adicionales: list[str] = Field(default_factory=list, max_length=30)


class Catalogo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    aviso: str
    productos: list[Producto] = Field(min_length=1, max_length=1000)
    adicionales: list[FilaCatalogo] = Field(max_length=100)

    @model_validator(mode="after")
    def validar_nombres(self):
        for filas in (self.productos, self.adicionales):
            if len({fila.nombre.casefold() for fila in filas}) != len(filas):
                raise ValueError("Hay nombres de catálogo duplicados.")
        adicionales = {fila.nombre for fila in self.adicionales}
        for item in self.productos:
            if not set(item.adicionales) <= adicionales or len(set(item.adicionales)) != len(item.adicionales):
                raise ValueError(f"Revisá los adicionales de {item.nombre}.")
        return self


def catalogo_inicial():
    ejemplo = "Extra de práctica (ejemplo)"
    return {
        "aviso": "Precios de referencia del repositorio, sin vigencia confirmada. Stock y extra de ejemplo ficticios.",
        "productos": [
            {
                "nombre": item["nombre"],
                "categoria": item["categoria"],
                "precio_centavos": item["precio"] * 100,
                "controla_stock": item["controla_stock"],
                "stock_inicial": 24 if item["controla_stock"] else 0,
                "adicionales": [ejemplo] if item["nombre"] == "Clasica simple" else [],
            }
            for item in CATALOGO_PRECIOS
        ],
        "adicionales": [{"nombre": ejemplo, "precio_centavos": 50000}],
    }


def cargar_catalogo(db, catalogo):
    db.execute("DELETE FROM adicionales_catalogo")
    ids_adicionales = {}
    for adicional in catalogo.adicionales:
        cursor = db.execute(
            "INSERT INTO adicionales_catalogo (nombre, precio_venta) VALUES (?, ?)",
            (adicional.nombre, adicional.precio_centavos / 100),
        )
        ids_adicionales[adicional.nombre] = cursor.lastrowid
    for producto in catalogo.productos:
        cursor = db.execute("""
            INSERT INTO productos (nombre, categoria, precio_venta, controla_stock, stock)
            VALUES (?, ?, ?, ?, ?)
        """, (producto.nombre, producto.categoria, producto.precio_centavos / 100,
              producto.controla_stock, producto.stock_inicial))
        db.executemany("""
            INSERT INTO pos_adicionales_producto (id_producto, id_adicional_catalogo)
            VALUES (?, ?)
        """, [(cursor.lastrowid, ids_adicionales[nombre]) for nombre in producto.adicionales])


def construir_base(ruta, catalogo):
    # El inicializador compartido siempre recibe un archivo privado, nuevo y temporal.
    with ruta.open("xb"):
        pass
    clave = "NEGOCIO_DB_PATH"
    anterior = os.environ.get(clave)
    os.environ[clave] = str(ruta)
    try:
        inicializar_base_de_datos()
        with closing(obtener_conexion()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            crear_esquema_simulacion(db)
            db.execute("CREATE TABLE pos_puente_ficticio (version INTEGER PRIMARY KEY CHECK (version = 1))")
            db.execute("INSERT INTO pos_puente_ficticio VALUES (1)")
            crear_caja_diaria(db)
            db.execute("CREATE TABLE pos_entrenamiento (identidad TEXT PRIMARY KEY NOT NULL)")
            db.execute("INSERT INTO pos_entrenamiento VALUES (?)", (IDENTIDAD,))
            # Las solicitudes que queden en pestañas viejas están asociadas al usuario de la base anterior.
            primer_id = secrets.randbelow(2**48) + 1
            db.executemany("""
                INSERT INTO usuarios_pos (id_usuario, usuario, rol, password_hash) VALUES (?, ?, ?, ?)
            """, [(primer_id + indice, nombre, rol, generar_hash(contrasena))
                  for indice, (nombre, rol, contrasena) in enumerate(USUARIOS)])
            cargar_catalogo(db, catalogo)
    finally:
        if anterior is None:
            os.environ.pop(clave, None)
        else:
            os.environ[clave] = anterior


def preparar_base(carpeta, *, confirmacion=None):
    reinicio = confirmacion is not None
    if reinicio and confirmacion != CONFIRMACION:
        raise ValueError(f"Para reiniciar escribí {CONFIRMACION}.")
    with bloquear_entrenamiento(carpeta):
        destino = carpeta / ARCHIVO_BASE
        comprobar_archivo(destino)
        if reinicio:
            with closing(abrir_base_entrenamiento(destino, solo_lectura=True)):
                pass
        elif destino.exists():
            raise FileExistsError(f"La base ya existe en {destino}. Usá servir o reiniciar.")
        plantilla = carpeta / ARCHIVO_CATALOGO
        comprobar_archivo(plantilla)
        if not plantilla.exists() and not reinicio:
            with plantilla.open("x", encoding="utf-8") as archivo:
                json.dump(catalogo_inicial(), archivo, ensure_ascii=False, indent=2)
                archivo.write("\n")
        catalogo = Catalogo.model_validate_json(plantilla.read_text(encoding="utf-8-sig"))
        with TemporaryDirectory(prefix="preparacion-", dir=carpeta) as temporal:
            nueva = Path(temporal) / "nueva.db"
            construir_base(nueva, catalogo)
            if reinicio:
                os.replace(nueva, destino)
            elif os.name == "nt":
                nueva.rename(destino)
            else:
                os.link(nueva, destino)
        return destino


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    comandos = parser.add_subparsers(dest="comando", required=True)
    comandos.add_parser("preparar", help="Crear la base y el catálogo inicial")
    comandos.add_parser("servir", help="Abrir el POS en http://127.0.0.1:8060/pos/")
    comandos.add_parser("reiniciar", help="Borrar las prácticas y recargar el catálogo JSON")
    args = parser.parse_args()
    try:
        carpeta = carpeta_local()
        if args.comando == "servir":
            with bloquear_entrenamiento(carpeta):
                app = crear_app_entrenamiento(carpeta)
                uvicorn.run(app, host="127.0.0.1", port=8060, proxy_headers=False)
            return
        confirmacion = None
        if args.comando == "reiniciar":
            print(f"Se borrarán las prácticas en {carpeta / ARCHIVO_BASE}. Se recargará el catálogo JSON.")
            confirmacion = input(f"Escribí {CONFIRMACION} para continuar: ")
        print(f"Base de entrenamiento lista en {preparar_base(carpeta, confirmacion=confirmacion)}")
    except (OSError, ValueError, sqlite3.Error, EOFError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
