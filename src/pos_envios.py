"""Importes de envío y fondos bancarios recibidos por cuenta del repartidor."""
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator

from pos_cobros import Centavos, ReversionEntrada, iniciar_evento, terminar_evento


ReceptorDigital = Literal[
    "comidas_banco", "comidas_mercado_pago", "bebidas_postres_banco", "bebidas_postres_mercado_pago",
]


class CargoEnvio(BaseModel):
    model_config = ConfigDict(extra="forbid")

    titular: Literal["negocio", "repartidor"]
    importe_centavos: int = Field(strict=True, ge=0, le=310_000_000_000_000_000)
    motivo_bonificacion: str | None = Field(default=None, min_length=1, max_length=300, exclude_if=lambda v: v is None)

    @model_validator(mode="after")
    def bonificacion(self):
        if self.importe_centavos == 0 and not (self.motivo_bonificacion or "").strip():
            raise ValueError("Indicá el motivo de la bonificación del envío.")
        return self


class MovimientoReparto(ReversionEntrada):
    receptor: ReceptorDigital | Literal["repartidor_directo"]
    importe_centavos: Centavos
    referencia: str = Field(min_length=1, max_length=120)


def crear_libro_reparto(db):
    db.execute("""
        CREATE TABLE IF NOT EXISTS pos_fondos_reparto (
            id_evento INTEGER PRIMARY KEY REFERENCES pos_eventos_simulados,
            id_venta INTEGER NOT NULL REFERENCES pos_ventas_simuladas,
            receptor TEXT NOT NULL,
            importe_centavos INTEGER NOT NULL CHECK (importe_centavos <> 0),
            referencia TEXT NOT NULL,
            tipo TEXT NOT NULL CHECK (tipo IN ('recepcion', 'liquidacion', 'reembolso', 'directo')),
            CHECK ((tipo IN ('recepcion', 'directo')) = (importe_centavos > 0)),
            CHECK ((tipo = 'directo') = (receptor = 'repartidor_directo')),
            UNIQUE (receptor, tipo, referencia)
        )
    """)
    db.execute("""
        CREATE INDEX IF NOT EXISTS pos_fondos_reparto_venta
        ON pos_fondos_reparto (id_venta, receptor)
    """)


def resumen_fondos_reparto(db, *, periodo=None, id_venta=None):
    existe = db.execute("SELECT 1 FROM sqlite_schema WHERE name = 'pos_fondos_reparto'").fetchone()
    if not existe:
        return []
    return [
        {"receptor": receptor, "recibido_centavos": recibido, "liquidado_centavos": liquidado,
         "reembolsado_centavos": reembolsado, "obligacion_centavos": saldo,
         **({"pagado_directo_centavos": directo} if receptor == "repartidor_directo" else {})}
        for receptor, recibido, liquidado, reembolsado, saldo, directo in db.execute("""
            SELECT r.receptor,
                   SUM(CASE WHEN r.tipo = 'recepcion' THEN r.importe_centavos ELSE 0 END),
                   -SUM(CASE WHEN r.tipo = 'liquidacion' THEN r.importe_centavos ELSE 0 END),
                   -SUM(CASE WHEN r.tipo = 'reembolso' THEN r.importe_centavos ELSE 0 END),
                   SUM(CASE WHEN r.tipo <> 'directo' THEN r.importe_centavos ELSE 0 END),
                   SUM(CASE WHEN r.tipo = 'directo' THEN r.importe_centavos ELSE 0 END)
            FROM pos_fondos_reparto AS r JOIN pos_eventos_simulados AS e USING (id_evento)
            WHERE (:periodo IS NULL OR e.periodo <= :periodo)
              AND (:venta IS NULL OR r.id_venta = :venta)
            GROUP BY r.receptor ORDER BY r.receptor
        """, {"periodo": periodo, "venta": id_venta})
    ]


def registrar_fondo_reparto(db, id_venta, pedido, entrada, usuario, *, tipo, anulada=False):
    if pedido.get("entrega", {}).get("circuito") == "sencillo":
        raise HTTPException(409, "El delivery sencillo se cobra con la venta y se entrega al confirmar el reparto.")
    evento, previo = iniciar_evento(
        db, "transferencia_interna", usuario, entrada,
        contexto={"operacion_reparto": tipo, "id_venta": id_venta},
    )
    if previo is not None:
        return previo
    envio = pedido.get("envio")
    if not envio or envio["titular"] != "repartidor":
        raise HTTPException(409, "La venta no tiene un importe de envío para el repartidor.")
    crear_libro_reparto(db)
    fondos = resumen_fondos_reparto(db, id_venta=id_venta)
    importe = entrada.importe_centavos
    if (tipo == "directo") != (entrada.receptor == "repartidor_directo"):
        raise HTTPException(422, "El receptor no corresponde a la operación de reparto.")
    if tipo in ("recepcion", "directo"):
        cobrado = sum(r["recibido_centavos"] - r["reembolsado_centavos"]
                      + r.get("pagado_directo_centavos", 0) for r in fondos)
        if anulada or importe > envio["importe_centavos"] - cobrado:
            raise HTTPException(409, "La recepción supera el importe de envío disponible.")
    else:
        pendiente = next((r["obligacion_centavos"] for r in fondos if r["receptor"] == entrada.receptor), 0)
        if importe > pendiente:
            raise HTTPException(409, "La operación supera la obligación en el receptor.")
    if db.execute("""
        SELECT 1 FROM pos_fondos_reparto WHERE receptor = ? AND tipo = ? AND referencia = ?
    """, (entrada.receptor, tipo, entrada.referencia)).fetchone():
        raise HTTPException(409, "La referencia de reparto ya fue registrada.")
    db.execute("""
        INSERT INTO pos_fondos_reparto VALUES (?, ?, ?, ?, ?, ?)
    """, (evento, id_venta, entrada.receptor, importe if tipo in ("recepcion", "directo") else -importe,
          entrada.referencia, tipo))
    return terminar_evento(db, evento, {
        "id_evento": evento, "id_venta": id_venta, "tipo": tipo,
        "fondos_reparto": resumen_fondos_reparto(db, id_venta=id_venta),
    })
