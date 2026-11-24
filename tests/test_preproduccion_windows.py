import json
import shutil
import sqlite3
from contextlib import closing
from uuid import uuid4
from threading import Event

import pytest
from fastapi.testclient import TestClient

from database import obtener_conexion
from pos_auth import verificar_contrasena
from pos_caja_diaria import ahora_local
from pos_entrenamiento_db import abrir_base_entrenamiento
from pos_preproduccion import (
    ARCHIVO, abrir_base, actualizar_catalogo, carpeta_segura, configuracion,
    mantenimiento, preparar, respaldo, restaurar, validar_respaldo,
)
from scripts.abadion_entrenamiento import PLANTILLA_CATALOGO, USUARIOS
from scripts.abadion_preproduccion import crear_app

ADMIN = "Admin-Privado-Ensayo-2026"
VENTAS = "Ventas-Privado-Ensayo-2026"
ORIGEN = "http://127.0.0.1:8077"
SIM = "/pos-api/simulacion"


@pytest.fixture
def instalacion(tmp_path):
    carpeta = tmp_path / "Preproduccion"
    preparar(carpeta, PLANTILLA_CATALOGO, ADMIN, VENTAS)
    return carpeta


def login(cliente):
    r = cliente.post("/pos-api/login", json={"usuario": "admin-preproduccion", "contrasena": ADMIN})
    assert r.status_code == 200, r.text
    assert r.headers["set-cookie"].startswith("abadion_preproduccion_admin=")


def test_inicializacion_vacia_privada_e_irrepetible(instalacion):
    with closing(abrir_base(instalacion)) as db:
        for tabla in ("ventas", "compras", "gastos", "pos_clientes", "sesiones_pos", "pos_jornadas_caja",
                      "pos_ventas_simuladas", "movimientos_caja", "pos_eventos_simulados"):
            assert db.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone() == (0,)
        assert db.execute("SELECT SUM(stock), COUNT(*) FROM productos").fetchone() == (0, 40)
        usuarios = dict(db.execute("SELECT usuario, password_hash FROM usuarios_pos"))
        assert set(usuarios) == {"admin-preproduccion", "ventas-preproduccion"}
        assert verificar_contrasena(ADMIN, usuarios["admin-preproduccion"])
        assert not db.execute("SELECT 1 FROM sqlite_schema WHERE name='pos_entrenamiento'").fetchone()
    anterior = (instalacion / ARCHIVO).read_bytes()
    with pytest.raises(FileExistsError):
        preparar(instalacion, PLANTILLA_CATALOGO, ADMIN, VENTAS)
    assert anterior == (instalacion / ARCHIVO).read_bytes()


@pytest.mark.parametrize("admin,ventas", [("corta", VENTAS), (ADMIN, ADMIN), (USUARIOS[0][2], VENTAS)])
def test_rechazo_credenciales_no_publica_carpeta(tmp_path, admin, ventas):
    carpeta = tmp_path / "Preproduccion"
    with pytest.raises(ValueError):
        preparar(carpeta, PLANTILLA_CATALOGO, admin, ventas)
    assert not carpeta.exists()


def test_aislamiento_base_general_entrenamiento_y_rutas(instalacion, tmp_path, monkeypatch):
    monkeypatch.setenv("NEGOCIO_DB_PATH", str(instalacion / ARCHIVO))
    with pytest.raises(ValueError):
        obtener_conexion()
    renombrada = tmp_path / "otra.db"
    shutil.copyfile(instalacion / ARCHIVO, renombrada)
    monkeypatch.setenv("NEGOCIO_DB_PATH", str(renombrada))
    with pytest.raises(ValueError):
        obtener_conexion()
    entrenamiento = tmp_path / "abadion-entrenamiento.db"
    shutil.copyfile(renombrada, entrenamiento)
    with pytest.raises(ValueError):
        abrir_base_entrenamiento(entrenamiento)
    with pytest.raises(ValueError):
        carpeta_segura(tmp_path / "OneDrive" / "Preproduccion")
    monkeypatch.setenv("OneDrive", str(tmp_path))
    with pytest.raises(ValueError):
        carpeta_segura(instalacion)


def test_api_venta_reinicio_restauracion_y_sesiones(instalacion, tmp_path, monkeypatch):
    testigo = tmp_path / "negocio.db"
    testigo.write_bytes(b"BASE REAL FALSA NO TOCAR")
    monkeypatch.setenv("NEGOCIO_DB_PATH", str(testigo))
    identidad = configuracion(instalacion)["id"]
    with TestClient(crear_app(instalacion), base_url=ORIGEN, headers={"Origin": ORIGEN}) as cliente:
        assert "PREPRODUCCIÓN PERSISTENTE" in cliente.get("/pos/").text
        assert cliente.post("/comandos", json={}).status_code == 404
        assert cliente.get("/pos/", headers={"Host": "externo"}).status_code == 400
        login(cliente)
        for caja in ("comidas", "bebidas_postres"):
            r = cliente.post(f"{SIM}/caja-diaria/{caja}/apertura", json={
                "id_solicitud": str(uuid4()), "fecha": ahora_local()[:10], "inicial_centavos": 0})
            assert r.status_code == 200, r.text
        productos = cliente.get("/pos-api/catalogo/productos").json()["productos"]
        comida = next(p for p in productos if p["nombre"] == "Mozzarella")
        pedido = {"id_solicitud": str(uuid4()), "items": [{"id_producto": comida["id_producto"], "cantidad": 1}],
                  "total_esperado_centavos": round(comida["precio_venta"] * 100), "medio_pago": "efectivo"}
        r = cliente.post(SIM + "/ventas", json=pedido)
        assert r.status_code == 200, r.text
        assert cliente.post(SIM + "/ventas", json=pedido).json() == r.json()
        bebida = next(p for p in productos if p["nombre"] == "Pepsi lata")
        compra = {"id_solicitud": str(uuid4()), "id_producto": bebida["id_producto"], "cantidad": 2,
                  "precio_unitario_centavos": 10000, "pagado_centavos": 20000,
                  "pagador": "comidas_efectivo", "medio_pago": "efectivo"}
        r = cliente.post(SIM + "/compras", json=compra)
        assert r.status_code == 200, r.text
        assert cliente.post(SIM + "/compras", json=compra).json() == r.json()
        r = cliente.post(SIM + "/ventas", json={**pedido, "id_solicitud": str(uuid4()),
            "items": [{"id_producto": bebida["id_producto"], "cantidad": 1}],
            "total_esperado_centavos": round(bebida["precio_venta"] * 100)})
        assert r.status_code == 200, r.text
        cliente_nuevo = cliente.post(SIM + "/clientes", json={
            "id_solicitud": str(uuid4()), "nombre": "Cliente ficticio de aceptación"})
        assert cliente_nuevo.status_code == 200, cliente_nuevo.text
        id_cliente = cliente_nuevo.json()["id_cliente"]
        fiado = {k: v for k, v in pedido.items() if k != "medio_pago"}
        r = cliente.post(SIM + "/ventas", json={**fiado, "id_solicitud": str(uuid4()),
            "pagos": [], "fiado": True, "id_cliente": id_cliente})
        assert r.status_code == 200, r.text
        pago = {"importe_centavos": pedido["total_esperado_centavos"], "receptor": "comidas_banco",
                "medio_pago": "transferencia", "referencia": "Ensayo de cobro"}
        ruta_cliente = SIM + f"/clientes/{id_cliente}/abonos"
        previa = cliente.post(ruta_cliente + "/vista-previa", json=pago)
        assert previa.status_code == 200, previa.text
        r = cliente.post(ruta_cliente, json={"id_solicitud": str(uuid4()), "pago": pago,
            "vista_previa": previa.json()["vista_previa"]})
        assert r.status_code == 200, r.text
        assert cliente.get(SIM + "/conciliacion").json()["cuadrado"]
        for caja, estado in cliente.get(SIM + "/caja-diaria").json()["cajas"].items():
            r = cliente.post(f"{SIM}/caja-diaria/{caja}/arqueo", json={
                "id_solicitud": str(uuid4()), "id_jornada": estado["id_jornada"],
                "revision_efectivo": estado["revision_efectivo"], "contado_centavos": estado["esperado_centavos"]})
            assert r.status_code == 200, r.text
            cierre = cliente.post(f"{SIM}/caja-diaria/{caja}/cierre", json={
                "id_solicitud": str(uuid4()), "id_jornada": estado["id_jornada"], "id_arqueo": r.json()["id_evento"]})
            assert cierre.status_code == 200, cierre.text
        esperado = cliente.get(SIM + "/caja-diaria").json()
        cookie = dict(cliente.cookies)
    copia = respaldo(instalacion)
    with closing(abrir_base(instalacion)) as db, db:
        db.execute("UPDATE productos SET stock=99")
    restaurar(instalacion, copia)
    with closing(abrir_base(instalacion)) as db:
        assert db.execute("SELECT SUM(stock) FROM productos").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM pos_ventas_simuladas").fetchone() == (3,)
        assert db.execute("SELECT COUNT(*) FROM compras").fetchone() == (1,)
        assert db.execute("SELECT COUNT(*) FROM sesiones_pos WHERE revocada=0").fetchone() == (0,)
    with TestClient(crear_app(instalacion), base_url=ORIGEN, headers={"Origin": ORIGEN}) as reinicio:
        reinicio.cookies.update(cookie)
        assert reinicio.get(SIM + "/caja-diaria").status_code == 401
        reinicio.cookies.clear()
        login(reinicio)
        assert reinicio.get(SIM + "/caja-diaria").json() == esperado
    assert configuracion(instalacion)["id"] == identidad
    assert testigo.read_bytes() == b"BASE REAL FALSA NO TOCAR"


def test_restauracion_rechaza_corrupcion_identidad_y_lock(instalacion, tmp_path):
    copia = respaldo(instalacion)
    with mantenimiento(instalacion):
        with pytest.raises(ValueError):
            restaurar(instalacion, copia)
    copia.write_bytes(copia.read_bytes() + b"corrupto")
    anterior = (instalacion / ARCHIVO).read_bytes()
    with pytest.raises(ValueError):
        restaurar(instalacion, copia)
    assert (instalacion / ARCHIVO).read_bytes() == anterior
    otra = tmp_path / "otro" / "Preproduccion"
    preparar(otra, PLANTILLA_CATALOGO, ADMIN, VENTAS)
    with pytest.raises(ValueError):
        restaurar(instalacion, respaldo(otra))


def test_catalogo_preserva_stock_ids_y_respalda(instalacion, tmp_path):
    with closing(abrir_base(instalacion)) as db, db:
        db.execute("UPDATE productos SET stock=7 WHERE nombre='Pepsi lata'")
        identificador = db.execute("SELECT id_producto FROM productos WHERE nombre='Pepsi lata'").fetchone()[0]
    catalogo = json.loads(PLANTILLA_CATALOGO.read_text(encoding="utf-8"))
    catalogo["productos"].append({**catalogo["productos"][-1], "nombre": "Bebida nueva", "stock_inicial": 999})
    archivo = tmp_path / "catalogo.json"
    archivo.write_text(json.dumps(catalogo), encoding="utf-8")
    validar_respaldo(instalacion, actualizar_catalogo(instalacion, archivo))
    with closing(abrir_base(instalacion)) as db:
        assert db.execute("SELECT id_producto, stock FROM productos WHERE nombre='Pepsi lata'").fetchone() == (identificador, 7)
        assert db.execute("SELECT stock FROM productos WHERE nombre='Bebida nueva'").fetchone() == (0,)


def test_respaldo_incluye_wal_confirmado(instalacion):
    with closing(abrir_base(instalacion)) as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("UPDATE productos SET stock=12 WHERE nombre='Pepsi lata'")
        db.commit()
        copia = respaldo(instalacion)
        validar_respaldo(instalacion, copia)
        with closing(sqlite3.connect(copia)) as restaurada:
            assert restaurada.execute("SELECT stock FROM productos WHERE nombre='Pepsi lata'").fetchone() == (12,)


def test_base_ausente_o_version_distinta_no_se_recrea(instalacion):
    with closing(abrir_base(instalacion)) as db:
        db.execute("PRAGMA user_version=999")
    with pytest.raises(ValueError):
        abrir_base(instalacion)
    (instalacion / ARCHIVO).unlink()
    with pytest.raises(sqlite3.OperationalError):
        abrir_base(instalacion)
    assert not (instalacion / ARCHIVO).exists()


def test_respaldos_automaticos_fallo_inicial_y_recuperacion(instalacion, monkeypatch, caplog):
    import scripts.abadion_preproduccion as lanzador

    def fallo_inicial(carpeta):
        raise PermissionError("Ensayo sin permiso para copia inicial")

    monkeypatch.setattr(lanzador, "respaldo", fallo_inicial)
    with pytest.raises(PermissionError):
        with TestClient(crear_app(instalacion), base_url=ORIGEN):
            pytest.fail("El servidor no debe arrancar sin respaldo inicial")

    completada = Event()
    llamadas = []

    def copia_con_fallo_transitorio(carpeta):
        llamadas.append(1)
        if len(llamadas) == 2:
            raise OSError("Ensayo de fallo periódico")
        resultado = respaldo(carpeta)
        if len(llamadas) >= 3:
            completada.set()
        return resultado

    monkeypatch.setattr(lanzador, "respaldo", copia_con_fallo_transitorio)
    with TestClient(crear_app(instalacion, intervalo=0.02), base_url=ORIGEN):
        assert completada.wait(10), "El respaldo periódico debe reintentarse"
    assert len(llamadas) >= 4  # inicial, fallo, recuperación, cierre
    assert "FALLÓ EL RESPALDO" in caplog.text
    for archivo in (instalacion / "backups").glob("*.db"):
        validar_respaldo(instalacion, archivo)
