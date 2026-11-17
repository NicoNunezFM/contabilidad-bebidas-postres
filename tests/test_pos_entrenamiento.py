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
from scripts.abadion_entrenamiento import (
    ARCHIVO_CATALOGO, CONFIRMACION, PLANTILLA_CATALOGO, USUARIOS, actualizar_catalogo, preparar_base,
)


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


def test_actualizar_catalogo_conserva_una_instalacion_anterior(tmp_path):
    json_local = tmp_path / ARCHIVO_CATALOGO
    legado = {
        "aviso": "Catálogo anterior",
        "productos": [
            {"nombre": nombre, "categoria": categoria, "precio_centavos": precio,
             "controla_stock": True, "stock_inicial": 7}
            for nombre, categoria, precio in (
                ("Chocotorta", "Postres", 450000), ("Manaos Lima 2.25l", "Bebidas", 200000),
            )
        ],
        "adicionales": [],
    }
    json_local.write_text(json.dumps(legado), encoding="utf-8")
    destino = preparar_base(tmp_path)
    with closing(sqlite3.connect(destino)) as db, db:
        db.execute("DROP TABLE pos_catalogo_entrenamiento")
    cliente = TestClient(crear_app_entrenamiento(tmp_path), base_url=ORIGEN, headers={"Origin": ORIGEN})
    simulacion = "/pos-api/simulacion"
    ventas = f"{simulacion}/ventas"
    catalogo = "/pos-api/catalogo/productos"
    validar = "/pos-api/pedidos/validar"
    usuario, _, clave = USUARIOS[0]
    assert cliente.post("/pos-api/login", json={"usuario": usuario, "contrasena": clave}).status_code == 200
    apertura = cliente.post(f"{simulacion}/caja-diaria/bebidas_postres/apertura", json={
        "id_solicitud": str(uuid4()), "fecha": ahora_local()[:10], "inicial_centavos": 10000,
    })
    assert apertura.status_code == 200, apertura.text
    grande, lima = cliente.get(catalogo).json()["productos"]
    pedido = {
        "id_solicitud": str(uuid4()),
        "items": [{"id_producto": grande["id_producto"], "cantidad": 1}],
        "total_esperado_centavos": 450000,
        "pagos": [{"receptor": "bebidas_postres_efectivo", "medio_pago": "efectivo", "importe_centavos": 450000}],
    }
    anterior = cliente.post(ventas, json=pedido)
    assert anterior.status_code == 200, anterior.text

    nuevo = PLANTILLA_CATALOGO.read_text(encoding="utf-8")
    json_local.write_text(nuevo, encoding="utf-8")
    with bloquear_entrenamiento(tmp_path), pytest.raises(ValueError, match="está en uso"):
        actualizar_catalogo(tmp_path)
    actualizar_catalogo(tmp_path)
    actualizar_catalogo(tmp_path)
    productos = {p["nombre"]: p for p in cliente.get(catalogo).json()["productos"]}
    assert len(productos) == 40
    assert "Manaos Lima 2.25l" not in productos
    assert productos["Chocotorta grande"]["id_producto"] == grande["id_producto"]
    assert productos["Chocotorta grande"]["stock"] == 6
    assert cliente.get("/pos-api/yo").status_code == 200
    assert cliente.post(ventas, json=pedido).json() == anterior.json()

    def item(nombre, cantidad=1):
        return {"id_producto": productos[nombre]["id_producto"], "cantidad": cantidad}

    for producto in ("Pollo con papas simple", "Pollo con papas doble", "Big Mac simple", "Big Mac doble",
                     "Cheddar y huevo simple", "Cheddar y huevo doble", "Mozzarella", "Jamón y morrones"):
        assert cliente.post(validar, json={"items": [item(producto)]}).status_code == 409
    assert productos["Mozzarella"]["precio_venta"] is None
    assert productos["Big Mac doble"]["precio_venta"] == 9000
    assert productos["Big Mac doble"]["estado_entrenamiento"] == "sin_stock"
    assert cliente.post(validar, json={"items": [{"id_producto": lima["id_producto"], "cantidad": 1}]}).status_code == 409
    assert cliente.patch(f'/pos-api/admin/productos/{grande["id_producto"]}/precio',
                         json={"precio_nuevo": 3000}).status_code == 403

    sabores = {"items": [item("Chocotorta chica"), item("Oreo chico")]}
    assert cliente.post(validar, json=sabores).json()["total_centavos"] == 600000
    items = [item("Oreo chico", 3), item("Clásica doble")]
    cotizacion = cliente.post(validar, json={"items": items}).json()
    assert cotizacion["descuento_centavos"] == 100000
    assert cotizacion["total_centavos"] == 1700000
    assert [(p["cantidad"], p["precio_unitario_centavos"]) for p in cotizacion["items"]] == [
        (2, 250000), (1, 300000), (1, 900000),
    ]
    apertura = cliente.post(f"{simulacion}/caja-diaria/comidas/apertura", json={
        "id_solicitud": str(uuid4()), "fecha": ahora_local()[:10], "inicial_centavos": 10000,
    })
    assert apertura.status_code == 200, apertura.text
    venta = cliente.post(ventas, json={
        "id_solicitud": str(uuid4()), "items": items,
        "total_esperado_centavos": 1700000, "medio_pago": "efectivo",
    })
    assert venta.status_code == 200, venta.text
    assert venta.json()["cajas_centavos"] == {"bebidas_postres": 800000, "comidas": 900000}
    usuario, _, clave = USUARIOS[1]
    assert cliente.post("/pos-api/login", json={"usuario": usuario, "contrasena": clave}).status_code == 200
    devolucion = cliente.post(f'{ventas}/{venta.json()["id_venta"]}/devoluciones', json={
        "id_solicitud": str(uuid4()), "motivo": "Prueba de promoción",
        "items": [{"linea": 1, "cantidad": 1}],
    })
    assert devolucion.status_code == 200, devolucion.text
    assert devolucion.json()["reembolsado_centavos"] == 250000

    configuracion = json.loads(nuevo)
    configuracion["combinar_sabores_promo"] = True
    pizza = next(p for p in configuracion["productos"] if p["nombre"] == "Mozzarella")
    pizza["precio_centavos"] = 0
    json_local.write_text(json.dumps(configuracion), encoding="utf-8")
    with pytest.raises(ValueError, match="precio_centavos"):
        actualizar_catalogo(tmp_path)
    assert cliente.post(validar, json=sabores).json()["total_centavos"] == 600000

    pizza["precio_centavos"] = 123400  # Importe ficticio para probar la activación por JSON.
    json_local.write_text(json.dumps(configuracion), encoding="utf-8")
    actualizar_catalogo(tmp_path)
    assert cliente.post(validar, json=sabores).json()["total_centavos"] == 500000
    assert cliente.post(validar, json={"items": [item("Mozzarella")]}).json()["total_centavos"] == 123400


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
