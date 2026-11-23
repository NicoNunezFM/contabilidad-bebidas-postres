"""Compras ficticias y sus pagos, separados del costo de mercadería."""
import json
from typing import Literal

from fastapi import HTTPException
from pydantic import Field, model_validator

from compras import anular_compra, registrar_compra
from pos_caja_diaria import ahora_local, exigir_caja_diaria, exigir_jornada_actual, guardar_evento, saldo_fisico
from pos_cobros import Medio, Receptor, SolicitudContable, caja_receptora
from pos_contabilidad import etapa_contable_activa


class CompraCajaEntrada(SolicitudContable):
    id_producto: int = Field(strict=True, gt=0, le=2**53 - 1)
    cantidad: int = Field(strict=True, gt=0, le=1_000_000)
    precio_unitario_centavos: int = Field(strict=True, gt=0, le=1_000_000_000_000)
    pagado_centavos: int = Field(strict=True, ge=0, le=1_000_000_000_000)
    pagador: Receptor | None = None
    medio_pago: Medio | None = None
    cuenta_deuda: str | None = Field(default=None, min_length=1, max_length=120)
    referencia: str | None = Field(default=None, min_length=1, max_length=120)

    @model_validator(mode="after")
    def validar_pago(self):
        total = self.cantidad * self.precio_unitario_centavos
        if total > 1_000_000_000_000 or self.pagado_centavos > total:
            raise ValueError("El importe pagado debe estar dentro del total admitido.")
        if self.pagado_centavos:
            sufijo = {"efectivo": "_efectivo", "transferencia": "_banco", "mercado_pago": "_mercado_pago"}
            if not self.medio_pago or not self.pagador or not self.pagador.endswith(sufijo[self.medio_pago]):
                raise ValueError("Indicá una cuenta pagadora compatible con el medio de pago.")
        elif self.pagador or self.medio_pago or self.referencia:
            raise ValueError("Una compra sin pago inicial no tiene medio, cuenta pagadora ni referencia.")
        if bool(self.cuenta_deuda and self.cuenta_deuda.strip()) != (self.pagado_centavos < total):
            raise ValueError("Indicá la cuenta del proveedor sólo cuando quede un saldo pendiente.")
        if self.cuenta_deuda and not self.cuenta_deuda.strip():
            raise ValueError("La cuenta del proveedor no puede estar vacía.")
        return self


class ReversoCompraCaja(SolicitudContable):
    motivo: str = Field(min_length=1, max_length=300)
    reintegro_confirmado: bool = Field(default=False, strict=True)

    @model_validator(mode="after")
    def validar_motivo(self):
        if not self.motivo.strip():
            raise ValueError("Indicá el motivo de la reversión.")
        return self


def compras_caja_existe(db):
    return db.execute("""
        SELECT 1 FROM sqlite_schema WHERE type = 'table' AND name = 'pos_compras_caja'
    """).fetchone() is not None


def preparar_compras_caja(db):
    db.execute("""
        CREATE TABLE IF NOT EXISTS pos_compras_caja (
            id_compra INTEGER NOT NULL REFERENCES compras(id_compra),
            evento TEXT NOT NULL CHECK (evento IN ('alta', 'anulacion', 'devolucion')),
            fecha TEXT NOT NULL,
            seccion TEXT NOT NULL CHECK (seccion IN ('comidas', 'bebidas_postres')),
            pagador TEXT,
            medio_pago TEXT,
            pagado_centavos INTEGER NOT NULL,
            deuda_centavos INTEGER NOT NULL,
            id_diario INTEGER UNIQUE REFERENCES pos_diario_caja(id_evento),
            id_usuario INTEGER NOT NULL REFERENCES usuarios_pos(id_usuario),
            id_solicitud TEXT NOT NULL UNIQUE,
            solicitud TEXT NOT NULL,
            resultado TEXT NOT NULL,
            PRIMARY KEY (id_compra, evento)
        )
    """)
    db.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS pos_compras_caja_un_reverso
        ON pos_compras_caja (id_compra) WHERE evento <> 'alta'
    """)


def movimiento_fisico(db, pagador, medio, importe, momento, usuario, motivo):
    if medio != "efectivo":
        return None
    jornada = exigir_jornada_actual(db, caja_receptora(pagador), momento[:10])
    if importe < 0 and saldo_fisico(db, jornada)["esperado_centavos"] < -importe:
        raise HTTPException(409, "La caja pagadora no tiene efectivo suficiente.")
    return guardar_evento(db, jornada, "retiro" if importe < 0 else "aporte", momento,
                          usuario, importe=importe, motivo=motivo)


def alta_compra(db, datos):
    costo = datos.cantidad * datos.precio_unitario_centavos
    pagado = datos.pagado_centavos
    deuda = costo - pagado
    compra = registrar_compra(
        datos.id_producto, datos.cantidad, datos.precio_unitario_centavos / 100,
        cuenta_deuda=datos.cuenta_deuda, _conexion=db, _financiado=deuda / 100,
    )
    verificar_resultado(compra)
    identificador = compra["id_compra"]
    seccion, importe = db.execute("""
        SELECT seccion, importe_centavos FROM pos_costos_contables
        WHERE tipo = 'compra' AND id_origen = ? AND evento = 'alta'
    """, (identificador,)).fetchone()
    if importe != costo:
        raise HTTPException(409, "El costo registrado difiere del importe de la compra.")
    return identificador, seccion, datos.pagador, datos.medio_pago, pagado, deuda


def verificar_resultado(resultado):
    if not resultado["ok"]:
        raise HTTPException(409, {"codigo": resultado["codigo"], "mensaje": resultado["mensaje"]})


def reverso_compra(db, identificador, datos):
    original = db.execute("""
        SELECT pc.seccion, pc.pagador, pc.medio_pago, pc.pagado_centavos, pc.deuda_centavos,
               c.id_cuenta_deuda, c.id_movimiento_deuda, c.anulada
        FROM pos_compras_caja AS pc JOIN compras AS c USING (id_compra)
        WHERE pc.id_compra = ? AND pc.evento = 'alta'
    """, (identificador,)).fetchone()
    if original is None:
        raise HTTPException(404, "Compra del POS no encontrada.")
    seccion, pagador, medio, pagado, deuda, cuenta, deuda_original, anulada = original
    if anulada:
        raise HTTPException(409, "La compra ya fue revertida.")
    if pagado and not datos.reintegro_confirmado:
        raise HTTPException(422, "Confirmá el reintegro total por el medio y la cuenta originales.")
    if not pagado and datos.reintegro_confirmado:
        raise HTTPException(422, "La compra no tiene un pago para reintegrar.")
    if cuenta is not None and db.execute("""
        SELECT 1 FROM movimientos_deuda_negocio
        WHERE id_cuenta = ? AND id_movimiento_deuda > ? AND tipo NOT IN ('Compra', 'Anulación compra')
    """, (cuenta, deuda_original)).fetchone():
        raise HTTPException(409, "La cuenta del proveedor tuvo movimientos posteriores. Conciliá la deuda antes de revertir.")
    verificar_resultado(anular_compra(identificador, datos.motivo, _conexion=db))
    return identificador, seccion, pagador, medio, pagado, deuda


EventoCompra = Literal["alta", "anulacion", "devolucion"]


def operar_compra(db, evento, datos, usuario, identificador=None):
    if not etapa_contable_activa(db):
        raise HTTPException(404, "Se requiere una base ficticia con contabilidad integrada.")
    exigir_caja_diaria(db)
    preparar_compras_caja(db)
    clave = str(datos.id_solicitud)
    solicitud = datos.model_dump_json(exclude={"id_solicitud"})
    previo = db.execute("""
        SELECT evento, id_usuario, solicitud, id_compra, resultado
        FROM pos_compras_caja WHERE id_solicitud = ?
    """, (clave,)).fetchone()
    if previo:
        if previo[:3] != (evento, usuario["id_usuario"], solicitud) or (
            identificador is not None and previo[3] != identificador
        ):
            raise HTTPException(409, "La solicitud ya corresponde a otra operación.")
        return json.loads(previo[4])

    alta = evento == "alta"
    (identificador, seccion, pagador, medio, pagado, deuda) = (
        alta_compra(db, datos) if alta else reverso_compra(db, identificador, datos)
    )
    momento = ahora_local()
    motivo = f"Pago compra #{identificador}" if alta else f"Reintegro compra #{identificador}: {datos.motivo}"
    diario = movimiento_fisico(db, pagador, medio, -pagado if alta else pagado, momento, usuario, motivo)
    resultado = {
        "id_compra": identificador, "evento": evento, "fecha": momento[:10], "seccion": seccion,
        "pagador": pagador, "medio_pago": medio, "costo_centavos": pagado + deuda,
        "pagado_centavos": pagado if alta else 0, "saldo_pendiente_centavos": deuda if alta else 0,
        "reintegrado_centavos": 0 if alta else pagado, "id_movimiento_fisico": diario,
    }
    db.execute("""
        INSERT INTO pos_compras_caja (
            id_compra, evento, fecha, seccion, pagador, medio_pago, pagado_centavos, deuda_centavos,
            id_diario, id_usuario, id_solicitud, solicitud, resultado
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (identificador, evento, momento[:10], seccion, pagador, medio, pagado, deuda,
          diario, usuario["id_usuario"], clave, solicitud, json.dumps(resultado, ensure_ascii=False)))
    return resultado


def resumen_pagos_compras(db, desde, hasta):
    return [
        {"pagador": pagador, "medio_pago": medio, "egreso_neto_centavos": egreso}
        for pagador, medio, egreso in db.execute("""
            SELECT pagador, medio_pago,
                   SUM(CASE WHEN evento = 'alta' THEN pagado_centavos ELSE -pagado_centavos END)
            FROM pos_compras_caja WHERE fecha BETWEEN ? AND ? AND pagado_centavos > 0
            GROUP BY pagador, medio_pago ORDER BY pagador, medio_pago
        """, (desde, hasta))
    ]


def listar_compras_caja(db, antes_de, limite):
    if not compras_caja_existe(db):
        return {"compras": [], "siguiente_antes_de": None}
    filas = db.execute("""
        SELECT pc.id_compra, p.nombre, pc.resultado, c.anulada, r.evento
        FROM pos_compras_caja AS pc JOIN compras AS c USING (id_compra)
        JOIN productos AS p USING (id_producto)
        LEFT JOIN pos_compras_caja AS r ON r.id_compra = pc.id_compra AND r.evento <> 'alta'
        WHERE pc.evento = 'alta' AND pc.id_compra < ?
        ORDER BY pc.id_compra DESC LIMIT ?
    """, (antes_de, limite + 1)).fetchall()
    return {
        "compras": [{**json.loads(datos), "producto": nombre, "revertida": bool(anulada),
                     "reverso": reverso}
                    for _, nombre, datos, anulada, reverso in filas[:limite]],
        "siguiente_antes_de": filas[limite - 1][0] if len(filas) > limite else None,
    }


def conciliar_compras_caja(db):
    return [
        {"codigo": "COMPRA_PAGO_DESCUADRADO", "id_compra": identificador, "evento": evento}
        for identificador, evento in db.execute("""
            SELECT pc.id_compra, pc.evento
            FROM pos_compras_caja AS pc JOIN compras AS c USING (id_compra)
            LEFT JOIN pos_costos_contables AS costo
              ON costo.id_origen = pc.id_compra AND costo.tipo = 'compra'
                AND costo.evento = CASE WHEN pc.evento = 'alta' THEN 'alta' ELSE 'anulacion' END
            LEFT JOIN pos_diario_caja AS d ON d.id_evento = pc.id_diario
            LEFT JOIN pos_jornadas_caja AS j ON j.id_jornada = d.id_jornada
            LEFT JOIN movimientos_deuda_negocio AS deuda ON deuda.id_movimiento_deuda = c.id_movimiento_deuda
            WHERE costo.seccion IS NOT pc.seccion OR costo.fecha IS NOT pc.fecha
               OR costo.importe_centavos IS NOT
                   (pc.pagado_centavos + pc.deuda_centavos) * CASE WHEN pc.evento = 'alta' THEN 1 ELSE -1 END
               OR (pc.evento = 'alta' AND c.anulada IS NOT EXISTS (
                     SELECT 1 FROM pos_compras_caja r
                     WHERE r.id_compra = pc.id_compra AND r.evento <> 'alta'
                   ))
               OR pc.deuda_centavos IS NOT CAST(round(COALESCE(deuda.importe, 0) * 100) AS INTEGER)
               OR (pc.medio_pago = 'efectivo' AND (
                    d.importe_centavos IS NOT pc.pagado_centavos * CASE WHEN pc.evento = 'alta' THEN -1 ELSE 1 END
                    OR j.caja || '_efectivo' IS NOT pc.pagador OR j.fecha IS NOT pc.fecha
                    OR d.tipo IS NOT CASE WHEN pc.evento = 'alta' THEN 'retiro' ELSE 'aporte' END
                    OR d.id_usuario IS NOT pc.id_usuario
               )) OR (pc.medio_pago IS NOT 'efectivo' AND pc.id_diario IS NOT NULL)
        """)
    ]
