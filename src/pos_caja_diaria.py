"""Arqueo físico del POS en copias ficticias de etapa 6."""
import json
from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import HTTPException


CAJAS = ("comidas", "bebidas_postres")
Caja = Literal["comidas", "bebidas_postres"]
ZONA = "America/Argentina/Buenos_Aires"


def ahora_local():
    return datetime.now(ZoneInfo(ZONA)).isoformat(timespec="microseconds")


def crear_caja_diaria(db):
    """Se llama al preparar una nueva copia marcada del puente."""
    db.execute("""
        CREATE TABLE pos_inicio_caja_diaria (
            ultimo_movimiento_anterior INTEGER NOT NULL
        )
    """)
    db.execute("""
        INSERT INTO pos_inicio_caja_diaria
        SELECT COALESCE(MAX(id_movimiento), 0) FROM pos_movimientos_simulados
    """)
    db.execute("""
        CREATE TABLE pos_jornadas_caja (
            id_jornada INTEGER PRIMARY KEY,
            caja TEXT NOT NULL CHECK (caja IN ('comidas', 'bebidas_postres')),
            fecha TEXT NOT NULL,
            cerrada INTEGER NOT NULL DEFAULT 0 CHECK (cerrada IN (0, 1)),
            UNIQUE (caja, fecha)
        )
    """)
    db.execute("""
        CREATE UNIQUE INDEX pos_jornada_caja_abierta ON pos_jornadas_caja (caja)
        WHERE cerrada = 0
    """)
    db.execute("""
        CREATE TABLE pos_diario_caja (
            id_evento INTEGER PRIMARY KEY,
            id_jornada INTEGER NOT NULL REFERENCES pos_jornadas_caja,
            tipo TEXT NOT NULL CHECK (tipo IN (
                'apertura', 'cobro', 'reembolso', 'transferencia', 'gasto',
                'aporte', 'retiro', 'arqueo', 'cierre'
            )),
            fecha_hora TEXT NOT NULL,
            id_usuario INTEGER NOT NULL REFERENCES usuarios_pos,
            usuario TEXT NOT NULL,
            rol TEXT NOT NULL,
            id_solicitud TEXT UNIQUE,
            solicitud TEXT,
            resultado TEXT,
            importe_centavos INTEGER,
            motivo TEXT,
            id_movimiento_pos INTEGER UNIQUE REFERENCES pos_movimientos_simulados
        )
    """)
    db.execute("CREATE INDEX pos_diario_por_jornada ON pos_diario_caja (id_jornada, id_evento)")
    db.execute("""
        CREATE UNIQUE INDEX pos_diario_apertura_cierre ON pos_diario_caja (id_jornada, tipo)
        WHERE tipo IN ('apertura', 'cierre')
    """)


def caja_diaria_activa(db):
    return db.execute("""
        SELECT 1 FROM sqlite_schema WHERE type = 'table' AND name = 'pos_inicio_caja_diaria'
    """).fetchone() is not None


def exigir_caja_diaria(db):
    if not caja_diaria_activa(db):
        raise HTTPException(404, "Prepará una copia ficticia para la etapa 6.")


def jornada_abierta(db, caja):
    return db.execute("""
        SELECT id_jornada, fecha FROM pos_jornadas_caja WHERE caja = ? AND cerrada = 0
    """, (caja,)).fetchone()


def exigir_jornada_actual(db, caja, fecha):
    jornada = jornada_abierta(db, caja)
    if not jornada or jornada[1] != fecha:
        nombre = "Rotisería / Comidas" if caja == "comidas" else "Bebidas y Postres"
        raise HTTPException(409, f"Abrí la caja de {nombre} para hoy antes de mover efectivo.")
    return jornada[0]


def guardar_evento(db, jornada, tipo, momento, usuario, *, importe=None, motivo=None,
                   movimiento_pos=None, clave=None, solicitud=None, resultado=None):
    cursor = db.execute("""
        INSERT INTO pos_diario_caja (
            id_jornada, tipo, fecha_hora, id_usuario, usuario, rol, importe_centavos,
            motivo, id_movimiento_pos, id_solicitud, solicitud, resultado
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (jornada, tipo, momento, usuario["id_usuario"], usuario["usuario"], usuario["rol"],
          importe, motivo, movimiento_pos, clave, solicitud,
          json.dumps(resultado, ensure_ascii=False) if resultado is not None else None))
    return cursor.lastrowid


def vincular_movimiento_pos(db, movimiento, evento, receptor, importe):
    if not receptor.endswith("_efectivo") or not caja_diaria_activa(db):
        return
    tipo, autor, usuario, rol, solicitud = db.execute("""
        SELECT e.tipo, e.id_usuario, u.usuario, u.rol, e.solicitud
        FROM pos_eventos_simulados AS e JOIN usuarios_pos AS u USING (id_usuario)
        WHERE e.id_evento = ?
    """, (evento,)).fetchone()
    momento = ahora_local()
    jornada = exigir_jornada_actual(db, receptor.removesuffix("_efectivo"), momento[:10])
    categoria = "transferencia" if tipo == "transferencia_interna" else (
        "cobro" if importe > 0 else "reembolso"
    )
    guardar_evento(
        db, jornada, categoria, momento, {"id_usuario": autor, "usuario": usuario, "rol": rol},
        importe=importe, motivo=json.loads(solicitud).get("motivo"), movimiento_pos=movimiento,
    )


def leer_evento(fila):
    evento, tipo, momento, autor, usuario, rol, importe, motivo, movimiento, resultado = fila
    return {
        "id_evento": evento, "tipo": tipo, "fecha_hora": momento, "id_usuario": autor,
        "usuario": usuario, "rol": rol, "importe_centavos": importe, "motivo": motivo,
        "id_movimiento_pos": movimiento, "resultado": json.loads(resultado) if resultado else None,
    }


CAMPOS_EVENTO = """
    id_evento, tipo, fecha_hora, id_usuario, usuario, rol, importe_centavos,
    motivo, id_movimiento_pos, resultado
"""


def ultimo_evento(db, jornada, tipo):
    fila = db.execute(f"""
        SELECT {CAMPOS_EVENTO} FROM pos_diario_caja
        WHERE id_jornada = ? AND tipo = ? ORDER BY id_evento DESC LIMIT 1
    """, (jornada, tipo)).fetchone()
    return leer_evento(fila) if fila else None


def saldo_fisico(db, jornada):
    importes = {}
    revision = 0
    for evento, tipo, importe in db.execute("""
        SELECT id_evento, tipo, importe_centavos FROM pos_diario_caja
        WHERE id_jornada = ? AND importe_centavos IS NOT NULL ORDER BY id_evento
    """, (jornada,)):
        importes[tipo] = importes.get(tipo, 0) + importe
        revision = evento
    return {"esperado_centavos": sum(importes.values()), "movimientos_centavos": importes,
            "revision_efectivo": revision}


def detalle_jornada(db, fila):
    jornada, caja, fecha, cerrada = fila
    arqueo = ultimo_evento(db, jornada, "arqueo")
    cierre = ultimo_evento(db, jornada, "cierre")
    saldo = cierre["resultado"]["saldo"] if cierre else saldo_fisico(db, jornada)
    return {
        "id_jornada": jornada, "caja": caja, "fecha": fecha, "cerrada": bool(cerrada),
        "apertura": ultimo_evento(db, jornada, "apertura"), "arqueo": arqueo, "cierre": cierre,
        "arqueo_vigente": bool(arqueo and arqueo["resultado"]["revision_efectivo"] == saldo["revision_efectivo"]),
        **saldo,
    }


def cierre_anterior(db, caja, fecha):
    fila = db.execute("""
        SELECT j.fecha, d.resultado FROM pos_jornadas_caja AS j
        JOIN pos_diario_caja AS d USING (id_jornada)
        WHERE j.caja = ? AND j.fecha < ? AND j.cerrada = 1 AND d.tipo = 'cierre'
        ORDER BY j.fecha DESC LIMIT 1
    """, (caja, fecha)).fetchone()
    if fila is None:
        return None
    return {"fecha": fila[0], "contado_centavos": json.loads(fila[1])["arqueo"]["resultado"]["contado_centavos"]}


def alertas_cierre(db, antes_de, limite):
    alertas = [
        {"id_evento": evento, "caja": caja, "fecha": fecha, "usuario": usuario,
         "observacion": motivo, "diferencia_centavos": json.loads(resultado)["arqueo"]["resultado"]["diferencia_centavos"]}
        for evento, caja, fecha, usuario, motivo, resultado in db.execute("""
            SELECT d.id_evento, j.caja, j.fecha, d.usuario, d.motivo, d.resultado
            FROM pos_diario_caja AS d JOIN pos_jornadas_caja AS j USING (id_jornada)
            WHERE d.tipo = 'cierre' AND d.id_evento < ?
              AND json_extract(d.resultado, '$.alerta_administracion') = 1
            ORDER BY d.id_evento DESC LIMIT ?
        """, (antes_de, limite + 1))
    ]
    return {"alertas": alertas[:limite],
            "siguiente_antes_de": alertas[limite - 1]["id_evento"] if len(alertas) > limite else None}


def estado_cajas(db):
    momento = ahora_local()
    fecha = momento[:10]
    cajas = {}
    propuestas = {}
    for caja in CAJAS:
        fila = db.execute("""
            SELECT id_jornada, caja, fecha, cerrada FROM pos_jornadas_caja
            WHERE caja = ? AND (cerrada = 0 OR fecha = ?) ORDER BY cerrada LIMIT 1
        """, (caja, fecha)).fetchone()
        cajas[caja] = detalle_jornada(db, fila) if fila else None
        if not fila and "10:00" <= momento[11:16] < "12:00":
            propuestas[caja] = cierre_anterior(db, caja, fecha)
    return {"fecha_local": fecha, "zona_horaria": ZONA, "cajas": cajas, "propuestas_apertura": propuestas}


def conciliar_caja_diaria(db):
    diferencias = [
        {"codigo": "MOVIMIENTO_FISICO_SIN_CONCILIAR", "id_movimiento": movimiento}
        for movimiento, in db.execute("""
            SELECT m.id_movimiento FROM pos_movimientos_simulados AS m
            JOIN pos_inicio_caja_diaria AS i ON m.id_movimiento > i.ultimo_movimiento_anterior
            LEFT JOIN pos_diario_caja AS d ON d.id_movimiento_pos = m.id_movimiento
            LEFT JOIN pos_jornadas_caja AS j ON j.id_jornada = d.id_jornada
            WHERE m.receptor IN ('comidas_efectivo', 'bebidas_postres_efectivo')
              AND (d.importe_centavos IS NOT m.importe_centavos OR j.caja IS NOT m.caja)
        """)
    ]
    for jornada, in db.execute("SELECT id_jornada FROM pos_jornadas_caja WHERE cerrada = 1"):
        cierre = ultimo_evento(db, jornada, "cierre")
        if not cierre or cierre["resultado"]["saldo"] != saldo_fisico(db, jornada):
            diferencias.append({"codigo": "CIERRE_DIARIO_DESCUADRADO", "id_jornada": jornada})
    return diferencias


def historial_caja(db, caja, antes_de, limite):
    filas = db.execute("""
        SELECT id_jornada, caja, fecha, cerrada FROM pos_jornadas_caja
        WHERE caja = ? AND id_jornada < ? ORDER BY id_jornada DESC LIMIT ?
    """, (caja, antes_de, limite + 1)).fetchall()
    return {
        "jornadas": [detalle_jornada(db, fila) for fila in filas[:limite]],
        "siguiente_antes_de": filas[limite - 1][0] if len(filas) > limite else None,
    }


def historial_eventos(db, caja, jornada, antes_de, limite):
    if not db.execute("SELECT 1 FROM pos_jornadas_caja WHERE id_jornada = ? AND caja = ?",
                      (jornada, caja)).fetchone():
        raise HTTPException(404, "Jornada de caja no encontrada.")
    filas = db.execute(f"""
        SELECT {CAMPOS_EVENTO} FROM pos_diario_caja
        WHERE id_jornada = ? AND id_evento < ? ORDER BY id_evento DESC LIMIT ?
    """, (jornada, antes_de, limite + 1)).fetchall()
    return {
        "eventos": [leer_evento(fila) for fila in filas[:limite]],
        "siguiente_antes_de": filas[limite - 1][0] if len(filas) > limite else None,
    }


def registrar_operacion(db, caja, tipo, entrada, usuario):
    clave = str(entrada.id_solicitud)
    solicitud = entrada.model_dump_json(exclude={"id_solicitud"})
    previo = db.execute("""
        SELECT j.caja, d.tipo, d.id_usuario, d.solicitud, d.resultado, d.id_evento
        FROM pos_diario_caja AS d JOIN pos_jornadas_caja AS j USING (id_jornada)
        WHERE d.id_solicitud = ?
    """, (clave,)).fetchone()
    if previo:
        if previo[:4] != (caja, tipo, usuario["id_usuario"], solicitud):
            raise HTTPException(409, "La solicitud ya corresponde a otra operación.")
        return {"id_evento": previo[5], **json.loads(previo[4])}

    momento = ahora_local()
    fecha = momento[:10]
    importe = None
    motivo = (getattr(entrada, "motivo", None) or "").strip() or None
    resultado = {}
    if tipo == "apertura":
        if entrada.fecha.isoformat() != fecha:
            raise HTTPException(409, "Cambió la fecha local. Actualizá el estado de las cajas.")
        if jornada_abierta(db, caja) or db.execute("""
            SELECT 1 FROM pos_jornadas_caja WHERE caja = ? AND fecha = ?
        """, (caja, fecha)).fetchone():
            raise HTTPException(409, "La caja ya tiene una jornada abierta o cerrada para hoy.")
        jornada = db.execute("INSERT INTO pos_jornadas_caja (caja, fecha) VALUES (?, ?)",
                             (caja, fecha)).lastrowid
        importe = entrada.inicial_centavos
        referencia = cierre_anterior(db, caja, fecha)
        if referencia:
            resultado.update(
                referencia_anterior=referencia,
                diferencia_centavos=importe - referencia["contado_centavos"],
            )
    else:
        abierta = jornada_abierta(db, caja)
        if not abierta or abierta[0] != entrada.id_jornada:
            raise HTTPException(409, "La jornada indicada ya no está abierta.")
        jornada = abierta[0]
        if tipo == "arqueo":
            saldo = saldo_fisico(db, jornada)
            if saldo["revision_efectivo"] != entrada.revision_efectivo:
                raise HTTPException(409, "Cambió el efectivo. Actualizá y volvé a contar la caja.")
            diferencia = entrada.contado_centavos - saldo["esperado_centavos"]
            if diferencia and not motivo:
                raise HTTPException(422, "Indicá el motivo de la diferencia.")
            resultado = {**saldo, "contado_centavos": entrada.contado_centavos,
                         "diferencia_centavos": diferencia}
        elif tipo == "cierre":
            saldo = saldo_fisico(db, jornada)
            arqueo = ultimo_evento(db, jornada, "arqueo")
            if (not arqueo or arqueo["id_evento"] != entrada.id_arqueo
                    or arqueo["resultado"]["revision_efectivo"] != saldo["revision_efectivo"]):
                raise HTTPException(409, "Se requiere el último arqueo y debe estar vigente.")
            alerta = arqueo["resultado"]["diferencia_centavos"] != 0
            motivo = arqueo["motivo"] if alerta else None
            if alerta and not (motivo or "").strip():
                raise HTTPException(422, "Registrá un arqueo con una observación para la diferencia.")
            resultado = {"saldo": saldo, "arqueo": arqueo,
                         "autorizado_por": None, "alerta_administracion": alerta}
            db.execute("UPDATE pos_jornadas_caja SET cerrada = 1 WHERE id_jornada = ?", (jornada,))
        else:
            exigir_jornada_actual(db, caja, fecha)
            if not motivo:
                raise HTTPException(422, "Indicá el motivo del movimiento.")
            if tipo == "retiro" and entrada.importe_centavos > saldo_fisico(db, jornada)["esperado_centavos"]:
                raise HTTPException(409, "La caja no tiene efectivo suficiente para el retiro.")
            importe = entrada.importe_centavos if tipo == "aporte" else -entrada.importe_centavos
    resultado.update(id_jornada=jornada, caja=caja, fecha_hora=momento)
    evento = guardar_evento(db, jornada, tipo, momento, usuario, importe=importe, motivo=motivo,
                            clave=clave, solicitud=solicitud, resultado=resultado)
    return {"id_evento": evento, **resultado}
