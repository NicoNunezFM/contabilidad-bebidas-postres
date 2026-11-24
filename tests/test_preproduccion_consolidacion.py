"""Only fictitious installations under pytest's external temporary directory."""
import json
import os
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path
from threading import Event

import pytest
from fastapi.testclient import TestClient

import pos_preproduccion as almacenamiento
from pos_preproduccion import (
    ARCHIVO, abrir_base, actualizar_catalogo, configuracion, integridad, respaldo,
    restaurar, validar_respaldo,
)
from pos_entrenamiento_db import bloquear_entrenamiento
from scripts.abadion_preproduccion import preparar, crear_app
from tests.test_preproduccion import cliente, post, SIM
from pos_contabilidad import fecha_local


@pytest.fixture
def instalada(tmp_path):
    carpeta = tmp_path / "Preproduccion"
    preparar(carpeta)
    return carpeta


@pytest.fixture
def archivo(tmp_path):
    ruta = tmp_path / "catalogo-ficticio.json"
    ruta.write_text(json.dumps({"aviso": "Sólo QA", "productos": [
        {"nombre": "Bebida QA", "categoria": "Bebidas", "precio_centavos": 2000,
         "controla_stock": True, "stock_inicial": 999, "adicionales": ["Extra QA"]},
        {"nombre": "Comida QA", "categoria": "Comidas", "precio_centavos": 1000,
         "controla_stock": False, "stock_inicial": 999}],
        "adicionales": [{"nombre": "Extra QA", "precio_centavos": 100}]}), encoding="utf-8")
    return ruta


def abrir(carpeta):
    return closing(abrir_base(carpeta, configuracion(carpeta)["id"]))


def editar(archivo, cambio):
    datos = json.loads(archivo.read_text(encoding="utf-8"))
    cambio(datos)
    archivo.write_text(json.dumps(datos), encoding="utf-8")


def contenido(carpeta):
    with abrir(carpeta) as db:
        # SQLite UPSERT may consume AUTOINCREMENT sequence values without creating rows.
        return [linea for linea in db.iterdump() if not linea.startswith('INSERT INTO "sqlite_sequence"')]


def test_catalogo_historial_stock_ids_omisiones_e_idempotencia(instalada, archivo):
    antes = contenido(instalada)
    plan = actualizar_catalogo(instalada, archivo, validar=True)
    assert plan["nuevos_stock_cero"] == ["Bebida QA", "Comida QA"]
    assert contenido(instalada) == antes
    assert not list((instalada / "backups").glob("*pre-catalogo.db"))
    actualizar_catalogo(instalada, archivo)
    c = cliente(instalada)
    with abrir(instalada) as db, db:
        ids = dict(db.execute("SELECT nombre,id_producto FROM productos"))
        assert db.execute("SELECT SUM(stock) FROM productos").fetchone() == (0,)
        db.execute("UPDATE productos SET stock=10 WHERE nombre='Bebida QA'")
    for caja in ("comidas", "bebidas_postres"):
        post(c, SIM + f"/caja-diaria/{caja}/apertura", fecha=fecha_local(), inicial_centavos=0)
    venta = post(c, SIM + "/ventas", items=[{"id_producto": ids["Bebida QA"], "cantidad": 1}],
                 total_esperado_centavos=2000, medio_pago="efectivo")
    informe = c.get(SIM + "/contabilidad").json()
    with abrir(instalada) as db:
        tablas = [t for t, in db.execute("SELECT name FROM sqlite_schema WHERE type='table'")
                  if t not in {"productos", "adicionales_catalogo", "pos_catalogo_entrenamiento",
                               "pos_adicionales_producto", "sqlite_sequence"}]
        historial = {t: db.execute(f'SELECT * FROM "{t}"').fetchall() for t in tablas}
    editar(archivo, lambda d: (d["productos"].pop(), d["productos"][0].update(precio_centavos=2500)))
    resultado = actualizar_catalogo(instalada, archivo)
    assert resultado["fuera_menu"] == ["Comida QA"]
    validar_respaldo(instalada, resultado["backup"])
    with abrir(instalada) as db:
        assert db.execute("SELECT id_producto,stock,precio_venta FROM productos WHERE nombre='Bebida QA'").fetchone() == (ids["Bebida QA"], 9, 25)
        assert db.execute("SELECT estado FROM pos_catalogo_entrenamiento WHERE id_producto=?", (ids["Comida QA"],)).fetchone() == ("fuera_menu",)
        assert {t: db.execute(f'SELECT * FROM "{t}"').fetchall() for t in tablas} == historial
    assert c.get(SIM + "/contabilidad").json() == informe
    assert c.get(SIM + "/conciliacion").json()["cuadrado"]
    estable = contenido(instalada)
    actualizar_catalogo(instalada, archivo)
    assert contenido(instalada) == estable
    assert venta["id_venta"]
    with bloquear_entrenamiento(instalada):
        restaurar(instalada, resultado["backup"])
    with abrir(instalada) as db:
        assert db.execute("SELECT stock,precio_venta FROM productos WHERE nombre='Bebida QA'").fetchone() == (9, 20)
    assert c.get(SIM + "/contabilidad").status_code == 401


@pytest.mark.parametrize("fallo", ["duplicado", "booleano", "precio", "referencia", "ejemplo", "campo"])
def test_catalogo_invalido_no_modifica(instalada, archivo, fallo):
    def cambio(d):
        if fallo == "duplicado":
            d["productos"].append(dict(d["productos"][0]))
        elif fallo == "booleano":
            d["productos"][0]["controla_stock"] = "sí"
        elif fallo == "precio":
            d["productos"][0]["precio_centavos"] = -1
        elif fallo == "referencia":
            d["productos"][0]["adicionales"] = ["Inexistente"]
        elif fallo == "ejemplo":
            d["adicionales"].append({"nombre": "Extra de práctica (ejemplo)", "precio_centavos": 0})
        else:
            d["productos"][0]["id_producto"] = 999
    editar(archivo, cambio)
    antes = (instalada / ARCHIVO).read_bytes()
    with pytest.raises(ValueError):
        actualizar_catalogo(instalada, archivo)
    assert (instalada / ARCHIVO).read_bytes() == antes


@pytest.mark.parametrize("campo,valor", [("categoria", "Postres"), ("controla_stock", False)])
def test_no_reclasifica_saldos(instalada, archivo, campo, valor):
    actualizar_catalogo(instalada, archivo)
    editar(archivo, lambda d: d["productos"][0].update({campo: valor}))
    antes = contenido(instalada)
    with pytest.raises(ValueError, match="revisión separada"):
        actualizar_catalogo(instalada, archivo)
    assert contenido(instalada) == antes


def test_alias_preserva_id_y_rechaza_ambiguos(instalada, archivo):
    with abrir(instalada) as db, db:
        id_original = db.execute("INSERT INTO productos(nombre,categoria,stock,controla_stock) VALUES ('Clasica simple','Comidas',7,0)").lastrowid
    editar(archivo, lambda d: d["productos"][1].update(nombre="Clásica simple"))
    actualizar_catalogo(instalada, archivo)
    with abrir(instalada) as db, db:
        assert db.execute("SELECT id_producto,stock FROM productos WHERE nombre='Clásica simple'").fetchone() == (id_original, 7)
        db.execute("INSERT INTO productos(nombre,categoria) VALUES ('CLASICA SIMPLE','Comidas')")
    antes = contenido(instalada)
    with pytest.raises(ValueError, match="ambiguos"):
        actualizar_catalogo(instalada, archivo)
    assert contenido(instalada) == antes


def test_adicional_casefold_no_duplica(instalada, archivo):
    actualizar_catalogo(instalada, archivo)
    editar(archivo, lambda d: (d["adicionales"][0].update(nombre="extra qa"),
                             d["productos"][0].update(adicionales=["extra qa"])))
    with pytest.raises(ValueError, match="nombre exacto"):
        actualizar_catalogo(instalada, archivo)


def test_lock_mantenimiento_y_backup_fallido(instalada, archivo, monkeypatch):
    with bloquear_entrenamiento(instalada):
        with pytest.raises(ValueError, match="en uso"):
            actualizar_catalogo(instalada, archivo)
    antes = contenido(instalada)
    def fallar(*args):
        raise PermissionError("Fallo ficticio de permisos/disco")
    monkeypatch.setattr(almacenamiento, "respaldo", fallar)
    with pytest.raises(PermissionError):
        actualizar_catalogo(instalada, archivo)
    assert contenido(instalada) == antes


def test_error_durante_catalogo_revierte_todo(instalada, archivo, monkeypatch):
    import scripts.abadion_entrenamiento as catalogos
    original = catalogos.cargar_catalogo
    def fallar(db, catalogo):
        original(db, catalogo)
        raise sqlite3.OperationalError("Interrupción ficticia tras escribir")
    monkeypatch.setattr(catalogos, "cargar_catalogo", fallar)
    antes = contenido(instalada)
    with pytest.raises(sqlite3.OperationalError):
        actualizar_catalogo(instalada, archivo)
    assert contenido(instalada) == antes
    validar_respaldo(instalada, next((instalada / "backups").glob("*pre-catalogo.db")).name)


def test_wal_snapshot_no_incluye_transaccion_abierta(instalada, archivo):
    actualizar_catalogo(instalada, archivo)
    with abrir(instalada) as db:
        assert db.execute("PRAGMA journal_mode=WAL").fetchone() == ("wal",)
        db.execute("UPDATE productos SET stock=12")
        db.commit()
        db.execute("BEGIN IMMEDIATE")
        db.execute("UPDATE productos SET stock=999")
        copia = respaldo(instalada)
        validar_respaldo(instalada, copia.name)
        with closing(sqlite3.connect(copia)) as foto:
            assert foto.execute("SELECT DISTINCT stock FROM productos").fetchall() == [(12,)]
        db.rollback()


@pytest.mark.parametrize("sufijo", ["-wal", "-shm", "-journal"])
def test_backup_con_auxiliares_no_restaura(instalada, sufijo):
    copia = respaldo(instalada)
    Path(str(copia) + sufijo).write_bytes(b"auxiliar ficticio")
    antes = (instalada / ARCHIVO).read_bytes()
    with bloquear_entrenamiento(instalada), pytest.raises(ValueError, match="auxiliares"):
        restaurar(instalada, copia.name)
    assert (instalada / ARCHIVO).read_bytes() == antes


def test_corrupcion_cuarentena_y_recuperacion_explicita(instalada):
    copia = respaldo(instalada)
    destino = instalada / ARCHIVO
    destino.write_bytes(b"SQLite corrupta ficticia")
    with bloquear_entrenamiento(instalada):
        with pytest.raises(sqlite3.DatabaseError):
            restaurar(instalada, copia.name)
        assert destino.read_bytes() == b"SQLite corrupta ficticia"
        destino.rename(instalada / "cuarentena-ficticia.db")
        restaurar(instalada, copia.name, base_ausente=True)
    assert (instalada / "cuarentena-ficticia.db").read_bytes() == b"SQLite corrupta ficticia"
    with abrir(instalada) as db:
        integridad(db)


def test_proceso_abrupto_wal_y_reapertura(instalada, archivo):
    actualizar_catalogo(instalada, archivo)
    codigo = ("import sqlite3,sys,os; d=sqlite3.connect(sys.argv[1]); "
              "d.execute('PRAGMA journal_mode=WAL'); d.execute('UPDATE productos SET stock=8'); d.commit(); "
              "d.execute('BEGIN IMMEDIATE'); d.execute('UPDATE productos SET stock=999'); os._exit(7)")
    assert subprocess.run([sys.executable, "-c", codigo, str(instalada / ARCHIVO)], timeout=20).returncode == 7
    with abrir(instalada) as db:
        assert db.execute("SELECT DISTINCT stock FROM productos").fetchall() == [(8,)]
        integridad(db)
    copia = respaldo(instalada)
    validar_respaldo(instalada, copia.name)


def test_periodico_reintenta_y_espera_cierre(instalada, monkeypatch):
    import scripts.abadion_preproduccion as lanzador
    recuperado = Event()
    llamadas = []
    def simular(carpeta, etapa="manual"):
        llamadas.append(etapa)
        if llamadas.count("automatico") == 1 and etapa == "automatico":
            raise OSError("fallo periódico ficticio")
        resultado = respaldo(carpeta, etapa)
        if etapa == "automatico":
            recuperado.set()
        return resultado
    monkeypatch.setattr(lanzador, "respaldo", simular)
    with TestClient(crear_app(instalada, intervalo=.02), base_url="http://127.0.0.1"):
        assert recuperado.wait(10)
    assert llamadas[0] == "inicio" and llamadas[-1] == "detencion"
    assert any(json.loads(l)["evento"] == "backup-fallido" for l in (instalada / "auditoria.jsonl").read_text().splitlines())


def test_fallo_backup_inicial_no_arranca(instalada, monkeypatch):
    import scripts.abadion_preproduccion as lanzador
    def fallar(*args):
        raise PermissionError("Fallo inicial ficticio")
    monkeypatch.setattr(lanzador, "respaldo", fallar)
    with pytest.raises(PermissionError), TestClient(crear_app(instalada)):
        pytest.fail("No debe iniciar sin backup")


def test_cli_catalogo_exige_ruta_explicita(archivo):
    script = Path(__file__).resolve().parents[1] / "scripts" / "abadion_preproduccion.py"
    resultado = subprocess.run([sys.executable, str(script), "validar-catalogo", "--catalogo", str(archivo)],
                              capture_output=True, text=True, encoding="utf-8", timeout=20)
    assert resultado.returncode == 1
    assert "--carpeta explícita" in resultado.stderr


def test_sha_revisado_impide_aplicar_otro_archivo(instalada, archivo):
    plan = actualizar_catalogo(instalada, archivo, validar=True)
    editar(archivo, lambda d: d["productos"][0].update(precio_centavos=3000))
    antes = contenido(instalada)
    with pytest.raises(ValueError, match="SHA-256"):
        actualizar_catalogo(instalada, archivo, sha256=plan["sha256"])
    assert contenido(instalada) == antes


def test_backup_fallido_no_publica_parcial(instalada, monkeypatch):
    anteriores = {p.name for p in (instalada / "backups").iterdir()}
    def fallar(db):
        raise ValueError("Integridad ficticia fallida")
    monkeypatch.setattr(almacenamiento, "integridad", fallar)
    with pytest.raises(ValueError, match="Integridad"):
        respaldo(instalada)
    assert {p.name for p in (instalada / "backups").iterdir()} == anteriores


def test_backup_corrupto_con_hash_recalculado_rechazado(instalada):
    import hashlib
    copia = respaldo(instalada)
    copia.write_bytes(b"No es SQLite aunque el hash sea correcto")
    manifiesto = copia.with_suffix(".json")
    meta = json.loads(manifiesto.read_text())
    meta["sha256"] = hashlib.sha256(copia.read_bytes()).hexdigest()
    manifiesto.write_text(json.dumps(meta))
    antes = contenido(instalada)
    with bloquear_entrenamiento(instalada), pytest.raises(sqlite3.DatabaseError):
        restaurar(instalada, copia.name)
    assert contenido(instalada) == antes


def test_catalogo_bloqueado_por_otro_proceso(instalada, archivo):
    fuente = Path(__file__).resolve().parents[1] / "src"
    codigo = ("import sys; from pathlib import Path; sys.path.insert(0,sys.argv[1]); "
              "from pos_entrenamiento_db import bloquear_entrenamiento; "
              "c=bloquear_entrenamiento(Path(sys.argv[2])); c.__enter__(); print('lock',flush=True); input()")
    proceso = subprocess.Popen([sys.executable, "-c", codigo, str(fuente), str(instalada)],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        assert proceso.stdout.readline().strip() == "lock"
        with pytest.raises(ValueError, match="en uso"):
            actualizar_catalogo(instalada, archivo)
    finally:
        proceso.communicate("\n", timeout=10)
    actualizar_catalogo(instalada, archivo)


@pytest.mark.parametrize("colision", ["db", "json"])
def test_colision_backup_nunca_borra_archivos_anteriores(instalada, monkeypatch, colision):
    from datetime import datetime, timezone
    instante = datetime.now(timezone.utc)
    class FechaFija:
        @staticmethod
        def now(zona):
            return instante
    monkeypatch.setattr(almacenamiento, "datetime", FechaFija)
    directorio = instalada / "backups"
    nombre = instante.strftime("%Y%m%dT%H%M%S%fZ-") + "colision"
    if colision == "db":
        respaldo(instalada, "colision")
    else:
        (directorio / (nombre + ".json")).write_text("manifiesto anterior ficticio")
    anteriores = {p.name: p.read_bytes() for p in directorio.iterdir()}
    with pytest.raises(FileExistsError):
        respaldo(instalada, "colision")
    assert {p.name: p.read_bytes() for p in directorio.iterdir()} == anteriores


def test_cierre_espera_backup_automatico_en_curso(instalada, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    import scripts.abadion_preproduccion as lanzador
    en_curso, liberar, terminado = Event(), Event(), Event()
    def controlado(carpeta, etapa="manual"):
        if etapa == "automatico":
            en_curso.set()
            assert liberar.wait(10)
        if etapa == "detencion":
            assert terminado.is_set(), "No cerrar antes de completar el snapshot en curso"
        resultado = respaldo(carpeta, etapa)
        if etapa == "automatico":
            terminado.set()
        return resultado
    monkeypatch.setattr(lanzador, "respaldo", controlado)
    def ciclo():
        with TestClient(crear_app(instalada, intervalo=.02), base_url="http://127.0.0.1"):
            assert en_curso.wait(10)
        return True
    with ThreadPoolExecutor(max_workers=1) as grupo:
        futuro = grupo.submit(ciclo)
        try:
            assert en_curso.wait(10)
            assert not futuro.done()
        finally:
            liberar.set()
        assert futuro.result(timeout=15)


def test_esquema_alternativo_30_no_se_migra(instalada):
    with abrir(instalada) as db, db:
        db.execute("ALTER TABLE pos_preproduccion RENAME COLUMN instalacion TO identidad")
    antes = (instalada / ARCHIVO).read_bytes()
    with pytest.raises(sqlite3.OperationalError, match="instalacion"):
        abrir_base(instalada, configuracion(instalada)["id"])
    assert (instalada / ARCHIVO).read_bytes() == antes
