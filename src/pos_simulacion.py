import json
import os
from collections import Counter
from contextlib import contextmanager
from typing import Literal
from uuid import UUID

from fastapi import HTTPException
from pydantic import Field

from caja import CATEGORIAS_CAJA_BEBIDAS_POSTRES
from database import obtener_conexion, obtener_ruta_base
from pos_pedidos import PedidoPos, calcular_pedido_pos


ID_SQLITE_SIMULACION = 0x41425031


class VentaSimuladaEntrada(PedidoPos):
    id_solicitud: UUID
    total_esperado_centavos: int = Field(strict=True, gt=0, le=310_000_000_000_000_000)
    medio_pago: Literal["efectivo", "transferencia", "mercado_pago"]


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
    conexion.execute(f"PRAGMA application_id = {ID_SQLITE_SIMULACION}")


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
            SELECT id_venta, solicitud, pedido FROM pos_ventas_simuladas
            WHERE id_usuario = ? AND id_solicitud = ?
            """,
            clave,
        ).fetchone()
        if existente is not None:
            id_venta, solicitud_guardada, pedido_guardado = existente
            if solicitud_guardada != solicitud:
                raise HTTPException(409, "La solicitud ya corresponde a otra venta.")
            return {"id_venta": id_venta, **json.loads(pedido_guardado)}

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
        return {"id_venta": id_venta, **pedido}


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
