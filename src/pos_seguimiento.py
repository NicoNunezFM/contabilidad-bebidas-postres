"""Seguimiento operativo de pedidos del POS de Entrenamiento."""
import json
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator

from pos_cobros import SolicitudContable, estado_cuenta
from pos_envios import CargoEnvio, resumen_fondos_reparto
from pos_pedidos import PedidoPos, calcular_pedido_pos


class EntregaPedido(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    origen: Literal["mostrador", "whatsapp"]
    modalidad: Literal["retiro", "envio"]
    circuito: Literal["avanzado", "sencillo"] = Field(default="avanzado", exclude_if=lambda v: v == "avanzado")
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


class AltaPedido(PedidoPos, SolicitudContable):
    entrega: EntregaPedido
    envio: CargoEnvio | None = None

    @model_validator(mode="after")
    def comprobar_envio(self):
        if self.envio and self.entrega.modalidad != "envio":
            raise ValueError("El cargo de envío requiere entrega a domicilio.")
        self.envio = normalizar_envio_sencillo(self.entrega, self.envio)
        return self


class TransicionPedido(SolicitudContable):
    version: int = Field(strict=True, ge=1, le=2**31 - 1)
    estado: Literal["preparacion", "listo", "en_camino", "entregado", "cancelado"]
    confirmar_pendiente: bool = Field(default=False, strict=True)
    saldo_confirmado_centavos: int | None = Field(default=None, strict=True, ge=0, le=2**63 - 1)
    motivo: str | None = Field(default=None, min_length=1, max_length=300)
    receptor_reparto: str | None = Field(default=None, exclude_if=lambda v: v is None)


def normalizar_envio_sencillo(entrega, envio):
    if entrega and entrega.circuito == "sencillo" and entrega.modalidad == "envio":
        envio = envio or CargoEnvio(titular="repartidor", importe_centavos=200_000)
        if envio.titular != "repartidor":
            raise ValueError("En el circuito sencillo el envío siempre corresponde al repartidor.")
    return envio


def columnas_seguimiento(db):
    return {fila[1] for fila in db.execute("PRAGMA table_info(pos_seguimiento_pedidos)")}


def exigir_esquema(columnas):
    if columnas and "id_pedido" not in columnas:
        raise HTTPException(409, "Prepará el esquema con activar-fondos-envio antes de usar Pedidos.")


def crear_seguimiento(db):
    columnas = columnas_seguimiento(db)
    anterior = bool(columnas and "id_pedido" not in columnas)
    if anterior:
        db.execute("ALTER TABLE pos_historial_pedidos RENAME TO pos_historial_pedidos_anterior")
        db.execute("ALTER TABLE pos_seguimiento_pedidos RENAME TO pos_seguimiento_pedidos_anterior")
    db.execute("""
        CREATE TABLE IF NOT EXISTS pos_seguimiento_pedidos (
            id_pedido INTEGER PRIMARY KEY,
            id_venta INTEGER UNIQUE REFERENCES pos_ventas_simuladas,
            estado TEXT NOT NULL CHECK (estado IN (
                'pendiente', 'preparacion', 'listo', 'en_camino', 'entregado', 'cancelado'
            )),
            version INTEGER NOT NULL CHECK (version > 0),
            fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            estimacion TEXT,
            entrada TEXT,
            alta_usuario INTEGER REFERENCES usuarios_pos,
            alta_uuid TEXT,
            CHECK (id_venta IS NOT NULL OR (entrada IS NOT NULL AND estimacion IS NOT NULL)),
            UNIQUE (alta_usuario, alta_uuid)
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS pos_historial_pedidos (
            id_pedido INTEGER NOT NULL REFERENCES pos_seguimiento_pedidos,
            version INTEGER NOT NULL,
            id_usuario INTEGER NOT NULL REFERENCES usuarios_pos,
            fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            estado TEXT NOT NULL,
            motivo TEXT,
            solicitud_id TEXT UNIQUE,
            solicitud TEXT,
            resultado TEXT,
            PRIMARY KEY (id_pedido, version)
        )
    """)
    if anterior:
        db.execute("""
            INSERT INTO pos_seguimiento_pedidos (id_pedido, id_venta, estado, version, fecha)
            SELECT id_venta, id_venta, p.estado, p.version, v.fecha
            FROM pos_seguimiento_pedidos_anterior AS p JOIN pos_ventas_simuladas AS v USING (id_venta)
        """)
        db.execute("INSERT INTO pos_historial_pedidos SELECT * FROM pos_historial_pedidos_anterior")
        db.execute("DROP TABLE pos_historial_pedidos_anterior")
        db.execute("DROP TABLE pos_seguimiento_pedidos_anterior")


def iniciar_seguimiento(db, venta, usuario, *, entrada=None, estimacion=None, clave=None):
    columnas = columnas_seguimiento(db)
    exigir_esquema(columnas)
    if not columnas:
        crear_seguimiento(db)
    cursor = db.execute("""
        INSERT INTO pos_seguimiento_pedidos
            (id_venta, estado, version, entrada, estimacion, alta_usuario, alta_uuid)
        VALUES (?, 'pendiente', 1, ?, ?, ?, ?)
    """, (venta, entrada, estimacion, usuario, clave))
    numero = cursor.lastrowid
    db.execute("""
        INSERT INTO pos_historial_pedidos (id_pedido, version, id_usuario, estado)
        VALUES (?, 1, ?, 'pendiente')
    """, (numero, usuario))
    return numero


def estimar_pedido(db, entrada, *, advertir_faltantes=False):
    estimacion = calcular_pedido_pos(db, entrada, advertir_faltantes=advertir_faltantes)
    estimacion["entrega"] = entrada.entrega.model_dump()
    if entrada.envio:
        estimacion["envio"] = entrada.envio.model_dump()
        if entrada.envio.titular == "negocio" or entrada.entrega.circuito == "sencillo":
            estimacion["total_centavos"] += entrada.envio.importe_centavos
    return estimacion


def alta_pedido(db, entrada, usuario):
    columnas = columnas_seguimiento(db)
    exigir_esquema(columnas)
    clave = str(entrada.id_solicitud)
    datos = entrada.model_dump_json(exclude={"id_solicitud"})
    if columnas:
        previo = db.execute("""
            SELECT id_pedido, entrada FROM pos_seguimiento_pedidos WHERE alta_usuario = ? AND alta_uuid = ?
        """, (usuario, clave)).fetchone()
        if previo:
            if previo[1] != datos:
                raise HTTPException(409, "La solicitud ya corresponde a otro pedido.")
            return leer_pedido(db, previo[0])
    estimacion = estimar_pedido(db, entrada)
    numero = iniciar_seguimiento(db, None, usuario, entrada=datos,
                                estimacion=json.dumps(estimacion, ensure_ascii=False), clave=clave)
    return leer_pedido(db, numero)


def datos_conversion(db, numero):
    columnas = columnas_seguimiento(db)
    exigir_esquema(columnas)
    fila = db.execute("""
        SELECT id_venta, estado, entrada FROM pos_seguimiento_pedidos WHERE id_pedido = ?
    """, (numero,)).fetchone() if columnas else None
    if not fila or fila[2] is None:
        raise HTTPException(404, "Pedido pendiente de venta no encontrado.")
    return fila


def leer_pedido(db, venta, *, con_historial=True):
    fila = db.execute("""
        SELECT p.id_pedido, p.id_venta, p.estado, p.version, p.fecha,
               COALESCE(v.pedido, p.estimacion), a.id_venta IS NOT NULL, p.estimacion
        FROM pos_seguimiento_pedidos AS p
        LEFT JOIN pos_ventas_simuladas AS v USING (id_venta)
        LEFT JOIN pos_anulaciones_simuladas AS a USING (id_venta)
        WHERE p.id_pedido = ?
    """, (venta,)).fetchone()
    if fila is None:
        raise HTTPException(404, "Pedido no encontrado.")
    numero, id_venta, estado, version, fecha, datos, anulada, estimacion = fila
    pedido = json.loads(datos)
    saldo = (estado_cuenta(db, id_venta, pedido, anulada) if id_venta is not None else
             {"estado": "sin_venta", "saldo_pendiente_centavos": 0})
    envio = pedido.get("envio")
    sencillo = pedido.get("entrega", {}).get("circuito") == "sencillo"
    pendiente_reparto = 0
    if envio and envio["titular"] == "repartidor" and not anulada and not sencillo:
        fondos = resumen_fondos_reparto(db, id_venta=id_venta) if id_venta is not None else []
        abonado = sum(f["recibido_centavos"] - f["reembolsado_centavos"]
                      + f.get("pagado_directo_centavos", 0) for f in fondos)
        pendiente_reparto = max(0, envio["importe_centavos"] - abonado)
    resultado = {
        "id_pedido": numero, "id_venta": id_venta,
        "total_estimado_centavos": json.loads(estimacion or datos)["total_centavos"], "estado": estado, "version": version, "fecha": fecha,
        **pedido["entrega"], "items": pedido["items"], "envio": pedido.get("envio"),
        "id_cliente": pedido.get("id_cliente"),
        "estado_cobro": saldo.get("estado_cliente", saldo["estado"]), "saldo_pendiente_centavos": saldo["saldo_pendiente_centavos"],
        "saldo_reparto_centavos": pendiente_reparto,
        "circuito": pedido.get("entrega", {}).get("circuito", "avanzado"),
        **({"delivery": saldo["delivery"], "saldo_cliente_centavos": saldo["saldo_cliente_centavos"]}
           if "delivery" in saldo else {}),
    }
    if con_historial:
        resultado["historial"] = [
            {"version": n, "id_usuario": usuario, "fecha": momento, "estado": paso, "motivo": motivo}
            for n, usuario, momento, paso, motivo in db.execute("""
                SELECT version, id_usuario, fecha, estado, motivo FROM pos_historial_pedidos
                WHERE id_pedido = ? ORDER BY version
            """, (venta,))
        ]
    return resultado


def listar_seguimiento(db, *, finalizados, antes_de, limite):
    columnas = columnas_seguimiento(db)
    exigir_esquema(columnas)
    if not columnas:
        return {"pedidos": [], "siguiente_antes_de": None}
    ids = db.execute("""
        SELECT id_pedido FROM pos_seguimiento_pedidos
        WHERE (estado IN ('entregado', 'cancelado')) = ?
          AND (? IS NULL OR id_pedido < ?)
        ORDER BY id_pedido DESC LIMIT ?
    """, (finalizados, antes_de, antes_de, limite + 1)).fetchall()
    return {
        "pedidos": [leer_pedido(db, venta) for venta, in ids[:limite]],
        "siguiente_antes_de": ids[limite - 1][0] if len(ids) > limite else None,
    }


def cambiar_estado_pedido(db, venta, cambio, usuario):
    columnas = columnas_seguimiento(db)
    exigir_esquema(columnas)
    if not columnas:
        raise HTTPException(404, "Pedido no encontrado.")
    solicitud = cambio.model_dump_json(exclude={"id_solicitud"})
    clave = str(cambio.id_solicitud)
    previo = db.execute("""
        SELECT id_pedido, id_usuario, solicitud, resultado
        FROM pos_historial_pedidos WHERE solicitud_id = ?
    """, (clave,)).fetchone()
    if previo is not None:
        if previo[:2] != (venta, usuario["id_usuario"]) or previo[2] != solicitud:
            raise HTTPException(409, "La solicitud ya corresponde a otro cambio.")
        return json.loads(previo[3])
    pedido = leer_pedido(db, venta)
    if pedido["version"] != cambio.version:
        raise HTTPException(409, "El pedido cambió. Actualizá su estado.")
    actual = pedido["estado"]
    sencillo = pedido["circuito"] == "sencillo"
    siguiente = {
        "pendiente": "preparacion", "preparacion": "listo",
        "listo": "en_camino" if pedido["modalidad"] == "envio" else "entregado",
        "en_camino": "entregado",
    }.get(actual)
    if sencillo and siguiente:
        siguiente = "entregado"
    if cambio.estado == "cancelado":
        if usuario["rol"] != "admin":
            raise HTTPException(403, "Solo Administración puede cancelar pedidos.")
        if not cambio.motivo:
            raise HTTPException(422, "Indicá el motivo de la cancelación.")
        if sencillo and pedido["id_venta"] is not None and pedido["estado_cobro"] not in ("anulada", "devuelta"):
            raise HTTPException(409, "Anulá la venta y sus cobros antes de cancelar el pedido.")
    if siguiente is None or cambio.estado not in (siguiente, "cancelado"):
        raise HTTPException(409, "La transición no corresponde al estado actual.")
    saldo = (pedido["total_estimado_centavos"] if pedido["id_venta"] is None
             else pedido.get("saldo_cliente_centavos", pedido["saldo_pendiente_centavos"])) + pedido["saldo_reparto_centavos"]
    if sencillo and cambio.estado == "entregado" and pedido["id_venta"] is None:
        raise HTTPException(409, "Confirmá la venta antes de entregar el pedido.")
    if cambio.estado == "entregado" and saldo > 0 and (
        not cambio.confirmar_pendiente or cambio.saldo_confirmado_centavos != saldo
    ):
        raise HTTPException(409, {"codigo": "ENTREGA_CON_SALDO", "saldo_centavos": saldo})
    if sencillo and cambio.estado == "entregado" and saldo > 0 and not cambio.motivo:
        raise HTTPException(422, "Indicá el motivo de la entrega fiada.")
    if cambio.estado != "cancelado" and pedido["estado_cobro"] == "anulada":
        raise HTTPException(409, "La venta ya fue anulada.")
    if sencillo and cambio.estado == "entregado" and pedido["estado_cobro"] == "devuelta":
        raise HTTPException(409, "La venta fue devuelta por completo. Cancelá el pedido en lugar de entregarlo.")
    if sencillo and cambio.estado == "entregado" and pedido.get("envio"):
        from pos_delivery import entregar_delivery
        entregar_delivery(db, pedido["id_venta"], cambio, usuario)
    version = cambio.version + 1
    db.execute("UPDATE pos_seguimiento_pedidos SET estado = ?, version = ? WHERE id_pedido = ?",
               (cambio.estado, version, venta))
    db.execute("""
        INSERT INTO pos_historial_pedidos (id_pedido, version, id_usuario, estado, motivo, solicitud_id, solicitud)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (venta, version, usuario["id_usuario"], cambio.estado, cambio.motivo, clave, solicitud))
    resultado = leer_pedido(db, venta)
    db.execute("UPDATE pos_historial_pedidos SET resultado = ? WHERE solicitud_id = ?",
               (json.dumps(resultado, ensure_ascii=False), clave))
    return resultado
