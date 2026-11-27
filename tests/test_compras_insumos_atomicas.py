"""Dinero, compras, costos, stock y recibo deben aparecer juntos o no aparecer."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from threading import Barrier

import pytest

import costos_postres as costos
from api import app
from caja import gastos_caja
from comandos import procesar_comando
from compras import registrar_compra
from database import obtener_conexion
from gastos import registrar_gasto
from pos_caja_diaria import crear_caja_diaria
from pos_contabilidad import crear_integracion_contable, fecha_local
from pos_simulacion import crear_esquema_simulacion
from tests import cliente_contabilidad


@pytest.fixture
def insumos(base_prueba):
    costos.inicializar_costos_postres()
    return base_prueba


def compra(**cambios):
    datos = dict(nombre_insumo="dulce de leche", cantidad=1, unidad="kg",
                 costo_total=2500, comercio="Proveedor ficticio", id_solicitud="solicitud-ficticia")
    datos.update(cambios)
    return costos.registrar_compra_insumo(**datos)


def estado():
    # Snapshot de todos los libros relevantes, incluyendo relaciones y contenido.
    with closing(obtener_conexion()) as db:
        db.execute("BEGIN")
        tablas = {t for t, in db.execute("SELECT name FROM sqlite_schema WHERE type='table'")}
        nombres = ("gastos", "compras_insumos", "insumos", "operaciones_compras_insumos",
                   "pos_costos_contables", "movimientos_caja", "movimientos_deuda_negocio",
                   "movimientos_reserva_deuda_negocio")
        return {t: db.execute(f'SELECT * FROM "{t}" ORDER BY rowid').fetchall()
                for t in nombres if t in tablas}


def integrar():
    with closing(obtener_conexion()) as db, db:
        crear_esquema_simulacion(db)
        crear_caja_diaria(db)
        crear_integracion_contable(db)


def test_compra_exitosa_gasto_stock_costo_y_trazabilidad(insumos):
    datos = compra(contexto={"canal": "api-ficticia", "usuario_id": "operador-ficticio"})
    assert datos["ok"] and (datos["stock_anterior"], datos["stock_nuevo"]) == (0, 1000)
    assert gastos_caja() == 2500
    with closing(obtener_conexion()) as db:
        fila = db.execute("SELECT id_insumo,id_gasto,cantidad_base,costo_total FROM compras_insumos").fetchone()
        assert fila[1:] == (datos["id_gasto"], 1000, 2500)
        assert costos._costo_unitario_reciente(db, fila[0]) == 2.5
        traza = db.execute("SELECT id_compra_insumo,contexto_json,resultado_json FROM operaciones_compras_insumos").fetchone()
        assert traza[0] == datos["id_compra_insumo"]
        assert json.loads(traza[1])["usuario_id"] == "operador-ficticio"
        assert json.loads(traza[2]) == datos
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        assert db.execute("SELECT COUNT(*) FROM movimientos_caja").fetchone() == (0,)
        assert db.execute("SELECT COUNT(*) FROM movimientos_deuda_negocio").fetchone() == (0,)


class FallaCommit:
    def __init__(self, conexion):
        self.conexion = conexion

    def __getattr__(self, nombre):
        return getattr(self.conexion, nombre)

    def commit(self):
        raise sqlite3.OperationalError("Fallo ficticio antes de COMMIT")


def test_regresion_gasto_huerfano(insumos):
    # Compatible también con la firma de #38: este caso debe fallar en la referencia.
    with closing(obtener_conexion()) as db, db:
        db.execute("""CREATE TRIGGER fallo_compra_ficticio BEFORE INSERT ON compras_insumos
                      BEGIN SELECT RAISE(ABORT,'Compra ficticia rechazada'); END""")
    with pytest.raises(sqlite3.Error):
        costos.registrar_compra_insumo("dulce de leche", 1, "kg", 2500)
    with closing(obtener_conexion()) as db:
        assert db.execute("SELECT COUNT(*) FROM gastos").fetchone() == (0,)
        assert db.execute("SELECT COUNT(*) FROM compras_insumos").fetchone() == (0,)
        assert db.execute("SELECT stock_base FROM insumos WHERE nombre='Dulce de leche'").fetchone() == (0,)


@pytest.mark.parametrize("tabla", ["gastos", "compras_insumos", "operaciones_compras_insumos"])
def test_insert_ignorado_no_se_confirma_como_compra_exitosa(insumos, tabla):
    antes = estado()
    with closing(obtener_conexion()) as db, db:
        db.execute(f"CREATE TRIGGER ignorar_ficticio BEFORE INSERT ON {tabla} BEGIN SELECT RAISE(IGNORE); END")
    with pytest.raises((sqlite3.Error, ValueError)):
        compra()
    assert estado() == antes


@pytest.mark.parametrize("integrada", [False, True])
@pytest.mark.parametrize("fase", ["gasto", "compra", "stock", "traza", "commit"])
def test_fallos_no_dejan_registros_parciales(insumos, monkeypatch, integrada, fase):
    if integrada:
        integrar()
    antes = estado()
    sql = {
        "gasto": "AFTER INSERT ON gastos",
        "compra": "BEFORE INSERT ON compras_insumos",
        "stock": "BEFORE UPDATE OF stock_base ON insumos",
        "traza": "BEFORE INSERT ON operaciones_compras_insumos",
    }
    if fase != "commit":
        with closing(obtener_conexion()) as db, db:
            db.execute(f"CREATE TRIGGER fallo_ficticio {sql[fase]} BEGIN SELECT RAISE(ABORT,'Fallo ficticio'); END")
    original = costos.obtener_conexion
    if fase == "commit":
        monkeypatch.setattr(costos, "obtener_conexion", lambda: FallaCommit(original()))
    with pytest.raises(sqlite3.Error):
        compra()
    assert estado() == antes
    monkeypatch.setattr(costos, "obtener_conexion", original)
    if fase != "commit":
        with closing(obtener_conexion()) as db, db:
            db.execute("DROP TRIGGER fallo_ficticio")
    confirmada = compra()
    assert confirmada["stock_nuevo"] == 1000
    assert compra() == confirmada
    assert len(estado()["gastos"]) == len(estado()["compras_insumos"]) == 1
    if integrada:
        assert len(estado()["pos_costos_contables"]) == 1


def test_lectores_no_observan_gasto_sin_compra(insumos, monkeypatch):
    integrar()
    original = costos.registrar_gasto
    vistas = []

    def observar(**datos):
        resultado = original(**datos)
        vistas.append(estado())
        return resultado

    antes = estado()
    monkeypatch.setattr(costos, "registrar_gasto", observar)
    assert compra()["ok"]
    assert vistas == [antes]
    assert len(estado()["compras_insumos"]) == len(estado()["pos_costos_contables"]) == 1


def test_excepcion_python_despues_del_gasto_revierte_todo(insumos, monkeypatch):
    antes = estado()
    original = costos.registrar_gasto

    def fallar(**datos):
        original(**datos)
        raise RuntimeError("Interrupción ficticia después del gasto")

    monkeypatch.setattr(costos, "registrar_gasto", fallar)
    with pytest.raises(RuntimeError):
        compra()
    assert estado() == antes


def test_sqlite_rechaza_commit_real_y_revierte_libros(insumos):
    integrar()
    with closing(obtener_conexion()) as db, db:
        db.execute("CREATE TABLE padre_ficticio(id INTEGER PRIMARY KEY)")
        db.execute("""CREATE TABLE hijo_ficticio(id INTEGER REFERENCES padre_ficticio
                      DEFERRABLE INITIALLY DEFERRED)""")
        db.execute("""CREATE TRIGGER fk_ficticia AFTER INSERT ON operaciones_compras_insumos
                      BEGIN INSERT INTO hijo_ficticio VALUES(999); END""")
    antes = estado()
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        compra()
    assert estado() == antes
    with closing(obtener_conexion()) as db:
        assert db.execute("SELECT COUNT(*) FROM hijo_ficticio").fetchone() == (0,)
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []


def test_caida_de_proceso_despues_del_gasto_no_confirma_parcial(insumos):
    integrar()
    antes = estado()
    codigo = """
import os, sys
sys.path.insert(0, sys.argv[1])
import costos_postres as c
original = c.registrar_gasto
def caer(**datos):
    original(**datos)
    os._exit(23)
c.registrar_gasto = caer
c.registrar_compra_insumo('dulce de leche',1,'kg',2500,id_solicitud='caida-ficticia')
"""
    entorno = {**os.environ, "NEGOCIO_DB_PATH": str(insumos), "PYTHON_DOTENV_DISABLED": "1"}
    resultado = subprocess.run([sys.executable, "-c", codigo, str(Path(__file__).resolve().parents[1] / "src")],
                               env=entorno, timeout=30, capture_output=True,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    assert resultado.returncode == 23, resultado.stderr
    # Abrir en modo escribible permite a SQLite recuperar su journal en esta base ficticia.
    with closing(sqlite3.connect(insumos)) as db:
        assert db.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    assert estado() == antes
    assert compra(id_solicitud="caida-ficticia")["stock_nuevo"] == 1000


def test_gasto_subordinado_no_confirma_ni_cierra_conexion(insumos):
    with closing(obtener_conexion()) as db:
        with pytest.raises(ValueError, match="transacción activa"):
            registrar_gasto("Materia prima", "Prueba", 100, _conexion=db)
        db.execute("BEGIN IMMEDIATE")
        assert registrar_gasto("Materia prima", "Prueba", 100, _conexion=db)["ok"]
        assert db.in_transaction and len(estado()["gastos"]) == 0
        db.rollback()
        assert len(estado()["gastos"]) == 0


@pytest.mark.parametrize("cambio", [{"costo_total": 2600}, {"contexto": {"usuario_id": "otro"}}])
def test_solicitud_duplicada_o_conflictiva(insumos, cambio):
    primera = compra()
    antes = estado()
    assert compra() == primera
    assert compra(**cambio)["codigo"] == "SOLICITUD_COMPRA_INSUMO_CONFLICTIVA"
    assert estado() == antes


def test_sin_identificador_son_dos_compras_legitimas(insumos):
    primera = compra(id_solicitud=None)
    segunda = compra(id_solicitud=None)
    assert primera["id_operacion"] != segunda["id_operacion"]
    assert segunda["stock_anterior"] == 1000 and segunda["stock_nuevo"] == 2000
    assert gastos_caja() == 5000


@pytest.mark.parametrize("misma_solicitud", [False, True])
def test_compras_concurrentes_sin_perdida_de_stock_ni_duplicados(insumos, misma_solicitud):
    barrera = Barrier(6)

    def ejecutar(numero):
        barrera.wait(timeout=10)
        return compra(id_solicitud="misma" if misma_solicitud else f"concurrente-{numero}")

    with ThreadPoolExecutor(max_workers=6) as pool:
        resultados = list(pool.map(ejecutar, range(6)))
    cantidad = 1 if misma_solicitud else 6
    assert all(r["ok"] for r in resultados)
    final = estado()
    assert len(final["gastos"]) == len(final["compras_insumos"]) == len(final["operaciones_compras_insumos"]) == cantidad
    assert max(r["stock_nuevo"] for r in resultados) == cantidad * 1000
    assert gastos_caja() == cantidad * 2500
    assert len({r["id_operacion"] for r in resultados}) == cantidad
    if not misma_solicitud:
        assert sorted(r["stock_anterior"] for r in resultados) == list(range(0, 6000, 1000))


def test_paquetes_reintento_usa_resultado_original_aunque_cambie_presentacion(insumos):
    datos = dict(nombre_insumo="oreo", cantidad_paquetes=2, presentacion="118g",
                 costo_total=900, id_solicitud="paquetes-ficticios")
    primera = costos.registrar_compra_insumo_paquetes(**datos)
    assert primera["cantidad_base_total"] == primera["stock_nuevo"] == 236
    with closing(obtener_conexion()) as db, db:
        db.execute("UPDATE presentaciones_insumos SET contenido_base=999")
    assert costos.registrar_compra_insumo_paquetes(**datos) == primera
    assert len(estado()["gastos"]) == 1


def test_compra_sin_control_stock_preserva_existencias(insumos):
    datos = compra(nombre_insumo="café con leche preparado", cantidad=100, unidad="ml")
    assert datos["ok"] and not datos["controla_stock"]
    assert datos["stock_anterior"] == datos["stock_nuevo"] == 0
    assert gastos_caja() == 2500


def test_bloque_distingue_lineas_identicas_y_reintentos(insumos):
    contexto = {"canal": "ficticio", "id_mensaje": "bloque", "usuario_id": "operador"}
    mensaje = "insumo dulce de leche 1 kg 2500\ninsumo dulce de leche 1 kg 2500"
    primera = procesar_comando(mensaje, contexto=contexto)
    assert primera["ok"]
    assert procesar_comando(mensaje, contexto=contexto) == primera
    assert gastos_caja() == 5000
    with closing(obtener_conexion()) as db:
        assert db.execute("SELECT indice_linea FROM operaciones_compras_insumos ORDER BY indice_linea").fetchall() == [(1,), (2,)]


@pytest.mark.parametrize("paquetes", [False, True])
def test_api_acciones_conserva_idempotencia_y_rechaza_credito_no_soportado(insumos, paquetes):
    cliente = cliente_contabilidad(app)
    accion = "registrar compra insumo paquetes" if paquetes else "registrar compra insumo"
    datos = {"insumo": "oreo", "costo_total": 800, "id_solicitud": "api-ficticia"}
    datos.update({"cantidad_paquetes": 1, "presentacion": "118g"} if paquetes else {"cantidad": 100, "unidad": "g"})
    cuerpo = {"accion": accion, "datos": datos}
    primera = cliente.post("/acciones", json=cuerpo)
    assert primera.status_code == 200
    assert cliente.post("/acciones", json=cuerpo).json() == primera.json()
    antes = estado()
    assert cliente.post("/acciones", json={**cuerpo, "datos": {**datos, "costo_total": 900}}).status_code == 409
    no_soportado = cliente.post("/acciones", json={**cuerpo, "datos": {**datos, "cuenta_deuda": "tarjeta-ficticia"}})
    assert no_soportado.status_code == 400
    assert no_soportado.json()["codigo"] == "MEDIO_PAGO_INSUMO_NO_SOPORTADO"
    assert estado() == antes


def test_api_comandos_repetido_conserva_trazabilidad(insumos):
    cliente = cliente_contabilidad(app)
    cuerpo = {"mensaje": "insumo oreo 2 paquetes 118g 900", "id_mensaje": "mensaje-ficticio", "canal": "whatsapp-ficticio"}
    assert cliente.post("/comandos", json=cuerpo).status_code == 200
    assert cliente.post("/comandos", json=cuerpo).json()["repetido"] is True
    with closing(obtener_conexion()) as db:
        assert db.execute("SELECT canal,id_solicitud FROM operaciones_compras_insumos").fetchall() == [("whatsapp-ficticio", "mensaje-ficticio")]
    assert len(estado()["gastos"]) == 1


@pytest.mark.parametrize("valor", [float("nan"), float("inf"), -1, True, 10**400])
def test_costo_invalido_no_deja_efectos(insumos, valor):
    antes = estado()
    assert not compra(costo_total=valor)["ok"]
    assert estado() == antes


def test_ddl_del_recibo_tambien_revierte_en_copia_anterior(insumos, monkeypatch):
    with closing(obtener_conexion()) as db, db:
        db.execute("DROP TABLE operaciones_compras_insumos")
    antes = estado()
    original = costos.obtener_conexion
    monkeypatch.setattr(costos, "obtener_conexion", lambda: FallaCommit(original()))
    with pytest.raises(sqlite3.Error):
        compra()
    assert estado() == antes


@pytest.mark.parametrize("credito", [False, True])
def test_productos_pagados_y_financiados_conservan_sus_reglas(producto_prueba, credito):
    datos = registrar_compra(producto_prueba, 2, 50,
                             cuenta_deuda="tarjeta-ficticia" if credito else None)
    assert datos["ok"]
    with closing(obtener_conexion()) as db:
        assert db.execute("SELECT stock FROM productos WHERE id_producto=?", (producto_prueba,)).fetchone() == (12,)
        assert db.execute("SELECT COUNT(*) FROM gastos").fetchone() == (0,)
        deuda = db.execute("SELECT COALESCE(SUM(importe),0) FROM movimientos_deuda_negocio").fetchone()[0]
        assert deuda == (100 if credito else 0)
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
