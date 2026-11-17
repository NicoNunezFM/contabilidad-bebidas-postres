import json
import sqlite3
from contextlib import closing
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from api import app as app_normal
from database import obtener_conexion
from pos_caja_diaria import ahora_local
from pos_entrenamiento_db import ARCHIVO_BASE, bloquear_entrenamiento, carpeta_local
from pos_entrenamiento_web import AVISO, crear_app_entrenamiento
from pos_simulacion import crear_esquema_simulacion
from scripts.abadion_entrenamiento import ARCHIVO_CATALOGO, CONFIRMACION, USUARIOS, preparar_base


ORIGEN = "http://127.0.0.1:8060"


def test_entrenamiento_aisla_ventas_fiados_caja_y_sesiones(tmp_path, monkeypatch):
    real_falsa = tmp_path / "negocio.db"
    real_falsa.write_bytes(b"testigo de aislamiento")
    monkeypatch.setenv("NEGOCIO_DB_PATH", str(real_falsa))
    carpeta = tmp_path / "entrenamiento"
    destino = preparar_base(carpeta)
    cliente = TestClient(crear_app_entrenamiento(carpeta), base_url=ORIGEN, headers={"Origin": ORIGEN})
    for url in ("/", "/pos/", "/pos/index.html"):
        assert AVISO in cliente.get(url).text
    assert AVISO not in TestClient(app_normal).get("/pos/").text
    assert cliente.get("/pos/", headers={"Host": "red-ajena"}).status_code == 400
    assert cliente.post("/comando", json={}).status_code == 404
    assert cliente.get("/pos-api/simulacion/estado").json()["caja_diaria"]

    usuario, _, clave = USUARIOS[0]
    sesion = cliente.post("/pos-api/login", json={"usuario": usuario, "contrasena": clave})
    assert sesion.status_code == 200
    assert sesion.headers["Set-Cookie"].startswith("abadion_entrenamiento_ventas=")
    apertura = cliente.post("/pos-api/simulacion/caja-diaria/bebidas_postres/apertura", json={
        "id_solicitud": str(uuid4()), "fecha": ahora_local()[:10], "inicial_centavos": 10000,
    })
    assert apertura.status_code == 200, apertura.text

    url_catalogo = "/pos-api/catalogo/productos"
    producto = next(p for p in cliente.get(url_catalogo).json()["productos"] if p["controla_stock"])
    total = round(producto["precio_venta"] * 100)
    venta = cliente.post("/pos-api/simulacion/ventas", json={
        "id_solicitud": str(uuid4()),
        "items": [{"id_producto": producto["id_producto"], "cantidad": 1}],
        "total_esperado_centavos": total,
        "pagos": [{"receptor": "bebidas_postres_efectivo", "medio_pago": "efectivo", "importe_centavos": 500}],
        "fiado": True, "deudor": "Cliente de ejemplo",
    })
    assert venta.status_code == 200, venta.text
    assert venta.json()["saldo_pendiente_centavos"] == total - 500
    assert real_falsa.read_bytes() == b"testigo de aislamiento"
    with closing(sqlite3.connect(destino)) as db:
        assert db.execute("SELECT stock FROM productos WHERE id_producto = ?", (producto["id_producto"],)).fetchone() == (23,)

    plantilla = carpeta / ARCHIVO_CATALOGO
    catalogo = json.loads(plantilla.read_text(encoding="utf-8"))
    catalogo["productos"][0]["nombre"] = "Bebida de catálogo editado"
    plantilla.write_text(json.dumps(catalogo), encoding="utf-8")
    preparar_base(carpeta, confirmacion=CONFIRMACION)
    assert cliente.get("/pos-api/yo").status_code == 401
    productos = cliente.get(url_catalogo).json()["productos"]
    assert "Bebida de catálogo editado" in {p["nombre"] for p in productos}
    assert {p["stock"] for p in productos if p["controla_stock"]} == {24}
    with closing(sqlite3.connect(destino)) as db:
        for tabla in ("pos_ventas_simuladas", "pos_jornadas_caja", "pos_movimientos_simulados", "sesiones_pos"):
            assert db.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone() == (0,)
    assert real_falsa.read_bytes() == b"testigo de aislamiento"
    monkeypatch.setenv("NEGOCIO_DB_PATH", str(destino))
    with pytest.raises(ValueError, match="Entrenamiento"):
        obtener_conexion()


def test_reinicio_exige_confirmacion_marcador_y_cierre_del_servidor(tmp_path):
    destino = preparar_base(tmp_path)
    contenido = destino.read_bytes()
    with pytest.raises(ValueError, match=CONFIRMACION):
        preparar_base(tmp_path, confirmacion="reiniciar")
    with pytest.raises(FileExistsError):
        preparar_base(tmp_path)
    with bloquear_entrenamiento(tmp_path), pytest.raises(ValueError, match="está en uso"):
        preparar_base(tmp_path, confirmacion=CONFIRMACION)
    (tmp_path / ARCHIVO_CATALOGO).write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="validation"):
        preparar_base(tmp_path, confirmacion=CONFIRMACION)
    assert destino.read_bytes() == contenido

    destino.unlink()
    with closing(sqlite3.connect(destino)) as db, db:
        crear_esquema_simulacion(db)
    contenido = destino.read_bytes()
    with pytest.raises(ValueError, match="marcador"):
        crear_app_entrenamiento(tmp_path)
    with pytest.raises(ValueError, match="marcador"):
        preparar_base(tmp_path, confirmacion=CONFIRMACION)
    assert destino.read_bytes() == contenido


def test_rechaza_alias_de_otra_base(tmp_path):
    carpeta = tmp_path / "simulacion"
    carpeta.mkdir()
    original = tmp_path / "negocio.db"
    original.write_bytes(b"testigo")
    try:
        (carpeta / ARCHIVO_BASE).hardlink_to(original)
    except PermissionError:
        pytest.skip("El entorno de pruebas no permite enlaces físicos.")
    with pytest.raises(ValueError, match="archivo local directo"):
        crear_app_entrenamiento(carpeta)
    assert original.read_bytes() == b"testigo"


def test_rechaza_directorio_sincronizado(tmp_path, monkeypatch):
    raiz = tmp_path / "OneDrive"
    monkeypatch.setenv("LOCALAPPDATA", str(raiz))
    monkeypatch.setattr(Path, "home", staticmethod(lambda: raiz))
    with pytest.raises(ValueError, match="fuera de OneDrive"):
        carpeta_local()
