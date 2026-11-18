"""Administra el POS local de entrenamiento de Lo de Clau."""
import argparse
import os
import secrets
import sqlite3
import sys
from contextlib import closing
from pathlib import Path
from datetime import datetime
from tempfile import TemporaryDirectory

import uvicorn
from pydantic import BaseModel, ConfigDict, Field, model_validator

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from database import inicializar_base_de_datos, obtener_conexion
from pos_auth import generar_hash
from pos_caja_diaria import crear_caja_diaria, caja_diaria_activa
from pos_contabilidad import crear_integracion_contable, corte_contable
from pos_entrenamiento_db import (
    ARCHIVO_BASE, DESCUENTO_POSTRE_CENTAVOS, IDENTIDAD, abrir_base_entrenamiento, bloquear_entrenamiento,
    carpeta_local, comprobar_archivo,
)
from pos_entrenamiento_web import crear_app_entrenamiento
from pos_simulacion import crear_esquema_simulacion


ARCHIVO_CATALOGO = "catalogo-entrenamiento.json"
PLANTILLA_CATALOGO = Path(__file__).with_name(ARCHIVO_CATALOGO)
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
    precio_centavos: int | None = Field(strict=True, gt=0, le=10_000_000_000)
    controla_stock: bool = Field(strict=True)
    stock_inicial: int = Field(strict=True, ge=0, le=100_000)
    adicionales: list[str] = Field(default_factory=list, max_length=30)
    sin_stock: bool = Field(default=False, strict=True)
    promo_postres_chicos: bool = Field(default=False, strict=True)

    @model_validator(mode="after")
    def validar_promocion(self):
        if self.promo_postres_chicos and (
            self.categoria != "Postres" or (self.precio_centavos or 0) <= DESCUENTO_POSTRE_CENTAVOS
        ):
            raise ValueError(f"Revisá la categoría o el precio promocionable de {self.nombre}.")
        return self


# Nombres de la primera versión del catálogo que conservan el ID al actualizarse.
NOMBRES_ANTERIORES = {"chocotorta": "chocotorta grande", "oreo": "oreo grande",
                     "clasica simple": "clásica simple", "clasica doble": "clásica doble"}
NOMBRES_ANTERIORES.update({
    f"{plato} de {carne} con pure": f"{plato} de {carne} con puré"
    for plato in ("milanesa", "napo") for carne in ("pollo", "carne")
})


def clave_producto(nombre):
    clave = nombre.casefold()
    return NOMBRES_ANTERIORES.get(clave, clave)


class Catalogo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    aviso: str
    productos: list[Producto] = Field(min_length=1, max_length=1000)
    adicionales: list[FilaCatalogo] = Field(max_length=100)
    combinar_sabores_promo: bool = Field(default=False, strict=True)

    @model_validator(mode="after")
    def validar_nombres(self):
        if (len({clave_producto(fila.nombre) for fila in self.productos}) != len(self.productos)
                or len({fila.nombre.casefold() for fila in self.adicionales}) != len(self.adicionales)):
            raise ValueError("Hay nombres de catálogo duplicados.")
        adicionales = {fila.nombre for fila in self.adicionales}
        for item in self.productos:
            if not set(item.adicionales) <= adicionales or len(set(item.adicionales)) != len(item.adicionales):
                raise ValueError(f"Revisá los adicionales de {item.nombre}.")
        return self


def cargar_catalogo(db, catalogo):
    db.execute("""
        CREATE TABLE IF NOT EXISTS pos_catalogo_entrenamiento (
            id_producto INTEGER PRIMARY KEY REFERENCES productos(id_producto),
            estado TEXT NOT NULL CHECK (estado IN ('disponible', 'sin_stock', 'fuera_menu')),
            grupo_promo TEXT
        )
    """)
    estados_anteriores = dict(db.execute("SELECT id_producto, estado FROM pos_catalogo_entrenamiento"))
    db.execute("""
        INSERT INTO pos_catalogo_entrenamiento (id_producto, estado)
        SELECT id_producto, 'fuera_menu' FROM productos WHERE 1
        ON CONFLICT(id_producto) DO UPDATE SET estado = excluded.estado, grupo_promo = NULL
    """)
    db.execute("UPDATE adicionales_catalogo SET activo = 0")
    ids_adicionales = {}
    for adicional in catalogo.adicionales:
        ids_adicionales[adicional.nombre] = db.execute("""
            INSERT INTO adicionales_catalogo (nombre, precio_venta) VALUES (?, ?)
            ON CONFLICT(nombre) DO UPDATE SET precio_venta = excluded.precio_venta, activo = 1
            RETURNING id_adicional_catalogo
        """, (adicional.nombre, adicional.precio_centavos / 100)).fetchone()[0]

    ids_productos = {}
    for id_producto, nombre in db.execute("SELECT id_producto, nombre FROM productos"):
        ids_productos.setdefault(clave_producto(nombre), []).append(id_producto)
    for producto in catalogo.productos:
        precio = None if producto.precio_centavos is None else producto.precio_centavos / 100
        valores = (producto.nombre, producto.categoria, precio, producto.controla_stock)
        ids = ids_productos.get(clave_producto(producto.nombre), [])
        if len(ids) > 1:
            raise ValueError(f"Hay más de un producto existente para {producto.nombre}.")
        if ids:
            id_producto = ids[0]
            db.execute("""
                UPDATE productos SET nombre = ?, categoria = ?, precio_venta = ?, controla_stock = ?
                WHERE id_producto = ?
            """, (*valores, id_producto))
        else:
            id_producto = db.execute("""
                INSERT INTO productos (nombre, categoria, precio_venta, controla_stock, stock)
                VALUES (?, ?, ?, ?, ?)
            """, (*valores, producto.stock_inicial)).lastrowid

        grupo = None
        if producto.promo_postres_chicos:
            grupo = "todos" if catalogo.combinar_sabores_promo else str(id_producto)
        estado = "sin_stock" if producto.sin_stock or estados_anteriores.get(id_producto) == "sin_stock" else "disponible"
        db.execute("""
            INSERT INTO pos_catalogo_entrenamiento VALUES (?, ?, ?)
            ON CONFLICT(id_producto) DO UPDATE SET estado = excluded.estado, grupo_promo = excluded.grupo_promo
        """, (id_producto, estado, grupo))
        db.execute("DELETE FROM pos_adicionales_producto WHERE id_producto = ?", (id_producto,))
        db.executemany("""
            INSERT INTO pos_adicionales_producto (id_producto, id_adicional_catalogo)
            VALUES (?, ?)
        """, [(id_producto, ids_adicionales[nombre]) for nombre in producto.adicionales])


def leer_catalogo(plantilla):
    comprobar_archivo(plantilla)
    return Catalogo.model_validate_json(plantilla.read_text(encoding="utf-8-sig"))


def actualizar_catalogo(carpeta):
    with bloquear_entrenamiento(carpeta):
        catalogo = leer_catalogo(carpeta / ARCHIVO_CATALOGO)
        with closing(abrir_base_entrenamiento(carpeta / ARCHIVO_BASE)) as db, db:
            db.execute("PRAGMA foreign_keys = ON")
            db.execute("BEGIN IMMEDIATE")
            cargar_catalogo(db, catalogo)
    return len(catalogo.productos)


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
            crear_integracion_contable(db)
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
                archivo.write(PLANTILLA_CATALOGO.read_text(encoding="utf-8"))
        catalogo = leer_catalogo(plantilla)
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


def activar_contabilidad(carpeta):
    """Incorpora etapa 7 a una base de práctica existente sin borrar transacciones."""
    with bloquear_entrenamiento(carpeta):
        ruta = carpeta / ARCHIVO_BASE
        with closing(abrir_base_entrenamiento(ruta)) as db, db:
            db.execute("PRAGMA foreign_keys = ON")
            # Reserva la escritura antes del respaldo para preservar el mismo estado previo al corte.
            db.execute("BEGIN IMMEDIATE")
            if not caja_diaria_activa(db):
                raise ValueError("La base de entrenamiento no tiene caja diaria habilitada.")
            if corte_contable(db) is not None:
                return None
            nombre = f"abadion-entrenamiento.pre-etapa7-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}.db"
            respaldo = carpeta / nombre
            with respaldo.open("xb"):
                pass
            try:
                # SQLite necesita una conexión lectora separada para copiar durante la transacción.
                with closing(sqlite3.connect(ruta.as_uri() + "?mode=ro", uri=True)) as origen, closing(
                    sqlite3.connect(respaldo)
                ) as copia:
                    origen.backup(copia)
            except BaseException:
                respaldo.unlink(missing_ok=True)
                raise
            crear_integracion_contable(db)
            return respaldo


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    comandos = parser.add_subparsers(dest="comando", required=True)
    comandos.add_parser("preparar", help="Crear la base y el catálogo inicial")
    comandos.add_parser("servir", help="Abrir el POS en http://127.0.0.1:8060/pos/")
    comandos.add_parser("actualizar-catalogo", help="Aplicar el JSON local y conservar las prácticas")
    comandos.add_parser("activar-contabilidad", help="Activar etapa 7 conservando las prácticas anteriores")
    comandos.add_parser("reiniciar", help="Borrar las prácticas y recargar el catálogo JSON")
    args = parser.parse_args()
    try:
        carpeta = carpeta_local()
        if args.comando == "activar-contabilidad":
            respaldo = activar_contabilidad(carpeta)
            if respaldo is None:
                print("Contabilidad de entrenamiento ya activada. Se conservaron las prácticas.")
            else:
                print(f"Contabilidad activada desde el nuevo corte. Respaldo previo: {respaldo}")
            return
        if args.comando == "actualizar-catalogo":
            print(f"Catálogo aplicado: {actualizar_catalogo(carpeta)} productos. Se conservaron las prácticas.")
            return
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
