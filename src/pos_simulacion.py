import json
import os
from collections import Counter
from contextlib import contextmanager
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator

from caja import CATEGORIAS_CAJA_BEBIDAS_POSTRES
from database import obtener_conexion, obtener_ruta_base
from pos_cobros import (
    Medio, PagoPos, caja_receptora, crear_libro, estado_cuenta, iniciar_evento,
    pagos_reversibles, receptor_original, registrar_movimiento,
    registrar_pagos, resumen_libro, terminar_evento,
)
from pos_pedidos import PedidoPos, calcular_pedido_pos


ID_SQLITE_SIMULACION = 0x41425031
VERSION_ESQUEMA_SIMULACION = 4


class VentaSimuladaEntrada(PedidoPos):
    id_solicitud: UUID
    total_esperado_centavos: int = Field(strict=True, gt=0, le=310_000_000_000_000_000)
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    medio_pago: Medio | None = None
    pagos: list[PagoPos] | None = Field(default=None, max_length=20)
    fiado: bool = Field(default=False, strict=True)
    deudor: str | None = Field(default=None, min_length=1, max_length=120)

    @model_validator(mode="after")
    def comprobar_modalidad(self):
        if self.medio_pago and (self.pagos is not None or self.fiado or self.deudor):
            raise ValueError("Elegí una sola modalidad de pago.")
        if not self.medio_pago and self.pagos is None:
            raise ValueError("Indicá los pagos de la venta, incluso si la lista está vacía.")
        if self.fiado != (self.deudor is not None):
            raise ValueError("Indicá el cliente o identificador para registrar el fiado.")
        return self


class AnulacionSimuladaEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    motivo: str = Field(min_length=1, max_length=300)
    id_solicitud: UUID | None = None


def seccion_del_item(item):
    categoria = item["categoria"].strip().lower()
    return "bebidas_postres" if categoria in CATEGORIAS_CAJA_BEBIDAS_POSTRES else "comidas"


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
    crear_libro(conexion)
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


def migrar_esquema_simulacion_v3(conexion):
    if (conexion.execute("PRAGMA application_id").fetchone()[0] != ID_SQLITE_SIMULACION
            or conexion.execute("PRAGMA user_version").fetchone()[0] != 3):
        raise ValueError("Se requiere una base ficticia marcada con el esquema POS 3.")
    with conexion:
        conexion.execute("BEGIN IMMEDIATE")
        conexion.execute("ALTER TABLE pos_movimientos_simulados RENAME TO pos_movimientos_v3")
        crear_libro(conexion)
        filas = conexion.execute("""
            SELECT v.id_venta, v.id_usuario, v.fecha, v.solicitud, v.pedido, 'venta',
                   (SELECT MIN(rowid) FROM pos_movimientos_v3 WHERE id_venta = v.id_venta AND tipo = 'venta') AS orden
            FROM pos_ventas_simuladas AS v
            UNION ALL
            SELECT a.id_venta, a.id_usuario, a.fecha, json_object('motivo', a.motivo), v.pedido, 'anulacion',
                   (SELECT MIN(rowid) FROM pos_movimientos_v3 WHERE id_venta = a.id_venta AND tipo = 'anulacion')
            FROM pos_anulaciones_simuladas AS a JOIN pos_ventas_simuladas AS v USING (id_venta)
            ORDER BY orden
        """).fetchall()
        for venta, usuario, fecha, solicitud, pedido_json, tipo, _ in filas:
            pedido = json.loads(pedido_json)
            for item in pedido["items"]:
                item["seccion"] = seccion_del_item(item)
            pedido["deudor"] = None
            if tipo == "venta":
                anterior = None
                normalizada = VentaSimuladaEntrada.model_validate(
                    {"id_solicitud": UUID(int=0), **json.loads(solicitud)}
                ).model_dump_json(exclude={"id_solicitud"})
                conexion.execute("""
                    UPDATE pos_ventas_simuladas SET solicitud = ?, pedido = ? WHERE id_venta = ?
                """, (normalizada, json.dumps(pedido, ensure_ascii=False), venta))
            else:
                anterior = estado_cuenta(conexion, venta, pedido)
            cursor = conexion.execute("""
                INSERT INTO pos_eventos_simulados (id_venta, id_usuario, fecha, solicitud, tipo, periodo)
                VALUES (?, ?, ?, ?, ?, 1)
            """, (venta, usuario, fecha, solicitud, tipo))
            evento = cursor.lastrowid
            if tipo == "anulacion":
                conexion.executemany("""
                    INSERT INTO pos_unidades_devueltas (id_evento, linea, cantidad) VALUES (?, ?, ?)
                """, [(evento, linea, item["cantidad"]) for linea, item in enumerate(pedido["items"], start=1)])
            for caja, medio, importe in conexion.execute("""
                SELECT caja, medio_pago, importe_centavos FROM pos_movimientos_v3
                WHERE id_venta = ? AND tipo = ? ORDER BY rowid
            """, (venta, tipo)):
                receptor = receptor_original(caja, medio)
                reversa = None
                if tipo == "anulacion":
                    reversa = conexion.execute("""
                        SELECT id_movimiento FROM pos_movimientos_simulados WHERE id_venta = ? AND receptor = ?
                    """, (venta, receptor)).fetchone()[0]
                registrar_movimiento(conexion, evento, venta, receptor, medio, importe, revierte=reversa)
            despues = estado_cuenta(conexion, venta, pedido, tipo == "anulacion")
            terminar_evento(conexion, evento, {"id_venta": venta, **despues}, antes=anterior, despues=despues)
        conexion.execute("DROP TABLE pos_movimientos_v3")
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
            pedido = json.loads(pedido_guardado)
            return {"id_venta": id_venta, "anulada": bool(anulada), **pedido,
                    **estado_cuenta(conexion, id_venta, pedido, anulada)}

        try:
            pedido = calcular_pedido_pos(conexion, entrada)
        except HTTPException as error:
            error.headers = {**(error.headers or {}), "X-POS-Resultado": "PEDIDO_RECHAZADO"}
            raise
        if pedido["total_centavos"] != entrada.total_esperado_centavos:
            raise HTTPException(409, {
                "codigo": "TOTAL_MODIFICADO",
                "mensaje": "Cambió el total. Volvé a validar el pedido.",
                "total_centavos": pedido["total_centavos"],
            })

        subtotales = Counter()
        stock = Counter()
        for item in pedido["items"]:
            seccion = seccion_del_item(item)
            item["seccion"] = seccion
            subtotales[seccion] += item["subtotal_centavos"]
            if item["controla_stock"]:
                stock[item["id_producto"]] += item["cantidad"]
        pedido["cajas_centavos"] = dict(subtotales)
        pedido["deudor"] = entrada.deudor

        pagos = entrada.pagos
        if entrada.medio_pago:
            pagos = [
                PagoPos(receptor=receptor_original(caja, entrada.medio_pago), medio_pago=entrada.medio_pago,
                        importe_centavos=subtotal)
                for caja, subtotal in subtotales.items()
            ]
        cobrado = sum(pago.importe_centavos for pago in pagos)
        if cobrado > pedido["total_centavos"] or entrada.fiado != (cobrado < pedido["total_centavos"]):
            raise HTTPException(422, "Los cobros deben cubrir el total o dejar un saldo en la modalidad fiada.")
        medios = {pago.medio_pago for pago in pagos}
        pedido["medio_pago"] = medios.pop() if len(medios) == 1 and not entrada.fiado else None

        cursor = conexion.execute(
            "INSERT INTO pos_ventas_simuladas (id_usuario, id_solicitud, solicitud, pedido) VALUES (?, ?, ?, ?)",
            (*clave, solicitud, json.dumps(pedido, ensure_ascii=False)),
        )
        id_venta = cursor.lastrowid
        evento, _ = iniciar_evento(conexion, "venta", usuario, entrada, id_venta, usar_uuid=False)
        try:
            registrar_pagos(conexion, evento, id_venta, pagos)
        except HTTPException as error:
            error.headers = {"X-POS-Resultado": "PAGO_RECHAZADO"}
            raise
        conexion.executemany(
            "UPDATE productos SET stock = stock - ? WHERE id_producto = ?",
            [(cantidad, id_producto) for id_producto, cantidad in stock.items()],
        )
        estado = estado_cuenta(conexion, id_venta, pedido)
        resultado = {"id_venta": id_venta, "anulada": False, **pedido, **estado}
        return terminar_evento(conexion, evento, resultado, despues=estado)


def consultar_venta(conexion, id_venta, usuario):
    fila = conexion.execute("""
        SELECT v.pedido, a.id_venta IS NOT NULL
        FROM pos_ventas_simuladas AS v LEFT JOIN pos_anulaciones_simuladas AS a USING (id_venta)
        WHERE v.id_venta = ? AND (? = 'admin' OR v.id_usuario = ?)
    """, (id_venta, usuario["rol"], usuario["id_usuario"])).fetchone()
    if fila is None:
        raise HTTPException(404, "Venta simulada no encontrada.")
    return json.loads(fila[0]), bool(fila[1])


def abonar_venta_simulada(id_venta, entrada, usuario):
    with transaccion_simulacion(escritura=True) as conexion:
        pedido, anulada = consultar_venta(conexion, id_venta, usuario)
        evento, previo = iniciar_evento(conexion, "abono", usuario, entrada, id_venta)
        if previo is not None:
            return previo
        antes = estado_cuenta(conexion, id_venta, pedido, anulada)
        if sum(pago.importe_centavos for pago in entrada.pagos) > antes["saldo_pendiente_centavos"]:
            raise HTTPException(409, "El abono supera el saldo pendiente.")
        registrar_pagos(conexion, evento, id_venta, entrada.pagos)
        despues = estado_cuenta(conexion, id_venta, pedido)
        return terminar_evento(conexion, evento, {"id_venta": id_venta, **despues}, antes=antes, despues=despues)


def revertir_venta_simulada(id_venta, entrada, usuario, *, tipo):
    with transaccion_simulacion(escritura=True) as conexion:
        pedido, anulada = consultar_venta(conexion, id_venta, usuario)
        evento, previo = iniciar_evento(conexion, tipo, usuario, entrada, id_venta)
        if previo is not None:
            return previo
        if anulada:
            raise HTTPException(409, "La venta simulada ya está anulada.")
        antes = estado_cuenta(conexion, id_venta, pedido)
        stock = Counter()
        reversas = Counter()
        if tipo == "anulacion":
            for linea, item in enumerate(pedido["items"], start=1):
                cantidad = item["cantidad"] - antes["unidades_devueltas"].get(linea, 0)
                if cantidad:
                    reversas[linea] = cantidad
        else:
            for item in entrada.items:
                reversas[item.linea] += item.cantidad

        if not reversas:
            raise HTTPException(409, "La venta ya fue devuelta por completo.")
        valor_devuelto = 0
        for linea, cantidad in reversas.items():
            if linea > len(pedido["items"]):
                raise HTTPException(422, "La línea seleccionada no existe en la venta.")
            item = pedido["items"][linea - 1]
            if cantidad > item["cantidad"] - antes["unidades_devueltas"].get(linea, 0):
                raise HTTPException(409, "La devolución supera las unidades disponibles.")
            valor_devuelto += cantidad * item["precio_unitario_centavos"]
            if item["controla_stock"]:
                stock[item["id_producto"]] += cantidad
        conexion.executemany("""
            INSERT INTO pos_unidades_devueltas (id_evento, linea, cantidad) VALUES (?, ?, ?)
        """, [(evento, linea, cantidad) for linea, cantidad in reversas.items()])
        cursor = conexion.executemany(
            "UPDATE productos SET stock = stock + ? WHERE id_producto = ?",
            [(cantidad, producto) for producto, cantidad in stock.items()],
        )
        if cursor.rowcount != len(stock):
            raise HTTPException(409, "Falta un producto cuyo stock debe restaurarse.")

        a_reembolsar = max(0, valor_devuelto - antes["saldo_pendiente_centavos"])
        reembolsado = a_reembolsar
        for movimiento, receptor, medio, disponible in pagos_reversibles(conexion, id_venta):
            if not a_reembolsar:
                break
            importe = min(disponible, a_reembolsar)
            registrar_movimiento(conexion, evento, id_venta, receptor, medio, -importe, revierte=movimiento)
            a_reembolsar -= importe
        if a_reembolsar:
            raise HTTPException(409, "No se pudo conciliar el reembolso.")
        if tipo == "anulacion":
            conexion.execute("""
                INSERT INTO pos_anulaciones_simuladas (id_venta, id_usuario, motivo)
                VALUES (?, ?, ?)
            """, (id_venta, usuario["id_usuario"], entrada.motivo))
        despues = estado_cuenta(conexion, id_venta, pedido, tipo == "anulacion")
        resultado = {"id_venta": id_venta, "anulada": tipo == "anulacion",
                     "reembolsado_centavos": reembolsado, **despues}
        return terminar_evento(conexion, evento, resultado, antes=antes, despues=despues)


def transferir_simulado(entrada, usuario):
    with transaccion_simulacion(escritura=True) as conexion:
        evento, previo = iniciar_evento(conexion, "transferencia_interna", usuario, entrada)
        if previo is not None:
            return previo
        origen, destino = caja_receptora(entrada.origen), caja_receptora(entrada.destino)
        if origen == destino:
            raise HTTPException(422, "Elegí receptores de secciones distintas.")
        resumen = resumen_libro(conexion)
        disponible = next((r["saldo_centavos"] for r in resumen["receptores"] if r["receptor"] == entrada.origen), 0)
        por_distribuir = resumen["secciones"][destino]["por_distribuir_centavos"]
        if entrada.importe_centavos > min(disponible, por_distribuir):
            raise HTTPException(409, "La transferencia supera el saldo disponible o la distribución pendiente.")
        registrar_movimiento(conexion, evento, None, entrada.origen, None, -entrada.importe_centavos)
        registrar_movimiento(conexion, evento, None, entrada.destino, None, entrada.importe_centavos)
        return terminar_evento(conexion, evento, {"id_evento": evento, **resumen_libro(conexion)})


def cerrar_periodo_simulado(entrada, usuario):
    with transaccion_simulacion(escritura=True) as conexion:
        evento, previo = iniciar_evento(conexion, "cierre", usuario, entrada)
        if previo is not None:
            return previo
        resumen = consultar_cajas_simuladas(conexion)
        periodo = resumen["periodo_abierto"]
        if entrada.periodo != periodo:
            raise HTTPException(409, "El período cambió. Volvé a consultar las cajas.")
        fecha = conexion.execute("SELECT fecha FROM pos_eventos_simulados WHERE id_evento = ?", (evento,)).fetchone()[0]
        resultado = {"periodo": periodo, "id_evento": evento, "resumen": resumen, "fecha": fecha,
                     "id_usuario": usuario["id_usuario"], "motivo": entrada.motivo}
        conexion.execute("""
            INSERT INTO pos_cierres_simulados (periodo, id_evento, resumen) VALUES (?, ?, ?)
        """, (periodo, evento, json.dumps(resultado, ensure_ascii=False)))
        return terminar_evento(conexion, evento, resultado)


def consultar_cierre_simulado(periodo):
    with transaccion_simulacion() as conexion:
        fila = conexion.execute("SELECT resumen FROM pos_cierres_simulados WHERE periodo = ?", (periodo,)).fetchone()
        if fila is None:
            raise HTTPException(404, "Cierre simulado no encontrado.")
        return json.loads(fila[0])


def eventos_venta(conexion, id_venta):
    eventos = conexion.execute("""
        SELECT id_evento, tipo, periodo, fecha, id_usuario, solicitud,
               devengado_comidas, devengado_bebidas, cobrado_comidas, cobrado_bebidas
        FROM pos_eventos_simulados WHERE id_venta = ? ORDER BY id_evento
    """, (id_venta,)).fetchall()
    movimientos = {}
    for evento, mov, receptor, medio, importe, referencia, revierte in conexion.execute("""
        SELECT id_evento, id_movimiento, receptor, medio_pago, importe_centavos, referencia, revierte
        FROM pos_movimientos_simulados WHERE id_venta = ? ORDER BY id_movimiento
    """, (id_venta,)):
        movimientos.setdefault(evento, []).append({
            "id_movimiento": mov, "receptor": receptor, "medio_pago": medio,
            "importe_centavos": importe, "referencia": referencia, "revierte": revierte,
        })
    devueltas = {}
    for evento, linea, cantidad in conexion.execute("""
        SELECT id_evento, linea, cantidad FROM pos_unidades_devueltas
        JOIN pos_eventos_simulados USING (id_evento) WHERE id_venta = ? ORDER BY linea
    """, (id_venta,)):
        devueltas.setdefault(evento, []).append({"linea": linea, "cantidad": cantidad})
    return [
        {"id_evento": evento, "tipo": tipo, "periodo": periodo, "fecha": fecha, "id_usuario": usuario,
         "devengado_centavos": {"comidas": dev_c, "bebidas_postres": dev_b},
         "cobrado_atribuido_centavos": {"comidas": cob_c, "bebidas_postres": cob_b},
         "motivo": json.loads(solicitud).get("motivo"),
         "unidades_devueltas": devueltas.get(evento, []),
         "movimientos": movimientos.get(evento, [])}
        for evento, tipo, periodo, fecha, usuario, solicitud, dev_c, dev_b, cob_c, cob_b in eventos
    ]


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

        ventas = []
        for id_venta, fecha, autor, pedido_json, anulador, fecha_anulacion, motivo in filas[:limite]:
            pedido = json.loads(pedido_json)
            ventas.append({
                "id_venta": id_venta, "fecha": fecha, "id_usuario": autor, "anulada": anulador is not None,
                "anulacion": {"id_usuario": anulador, "fecha": fecha_anulacion, "motivo": motivo} if anulador else None,
                **pedido, **estado_cuenta(conexion, id_venta, pedido, anulador is not None),
                "historial": eventos_venta(conexion, id_venta),
            })
    return {"ventas": ventas, "siguiente_antes_de": ventas[-1]["id_venta"] if len(filas) > limite else None}


def consultar_cajas_simuladas(conexion=None):
    if conexion is None:
        with transaccion_simulacion() as lectura:
            return consultar_cajas_simuladas(lectura)
    filas = conexion.execute("""
        SELECT caja, medio_pago, SUM(importe_centavos) FROM pos_movimientos_simulados
        WHERE medio_pago IS NOT NULL GROUP BY caja, medio_pago ORDER BY caja, medio_pago
    """).fetchall()
    return {
        **resumen_libro(conexion),
        "saldos": [{"caja": caja, "medio_pago": medio, "saldo_centavos": saldo} for caja, medio, saldo in filas],
    }


def consultar_movimientos_simulados(caja, antes_de, limite):
    with transaccion_simulacion() as conexion:
        filas = conexion.execute(
            """
            SELECT m.id_movimiento, m.id_venta, m.medio_pago, e.tipo, m.importe_centavos,
                   e.fecha, e.id_usuario, m.receptor, e.periodo, e.id_evento, m.revierte, m.referencia,
                   json_extract(e.solicitud, '$.motivo')
            FROM pos_movimientos_simulados AS m JOIN pos_eventos_simulados AS e USING (id_evento)
            WHERE m.caja = :caja AND (:antes_de IS NULL OR m.id_movimiento < :antes_de)
            ORDER BY m.id_movimiento DESC
            LIMIT :limite
            """, {"caja": caja, "antes_de": antes_de, "limite": limite + 1},
        ).fetchall()

    movimientos = [
        {
            "id_venta": id_venta, "medio_pago": medio, "tipo": tipo,
            "importe_centavos": importe, "fecha": fecha, "id_usuario": id_usuario,
            "receptor": receptor, "periodo": periodo, "id_evento": evento,
            "id_movimiento": movimiento, "revierte": revierte, "referencia": referencia, "motivo": motivo,
        }
        for movimiento, id_venta, medio, tipo, importe, fecha, id_usuario, receptor, periodo,
        evento, revierte, referencia, motivo in filas[:limite]
    ]
    siguiente = filas[limite - 1][0] if len(filas) > limite else None
    return {"movimientos": movimientos, "siguiente_antes_de": siguiente}
