"""Identidad y agrupación de abonos sobre el libro existente del POS."""
import hashlib
import json

from fastapi import HTTPException
from pydantic import Field

from database import RUTA_ENTRENAMIENTO
from pos_cobros import (
    PagoPos, ReversionEntrada, SECCIONES, SolicitudContable,
    estado_cuenta, imputar, iniciar_evento, registrar_movimiento, registrar_pagos, terminar_evento,
)
from pos_simulacion import eventos_venta, transaccion_simulacion
from pos_delivery import es_sencillo, existe as existe_delivery, mover as mover_delivery, registrar_pago_conjunto


class AltaCliente(SolicitudContable):
    nombre: str = Field(min_length=1, max_length=120)
    telefono: str | None = Field(default=None, min_length=1, max_length=60)
    referencia: str | None = Field(default=None, min_length=1, max_length=300)


class PagoCliente(SolicitudContable):
    pago: PagoPos
    vista_previa: str = Field(pattern=r"^[0-9a-f]{64}$")


def crear_esquema_clientes(db):
    db.execute("""
        CREATE TABLE pos_clientes (
            id_cliente INTEGER PRIMARY KEY, nombre TEXT NOT NULL, telefono TEXT, referencia TEXT,
            id_usuario INTEGER NOT NULL REFERENCES usuarios_pos, fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    db.execute("""
        CREATE TABLE pos_ventas_clientes (
            id_venta INTEGER PRIMARY KEY REFERENCES pos_ventas_simuladas,
            id_cliente INTEGER NOT NULL REFERENCES pos_clientes
        )
    """)
    db.execute("CREATE INDEX pos_ventas_cliente ON pos_ventas_clientes (id_cliente, id_venta)")
    db.execute("""
        CREATE TABLE pos_solicitudes_clientes (
            uuid TEXT PRIMARY KEY, id_cliente INTEGER NOT NULL REFERENCES pos_clientes,
            id_usuario INTEGER NOT NULL REFERENCES usuarios_pos,
            tipo TEXT NOT NULL CHECK (tipo IN ('alta', 'abono', 'correccion')),
            solicitud TEXT NOT NULL, resultado TEXT NOT NULL, fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    db.execute("CREATE INDEX pos_solicitudes_cliente ON pos_solicitudes_clientes (id_cliente)")
    db.execute("""
        CREATE TABLE pos_eventos_clientes (
            id_evento INTEGER PRIMARY KEY REFERENCES pos_eventos_simulados,
            uuid TEXT NOT NULL REFERENCES pos_solicitudes_clientes
        )
    """)
    db.execute("CREATE INDEX pos_eventos_cliente_uuid ON pos_eventos_clientes (uuid)")


def exigir_modulo(db):
    from pos_entrenamiento_db import clientes_activos

    if RUTA_ENTRENAMIENTO.get() is None or not clientes_activos(db):
        raise HTTPException(404, "Clientes requiere una base de Entrenamiento actualizada.")


def obtener_cliente(db, id_cliente):
    fila = db.execute("""
        SELECT id_cliente, nombre, telefono, referencia, id_usuario, fecha
        FROM pos_clientes WHERE id_cliente = ?
    """, (id_cliente,)).fetchone()
    if fila is None:
        raise HTTPException(404, "Cliente no encontrado.")
    return dict(zip(("id_cliente", "nombre", "telefono", "referencia", "id_usuario", "fecha"), fila))


def solicitud_anterior(db, tipo, entrada, usuario, id_cliente=None):
    fila = db.execute("""
        SELECT tipo, id_usuario, id_cliente, solicitud, resultado
        FROM pos_solicitudes_clientes WHERE uuid = ?
    """, (str(entrada.id_solicitud),)).fetchone()
    if fila is None:
        return None
    if (fila[:2] != (tipo, usuario["id_usuario"])
            or (id_cliente is not None and fila[2] != id_cliente)
            or fila[3] != entrada.model_dump_json(exclude={"id_solicitud"})):
        raise HTTPException(409, "La solicitud ya corresponde a otra operación.")
    return json.loads(fila[4])


def guardar_solicitud(db, tipo, entrada, usuario, id_cliente, resultado):
    db.execute("""
        INSERT INTO pos_solicitudes_clientes (uuid, id_cliente, id_usuario, tipo, solicitud, resultado)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (str(entrada.id_solicitud), id_cliente, usuario["id_usuario"], tipo,
          entrada.model_dump_json(exclude={"id_solicitud"}), json.dumps(resultado, ensure_ascii=False)))
    return resultado


def alta_cliente(entrada, usuario):
    with transaccion_simulacion(escritura=True) as db:
        exigir_modulo(db)
        previo = solicitud_anterior(db, "alta", entrada, usuario)
        if previo is not None:
            return previo
        cursor = db.execute("""
            INSERT INTO pos_clientes (nombre, telefono, referencia, id_usuario) VALUES (?, ?, ?, ?)
        """, (entrada.nombre, entrada.telefono, entrada.referencia, usuario["id_usuario"]))
        cliente = obtener_cliente(db, cursor.lastrowid)
        return guardar_solicitud(db, "alta", entrada, usuario, cursor.lastrowid, cliente)


def buscar_clientes(texto):
    with transaccion_simulacion() as db:
        exigir_modulo(db)
        db.create_function("casefold", 1, str.casefold, deterministic=True)
        filas = db.execute("""
            SELECT id_cliente, nombre, telefono, referencia FROM pos_clientes
            WHERE CAST(id_cliente AS TEXT) = :texto
               OR instr(casefold(nombre), :texto) > 0
               OR instr(casefold(COALESCE(telefono, '')), :texto) > 0
               OR instr(casefold(COALESCE(referencia, '')), :texto) > 0
            ORDER BY (CAST(id_cliente AS TEXT) = :texto) DESC, casefold(nombre), id_cliente
            LIMIT 50
        """, {"texto": texto.strip().casefold()}).fetchall()
        return [dict(zip(("id_cliente", "nombre", "telefono", "referencia"), fila)) for fila in filas]


def ventas_cliente(db, id_cliente):
    filas = db.execute("""
        SELECT v.id_venta, v.fecha, v.pedido, a.id_venta IS NOT NULL
        FROM pos_ventas_clientes AS c JOIN pos_ventas_simuladas AS v USING (id_venta)
        LEFT JOIN pos_anulaciones_simuladas AS a USING (id_venta)
        WHERE c.id_cliente = ? ORDER BY v.fecha, v.id_venta
    """, (id_cliente,))
    for venta, fecha, pedido, anulada in filas:
        pedido = json.loads(pedido)
        yield venta, fecha, pedido, estado_cuenta(db, venta, pedido, anulada)


def ficha_cliente(id_cliente):
    with transaccion_simulacion() as db:
        exigir_modulo(db)
        cliente = obtener_cliente(db, id_cliente)
        saldo = dict.fromkeys(SECCIONES, 0)
        ventas = []
        deuda_delivery = 0
        for venta, fecha, pedido, estado in ventas_cliente(db, id_cliente):
            deuda_delivery += estado.get('delivery', {}).get('saldo_cliente_centavos', 0)
            for seccion in SECCIONES:
                saldo[seccion] += estado["pendiente_por_seccion_centavos"][seccion]
            ventas.append({"id_venta": venta, "fecha": fecha, "items": pedido["items"], **estado,
                           "historial": eventos_venta(db, venta)})
        operaciones = [
            {"uuid": uuid, "tipo": tipo, "fecha": fecha, "id_usuario": usuario, **json.loads(resultado)}
            for uuid, tipo, fecha, usuario, resultado in db.execute("""
                SELECT uuid, tipo, fecha, id_usuario, resultado FROM pos_solicitudes_clientes
                WHERE id_cliente = ? AND tipo <> 'alta' ORDER BY rowid DESC
            """, (id_cliente,))
        ]
        return {**cliente, "saldo_centavos": sum(saldo.values()) + deuda_delivery, "saldo_por_seccion_centavos": saldo,
                **({'saldo_delivery_centavos': deuda_delivery} if deuda_delivery else {}),
                "ventas": ventas, "operaciones": operaciones}


def planificar(db, cliente, pago):
    pendiente = pago.importe_centavos
    plan = []
    for venta, _, pedido, estado in ventas_cliente(db, cliente):
        importe = min(pendiente, estado.get("saldo_cliente_centavos", estado["saldo_pendiente_centavos"]))
        if importe <= 0:
            continue
        plan.append((venta, pedido, estado, importe))
        pendiente -= importe
        if not pendiente:
            break
    if pendiente:
        raise HTTPException(409, "El abono supera el saldo pendiente del cliente.")
    return plan


def mostrar_plan(cliente, pago, plan):
    reparto = []
    for venta, _, estado, importe in plan:
        parte_productos = min(importe, estado['saldo_pendiente_centavos'])
        atribuido = imputar(estado["devengado_centavos"], estado["cobrado_centavos"] + parte_productos)
        reparto.append({"id_venta": venta, "importe_centavos": importe,
                        "saldo_anterior_centavos": estado.get("saldo_cliente_centavos", estado["saldo_pendiente_centavos"]),
                        **({'delivery_centavos': importe - parte_productos} if 'delivery' in estado else {}),
                        "por_seccion_centavos": {
                            s: atribuido[s] - estado["cobrado_atribuido_centavos"][s] for s in SECCIONES
                        }})
    huella = hashlib.sha256(json.dumps([cliente, pago.model_dump(), reparto], sort_keys=True).encode()).hexdigest()
    return {"vista_previa": huella, "imputaciones": reparto}


def prever_abono(cliente, pago):
    with transaccion_simulacion() as db:
        exigir_modulo(db)
        obtener_cliente(db, cliente)
        return mostrar_plan(cliente, pago, planificar(db, cliente, pago))


def abonar_cliente(cliente, entrada, usuario):
    with transaccion_simulacion(escritura=True) as db:
        exigir_modulo(db)
        obtener_cliente(db, cliente)
        previo = solicitud_anterior(db, "abono", entrada, usuario, cliente)
        if previo is not None:
            return previo
        pago = entrada.pago
        plan = planificar(db, cliente, pago)
        resultado = mostrar_plan(cliente, pago, plan)
        if resultado["vista_previa"] != entrada.vista_previa:
            raise HTTPException(409, "Cambió la distribución. Volvé a consultar la vista previa.")
        resultado["pago"] = pago.model_dump()
        guardar_solicitud(db, "abono", entrada, usuario, cliente, resultado)
        for indice, (venta, pedido, antes, importe) in enumerate(plan):
            evento, _ = iniciar_evento(db, "abono", usuario, entrada, venta, usar_uuid=False)
            db.execute("INSERT INTO pos_eventos_clientes VALUES (?, ?)", (evento, str(entrada.id_solicitud)))
            # El comprobante corresponde al cobro global. Solo una fila reserva su referencia única.
            parte = pago.model_copy(update={"importe_centavos": importe,
                                           "referencia": pago.referencia if indice == 0 else None})
            if es_sencillo(pedido):
                registrar_pago_conjunto(db, evento, venta, pedido, [parte], usuario)
            else:
                if parte.envio_directo:
                    raise HTTPException(422, 'La retención de efectivo corresponde al delivery sencillo.')
                registrar_pagos(db, evento, venta, [parte])
            despues = estado_cuenta(db, venta, pedido)
            terminar_evento(db, evento, {"id_venta": venta, **despues}, antes=antes, despues=despues)
        return resultado


def corregir_abono(cliente, uuid_abono, entrada: ReversionEntrada, usuario):
    with transaccion_simulacion(escritura=True) as db:
        exigir_modulo(db)
        obtener_cliente(db, cliente)
        anterior = solicitud_anterior(db, "correccion", entrada, usuario, cliente)
        if anterior is not None:
            if anterior["uuid_abono"] != uuid_abono:
                raise HTTPException(409, "La solicitud ya corresponde a otra corrección.")
            return anterior
        filas = db.execute("""
            SELECT m.id_movimiento, m.id_venta, m.receptor, m.medio_pago, m.importe_centavos,
                   v.pedido, a.id_venta IS NOT NULL,
                   EXISTS (SELECT 1 FROM pos_movimientos_simulados WHERE revierte = m.id_movimiento)
            FROM pos_solicitudes_clientes AS s JOIN pos_eventos_clientes AS c USING (uuid)
            JOIN pos_movimientos_simulados AS m USING (id_evento)
            JOIN pos_ventas_simuladas AS v USING (id_venta)
            LEFT JOIN pos_anulaciones_simuladas AS a USING (id_venta)
            WHERE s.uuid = ? AND s.tipo = 'abono' AND s.id_cliente = ?
            ORDER BY m.id_movimiento
        """, (uuid_abono, cliente)).fetchall()
        delivery = db.execute('''
            SELECT d.id_evento, d.id_venta, d.receptor, d.importe_centavos FROM pos_delivery_movimientos d
            JOIN pos_eventos_clientes c ON c.id_evento=d.id_evento_cobro
            WHERE c.uuid=? AND d.tipo='recepcion' AND EXISTS (
                SELECT 1 FROM pos_solicitudes_clientes WHERE uuid=c.uuid AND id_cliente=?)
        ''', (uuid_abono, cliente)).fetchall() if existe_delivery(db) else []
        if not filas and not delivery:
            raise HTTPException(404, "Abono global no encontrado.")
        if db.execute("SELECT 1 FROM pos_solicitudes_clientes WHERE tipo='correccion' AND json_extract(resultado,'$.uuid_abono')=?",
                      (uuid_abono,)).fetchone():
            raise HTTPException(409, 'El abono ya fue corregido.')
        if any(anulada or revertido for *_, anulada, revertido in filas):
            raise HTTPException(409, "El abono ya fue corregido o tiene un reembolso asociado.")
        resultado = {"uuid_abono": uuid_abono, "motivo": entrada.motivo,
                     "importe_centavos": sum(fila[4] for fila in filas) + sum(fila[3] for fila in delivery)}
        guardar_solicitud(db, "correccion", entrada, usuario, cliente, resultado)
        for origen, venta, receptor, importe in delivery:
            if db.execute('''SELECT 1 FROM pos_delivery_movimientos WHERE id_venta=? AND tipo='reembolso' ''', (venta,)).fetchone():
                raise HTTPException(409, 'El envío ya tiene un reembolso; revisá el historial antes de corregirlo.')
            mover_delivery(db, venta, 'reembolso', receptor, -importe, usuario,
                           f'correccion:{entrada.id_solicitud}:{origen}', entrada.motivo)
        for movimiento, venta, receptor, medio, importe, pedido, _, _ in filas:
            datos = json.loads(pedido)
            antes = estado_cuenta(db, venta, datos)
            evento, _ = iniciar_evento(db, "abono", usuario, entrada, venta, usar_uuid=False)
            db.execute("INSERT INTO pos_eventos_clientes VALUES (?, ?)", (evento, str(entrada.id_solicitud)))
            registrar_movimiento(db, evento, venta, receptor, medio, -importe, revierte=movimiento)
            despues = estado_cuenta(db, venta, datos)
            terminar_evento(db, evento, {"id_venta": venta, **despues}, antes=antes, despues=despues)
        return resultado
