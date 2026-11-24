import json
import os
import sqlite3
import subprocess
import sys
import time
from contextlib import closing
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from database import obtener_conexion
from pos_preproduccion import ARCHIVO, MODO, abrir_base, configuracion, respaldo, restaurar
from pos_entrenamiento_db import bloquear_entrenamiento, abrir_base_entrenamiento
from scripts.abadion_preproduccion import preparar, crear_app
from pos_contabilidad import fecha_local

URL = "http://127.0.0.1:8078"
SIM = "/pos-api/simulacion"


@pytest.fixture
def instalada(tmp_path):
    carpeta = tmp_path / "Preproduccion"
    preparar(carpeta)
    return carpeta


def cliente(carpeta, rol="admin"):
    app = crear_app(carpeta)
    c = TestClient(app, base_url=URL, headers={"Origin": URL})
    nombre = rol + "-preprod"
    clave = json.loads((carpeta / "credenciales.json").read_text())[nombre]
    assert c.post("/pos-api/login", json={"usuario": nombre, "contrasena": clave}).status_code == 200
    return c


def post(c, ruta, **datos):
    respuesta = c.post(ruta, json={"id_solicitud": str(uuid4()), **datos})
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()


def test_aislamiento_identidad_credenciales_y_bot(instalada, tmp_path, monkeypatch):
    c = cliente(instalada)
    assert "PREPRODUCCIÓN PERSISTENTE" in c.get("/pos/").text
    assert c.get("/pos/").headers["X-Abadion-Modo"] == MODO
    for ruta in ("/comandos", "/ventas", "/compras"):
        assert c.post(ruta, json={}).status_code == 404
    assert c.get("/_preprod/status").status_code == 403
    assert c.post("/pos-api/login", json={"usuario": "admin-prueba", "contrasena": "Admin-Prueba-8060"}).status_code == 401
    otra = tmp_path / "otro" / "Preproduccion"
    preparar(otra)
    ajeno = TestClient(crear_app(otra), base_url=URL, headers={"Origin": URL}, cookies=dict(c.cookies))
    assert ajeno.get(SIM + "/contabilidad").status_code == 401
    for nombre in (ARCHIVO, "renombrada.db"):
        ruta = instalada / nombre
        if nombre != ARCHIVO:
            ruta.write_bytes((instalada / ARCHIVO).read_bytes())
        monkeypatch.setenv("NEGOCIO_DB_PATH", str(ruta))
        with pytest.raises(ValueError, match="Preproducción"):
            obtener_conexion()
    with pytest.raises(ValueError):
        abrir_base(instalada, configuracion(otra)["id"])
    copia = instalada / "abadion-entrenamiento.db"
    copia.write_bytes((instalada / ARCHIVO).read_bytes())
    with pytest.raises(ValueError, match="Preproducción"):
        abrir_base_entrenamiento(copia)
    with pytest.raises(ValueError):
        preparar(instalada)


def test_jornada_reinicio_stock_dos_cajas_compras_fiado_cierres_restore(instalada):
    identidad = configuracion(instalada)["id"]
    with closing(abrir_base(instalada, identidad)) as db, db:
        assert db.execute("SELECT COUNT(*) FROM productos").fetchone() == (0,)
        assert db.execute("SELECT COUNT(*) FROM ventas").fetchone() == (0,)
        db.executemany("INSERT INTO productos(nombre,categoria,precio_venta,controla_stock,stock) VALUES (?,?,?,1,10)",
                       [("Comida QA", "Comidas", 10), ("Bebida QA", "Bebidas", 20)])
        ids = [fila[0] for fila in db.execute("SELECT id_producto FROM productos ORDER BY id_producto")]
    admin, ventas = cliente(instalada), cliente(instalada, "ventas")
    jornadas = {caja: post(ventas, SIM + f"/caja-diaria/{caja}/apertura", fecha=fecha_local(), inicial_centavos=10000)["id_jornada"]
                for caja in ("comidas", "bebidas_postres")}
    datos = {"id_solicitud": str(uuid4()), "items": [{"id_producto": i, "cantidad": 1} for i in ids],
             "total_esperado_centavos": 3000, "medio_pago": "efectivo"}
    alta = ventas.post(SIM + "/ventas", json=datos)
    assert alta.status_code == 200, alta.text
    assert ventas.post(SIM + "/ventas", json=datos).json() == alta.json()
    post(admin, SIM + "/compras", id_producto=ids[1], cantidad=2, precio_unitario_centavos=100,
         pagado_centavos=200, pagador="comidas_efectivo", medio_pago="efectivo")
    comprador = admin.post(SIM + "/clientes", json={"id_solicitud": str(uuid4()), "nombre": "Cliente QA"})
    assert comprador.status_code == 200, comprador.text
    fiado = post(ventas, SIM + "/ventas", items=[{"id_producto": ids[0], "cantidad": 1}],
                 total_esperado_centavos=1000, pagos=[], fiado=True, id_cliente=comprador.json()["id_cliente"])
    assert fiado["saldo_pendiente_centavos"] == 1000
    post(ventas, SIM + f"/ventas/{fiado['id_venta']}/abonos", pagos=[{
        "receptor": "comidas_efectivo", "medio_pago": "efectivo", "importe_centavos": 1000}])
    for caja, saldo in (("comidas", 11800), ("bebidas_postres", 12000)):
        estado = ventas.get(SIM + "/caja-diaria").json()["cajas"][caja]
        assert estado["esperado_centavos"] == saldo
        arqueo = post(ventas, SIM + f"/caja-diaria/{caja}/arqueo", id_jornada=jornadas[caja],
                      revision_efectivo=estado["revision_efectivo"], contado_centavos=saldo)
        post(ventas, SIM + f"/caja-diaria/{caja}/cierre", id_jornada=jornadas[caja], id_arqueo=arqueo["id_evento"])
    informe = admin.get(SIM + "/contabilidad").json()
    assert informe["cobrado_neto_centavos"] == 4000
    assert informe["compras_centavos"] == 200
    assert admin.get(SIM + "/conciliacion").json()["cuadrado"]
    copia = respaldo(instalada)
    with closing(abrir_base(instalada, identidad)) as db, db:
        assert db.execute("SELECT stock FROM productos ORDER BY id_producto").fetchall() == [(8,), (11,)]
        db.execute("UPDATE productos SET stock=999")
    # New process checks disk persistence, without importing any normal API startup.
    codigo = "import sqlite3,sys; d=sqlite3.connect(sys.argv[1]); assert d.execute('select count(*) from pos_ventas_simuladas').fetchone()==(2,)"
    subprocess.run([sys.executable, "-c", codigo, str(instalada / ARCHIVO)], check=True)
    with bloquear_entrenamiento(instalada):
        restaurar(instalada, copia.name)
    assert admin.get(SIM + "/contabilidad").status_code == 401  # Restore invalidates old cookies.
    reiniciado = cliente(instalada)
    assert reiniciado.get(SIM + "/contabilidad").json() == informe
    assert reiniciado.get(SIM + "/conciliacion").json()["cuadrado"]
    with closing(abrir_base(instalada, identidad)) as db:
        assert db.execute("SELECT stock FROM productos ORDER BY id_producto").fetchall() == [(8,), (11,)]
    assert len(list((instalada / "backups").glob("*pre-restore.db"))) == 1


def test_backup_alterado_y_exclusion(instalada):
    copia = respaldo(instalada)
    antes = (instalada / ARCHIVO).read_bytes()
    copia.write_bytes(b"backup corrupto")
    with bloquear_entrenamiento(instalada):
        with pytest.raises(ValueError, match="alterado"):
            restaurar(instalada, copia.name)
        with pytest.raises(ValueError):
            with bloquear_entrenamiento(instalada):
                pass
    assert (instalada / ARCHIVO).read_bytes() == antes
    with pytest.raises(ValueError):
        restaurar(instalada, "../negocio.db")


def test_recuperacion_base_ausente_explicita_conserva_original(instalada):
    copia = respaldo(instalada)
    destino = instalada / ARCHIVO
    original = destino.read_bytes()
    destino.rename(instalada / "original-conservada.db")
    with bloquear_entrenamiento(instalada):
        with pytest.raises(ValueError, match="base-ausente"):
            restaurar(instalada, copia.name)
        restaurar(instalada, copia.name, base_ausente=True)
        with pytest.raises(ValueError, match="no sobrescribe"):
            restaurar(instalada, copia.name, base_ausente=True)
    assert (instalada / "original-conservada.db").read_bytes() == original
    assert cliente(instalada).get(SIM + "/contabilidad").status_code == 200


def test_rechaza_ruta_sincronizada(tmp_path):
    with pytest.raises(ValueError, match="OneDrive"):
        preparar(tmp_path / "OneDrive" / "Preproduccion")


def test_windows_arranque_duplicado_reinicio_restore_bloqueado_y_puerto_ajeno(instalada):
    from scripts.abadion_preproduccion import ocupado, consulta
    if ocupado():
        pytest.skip("8078 ocupado: no se interfiere con una instalación existente")
    script = Path(__file__).resolve().parents[1] / "scripts" / "abadion_preproduccion.py"
    comando = [sys.executable, "-X", "utf8", str(script), "--carpeta", str(instalada)]

    def ejecutar(*args):
        return subprocess.run([*comando, *args], capture_output=True, text=True, encoding="utf-8", timeout=75)

    try:
        assert ejecutar("iniciar", "--sin-edge").returncode == 0
        identidad = consulta(instalada)["id"]
        assert ejecutar("iniciar", "--sin-edge").returncode == 0
        assert ejecutar("backup").returncode == 0
        copia = next((instalada / "backups").glob("*.db"))
        assert ejecutar("restaurar", "--archivo", copia.name).returncode != 0
        assert ejecutar("detener").returncode == 0
        assert ejecutar("iniciar", "--sin-edge").returncode == 0
        assert consulta(instalada)["id"] == identidad
        assert ejecutar("detener").returncode == 0
        eventos = [json.loads(f)["evento"] for f in (instalada / "auditoria.jsonl").read_text().splitlines()]
        assert eventos.count("servidor-iniciado") == 2  # duplicate start reused the first instance
        assert eventos.count("servidor-detenido") == 2
        import threading
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        class Ajeno(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_error(403)
            def log_message(self, *args):
                pass
        with ThreadingHTTPServer(("127.0.0.1", 8078), Ajeno) as ajeno:
            hilo = threading.Thread(target=ajeno.serve_forever, daemon=True)
            hilo.start()
            assert ejecutar("iniciar", "--sin-edge").returncode != 0
            ajeno.shutdown()
            hilo.join(timeout=3)
    finally:
        if ocupado():
            ejecutar("detener")


def test_interrupcion_transaccion_no_deja_stock_parcial(instalada):
    identidad = configuracion(instalada)["id"]
    with closing(abrir_base(instalada, identidad)) as db, db:
        db.execute("INSERT INTO productos(nombre,categoria,stock) VALUES ('QA','Bebidas',10)")
    codigo = ("import sqlite3,sys,os; d=sqlite3.connect(sys.argv[1]); "
              "d.execute('BEGIN IMMEDIATE'); d.execute('UPDATE productos SET stock=999'); os._exit(7)")
    resultado = subprocess.run([sys.executable, "-c", codigo, str(instalada / ARCHIVO)])
    assert resultado.returncode == 7
    with closing(abrir_base(instalada, identidad)) as db:
        assert db.execute("SELECT stock FROM productos").fetchall() == [(10,)]
        assert db.execute("PRAGMA integrity_check").fetchall() == [("ok",)]


def test_edge_preproduccion_aviso_login_y_catalogo_vacio(instalada, tmp_path):
    ejecutable = os.getenv("POS_TEST_BROWSER")
    if not ejecutable:
        pytest.skip("Configurar POS_TEST_BROWSER con Edge")
    import websocket
    from tests.test_pos_web import abrir_navegador, esperar
    navegador = abrir_navegador(crear_app(instalada), ejecutable, tmp_path, websocket)
    with closing(navegador):
        evaluar = next(navegador)
        esperar(lambda: evaluar("document.querySelector('#entrenamientoAviso')?.textContent.includes('PREPRODUCCIÓN PERSISTENTE')"))
        assert evaluar("document.title.includes('PREPRODUCCIÓN')")
        esperar(lambda: evaluar("document.querySelector('#adminAccess')?.getClientRects().length > 0"))
        evaluar("document.querySelector('#adminAccess').click()")
        esperar(lambda: evaluar("document.querySelector('#usuarioPos') !== null"))
        clave = json.loads((instalada / "credenciales.json").read_text())["admin-preprod"]
        evaluar("document.querySelector('#usuarioPos').value = 'admin-preprod'; "
                "document.querySelector('#claveAdmin').value = " + json.dumps(clave) + "; document.querySelector('#accept').click()")
        esperar(lambda: evaluar("document.querySelector('#adminAccess').textContent.includes('Cerrar sesión (admin-preprod)')"))
        esperar(lambda: evaluar("document.querySelector('#productCount').textContent === '0 de 0 productos'"))
        assert evaluar("document.querySelectorAll('#cardsReal .card').length === 0")
        assert evaluar("document.querySelector('#entrenamientoAviso').getBoundingClientRect().top === 0")
