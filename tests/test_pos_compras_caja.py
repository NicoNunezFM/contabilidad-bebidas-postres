import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from threading import Barrier

from compras import anular_compra
from database import RUTA_ENTRENAMIENTO
from deudas_negocio import detalle_deuda
from pos_contabilidad import fecha_local
from scripts.abadion_entrenamiento import preparar_base
from tests.test_jornada_contable import BEBIDAS, COMIDAS, existencias, obtener, operar, preparar_productos
from tests.test_pos_qa_integrado import SIM, cliente, post, solicitud


RUTA = SIM + "/compras"


def compra(producto, pagador, medio, costo, *, pagado=None, cuenta=None):
    return solicitud(id_producto=producto, cantidad=1, precio_unitario_centavos=costo,
                     pagado_centavos=costo if pagado is None else pagado,
                     pagador=pagador, medio_pago=medio, cuenta_deuda=cuenta)


def test_compras_propia_cruzada_digital_y_financiada(tmp_path):
    ruta = preparar_base(tmp_path)
    ids, _ = preparar_productos(ruta)
    admin, ventas = cliente(tmp_path, 1), cliente(tmp_path, 0)
    fecha = fecha_local()
    jornadas = {caja: operar(ventas, caja, "apertura", fecha=fecha, inicial_centavos=1000)["id_jornada"]
                for caja in (COMIDAS, BEBIDAS)}
    operaciones = (
        ("Comida", COMIDAS, "comidas_efectivo", "efectivo", 100),
        ("Bebida", BEBIDAS, "bebidas_postres_efectivo", "efectivo", 200),
        ("Comida", COMIDAS, "bebidas_postres_efectivo", "efectivo", 300),
        ("Bebida", BEBIDAS, "comidas_efectivo", "efectivo", 400),
        ("Comida", COMIDAS, "comidas_banco", "transferencia", 500),
        ("Postre", BEBIDAS, "bebidas_postres_mercado_pago", "mercado_pago", 600),
    )
    altas = []
    for producto, seccion, pagador, medio, costo in operaciones:
        datos = compra(ids[producto], pagador, medio, costo)
        assert ventas.post(RUTA, json=datos).status_code == 403
        resultado = post(admin, RUTA, datos)
        assert post(admin, RUTA, datos) == resultado
        assert (resultado["seccion"], resultado["pagador"], resultado["medio_pago"],
                resultado["costo_centavos"], resultado["pagado_centavos"]) == (seccion, pagador, medio, costo, costo)
        assert bool(resultado["id_movimiento_fisico"]) == (medio == "efectivo")
        altas.append(resultado)

    parcial = compra(ids["Comida"], "comidas_efectivo", "efectivo", 700,
                     pagado=250, cuenta="Proveedor ficticio")
    financiada = post(admin, RUTA, parcial)
    assert financiada["saldo_pendiente_centavos"] == 450
    assert admin.post(RUTA, json={**parcial, "pagado_centavos": 200}).status_code == 409
    assert admin.post(RUTA, json=compra(ids["Comida"], "comidas_efectivo", "efectivo", 251)).status_code == 409
    contexto = RUTA_ENTRENAMIENTO.set(ruta)
    try:
        assert detalle_deuda("Proveedor ficticio")["saldo"] == 4.50
        assert anular_compra(financiada["id_compra"], "Prueba")["codigo"] == "COMPRA_REQUIERE_REVERSO_POS"
    finally:
        RUTA_ENTRENAMIENTO.reset(contexto)
    assert existencias(ruta, ids) == {"Comida": 14, "Bebida": 12, "Postre": 11}

    for original, evento, efectivo in ((altas[0], "anulacion", 100), (altas[1], "devolucion", 200)):
        destino = f"{RUTA}/{original['id_compra']}/{evento}"
        assert admin.post(destino, json=solicitud(motivo="Reintegro pendiente")).status_code == 422
        datos = solicitud(motivo="Reintegro ficticio", reintegro_confirmado=True)
        reverso = post(admin, destino, datos)
        assert post(admin, destino, datos) == reverso
        assert reverso["reintegrado_centavos"] == efectivo
        assert admin.post(destino, json={**datos, **solicitud()}).status_code == 409

    for caja, saldo in ((COMIDAS, 1000 - 100 - 400 - 250 + 100),
                       (BEBIDAS, 1000 - 200 - 300 + 200)):
        estado = obtener(ventas, SIM + "/caja-diaria")["cajas"][caja]
        assert estado["esperado_centavos"] == saldo
        arqueo = operar(ventas, caja, "arqueo", id_jornada=jornadas[caja],
                        revision_efectivo=estado["revision_efectivo"], contado_centavos=saldo)
        assert arqueo["diferencia_centavos"] == 0
        operar(ventas, caja, "cierre", id_jornada=jornadas[caja], id_arqueo=arqueo["id_evento"])
    reporte = obtener(admin, SIM + "/contabilidad")
    assert reporte["compras_centavos"] == 2500
    assert reporte["gastos_centavos"] == reporte["retiros_fisicos_centavos"] == reporte["aportes_fisicos_centavos"] == 0
    assert reporte["resultado_base_diezmo_centavos"] == -2500 and reporte["diezmo_centavos"] == 0
    costos = {seccion: sum(f["neto_centavos"] for f in reporte["costos_legados_por_seccion"]
                           if f["seccion"] == seccion) for seccion in (COMIDAS, BEBIDAS)}
    assert costos == {COMIDAS: 1500, BEBIDAS: 1000}
    assert {p["pagador"]: p["egreso_neto_centavos"] for p in reporte["pagos_compras_por_receptor"]} == {
        "comidas_efectivo": 650, "bebidas_postres_efectivo": 300, "comidas_banco": 500,
        "bebidas_postres_mercado_pago": 600,
    }
    assert obtener(admin, SIM + "/conciliacion")["cuadrado"]
    with closing(sqlite3.connect(ruta)) as db:
        assert db.execute("SELECT COUNT(*) FROM compras").fetchone() == (7,)
        assert db.execute("SELECT COUNT(*) FROM pos_compras_caja").fetchone() == (9,)


def test_reverso_compra_parcial_y_stock_concurrente(tmp_path):
    ruta = preparar_base(tmp_path)
    ids, _ = preparar_productos(ruta)
    admin, ventas = cliente(tmp_path, 1), cliente(tmp_path, 0)
    datos = compra(ids["Comida"], "comidas_banco", "transferencia", 500, pagado=200,
                   cuenta="Proveedor ficticio reverso")
    inicial = post(admin, RUTA, datos)
    reverso = post(admin, f"{RUTA}/{inicial['id_compra']}/devolucion",
                   solicitud(motivo="Devolución total", reintegro_confirmado=True))
    assert reverso["reintegrado_centavos"] == 200
    contexto = RUTA_ENTRENAMIENTO.set(ruta)
    try:
        assert detalle_deuda("Proveedor ficticio reverso")["saldo"] == 0
    finally:
        RUTA_ENTRENAMIENTO.reset(contexto)
    assert existencias(ruta, ids)["Comida"] == 10

    barrera = Barrier(2, timeout=10)

    def comprar():
        barrera.wait()
        return post(admin, RUTA, compra(ids["Comida"], "comidas_banco", "transferencia", 100))

    def vender():
        barrera.wait()
        return post(ventas, SIM + "/ventas", solicitud(
            items=[{"id_producto": ids["Comida"], "cantidad": 2}],
            total_esperado_centavos=2000, medio_pago="transferencia",
        ))

    with ThreadPoolExecutor(max_workers=2) as equipo:
        tareas = [equipo.submit(comprar), equipo.submit(vender)]
        for tarea in tareas:
            tarea.result()
    assert existencias(ruta, ids)["Comida"] == 9
    informe = obtener(admin, SIM + "/contabilidad")
    assert informe["compras_centavos"] == 100
    assert informe["cobrado_neto_centavos"] == 2000
    assert informe["resultado_base_diezmo_centavos"] == 1900
    assert informe["diezmo_centavos"] == 190
    assert obtener(admin, SIM + "/conciliacion")["cuadrado"]
