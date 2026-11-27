"""Contabilidad de etapa 7 sobre los registros de origen de una copia ficticia."""
import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from pos_caja_diaria import ZONA
from pos_cobros import SECCIONES


def fecha_local():
    return datetime.now(ZoneInfo(ZONA)).date().isoformat()


def corte_contable(db):
    if not db.execute("""
        SELECT 1 FROM sqlite_schema WHERE type = 'table' AND name = 'pos_inicio_contable'
    """).fetchone():
        return None
    return db.execute("""
        SELECT fecha, ultimo_evento_pos, ultimo_evento_diario FROM pos_inicio_contable
    """).fetchone()


def etapa_contable_activa(db):
    from database import RUTA_ENTRENAMIENTO, obtener_ruta_base
    from pos_simulacion import ID_SQLITE_SIMULACION, VERSION_ESQUEMA_SIMULACION

    entrenamiento = RUTA_ENTRENAMIENTO.get() is not None
    if not entrenamiento and (
        os.getenv("POS_V1_SIMULACION") != "1" or os.getenv("ABADION_PUENTE_FICTICIO") != "1"
    ):
        return False

    from migraciones import verificar_version
    try:
        verificar_version(db, VERSION_ESQUEMA_SIMULACION)
    except ValueError:
        return False

    return (
        (entrenamiento or bool(os.getenv("NEGOCIO_DB_PATH")))
        and obtener_ruta_base().resolve().name.casefold() != "negocio.db"
        and db.execute("PRAGMA application_id").fetchone()[0] == ID_SQLITE_SIMULACION
        and corte_contable(db) is not None
    )


def crear_integracion_contable(db):
    db.execute("""
        CREATE TABLE pos_inicio_contable (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            fecha TEXT NOT NULL,
            ultimo_evento_pos INTEGER NOT NULL,
            ultimo_evento_diario INTEGER NOT NULL
        )
    """)
    db.execute("""
        INSERT INTO pos_inicio_contable VALUES (
            1, ?, (SELECT COALESCE(MAX(id_evento), 0) FROM pos_eventos_simulados),
            (SELECT COALESCE(MAX(id_evento), 0) FROM pos_diario_caja)
        )
    """, (fecha_local(),))
    db.execute("""
        CREATE TABLE pos_costos_contables (
            tipo TEXT NOT NULL CHECK (tipo IN ('compra', 'gasto')),
            id_origen INTEGER NOT NULL,
            evento TEXT NOT NULL CHECK (evento IN ('alta', 'anulacion')),
            fecha TEXT NOT NULL,
            importe_centavos INTEGER NOT NULL,
            seccion TEXT,
            medio_declarado TEXT,
            PRIMARY KEY (tipo, id_origen, evento)
        )
    """)
    db.execute("CREATE INDEX pos_costos_por_fecha ON pos_costos_contables (fecha)")
    db.execute("""
        CREATE TABLE pos_cierres_contables (
            tipo TEXT NOT NULL CHECK (tipo IN ('semanal', 'mensual')),
            id_cierre INTEGER NOT NULL,
            resumen TEXT NOT NULL,
            PRIMARY KEY (tipo, id_cierre)
        )
    """)
    # El libro legado sigue siendo dueño de su stock y de los datos del costo.
    # Sus altas y reversos emiten el cambio contable en la misma transacción.
    for tabla, tipo, clave, anulada, importe, seccion, medio in (
        ("compras", "compra", "id_compra", "anulada", "NEW.cantidad * NEW.precio_unitario",
         """(SELECT CASE WHEN lower(trim(categoria)) IN ('bebidas', 'postres')
                     THEN 'bebidas_postres' ELSE 'comidas' END
              FROM productos WHERE id_producto = NEW.id_producto)""", "NEW.medio_pago"),
        ("gastos", "gasto", "id_gasto", "anulado", "NEW.valor_final", "NEW.seccion", "NULL"),
    ):
        db.execute(f"""
            CREATE TRIGGER pos_contable_{tabla}_alta AFTER INSERT ON {tabla}
            WHEN NEW.{anulada} = 0
            BEGIN
                INSERT INTO pos_costos_contables
                VALUES ('{tipo}', NEW.{clave}, 'alta', date('now', '-3 hours'),
                        CAST(round(({importe}) * 100) AS INTEGER), {seccion}, {medio});
            END
        """)
        db.execute(f"""
            CREATE TRIGGER pos_contable_{tabla}_anulacion AFTER UPDATE OF {anulada} ON {tabla}
            WHEN OLD.{anulada} = 0 AND NEW.{anulada} = 1
            BEGIN
                SELECT CASE WHEN NOT EXISTS (
                    SELECT 1 FROM pos_costos_contables
                    WHERE tipo = '{tipo}' AND id_origen = OLD.{clave} AND evento = 'alta'
                ) THEN RAISE(ABORT, 'El costo es anterior al corte contable ficticio.') END;
                INSERT INTO pos_costos_contables
                SELECT tipo, id_origen, 'anulacion', date('now', '-3 hours'),
                       -importe_centavos, seccion, medio_declarado
                FROM pos_costos_contables
                WHERE tipo = '{tipo}' AND id_origen = OLD.{clave} AND evento = 'alta';
            END
        """)
    for sql, nombre in (("INSERT", "alta"), ("UPDATE", "cambio"), ("DELETE", "baja")):
        db.execute(f"""
            CREATE TRIGGER pos_contable_ventas_{nombre} BEFORE {sql} ON ventas
            BEGIN
                SELECT RAISE(ABORT, 'Usá el POS para ventas nuevas. El historial legado queda archivado.');
            END
        """)


def calcular_periodo(db, desde, hasta):
    from pos_compras_caja import compras_caja_existe, resumen_pagos_compras

    inicio, ultimo_pos, ultimo_diario = corte_contable(db)
    desde_contable = max(inicio, desde)
    eventos = (ultimo_pos, desde_contable, hasta)
    dev_c, dev_b, cob_c, cob_b = db.execute("""
        SELECT COALESCE(SUM(devengado_comidas), 0), COALESCE(SUM(devengado_bebidas), 0),
               COALESCE(SUM(cobrado_comidas), 0), COALESCE(SUM(cobrado_bebidas), 0)
        FROM pos_eventos_simulados
        WHERE id_evento > ? AND date(fecha, '-3 hours') BETWEEN ? AND ?
    """, eventos).fetchone()
    cobros = [
        {"receptor": receptor, "medio_pago": medio, "neto_centavos": neto}
        for receptor, medio, neto in db.execute("""
            SELECT m.receptor, m.medio_pago, SUM(m.importe_centavos)
            FROM pos_movimientos_simulados AS m JOIN pos_eventos_simulados AS e USING (id_evento)
            WHERE e.id_evento > ? AND date(e.fecha, '-3 hours') BETWEEN ? AND ?
              AND (m.medio_pago IS NOT NULL OR m.receptor LIKE '%_saldo_unificado' AND m.id_venta IS NOT NULL)
            GROUP BY m.receptor, m.medio_pago ORDER BY m.receptor, m.medio_pago
        """, eventos)
    ]
    pendiente_c, pendiente_b = db.execute("""
        SELECT COALESCE(SUM(devengado_comidas - cobrado_comidas), 0),
               COALESCE(SUM(devengado_bebidas - cobrado_bebidas), 0)
        FROM pos_eventos_simulados WHERE date(fecha, '-3 hours') <= ?
    """, (hasta,)).fetchone()

    costos_legados = [
        {"tipo": tipo, "seccion": seccion, "medio_declarado": medio, "neto_centavos": neto}
        for tipo, seccion, medio, neto in db.execute("""
            SELECT tipo, seccion, medio_declarado, SUM(importe_centavos)
            FROM pos_costos_contables WHERE fecha BETWEEN ? AND ?
            GROUP BY tipo, seccion, medio_declarado ORDER BY tipo, seccion, medio_declarado
        """, (desde_contable, hasta))
    ]
    compras = sum(fila["neto_centavos"] for fila in costos_legados if fila["tipo"] == "compra")
    gastos_legados = sum(fila["neto_centavos"] for fila in costos_legados if fila["tipo"] == "gasto")

    diario = (ultimo_diario, desde_contable, hasta)
    efectivo = {
        caja: {"gasto": 0, "aporte": 0, "retiro": 0, "transferencia": 0}
        for caja in SECCIONES
    }
    pagos_compras = {}
    excluir_pagos_compras = ""
    if compras_caja_existe(db):
        pagos_compras["pagos_compras_por_receptor"] = resumen_pagos_compras(db, desde_contable, hasta)
        excluir_pagos_compras = "AND d.id_evento NOT IN (SELECT id_diario FROM pos_compras_caja WHERE id_diario IS NOT NULL)"
    for caja, tipo, importe in db.execute(f"""
        SELECT j.caja, d.tipo, SUM(d.importe_centavos)
        FROM pos_diario_caja AS d JOIN pos_jornadas_caja AS j USING (id_jornada)
        WHERE d.id_evento > ? AND substr(d.fecha_hora, 1, 10) BETWEEN ? AND ?
          AND d.tipo IN ('gasto', 'aporte', 'retiro', 'transferencia')
          {excluir_pagos_compras}
        GROUP BY j.caja, d.tipo
    """, diario):
        efectivo[caja][tipo] = importe
    gastos_pos = -sum(fila["gasto"] for fila in efectivo.values())
    aportes = sum(fila["aporte"] for fila in efectivo.values())
    retiros = -sum(fila["retiro"] for fila in efectivo.values())
    jornadas = []
    for jornada, caja, fecha, cierre, resultado in db.execute("""
        SELECT j.id_jornada, j.caja, j.fecha, d.id_evento, d.resultado
        FROM pos_jornadas_caja AS j
        LEFT JOIN pos_diario_caja AS d ON d.id_jornada = j.id_jornada AND d.tipo = 'cierre'
        WHERE j.fecha BETWEEN ? AND ? ORDER BY j.fecha, j.caja
    """, (desde_contable, hasta)):
        datos = {"id_jornada": jornada, "caja": caja, "fecha": fecha, "id_cierre_diario": cierre}
        if cierre is not None:
            guardado = json.loads(resultado)
            datos["esperado_centavos"] = guardado["saldo"]["esperado_centavos"]
            datos["contado_centavos"] = guardado["arqueo"]["resultado"]["contado_centavos"]
            datos["diferencia_centavos"] = guardado["arqueo"]["resultado"]["diferencia_centavos"]
        jornadas.append(datos)

    devengado = dev_c + dev_b
    cobrado = cob_c + cob_b
    gastos = gastos_legados + gastos_pos
    base = cobrado - compras - gastos
    from pos_costos_historicos import informe as informe_margen
    return {
        "rentabilidad_historica": informe_margen(db, desde_contable, hasta,
                                               id_evento_minimo=ultimo_pos, incluir_legado=False),
        **pagos_compras,
        "simulacion": True, "fecha_corte": inicio, "desde_contable": desde_contable, "hasta": hasta,
        "devengado_centavos": devengado, "cobrado_neto_centavos": cobrado,
        "variacion_fiado_centavos": devengado - cobrado, "fiado_al_cierre_centavos": pendiente_c + pendiente_b,
        "compras_centavos": compras, "gastos_centavos": gastos,
        "gastos_con_receptor_centavos": gastos_pos, "gastos_sin_receptor_centavos": gastos_legados,
        "aportes_fisicos_centavos": aportes, "retiros_fisicos_centavos": retiros,
        "resultado_devengado_centavos": devengado - compras - gastos,
        "resultado_base_diezmo_centavos": base, "diezmo_centavos": (max(base, 0) + 5) // 10,
        "secciones": {
            seccion: {"devengado_centavos": dev, "cobrado_atribuido_centavos": cob,
                      "variacion_fiado_centavos": dev - cob, "fiado_al_cierre_centavos": pendiente}
            for seccion, dev, cob, pendiente in zip(SECCIONES, (dev_c, dev_b), (cob_c, cob_b), (pendiente_c, pendiente_b))
        },
        "cobros_por_receptor": cobros, "movimientos_fisicos_por_caja": efectivo,
        "costos_legados_por_seccion": costos_legados, "jornadas": jornadas,
    }


def validar_periodo_cierre(db, tipo, desde, hasta, informe):
    if hasta >= fecha_local():
        return "Esperá a que termine el último día del período."
    if any(jornada["id_cierre_diario"] is None for jornada in informe["jornadas"]):
        return "Cerrá las jornadas físicas abiertas dentro del período."
    tabla = "cierres_semanales" if tipo == "semanal" else "cierres_mensuales"
    if db.execute(f"""
        SELECT 1 FROM {tabla} WHERE fecha_desde <= ? AND fecha_hasta >= ?
    """, (hasta, max(desde, informe["fecha_corte"]))).fetchone():
        return "El período se superpone con un cierre guardado."
    return None


def guardar_detalle_cierre(db, tipo, id_cierre, informe):
    db.execute("INSERT INTO pos_cierres_contables VALUES (?, ?, ?)",
               (tipo, id_cierre, json.dumps(informe, ensure_ascii=False)))


def detalle_cierre(db, tipo, id_cierre):
    if not corte_contable(db):
        return {}
    fila = db.execute("""
        SELECT resumen FROM pos_cierres_contables WHERE tipo = ? AND id_cierre = ?
    """, (tipo, id_cierre)).fetchone()
    return {"contabilidad_centavos": json.loads(fila[0])} if fila else {}


def validar_fecha_costo(fecha):
    if fecha != fecha_local():
        return {
            "ok": False, "codigo": "FECHA_CONTABLE_INVALIDA",
            "mensaje": "En esta simulación, las compras y los gastos se registran con la fecha local de hoy.",
        }
    return None


def validar_reversion_costo(db, tipo, id_origen):
    if not db.execute("""
        SELECT 1 FROM pos_costos_contables WHERE tipo = ? AND id_origen = ? AND evento = 'alta'
    """, (tipo, id_origen)).fetchone():
        return {
            "ok": False, "codigo": "COSTO_ANTERIOR_AL_CORTE",
            "mensaje": "El costo es anterior al corte contable ficticio.",
        }
    return None
