import json
import os
from collections import Counter
from contextlib import contextmanager
from typing import Literal
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field

from caja import CATEGORIAS_CAJA_BEBIDAS_POSTRES
from database import obtener_conexion, obtener_ruta_base
from pos_pedidos import PedidoPos, calcular_pedido_pos


ID_SQLITE_SIMULACION = 0x41425031
VERSION_ESQUEMA_SIMULACION = 3


class VentaSimuladaEntrada(PedidoPos):
    id_solicitud: UUID
    total_esperado_centavos: int = Field(strict=True, gt=0, le=310_000_000_000_000_000)
    medio_pago: Literal["efectivo", "transferencia", "mercado_pago"]


class AnulacionSimuladaEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    motivo: str = Field(min_length=1, max_length=300)


def crear_esquema_simulacion(conexion):
    """Invocado exclusivamente al preparar una base nueva de pruebas."""
    conexion.execute("""
        CREATE TABLE pos_ventas_simuladas (
            id_venta INTEGER PRIMARY KEY,
            id_usuario INTEGER NOT NULL REFERENCES usuarios_pos (id_usuario),
            id_solicitud TEXT NOT NULL,
            solicitud TEXT NOT NULL,
            fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            pedido TEXT NOT NULL,
            UNIQUE (id_usuario, id_solicitud)
        )
    """)
    conexion.execute("""
        CREATE TABLE pos_movimientos_simulados (
            id_venta INTEGER NOT NULL REFERENCES pos_ventas_simuladas (id_venta),
            caja TEXT NOT NULL CHECK (caja IN ('bebidas_postres', 'comidas')),
            medio_pago TEXT NOT NULL CHECK (medio_pago IN ('efectivo', 'transferencia', 'mercado_pago')),
            tipo TEXT NOT NULL CHECK (tipo IN ('venta', 'anulacion')),
            importe_centavos INTEGER NOT NULL CHECK (
                (tipo = 'venta' AND importe_centavos > 0) OR
                (tipo = 'anulacion' AND importe_centavos < 0)
            ),
            PRIMARY KEY (id_venta, caja, tipo)
        )
    """)
    conexion.execute("""
        CREATE TABLE pos_anulaciones_simuladas (
            id_venta INTEGER PRIMARY KEY REFERENCES pos_ventas_simuladas (id_venta),
            id_usuario INTEGER NOT NULL REFERENCES usuarios_pos (id_usuario),
            motivo TEXT NOT NULL,
            fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conexion.execute(f"PRAGMA application_id = {ID_SQLITE_SIMULACION}")
    conexion.execute(f"PRAGMA user_version = {VERSION_ESQUEMA_SIMULACION}")


@contextmanager
def transaccion_simulacion(*, escritura=False):
    ruta = obtener_ruta_base()
    if (
        os.getenv("POS_V1_SIMULACION") != "1"
        or not os.getenv("NEGOCIO_DB_PATH")
        or ruta.resolve().name.casefold() == "negocio.db"
        or not ruta.is_file()
    ):
        raise HTTPException(404, "Simulación POS deshabilitada.")

    conexion = obtener_conexion()
    try:
        if conexion.execute("PRAGMA application_id").fetchone()[0] != ID_SQLITE_SIMULACION:
            raise HTTPException(404, "Simulación POS deshabilitada.")
        if conexion.execute("PRAGMA user_version").fetchone()[0] != VERSION_ESQUEMA_SIMULACION:
            raise HTTPException(409, "Prepará una base nueva para esta versión de la simulación POS.")
        if not escritura:
            conexion.execute("PRAGMA query_only = ON")
        with conexion:
            conexion.execute("BEGIN IMMEDIATE" if escritura else "BEGIN")
            yield conexion
    finally:
        conexion.close()


def cantidades_descontadas(pedido):
    cantidades = Counter()
    for item in pedido["items"]:
        if item["controla_stock"]:
            cantidades[item["id_producto"]] += item["cantidad"]
    return cantidades


def registrar_venta_simulada(entrada, usuario):
    solicitud = entrada.model_dump_json(exclude={"id_solicitud"})
    clave = (usuario["id_usuario"], str(entrada.id_solicitud))
    with transaccion_simulacion(escritura=True) as conexion:
        existente = conexion.execute(
            """
            SELECT v.id_venta, v.solicitud, v.pedido, a.id_venta IS NOT NULL
            FROM pos_ventas_simuladas AS v
            LEFT JOIN pos_anulaciones_simuladas AS a USING (id_venta)
            WHERE v.id_usuario = ? AND v.id_solicitud = ?
            """,
            clave,
        ).fetchone()
        if existente is not None:
            id_venta, solicitud_guardada, pedido_guardado, anulada = existente
            if solicitud_guardada != solicitud:
                raise HTTPException(409, "La solicitud ya corresponde a otra venta.")
            return {"id_venta": id_venta, "anulada": bool(anulada), **json.loads(pedido_guardado)}

        pedido = calcular_pedido_pos(conexion, entrada)
        if pedido["total_centavos"] != entrada.total_esperado_centavos:
            raise HTTPException(409, {
                "codigo": "TOTAL_MODIFICADO",
                "mensaje": "Cambió el total. Volvé a validar el pedido.",
                "total_centavos": pedido["total_centavos"],
            })

        subtotales = Counter()
        for item in pedido["items"]:
            categoria = item["categoria"].strip().lower()
            caja = "bebidas_postres" if categoria in CATEGORIAS_CAJA_BEBIDAS_POSTRES else "comidas"
            subtotales[caja] += item["subtotal_centavos"]
        pedido["medio_pago"] = entrada.medio_pago
        pedido["cajas_centavos"] = dict(subtotales)

        cursor = conexion.execute(
            "INSERT INTO pos_ventas_simuladas (id_usuario, id_solicitud, solicitud, pedido) VALUES (?, ?, ?, ?)",
            (*clave, solicitud, json.dumps(pedido, ensure_ascii=False)),
        )
        id_venta = cursor.lastrowid
        conexion.executemany(
            """
            INSERT INTO pos_movimientos_simulados (id_venta, caja, medio_pago, tipo, importe_centavos)
            VALUES (?, ?, ?, 'venta', ?)
            """,
            [(id_venta, caja, entrada.medio_pago, subtotal) for caja, subtotal in subtotales.items()],
        )
        conexion.executemany(
            "UPDATE productos SET stock = stock - ? WHERE id_producto = ?",
            [(cantidad, id_producto) for id_producto, cantidad in cantidades_descontadas(pedido).items()],
        )
        return {"id_venta": id_venta, "anulada": False, **pedido}


def anular_venta_simulada(id_venta, motivo, usuario):
    with transaccion_simulacion(escritura=True) as conexion:
        venta = conexion.execute(
            """
            SELECT v.pedido, a.id_venta IS NOT NULL
            FROM pos_ventas_simuladas AS v
            LEFT JOIN pos_anulaciones_simuladas AS a USING (id_venta)
            WHERE v.id_venta = ?
            """, (id_venta,),
        ).fetchone()
        if venta is None:
            raise HTTPException(404, "Venta simulada no encontrada.")
        pedido, anulada = venta
        if anulada:
            raise HTTPException(409, "La venta simulada ya está anulada.")

        cantidades = cantidades_descontadas(json.loads(pedido))
        cursor = conexion.executemany(
            "UPDATE productos SET stock = stock + ? WHERE id_producto = ?",
            [(cantidad, id_producto) for id_producto, cantidad in cantidades.items()],
        )
        if cursor.rowcount != len(cantidades):
            raise HTTPException(409, "Falta un producto cuyo stock debe restaurarse.")

        conexion.execute(
            "INSERT INTO pos_anulaciones_simuladas (id_venta, id_usuario, motivo) VALUES (?, ?, ?)",
            (id_venta, usuario["id_usuario"], motivo),
        )
        conexion.execute(
            """
            INSERT INTO pos_movimientos_simulados (id_venta, caja, medio_pago, tipo, importe_centavos)
            SELECT id_venta, caja, medio_pago, 'anulacion', -importe_centavos
            FROM pos_movimientos_simulados WHERE id_venta = ? AND tipo = 'venta'
            """, (id_venta,),
        )
    return {"id_venta": id_venta, "anulada": True}


def consultar_historial_simulado(usuario, antes_de, limite):
    id_usuario = None if usuario["rol"] == "admin" else usuario["id_usuario"]
    with transaccion_simulacion() as conexion:
        filas = conexion.execute(
            """
            SELECT v.id_venta, v.fecha, v.id_usuario, v.pedido, a.id_usuario, a.fecha, a.motivo
            FROM pos_ventas_simuladas AS v
            LEFT JOIN pos_anulaciones_simuladas AS a USING (id_venta)
            WHERE (:antes_de IS NULL OR v.id_venta < :antes_de)
              AND (:id_usuario IS NULL OR v.id_usuario = :id_usuario)
            ORDER BY v.id_venta DESC
            LIMIT :limite
            """, {"antes_de": antes_de, "id_usuario": id_usuario, "limite": limite + 1},
        ).fetchall()

    ventas = [
        {
            "id_venta": id_venta,
            "fecha": fecha,
            "id_usuario": autor,
            "anulada": anulador is not None,
            "anulacion": {"id_usuario": anulador, "fecha": fecha_anulacion, "motivo": motivo} if anulador else None,
            **json.loads(pedido),
        }
        for id_venta, fecha, autor, pedido, anulador, fecha_anulacion, motivo in filas[:limite]
    ]
    return {"ventas": ventas, "siguiente_antes_de": ventas[-1]["id_venta"] if len(filas) > limite else None}


def consultar_cajas_simuladas():
    with transaccion_simulacion() as conexion:
        filas = conexion.execute("""
            SELECT caja, medio_pago, SUM(importe_centavos)
            FROM pos_movimientos_simulados
            GROUP BY caja, medio_pago
            ORDER BY caja, medio_pago
        """).fetchall()
    return [
        {"caja": caja, "medio_pago": medio, "saldo_centavos": saldo}
        for caja, medio, saldo in filas
    ]
