from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from threading import Barrier

import ventas
from compras import anular_compra, registrar_compra
from database import obtener_conexion


def _en_paralelo(operacion):
    salida = Barrier(2, timeout=5)

    def ejecutar(_):
        salida.wait()
        return operacion()

    with ThreadPoolExecutor(max_workers=2) as equipo:
        return list(equipo.map(ejecutar, range(2)))


def _stock(id_producto):
    with closing(obtener_conexion()) as conexion:
        return conexion.execute(
            "SELECT stock FROM productos WHERE id_producto = ?", (id_producto,)
        ).fetchone()[0]


def test_ventas_individuales_concurrentes_no_sobrevenden(producto_prueba, monkeypatch):
    antes_de_escribir = Barrier(2, timeout=5)
    calcular_costo = ventas.costo_unitario_para_venta

    def calcular_costo_en_paralelo(id_producto):
        costo = calcular_costo(id_producto)
        antes_de_escribir.wait()
        return costo

    monkeypatch.setattr(ventas, "costo_unitario_para_venta", calcular_costo_en_paralelo)
    resultados = _en_paralelo(lambda: ventas.registrar_venta(producto_prueba, 7, 100))
    assert sorted(r["codigo"] for r in resultados) == ["STOCK_INSUFICIENTE", "VENTA_REGISTRADA"]
    assert _stock(producto_prueba) == 3
    with closing(obtener_conexion()) as conexion:
        assert conexion.execute("SELECT COUNT(*) FROM ventas_operaciones").fetchone() == (1,)
        assert conexion.execute("SELECT COUNT(*) FROM ventas").fetchone() == (1,)


def test_anulaciones_concurrentes_de_venta_devuelven_stock_una_vez(producto_prueba):
    venta = ventas.registrar_venta(producto_prueba, 3, 100)
    resultados = _en_paralelo(lambda: ventas.anular_venta(venta["id_venta"], "Prueba ficticia"))
    assert sorted(r["codigo"] for r in resultados) == ["VENTA_ANULADA", "VENTA_YA_ANULADA"]
    assert _stock(producto_prueba) == 10


def test_anulaciones_concurrentes_de_compra_revierten_stock_una_vez(producto_prueba):
    compra = registrar_compra(producto_prueba, 3, 100)
    resultados = _en_paralelo(lambda: anular_compra(compra["id_compra"], "Prueba ficticia"))
    assert sorted(r["codigo"] for r in resultados) == ["COMPRA_ANULADA", "COMPRA_YA_ANULADA"]
    assert _stock(producto_prueba) == 10
