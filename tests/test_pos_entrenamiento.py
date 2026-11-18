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
    activar_contabilidad,
)


ORIGEN = "http://127.0.0.1:8060"


@pytest.fixture
def menu_entrenamiento(tmp_path):
    ruta = preparar_base(tmp_path)
    with TestClient(crear_app_entrenamiento(tmp_path), base_url=ORIGEN, headers={"Origin": ORIGEN}) as cliente:
        usuario, _, clave = USUARIOS[1]
        assert cliente.post("/pos-api/login", json={"usuario": usuario, "contrasena": clave}).status_code == 200
        productos = cliente.get("/pos-api/catalogo/productos").json()["productos"]
        yield ruta, cliente, {producto["nombre"]: producto for producto in productos}


def test_menu_entrenamiento_variantes_precios_y_disponibilidad(menu_entrenamiento):
    _, cliente, productos = menu_entrenamiento
    validar = "/pos-api/pedidos/validar"
    familias = {
        "Hamburguesas": {
            "Clásica simple": 7000, "Clásica doble": 9000, "Cheddar y huevo simple": 8000,
            "Cheddar y huevo doble": 10000, "Pollo con papas simple": 5500,
        },
        "Sándwiches": {
            "Chico de pollo + papas": 7000, "Chico de carne + papas": 8000,
            "Grande de pollo individual": 7500, "Grande de carne individual": 8500,
            "Grande de pollo + papas": 9000, "Grande de carne + papas": 10000,
        },
        "Milanesas al plato": {
            "Milanesa de pollo con fritas": 9000, "Milanesa de carne con fritas": 10000,
            "Milanesa de pollo con puré": 8500, "Milanesa de carne con puré": 9500,
            "Napo de pollo con fritas": 10500, "Napo de carne con fritas": 11500,
            "Napo de pollo con puré": 10000, "Napo de carne con puré": 11000,
        },
    }
    assert len(productos) == 40
    for familia, variantes in familias.items():
        for nombre, precio in variantes.items():
            producto = productos[nombre]
            assert producto["familia_menu"] == familia
            assert producto["precio_venta"] == precio
            respuesta = cliente.post(validar, json={"items": [{"id_producto": producto["id_producto"], "cantidad": 1}]})
            if nombre.startswith(("Cheddar", "Pollo con papas")):
                assert producto["estado_entrenamiento"] == "sin_stock" and respuesta.status_code == 409
            else:
                assert respuesta.status_code == 200, respuesta.text
                assert respuesta.json()["total_centavos"] == precio * 100
    for nombre in ("Pollo con papas doble", "Big Mac simple", "Big Mac doble"):
        assert productos[nombre]["estado_entrenamiento"] == "sin_stock"
    assert productos["Pollo con papas doble"]["precio_venta"] is None
    assert {p["variante_menu"]["Guarnición"] for p in productos.values()
            if p.get("familia_menu") == "Milanesas al plato"} == {"Papas fritas", "Puré"}
    for nombre, precio in {
        "Tortilla": 8500, "Conos": 3500, "Bandeja chica": 4500, "Bandeja grande": 5500,
        "Chocotorta grande": 4500, "Oreo grande": 4500, "Pepsi lata": 1600, "7up lata": 1600,
        **{f"Manaos {sabor} 600ml": 1300 for sabor in ("Pomelo", "Cola")},
        **{f"Manaos {sabor} 2.25l": 2000 for sabor in ("Pomelo", "Cola", "Naranja", "Manzana")},
    }.items():
        assert productos[nombre]["precio_venta"] == precio
        assert "familia_menu" not in productos[nombre]


def test_personalizacion_menu_en_venta_sqlite_e_historial(menu_entrenamiento):
    ruta, cliente, productos = menu_entrenamiento
    simulacion = "/pos-api/simulacion"
    ventas = f"{simulacion}/ventas"
    validar = "/pos-api/pedidos/validar"

    def item(nombre, **datos):
        return {"id_producto": productos[nombre]["id_producto"], "cantidad": 1, **datos}

    extra = {"tipo": "cheddar", "destino": "principal", "cantidad": 1}
    linea = item("Clásica doble", ingredientes_quitados=["tomate", "kétchup"],
                 papas_dobles=True, observacion="  Bien cocida <sin salsa>  ",
                 adicionales_preparacion=[extra, dict(extra, destino="papas", cantidad=2)])
    for invalida in (
        item("Grande de pollo individual", papas_dobles=True), item("Milanesa de pollo con fritas", papas_dobles=True),
        item("Milanesa de pollo con puré", adicionales_preparacion=[dict(extra, destino="papas")]),
        item("Manaos Cola 600ml", adicionales_preparacion=[extra]),
        item("Clásica doble", adicionales_preparacion=[extra, extra]),
        item("Clásica doble", adicionales_preparacion=[dict(extra, precio_centavos=1)]),
        item("Napo de carne con puré", ingredientes_quitados=["Media porción"]),
    ):
        assert cliente.post(validar, json={"items": [invalida]}).status_code == 422
    for personalizable in (
        item("Tortilla", adicionales_preparacion=[extra]), item("Bandeja chica", adicionales_preparacion=[extra]),
        item("Mozzarella", adicionales_preparacion=[extra]),
        item("Napo de carne con puré", ingredientes_quitados=["Orégano", "Rodaja de tomate"],
             adicionales_preparacion=[dict(extra, tipo="huevo", destino="pure")]),
        item("Grande de carne individual", ingredientes_quitados=["Lechuga"]),
    ):
        assert cliente.post(validar, json={"items": [personalizable]}).status_code == 200

    bebida = item("Manaos Cola 600ml")
    apertura = {"fecha": ahora_local()[:10], "inicial_centavos": 0}
    for caja in ("comidas", "bebidas_postres"):
        respuesta = cliente.post(f"{simulacion}/caja-diaria/{caja}/apertura", json={
            **apertura, "id_solicitud": str(uuid4()),
        })
        assert respuesta.status_code == 200, respuesta.text
    pedido = {"items": [linea, bebida], "id_solicitud": str(uuid4()),
              "total_esperado_centavos": 1_530_000, "medio_pago": "efectivo"}
    respuesta = cliente.post(ventas, json=pedido)
    assert respuesta.status_code == 200, respuesta.text
    venta = respuesta.json()
    assert venta["cajas_centavos"] == {"comidas": 1_400_000, "bebidas_postres": 130_000}
    comida, bebida_vendida = venta["items"]
    assert comida["id_producto"] == linea["id_producto"]
    assert comida["precio_base_centavos"] == 900_000
    assert comida["guarnicion"] == "Papas fritas dobles"
    assert comida["recargo_papas_dobles_centavos"] == 200_000
    assert comida["observacion"] == "Bien cocida <sin salsa>"
    assert comida["ingredientes_quitados"] == ["Tomate", "Kétchup"]
    assert [(a["destino"], a["cantidad"], a["precio_unitario_centavos"])
            for a in comida["adicionales_preparacion"]] == [("principal", 1, 100_000), ("papas", 2, 100_000)]
    assert "observacion" not in bebida_vendida
    assert cliente.post(ventas, json=pedido).json() == venta
    pedido["items"][0] = dict(linea, observacion="Otro pedido")
    assert cliente.post(ventas, json=pedido).status_code == 409
    assert cliente.get(ventas).json()["ventas"][0]["items"] == venta["items"]
    assert cliente.get(f"{simulacion}/contabilidad").json()["devengado_centavos"] == 1_530_000
    assert cliente.get(f"{simulacion}/conciliacion").json()["cuadrado"] is True
    with closing(sqlite3.connect(ruta)) as db:
        assert db.execute("SELECT stock FROM productos WHERE id_producto = ?", (bebida["id_producto"],)).fetchone() == (23,)
        solicitud, guardado = db.execute("SELECT solicitud, pedido FROM pos_ventas_simuladas").fetchone()
        assert json.loads(guardado)["items"] == venta["items"]
        assert json.loads(solicitud)["items"][1] == dict(bebida, ingredientes_quitados=[], ids_adicionales=[])


def test_actualizacion_menu_conserva_ids_stock_historial_y_agotados(menu_entrenamiento, tmp_path):
    ruta, cliente, productos = menu_entrenamiento
    bebida = productos["Manaos Cola 600ml"]["id_producto"]
    clasica = productos["Clásica simple"]["id_producto"]
    with closing(sqlite3.connect(ruta)) as db, db:
        db.execute("UPDATE productos SET stock = 3 WHERE id_producto = ?", (bebida,))
        db.execute("UPDATE pos_catalogo_entrenamiento SET estado = 'sin_stock' WHERE id_producto = ?", (clasica,))
        db.execute("UPDATE productos SET precio_venta = 7000 WHERE nombre = 'Cheddar y huevo simple'")
        antiguo = {"items": [{"id_producto": bebida, "producto": "Nombre histórico", "cantidad": 1,
                              "precio_unitario_centavos": 130000}], "total_centavos": 130000}
        db.execute("""INSERT INTO pos_ventas_simuladas (id_usuario, id_solicitud, solicitud, pedido)
                      VALUES (1, ?, '{}', ?)""", (str(uuid4()), json.dumps(antiguo)))
        antes = db.execute("SELECT * FROM pos_ventas_simuladas").fetchall()
    actualizar_catalogo(tmp_path)
    actualizar_catalogo(tmp_path)
    with closing(sqlite3.connect(ruta)) as db:
        assert db.execute("SELECT * FROM pos_ventas_simuladas").fetchall() == antes
        assert db.execute("SELECT stock FROM productos WHERE id_producto = ?", (bebida,)).fetchone() == (3,)
        assert dict(db.execute("SELECT nombre, id_producto FROM productos")) == {
            nombre: producto["id_producto"] for nombre, producto in productos.items()
        }
    actuales = {p["nombre"]: p for p in cliente.get("/pos-api/catalogo/productos").json()["productos"]}
    assert actuales["Cheddar y huevo simple"]["precio_venta"] == 8000
    assert actuales["Clásica simple"]["estado_entrenamiento"] == "sin_stock"
    assert cliente.post("/pos-api/pedidos/validar", json={"items": [{"id_producto": clasica, "cantidad": 1}]}).status_code == 409


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
                     "Cheddar y huevo simple", "Cheddar y huevo doble"):
        assert cliente.post(validar, json={"items": [item(producto)]}).status_code == 409
    assert productos["Mozzarella"]["precio_venta"] == 10000
    assert productos["Jamón y morrones"]["precio_venta"] == 12000
    assert cliente.post(validar, json={"items": [item("Mozzarella"), item("Jamón y morrones")]}).json()["total_centavos"] == 2200000
    assert productos["Big Mac doble"]["precio_venta"] == 9000
    assert productos["Big Mac doble"]["estado_entrenamiento"] == "sin_stock"
    assert cliente.post(validar, json={"items": [{"id_producto": lima["id_producto"], "cantidad": 1}]}).status_code == 409
    assert cliente.patch(f'/pos-api/admin/productos/{grande["id_producto"]}/precio',
                         json={"precio_nuevo": 3000}).status_code == 403

    sabores = {"items": [item("Chocotorta chica"), item("Oreo chico")]}
    assert cliente.post(validar, json=sabores).json()["total_centavos"] == 500000
    assert cliente.post(validar, json={"items": [item("Chocotorta chica", 2)]}).json()["total_centavos"] == 500000
    assert cliente.post(validar, json={"items": [item("Chocotorta chica", 2), item("Oreo chico")]}).json()["total_centavos"] == 800000
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
    configuracion["combinar_sabores_promo"] = False
    pizza = next(p for p in configuracion["productos"] if p["nombre"] == "Mozzarella")
    pizza["precio_centavos"] = 0
    json_local.write_text(json.dumps(configuracion), encoding="utf-8")
    with pytest.raises(ValueError, match="precio_centavos"):
        actualizar_catalogo(tmp_path)
    assert cliente.post(validar, json=sabores).json()["total_centavos"] == 500000

    pizza["precio_centavos"] = 123400  # Importe ficticio para probar la activación por JSON.
    json_local.write_text(json.dumps(configuracion), encoding="utf-8")
    actualizar_catalogo(tmp_path)
    assert cliente.post(validar, json=sabores).json()["total_centavos"] == 600000
    assert cliente.post(validar, json={"items": [item("Chocotorta chica", 2)]}).json()["total_centavos"] == 500000
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


def test_entrenamiento_integrado_promocion_fiado_y_diezmo(tmp_path):
    destino = preparar_base(tmp_path)
    cliente = TestClient(crear_app_entrenamiento(tmp_path), base_url=ORIGEN, headers={"Origin": ORIGEN})
    assert cliente.get("/pos-api/simulacion/estado").json()["contabilidad"] is True

    usuario, _, clave = USUARIOS[1]
    assert cliente.post("/pos-api/login", json={"usuario": usuario, "contrasena": clave}).status_code == 200
    apertura = cliente.post("/pos-api/simulacion/caja-diaria/bebidas_postres/apertura", json={
        "id_solicitud": str(uuid4()), "fecha": ahora_local()[:10], "inicial_centavos": 10000,
    })
    assert apertura.status_code == 200, apertura.text

    productos = {p["nombre"]: p for p in cliente.get("/pos-api/catalogo/productos").json()["productos"]}
    items = [{"id_producto": productos[n]["id_producto"], "cantidad": 1}
             for n in ("Chocotorta chica", "Oreo chico")]
    validacion = cliente.post("/pos-api/pedidos/validar", json={"items": items})
    assert validacion.status_code == 200, validacion.text
    assert validacion.json()["total_centavos"] == 500000
    venta = cliente.post("/pos-api/simulacion/ventas", json={
        "id_solicitud": str(uuid4()), "items": items, "total_esperado_centavos": 500000,
        "fiado": True, "deudor": "Cliente ficticio",
        "pagos": [{"medio_pago": "efectivo", "receptor": "bebidas_postres_efectivo",
                   "importe_centavos": 200000}],
    })
    assert venta.status_code == 200, venta.text
    assert venta.json()["saldo_pendiente_centavos"] == 300000

    informe = cliente.get("/pos-api/simulacion/contabilidad")
    assert informe.status_code == 200, informe.text
    assert informe.json()["devengado_centavos"] == 500000
    assert informe.json()["cobrado_neto_centavos"] == 200000
    assert informe.json()["diezmo_centavos"] == 20000

    abono = cliente.post(
        f'/pos-api/simulacion/ventas/{venta.json()["id_venta"]}/abonos',
        json={"id_solicitud": str(uuid4()),
              "pagos": [{"medio_pago": "transferencia", "receptor": "bebidas_postres_banco",
                         "importe_centavos": 300000}]},
    )
    assert abono.status_code == 200, abono.text
    final = cliente.get("/pos-api/simulacion/contabilidad").json()
    assert final["devengado_centavos"] == 500000
    assert final["cobrado_neto_centavos"] == 500000
    assert final["fiado_al_cierre_centavos"] == 0
    assert final["diezmo_centavos"] == 50000
    assert destino.exists()
    assert activar_contabilidad(tmp_path) is None


def test_activar_etapa7_respalda_base_de_entrenamiento_anterior(tmp_path):
    destino = preparar_base(tmp_path)
    with closing(sqlite3.connect(destino)) as db, db:
        for (nombre,) in db.execute(
            "SELECT name FROM sqlite_schema WHERE type = 'trigger' AND name LIKE 'pos_contable_%'"
        ).fetchall():
            db.execute(f'DROP TRIGGER "{nombre}"')
        for nombre in ("pos_inicio_contable", "pos_costos_contables", "pos_cierres_contables"):
            db.execute(f"DROP TABLE {nombre}")
    respaldo = activar_contabilidad(tmp_path)
    assert respaldo is not None and respaldo.exists()
    with closing(sqlite3.connect(destino)) as db:
        assert db.execute("SELECT COUNT(*) FROM pos_inicio_contable").fetchone() == (1,)
        assert db.execute("SELECT COUNT(*) FROM productos").fetchone()[0] == 40
    assert activar_contabilidad(tmp_path) is None
