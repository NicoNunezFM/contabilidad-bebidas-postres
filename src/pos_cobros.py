"""Libro contable del POS ficticio. El llamador aporta una transacción SQLite."""
import json
from typing import Annotated, Literal
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from pos_caja_diaria import vincular_movimiento_pos


Seccion = Literal["comidas", "bebidas_postres"]
Medio = Literal["efectivo", "transferencia", "mercado_pago"]
Receptor = Literal[
    "comidas_efectivo", "comidas_banco", "comidas_mercado_pago",
    "bebidas_postres_efectivo", "bebidas_postres_banco", "bebidas_postres_mercado_pago",
]
ReceptorCobro = Receptor | Literal["comidas_efectivo_en_transito", "bebidas_postres_efectivo_en_transito"]
SUFIJO_TRANSITO = "_en_transito"

Centavos = Annotated[int, Field(strict=True, gt=0, le=310_000_000_000_000_000)]
SECCIONES = ("comidas", "bebidas_postres")


class PagoPos(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    receptor: ReceptorCobro
    medio_pago: Medio
    importe_centavos: Centavos
    referencia: str | None = Field(default=None, min_length=1, max_length=120)

    @model_validator(mode="after")
    def comprobar_receptor(self):
        if self.receptor.removesuffix(SUFIJO_TRANSITO).endswith("_efectivo") != (self.medio_pago == "efectivo"):
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


class RendicionEntrada(ReversionEntrada):
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


def iniciar_evento(conexion, tipo, usuario, entrada, id_venta=None, *, usar_uuid=True, contexto=None):
    solicitud = entrada.model_dump_json(exclude={"id_solicitud"})
    if contexto is not None:
        solicitud = json.dumps({**json.loads(solicitud), **contexto}, ensure_ascii=False)
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
    if revierte is not None and receptor.endswith(SUFIJO_TRANSITO):
        pendiente = efectivo_en_transito(conexion, revierte)
        en_transito = min(pendiente, -importe)
        en_caja = -importe - en_transito
        if en_transito:
            _insertar_movimiento(conexion, evento, venta, receptor, medio, -en_transito, referencia, revierte)
        if en_caja:
            _insertar_movimiento(
                conexion, evento, venta, receptor.removesuffix(SUFIJO_TRANSITO),
                medio, -en_caja, None, revierte,
            )
        return
    return _insertar_movimiento(conexion, evento, venta, receptor, medio, importe, referencia, revierte)


def _insertar_movimiento(conexion, evento, venta, receptor, medio, importe, referencia, revierte):
    cursor = conexion.execute("""
        INSERT INTO pos_movimientos_simulados
            (id_evento, id_venta, receptor, caja, medio_pago, importe_centavos, referencia, revierte)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (evento, venta, receptor, caja_receptora(receptor), medio, importe, referencia, revierte))
    vincular_movimiento_pos(conexion, cursor.lastrowid, evento, receptor, importe)


def crear_rendiciones(conexion):
    conexion.execute("""
        CREATE TABLE IF NOT EXISTS pos_rendiciones_efectivo (
            id_evento INTEGER PRIMARY KEY REFERENCES pos_eventos_simulados,
            id_cobro INTEGER NOT NULL REFERENCES pos_movimientos_simulados,
            importe_centavos INTEGER NOT NULL CHECK (importe_centavos > 0)
        )
    """)
    conexion.execute("""
        CREATE INDEX IF NOT EXISTS pos_rendiciones_por_cobro
        ON pos_rendiciones_efectivo (id_cobro)
    """)


def efectivo_en_transito(conexion, id_cobro):
    cobro = conexion.execute("""
        SELECT receptor, importe_centavos
        FROM pos_movimientos_simulados
        WHERE id_movimiento = ? AND id_venta IS NOT NULL AND importe_centavos > 0
    """, (id_cobro,)).fetchone()
    if cobro is None or not cobro[0].endswith(SUFIJO_TRANSITO):
        raise HTTPException(404, "Cobro en tránsito no encontrado.")
    receptor, importe = cobro
    reembolsado = conexion.execute("""
        SELECT COALESCE(SUM(importe_centavos), 0)
        FROM pos_movimientos_simulados WHERE revierte = ? AND receptor = ?
    """, (id_cobro, receptor)).fetchone()[0]
    existe = conexion.execute("""
        SELECT 1 FROM sqlite_schema WHERE name = 'pos_rendiciones_efectivo'
    """).fetchone()
    rendido = 0
    if existe:
        rendido = conexion.execute("""
            SELECT COALESCE(SUM(importe_centavos), 0)
            FROM pos_rendiciones_efectivo WHERE id_cobro = ?
        """, (id_cobro,)).fetchone()[0]
    return importe + reembolsado - rendido


def registrar_rendicion(conexion, id_cobro, entrada, usuario):
    evento, previo = iniciar_evento(
        conexion, "transferencia_interna", usuario, entrada, contexto={"id_cobro": id_cobro},
    )
    if previo is not None:
        return previo
    pendiente = efectivo_en_transito(conexion, id_cobro)
    importe = entrada.importe_centavos
    if importe > pendiente:
        raise HTTPException(409, "La rendición supera el efectivo pendiente.")
    receptor = conexion.execute("""
        SELECT receptor FROM pos_movimientos_simulados WHERE id_movimiento = ?
    """, (id_cobro,)).fetchone()[0]
    crear_rendiciones(conexion)
    conexion.execute("INSERT INTO pos_rendiciones_efectivo VALUES (?, ?, ?)", (evento, id_cobro, importe))
    registrar_movimiento(conexion, evento, None, receptor, None, -importe)
    registrar_movimiento(conexion, evento, None, receptor.removesuffix(SUFIJO_TRANSITO), None, importe)
    return terminar_evento(conexion, evento, {
        "id_evento": evento, "id_cobro": id_cobro,
        "importe_centavos": importe, "pendiente_centavos": pendiente - importe,
    })


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


def resumen_libro(conexion, *, hasta_periodo=None):
    periodo = periodo_abierto(conexion) if hasta_periodo is None else hasta_periodo
    dev_comidas, dev_bebidas, cob_comidas, cob_bebidas = conexion.execute("""
        SELECT COALESCE(SUM(devengado_comidas), 0), COALESCE(SUM(devengado_bebidas), 0),
               COALESCE(SUM(cobrado_comidas), 0), COALESCE(SUM(cobrado_bebidas), 0)
        FROM pos_eventos_simulados
        WHERE periodo <= ?
    """, (periodo,)).fetchone()
    saldos = conexion.execute("""
        SELECT caja, receptor, SUM(importe_centavos),
               SUM(CASE WHEN medio_pago IS NOT NULL THEN importe_centavos ELSE 0 END)
        FROM pos_movimientos_simulados
        JOIN pos_eventos_simulados USING (id_evento)
        WHERE periodo <= ?
        GROUP BY caja, receptor ORDER BY caja, receptor
    """, (periodo,)).fetchall()
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
        "periodo_abierto": periodo,
        "secciones": secciones,
        "receptores": [
            {"caja": caja, "receptor": receptor, "saldo_centavos": saldo,
             "recibido_neto_centavos": cobros, "transferencia_neta_centavos": saldo - cobros}
            for caja, receptor, saldo, cobros in saldos
        ],
    }
