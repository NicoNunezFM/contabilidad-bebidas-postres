"""Libro contable del POS ficticio. El llamador aporta una transacción SQLite."""
import json
from typing import Annotated, Literal
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator


Seccion = Literal["comidas", "bebidas_postres"]
Medio = Literal["efectivo", "transferencia", "mercado_pago"]
Receptor = Literal[
    "comidas_efectivo", "comidas_banco", "comidas_mercado_pago",
    "bebidas_postres_efectivo", "bebidas_postres_banco", "bebidas_postres_mercado_pago",
]
Centavos = Annotated[int, Field(strict=True, gt=0, le=310_000_000_000_000_000)]
SECCIONES = ("comidas", "bebidas_postres")


class PagoPos(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    receptor: Receptor
    medio_pago: Medio
    importe_centavos: Centavos
    referencia: str | None = Field(default=None, min_length=1, max_length=120)

    @model_validator(mode="after")
    def comprobar_receptor(self):
        if self.receptor.endswith("_efectivo") != (self.medio_pago == "efectivo"):
            raise ValueError("El efectivo requiere una caja y el pago digital una cuenta.")
        return self


class SolicitudContable(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id_solicitud: UUID


class AbonoEntrada(SolicitudContable):
    pagos: list[PagoPos] = Field(min_length=1, max_length=20)


class ReversionEntrada(SolicitudContable):
    motivo: str = Field(min_length=1, max_length=300)


class LineaDevuelta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    linea: int = Field(strict=True, ge=1, le=100)
    cantidad: int = Field(strict=True, ge=1, le=10_000)


class DevolucionEntrada(ReversionEntrada):
    items: list[LineaDevuelta] = Field(min_length=1, max_length=100)


class TransferenciaEntrada(ReversionEntrada):
    origen: Receptor
    destino: Receptor
    importe_centavos: Centavos


class CierreEntrada(ReversionEntrada):
    periodo: int = Field(strict=True, gt=0, le=2**63 - 1)


def crear_libro(conexion):
    # Se ejecuta dentro de la misma transacción que prepara la base ficticia.
    conexion.execute("""
        CREATE TABLE pos_eventos_simulados (
            id_evento INTEGER PRIMARY KEY,
            id_venta INTEGER REFERENCES pos_ventas_simuladas,
            id_usuario INTEGER NOT NULL REFERENCES usuarios_pos,
            id_solicitud TEXT UNIQUE,
            solicitud TEXT NOT NULL,
            tipo TEXT NOT NULL CHECK (tipo IN ('venta', 'abono', 'anulacion', 'devolucion',
                                               'transferencia_interna', 'cierre')),
            periodo INTEGER NOT NULL CHECK (periodo > 0),
            fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            devengado_comidas INTEGER NOT NULL DEFAULT 0,
            devengado_bebidas INTEGER NOT NULL DEFAULT 0,
            cobrado_comidas INTEGER NOT NULL DEFAULT 0,
            cobrado_bebidas INTEGER NOT NULL DEFAULT 0,
            resultado TEXT,
            CHECK ((id_venta IS NULL) = (tipo IN ('transferencia_interna', 'cierre')))
        )
    """)
    conexion.execute("""
        CREATE TABLE pos_movimientos_simulados (
            id_movimiento INTEGER PRIMARY KEY,
            id_evento INTEGER NOT NULL REFERENCES pos_eventos_simulados,
            id_venta INTEGER REFERENCES pos_ventas_simuladas,
            receptor TEXT NOT NULL,
            caja TEXT NOT NULL CHECK (caja IN ('bebidas_postres', 'comidas')),
            medio_pago TEXT CHECK (medio_pago IN ('efectivo', 'transferencia', 'mercado_pago')),
            importe_centavos INTEGER NOT NULL CHECK (importe_centavos <> 0),
            referencia TEXT,
            revierte INTEGER REFERENCES pos_movimientos_simulados
        )
    """)
    conexion.execute("""
        CREATE UNIQUE INDEX pos_referencias_pago ON pos_movimientos_simulados (receptor, referencia)
        WHERE referencia IS NOT NULL
    """)
    conexion.execute("CREATE INDEX pos_eventos_por_venta ON pos_eventos_simulados (id_venta)")
    conexion.execute("CREATE INDEX pos_movimientos_por_venta ON pos_movimientos_simulados (id_venta)")
    conexion.execute("CREATE INDEX pos_movimientos_por_caja ON pos_movimientos_simulados (caja, id_movimiento)")
    conexion.execute("CREATE INDEX pos_movimientos_reversion ON pos_movimientos_simulados (revierte)")
    conexion.execute("""
        CREATE TABLE pos_unidades_devueltas (
            id_evento INTEGER NOT NULL REFERENCES pos_eventos_simulados,
            linea INTEGER NOT NULL,
            cantidad INTEGER NOT NULL CHECK (cantidad > 0),
            PRIMARY KEY (id_evento, linea)
        )
    """)
    conexion.execute("""
        CREATE TABLE pos_cierres_simulados (
            periodo INTEGER PRIMARY KEY,
            id_evento INTEGER NOT NULL UNIQUE REFERENCES pos_eventos_simulados,
            resumen TEXT NOT NULL
        )
    """)


def caja_receptora(receptor):
    return "comidas" if receptor.startswith("comidas_") else "bebidas_postres"


def receptor_original(caja, medio):
    return f"{caja}_{'banco' if medio == 'transferencia' else medio}"


def imputar(devengado, cobrado):
    total = sum(devengado.values())
    comidas = cobrado * devengado.get("comidas", 0) // total if total else 0
    return {"comidas": comidas, "bebidas_postres": cobrado - comidas}


def periodo_abierto(conexion):
    return conexion.execute("SELECT COALESCE(MAX(periodo), 0) + 1 FROM pos_cierres_simulados").fetchone()[0]


def iniciar_evento(conexion, tipo, usuario, entrada, id_venta=None, *, usar_uuid=True):
    solicitud = entrada.model_dump_json(exclude={"id_solicitud"})
    clave = str(entrada.id_solicitud) if usar_uuid and entrada.id_solicitud else None
    autor = usuario["id_usuario"]
    if clave:
        previo = conexion.execute("""
            SELECT tipo, id_usuario, id_venta, solicitud, resultado
            FROM pos_eventos_simulados WHERE id_solicitud = ?
        """, (clave,)).fetchone()
        if previo:
            if previo[:4] != (tipo, autor, id_venta, solicitud):
                raise HTTPException(409, "La solicitud ya corresponde a otra operación.")
            return None, json.loads(previo[4])

    cursor = conexion.execute("""
        INSERT INTO pos_eventos_simulados (tipo, id_usuario, id_venta, id_solicitud, solicitud, periodo)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (tipo, autor, id_venta, clave, solicitud, periodo_abierto(conexion)))
    return cursor.lastrowid, None


def terminar_evento(conexion, id_evento, resultado, *, antes=None, despues=None):
    antes, despues = antes or {}, despues or {}
    deltas = [
        despues.get(clave, {}).get(seccion, 0) - antes.get(clave, {}).get(seccion, 0)
        for clave in ("devengado_centavos", "cobrado_atribuido_centavos") for seccion in SECCIONES
    ]
    conexion.execute("""
        UPDATE pos_eventos_simulados
        SET resultado = ?, devengado_comidas = ?, devengado_bebidas = ?,
            cobrado_comidas = ?, cobrado_bebidas = ?
        WHERE id_evento = ?
    """, (json.dumps(resultado, ensure_ascii=False), *deltas, id_evento))
    return resultado


def registrar_movimiento(conexion, evento, venta, receptor, medio, importe, *, referencia=None, revierte=None):
    conexion.execute("""
        INSERT INTO pos_movimientos_simulados
            (id_evento, id_venta, receptor, caja, medio_pago, importe_centavos, referencia, revierte)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (evento, venta, receptor, caja_receptora(receptor), medio, importe, referencia, revierte))


def registrar_pagos(conexion, evento, venta, pagos):
    for pago in pagos:
        if pago.referencia and conexion.execute("""
            SELECT 1 FROM pos_movimientos_simulados WHERE receptor = ? AND referencia = ?
        """, (pago.receptor, pago.referencia)).fetchone():
            raise HTTPException(409, "La referencia ya fue registrada en esa cuenta.")
        registrar_movimiento(conexion, evento, venta, pago.receptor, pago.medio_pago,
                             pago.importe_centavos, referencia=pago.referencia)


def pagos_reversibles(conexion, id_venta):
    return conexion.execute("""
        SELECT m.id_movimiento, m.receptor, m.medio_pago,
               m.importe_centavos + COALESCE(SUM(r.importe_centavos), 0) AS disponible
        FROM pos_movimientos_simulados AS m
        LEFT JOIN pos_movimientos_simulados AS r ON r.revierte = m.id_movimiento
        WHERE m.id_venta = ? AND m.importe_centavos > 0
        GROUP BY m.id_movimiento HAVING disponible > 0
        ORDER BY m.id_movimiento DESC
    """, (id_venta,)).fetchall()


def unidades_devueltas(conexion, id_venta):
    return dict(conexion.execute("""
        SELECT u.linea, SUM(u.cantidad)
        FROM pos_unidades_devueltas AS u JOIN pos_eventos_simulados AS e USING (id_evento)
        WHERE e.id_venta = ? GROUP BY u.linea
    """, (id_venta,)))


def estado_cuenta(conexion, venta, pedido, anulada=False):
    devengado = dict.fromkeys(SECCIONES, 0)
    devueltas = unidades_devueltas(conexion, venta)
    if not anulada:
        for linea, item in enumerate(pedido["items"], start=1):
            cantidad = item["cantidad"] - devueltas.get(linea, 0)
            devengado[item["seccion"]] += cantidad * item["precio_unitario_centavos"]

    cobrado = conexion.execute("""
        SELECT COALESCE(SUM(importe_centavos), 0)
        FROM pos_movimientos_simulados WHERE id_venta = ?
    """, (venta,)).fetchone()[0]
    atribuido = imputar(devengado, cobrado)
    total = sum(devengado.values())
    saldo = total - cobrado
    return {
        "importe_original_centavos": pedido["total_centavos"],
        "importe_vigente_centavos": total,
        "cobrado_centavos": cobrado,
        "saldo_pendiente_centavos": saldo,
        "estado": ("anulada" if anulada else "devuelta" if total == 0 else
                   "saldado" if saldo == 0 else "parcial" if cobrado else "pendiente"),
        "devengado_centavos": devengado,
        "cobrado_atribuido_centavos": atribuido,
        "pendiente_por_seccion_centavos": {caja: devengado[caja] - atribuido[caja] for caja in SECCIONES},
        "unidades_devueltas": devueltas,
    }


def resumen_libro(conexion):
    dev_comidas, dev_bebidas, cob_comidas, cob_bebidas = conexion.execute("""
        SELECT COALESCE(SUM(devengado_comidas), 0), COALESCE(SUM(devengado_bebidas), 0),
               COALESCE(SUM(cobrado_comidas), 0), COALESCE(SUM(cobrado_bebidas), 0)
        FROM pos_eventos_simulados
    """).fetchone()
    saldos = conexion.execute("""
        SELECT caja, receptor, SUM(importe_centavos),
               SUM(CASE WHEN medio_pago IS NOT NULL THEN importe_centavos ELSE 0 END)
        FROM pos_movimientos_simulados
        GROUP BY caja, receptor ORDER BY caja, receptor
    """).fetchall()
    secciones = {}
    for caja, devengado, cobrado in zip(SECCIONES, (dev_comidas, dev_bebidas), (cob_comidas, cob_bebidas)):
        disponible = sum(saldo for seccion, _, saldo, _ in saldos if seccion == caja)
        recibido = sum(cobros for seccion, _, _, cobros in saldos if seccion == caja)
        secciones[caja] = {
            "devengado_centavos": devengado, "cobrado_atribuido_centavos": cobrado,
            "por_cobrar_centavos": devengado - cobrado, "disponible_centavos": disponible,
            "recibido_neto_centavos": recibido, "transferencia_neta_centavos": disponible - recibido,
            "por_distribuir_centavos": cobrado - disponible,
        }
    return {
        "periodo_abierto": periodo_abierto(conexion),
        "secciones": secciones,
        "receptores": [
            {"caja": caja, "receptor": receptor, "saldo_centavos": saldo,
             "recibido_neto_centavos": cobros, "transferencia_neta_centavos": saldo - cobros}
            for caja, receptor, saldo, cobros in saldos
        ],
    }
