"""Conciliación de una jornada completa de Lo de Clau sobre SQLite descartable."""
import sqlite3
from contextlib import closing
from shutil import copy2

from ajustes_stock import registrar_inventario_fisico, registrar_merma
from database import RUTA_ENTRENAMIENTO
from pos_contabilidad import fecha_local
from scripts.abadion_entrenamiento import ARCHIVO_CATALOGO, preparar_base, respaldar_sqlite
from tests.test_pos_caja_diaria import BEBIDAS, COMIDAS, RUTA
from tests.test_pos_clientes import preparar_abono
from tests.test_pos_entrenamiento import registrar_cliente_prueba
from tests.test_pos_qa_integrado import SIM, cliente, post, solicitud


def pago(receptor, medio, importe, referencia=None):
    return {"receptor": receptor, "medio_pago": medio, "importe_centavos": importe,
            "referencia": referencia}


def preparar_productos(ruta):
    with closing(sqlite3.connect(ruta)) as db, db:
        ids = {}
        for nombre, categoria, precio in (("Comida", "Comidas", 10),
                                          ("Bebida", "Bebidas", 3),
                                          ("Postre", "Postres", 5)):
            ids[nombre] = db.execute("""
                INSERT INTO productos (nombre, categoria, precio_venta, stock)
                VALUES (?, ?, ?, 10)
            """, (f"{nombre} ficticio jornada", categoria, precio)).lastrowid
        extra = db.execute("""
            INSERT INTO adicionales_catalogo (nombre, precio_venta) VALUES ('Extra ficticio jornada', 2)
        """).lastrowid
        db.execute("INSERT INTO pos_adicionales_producto VALUES (?, ?)", (ids["Comida"], extra))
        db.execute("INSERT INTO pos_ingredientes_producto VALUES (?, 'Cebolla')", (ids["Comida"],))
    return ids, extra


def existencias(ruta, ids):
    with closing(sqlite3.connect(ruta)) as db:
        return {nombre: db.execute("SELECT stock FROM productos WHERE id_producto = ?", (identificador,)).fetchone()[0]
                for nombre, identificador in ids.items()}


def obtener(navegador, ruta, **params):
    respuesta = navegador.get(ruta, params=params)
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()


def operar(navegador, caja, accion, **datos):
    return post(navegador, f"{RUTA}/{caja}/{accion}", solicitud(**datos))


def test_jornada_contable_completa(tmp_path):
    ruta = preparar_base(tmp_path)
    ids, extra = preparar_productos(ruta)
    ventas, admin = cliente(tmp_path, 0), cliente(tmp_path, 1)
    fecha = fecha_local()
    inicial = {COMIDAS: 1000, BEBIDAS: 500}
    jornadas = {
        caja: operar(ventas, caja, "apertura", fecha=fecha, inicial_centavos=importe)["id_jornada"]
        for caja, importe in inicial.items()
    }
    pedidos = SIM + "/pedidos"
    informe = SIM + "/contabilidad"
    ruta_ventas = SIM + "/ventas"
    def control(rotiseria, postres_bebidas, banco, mercado_pago, fiado):
        cajas = obtener(ventas, RUTA)["cajas"]
        reporte = obtener(admin, informe)
        digital = {(m["receptor"], m["medio_pago"]): m["neto_centavos"]
                   for m in reporte["cobros_por_receptor"]}
        assert (
            cajas[COMIDAS]["esperado_centavos"], cajas[BEBIDAS]["esperado_centavos"],
            digital.get(("bebidas_postres_banco", "transferencia"), 0),
            digital.get(("bebidas_postres_mercado_pago", "mercado_pago"), 0),
            reporte["fiado_al_cierre_centavos"],
        ) == (rotiseria, postres_bebidas, banco, mercado_pago, fiado)

    control(1000, 500, 0, 0, 0)
    titular = registrar_cliente_prueba(ventas, "Cliente ficticio jornada")
    cuenta = f"{SIM}/clientes/{titular}"
    comida = {"id_producto": ids["Comida"], "cantidad": 1}
    bebida = {"id_producto": ids["Bebida"], "cantidad": 1}
    postre = {"id_producto": ids["Postre"], "cantidad": 2}

    mostrador = post(ventas, pedidos, solicitud(
        items=[{**comida, "ingredientes_quitados": ["Cebolla"], "ids_adicionales": [extra]}, bebida],
        entrega={"origen": "mostrador", "modalidad": "retiro"},
    ))
    whatsapp = post(ventas, pedidos, solicitud(
        items=[postre], entrega={"origen": "whatsapp", "modalidad": "retiro"},
    ))
    pendiente = f"{pedidos}/{whatsapp['id_pedido']}"
    preparado = post(ventas, pendiente + "/estado", solicitud(estado="preparacion", version=1))
    assert preparado["id_venta"] is None
    assert mostrador["id_venta"] is None
    assert existencias(ruta, ids) == dict.fromkeys(ids, 10)
    assert obtener(admin, informe)["devengado_centavos"] == 0
    assert obtener(admin, informe)["cobrado_neto_centavos"] == 0
    with closing(sqlite3.connect(ruta)) as db:
        for tabla in ("pos_ventas_simuladas", "pos_movimientos_simulados"):
            assert db.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone() == (0,)
        assert db.execute("SELECT tipo, COUNT(*) FROM pos_diario_caja GROUP BY tipo").fetchall() == [("apertura", 2)]

    control(1000, 500, 0, 0, 0)
    conversion = solicitud(total_esperado_centavos=1500, pagos=[
        pago("comidas_efectivo", "efectivo", 1400),
        pago("bebidas_postres_banco", "transferencia", 100, "transferencia-jornada"),
    ])
    convertir = f"{pedidos}/{mostrador['id_pedido']}/venta"
    primera = post(ventas, convertir, conversion)
    assert post(ventas, convertir, conversion) == primera
    assert primera["items"][0]["ingredientes_quitados"] == ["Cebolla"]
    assert primera["items"][0]["subtotal_centavos"] == 1200
    assert existencias(ruta, ids) == {"Comida": 9, "Bebida": 9, "Postre": 10}

    control(2400, 500, 100, 0, 0)
    traslado = solicitud(origen="comidas_efectivo", destino="bebidas_postres_efectivo",
                         importe_centavos=200, motivo="Distribución del cobro mixto")
    mover = SIM + "/cajas/transferencias"
    assert post(admin, mover, traslado) == post(admin, mover, traslado)

    control(2200, 700, 100, 0, 0)
    contexto = RUTA_ENTRENAMIENTO.set(ruta)
    try:
        assert registrar_inventario_fisico(ids["Postre"], 1, fecha=fecha)["ok"]
    finally:
        RUTA_ENTRENAMIENTO.reset(contexto)
    faltantes = {str(ids["Postre"]): 1}
    assert obtener(ventas, pendiente + "/cotizacion")["faltantes_stock"] == faltantes
    segunda = post(ventas, pendiente + "/venta", solicitud(
        total_esperado_centavos=1000, confirmar_faltantes=faltantes, pagos=[
            pago("bebidas_postres_mercado_pago", "mercado_pago", 1000, "mp-jornada"),
        ],
    ))
    control(2200, 700, 100, 1000, 0)
    fiada = post(ventas, ruta_ventas, solicitud(
        items=[comida], total_esperado_centavos=1000, id_cliente=titular, fiado=True, pagos=[],
    ))
    assert obtener(ventas, cuenta)["saldo_centavos"] == 1000
    control(2200, 700, 100, 1000, 1000)
    previa, abono = preparar_abono(ventas, cuenta, pago(
        "bebidas_postres_banco", "transferencia", 400, "abono-jornada",
    ))
    assert [(p["id_venta"], p["importe_centavos"]) for p in previa["imputaciones"]] == [(fiada["id_venta"], 400)]
    abonar = cuenta + "/abonos"
    assert post(ventas, abonar, abono) == post(ventas, abonar, abono)
    control(2200, 700, 500, 1000, 600)
    anulable = post(ventas, ruta_ventas, solicitud(
        items=[bebida], total_esperado_centavos=300, medio_pago="efectivo",
    ))

    control(2200, 1000, 500, 1000, 600)
    compra = solicitud(id_producto=ids["Bebida"], cantidad=2, precio_unitario_centavos=100,
                       pagado_centavos=200, pagador="comidas_efectivo", medio_pago="efectivo")
    alta_compra = post(admin, SIM + "/compras", compra)
    assert alta_compra["seccion"] == BEBIDAS
    assert post(admin, SIM + "/compras", compra) == alta_compra
    # Inventario y merma conservan las funciones de dominio legadas.
    contexto = RUTA_ENTRENAMIENTO.set(ruta)
    try:
        assert registrar_inventario_fisico(ids["Bebida"], 9, fecha=fecha)["ok"]
        assert registrar_merma(ids["Bebida"], 1, fecha=fecha)["ok"]
    finally:
        RUTA_ENTRENAMIENTO.reset(contexto)
    control(2000, 1000, 500, 1000, 600)
    operar(admin, COMIDAS, "movimientos", id_jornada=jornadas[COMIDAS],
           tipo="gasto", importe_centavos=100, motivo="Gasto ficticio jornada")
    operar(ventas, BEBIDAS, "movimientos", id_jornada=jornadas[BEBIDAS],
           tipo="aporte", importe_centavos=150, motivo="Cambio temporal")
    control(1900, 1150, 500, 1000, 600)
    operar(ventas, BEBIDAS, "movimientos", id_jornada=jornadas[BEBIDAS],
           tipo="retiro", importe_centavos=150, motivo="Devolución de cambio")

    control(1900, 1000, 500, 1000, 600)
    antes = obtener(admin, informe)
    with closing(sqlite3.connect(ruta)) as db, db:
        db.execute("UPDATE productos SET categoria = 'Comidas', precio_venta = 8 WHERE id_producto = ?",
                   (ids["Postre"],))
        db.execute("UPDATE productos SET categoria = 'Comidas', precio_venta = 4 WHERE id_producto = ?",
                   (ids["Bebida"],))
    assert obtener(admin, informe) == antes
    devolver = f"{ruta_ventas}/{segunda['id_venta']}/devoluciones"
    devolucion = solicitud(motivo="Devolución ficticia", items=[{"linea": 1, "cantidad": 1}])
    aplicada = post(admin, devolver, devolucion)
    assert aplicada["reembolsado_centavos"] == 500
    assert post(admin, devolver, devolucion) == aplicada
    control(1900, 1000, 500, 500, 600)
    anular = f"{ruta_ventas}/{anulable['id_venta']}/anulacion"
    anulacion = solicitud(motivo="Anulación ficticia")
    anulada = post(admin, anular, anulacion)
    assert post(admin, anular, anulacion) == anulada
    assert anulada["reembolsado_centavos"] == 300

    control(1900, 700, 500, 500, 600)
    efectivo = {COMIDAS: 1000 + 1400 - 100 - 200 - 200, BEBIDAS: 500 + 300 + 200 - 300}
    for caja, contado in efectivo.items():
        actual = obtener(ventas, RUTA)["cajas"][caja]
        assert actual["esperado_centavos"] == contado
        arqueo = operar(ventas, caja, "arqueo", id_jornada=jornadas[caja],
                        revision_efectivo=actual["revision_efectivo"], contado_centavos=contado)
        assert arqueo["diferencia_centavos"] == 0
        operar(ventas, caja, "cierre", id_jornada=jornadas[caja], id_arqueo=arqueo["id_evento"])

    reporte = obtener(admin, informe, desde=fecha, hasta=fecha)
    esperado = {
        "devengado_centavos": 1200 + 300 + 1000 - 500 + 1000 + 300 - 300,
        "cobrado_neto_centavos": 1400 + 100 + 1000 - 500 + 400 + 300 - 300,
        "fiado_al_cierre_centavos": 1000 - 400,
        "compras_centavos": 2 * 100,
        "gastos_centavos": 100,
        "resultado_base_diezmo_centavos": 2400 - 200 - 100,
        "diezmo_centavos": 2100 // 10,
    }
    assert {campo: reporte[campo] for campo in esperado} == esperado
    assert {caja: (valores["devengado_centavos"], valores["cobrado_atribuido_centavos"])
            for caja, valores in reporte["secciones"].items()} == {COMIDAS: (2200, 1600), BEBIDAS: (800, 800)}
    netos = {(m["receptor"], m["medio_pago"]): m["neto_centavos"] for m in reporte["cobros_por_receptor"]}
    assert netos == {
        ("comidas_efectivo", "efectivo"): 1400, ("bebidas_postres_efectivo", "efectivo"): 0,
        ("bebidas_postres_banco", "transferencia"): 500, ("bebidas_postres_mercado_pago", "mercado_pago"): 500,
    }
    assert sum(netos.values()) == esperado["cobrado_neto_centavos"]
    assert reporte["pagos_compras_por_receptor"] == [
        {"pagador": "comidas_efectivo", "medio_pago": "efectivo", "egreso_neto_centavos": 200},
    ]
    assert reporte["aportes_fisicos_centavos"] == reporte["retiros_fisicos_centavos"] == 150
    assert {j["caja"]: (j["esperado_centavos"], j["contado_centavos"], j["diferencia_centavos"])
            for j in reporte["jornadas"] if j["id_cierre_diario"]} == {
        caja: (saldo, saldo, 0) for caja, saldo in efectivo.items()
    }
    assert {caja: m["transferencia"] for caja, m in reporte["movimientos_fisicos_por_caja"].items()} == {
        COMIDAS: -200, BEBIDAS: 200,
    }
    assert obtener(ventas, cuenta)["saldo_centavos"] == 600
    assert existencias(ruta, ids) == {"Comida": 8, "Bebida": 9, "Postre": 0}
    assert obtener(admin, SIM + "/conciliacion")["cuadrado"]

    copia = tmp_path / "restaurada"
    copia.mkdir()
    destino = copia / ruta.name
    copy2(respaldar_sqlite(ruta, "jornada"), destino)
    copy2(tmp_path / ARCHIVO_CATALOGO, copia / ARCHIVO_CATALOGO)
    with closing(sqlite3.connect(destino)) as db:
        assert db.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        assert db.execute("SELECT COUNT(*) FROM pos_ventas_simuladas").fetchone() == (4,)
    assert existencias(destino, ids) == existencias(ruta, ids)
    assert obtener(cliente(copia, 1), informe, desde=fecha, hasta=fecha) == reporte
    assert obtener(cliente(copia, 0), cuenta)["saldo_centavos"] == 600

