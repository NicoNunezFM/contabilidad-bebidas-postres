"""Seguimiento operativo de ventas del POS de Entrenamiento."""
import json
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator

from pos_cobros import SolicitudContable, estado_cuenta
from pos_envios import resumen_fondos_reparto


class EntregaPedido(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    origen: Literal["mostrador", "whatsapp"]
    modalidad: Literal["retiro", "envio"]
    direccion: str | None = Field(default=None, min_length=1, max_length=250)
    referencias: str | None = Field(default=None, min_length=1, max_length=300)
    observacion: str | None = Field(default=None, min_length=1, max_length=300)

    @model_validator(mode="after")
    def comprobar_direccion(self):
        if self.modalidad == "envio" and self.direccion is None:
            raise ValueError("Ingresá la dirección del envío.")
        if self.modalidad == "retiro" and (self.direccion or self.referencias):
            raise ValueError("La dirección y las referencias corresponden a un envío.")
        return self


class TransicionPedido(SolicitudContable):
    version: int = Field(strict=True, ge=1, le=2**31 - 1)
    estado: Literal["preparacion", "listo", "en_camino", "entregado", "cancelado"]
    confirmar_pendiente: bool = Field(default=False, strict=True)
    saldo_confirmado_centavos: int | None = Field(default=None, strict=True, ge=0, le=2**63 - 1)
    motivo: str | None = Field(default=None, min_length=1, max_length=300)


def crear_seguimiento(db):
    db.execute("""
        CREATE TABLE IF NOT EXISTS pos_seguimiento_pedidos (
            id_venta INTEGER PRIMARY KEY REFERENCES pos_ventas_simuladas,
            estado TEXT NOT NULL CHECK (estado IN (
                'pendiente', 'preparacion', 'listo', 'en_camino', 'entregado', 'cancelado'
            )),
            version INTEGER NOT NULL CHECK (version > 0)
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS pos_historial_pedidos (
            id_venta INTEGER NOT NULL REFERENCES pos_seguimiento_pedidos,
            version INTEGER NOT NULL,
            id_usuario INTEGER NOT NULL REFERENCES usuarios_pos,
            fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            estado TEXT NOT NULL,
            motivo TEXT,
            solicitud_id TEXT UNIQUE,
            solicitud TEXT,
            resultado TEXT,
            PRIMARY KEY (id_venta, version)
        )
    """)


def iniciar_seguimiento(db, venta, usuario):
    crear_seguimiento(db)
    db.execute("INSERT INTO pos_seguimiento_pedidos VALUES (?, 'pendiente', 1)", (venta,))
    db.execute("""
        INSERT INTO pos_historial_pedidos (id_venta, version, id_usuario, estado)
        VALUES (?, 1, ?, 'pendiente')
    """, (venta, usuario))


def leer_pedido(db, venta, *, con_historial=True):
    fila = db.execute("""
        SELECT p.id_venta, p.estado, p.version, v.fecha, v.pedido, a.id_venta IS NOT NULL
        FROM pos_seguimiento_pedidos AS p
        JOIN pos_ventas_simuladas AS v USING (id_venta)
        LEFT JOIN pos_anulaciones_simuladas AS a USING (id_venta)
        WHERE p.id_venta = ?
    """, (venta,)).fetchone()
    if fila is None:
        raise HTTPException(404, "Pedido no encontrado.")
    numero, estado, version, fecha, datos, anulada = fila
    pedido = json.loads(datos)
    saldo = estado_cuenta(db, numero, pedido, anulada)
    envio = pedido.get("envio")
    pendiente_reparto = 0
    if envio and envio["titular"] == "repartidor" and not anulada:
        fondos = resumen_fondos_reparto(db, id_venta=numero)
        abonado = sum(f["recibido_centavos"] - f["reembolsado_centavos"]
                      + f.get("pagado_directo_centavos", 0) for f in fondos)
        pendiente_reparto = max(0, envio["importe_centavos"] - abonado)
    resultado = {
        "id_pedido": numero, "estado": estado, "version": version, "fecha": fecha,
        **pedido["entrega"], "items": pedido["items"], "envio": pedido.get("envio"),
        "id_cliente": pedido.get("id_cliente"),
        "estado_cobro": saldo["estado"], "saldo_pendiente_centavos": saldo["saldo_pendiente_centavos"],
        "saldo_reparto_centavos": pendiente_reparto,
    }
    if con_historial:
        resultado["historial"] = [
            {"version": n, "id_usuario": usuario, "fecha": momento, "estado": paso, "motivo": motivo}
            for n, usuario, momento, paso, motivo in db.execute("""
                SELECT version, id_usuario, fecha, estado, motivo FROM pos_historial_pedidos
                WHERE id_venta = ? ORDER BY version
            """, (venta,))
        ]
    return resultado


def listar_seguimiento(db, *, finalizados, antes_de, limite):
    if not db.execute("SELECT 1 FROM sqlite_schema WHERE name = 'pos_seguimiento_pedidos'").fetchone():
        return {"pedidos": [], "siguiente_antes_de": None}
    ids = db.execute("""
        SELECT id_venta FROM pos_seguimiento_pedidos
        WHERE (estado IN ('entregado', 'cancelado')) = ?
          AND (? IS NULL OR id_venta < ?)
        ORDER BY id_venta DESC LIMIT ?
    """, (finalizados, antes_de, antes_de, limite + 1)).fetchall()
    return {
        "pedidos": [leer_pedido(db, venta) for venta, in ids[:limite]],
        "siguiente_antes_de": ids[limite - 1][0] if len(ids) > limite else None,
    }


def cambiar_estado_pedido(db, venta, cambio, usuario):
    if not db.execute("SELECT 1 FROM sqlite_schema WHERE name = 'pos_seguimiento_pedidos'").fetchone():
        raise HTTPException(404, "Pedido no encontrado.")
    solicitud = cambio.model_dump_json(exclude={"id_solicitud"})
    clave = str(cambio.id_solicitud)
    previo = db.execute("""
        SELECT id_venta, id_usuario, solicitud, resultado
        FROM pos_historial_pedidos WHERE solicitud_id = ?
    """, (clave,)).fetchone()
    if previo is not None:
        if previo[:3] != (venta, usuario["id_usuario"], solicitud):
            raise HTTPException(409, "La solicitud ya corresponde a otro cambio.")
        return json.loads(previo[3])
    pedido = leer_pedido(db, venta)
    if pedido["version"] != cambio.version:
        raise HTTPException(409, "El pedido cambió. Actualizá su estado.")
    actual = pedido["estado"]
    siguiente = {
        "pendiente": "preparacion", "preparacion": "listo",
        "listo": "en_camino" if pedido["modalidad"] == "envio" else "entregado",
        "en_camino": "entregado",
    }.get(actual)
    if cambio.estado == "cancelado":
        if usuario["rol"] != "admin":
            raise HTTPException(403, "Solo Administración puede cancelar pedidos.")
        if not cambio.motivo:
            raise HTTPException(422, "Indicá el motivo de la cancelación.")
    if siguiente is None or cambio.estado not in (siguiente, "cancelado"):
        raise HTTPException(409, "La transición no corresponde al estado actual.")
    saldo = pedido["saldo_pendiente_centavos"] + pedido["saldo_reparto_centavos"]
    if cambio.estado == "entregado" and saldo > 0 and (
        not cambio.confirmar_pendiente or cambio.saldo_confirmado_centavos != saldo
    ):
        raise HTTPException(409, {"codigo": "ENTREGA_CON_SALDO", "saldo_centavos": saldo})
    if cambio.estado != "cancelado" and pedido["estado_cobro"] == "anulada":
        raise HTTPException(409, "La venta ya fue anulada.")
    version = cambio.version + 1
    db.execute("UPDATE pos_seguimiento_pedidos SET estado = ?, version = ? WHERE id_venta = ?",
               (cambio.estado, version, venta))
    db.execute("""
        INSERT INTO pos_historial_pedidos (id_venta, version, id_usuario, estado, motivo, solicitud_id, solicitud)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (venta, version, usuario["id_usuario"], cambio.estado, cambio.motivo, clave, solicitud))
    resultado = leer_pedido(db, venta)
    db.execute("UPDATE pos_historial_pedidos SET resultado = ? WHERE solicitud_id = ?",
               (json.dumps(resultado, ensure_ascii=False), clave))
    return resultado
