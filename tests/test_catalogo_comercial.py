"""Commercial menu on NEW temporary SQLite only; never an installed directory."""
import json
import os
from collections import Counter
from contextlib import closing
from pathlib import Path
from uuid import uuid4

import pytest

from pos_contabilidad import fecha_local
from pos_preproduccion import actualizar_catalogo, integridad, validar_respaldo
from tests.test_preproduccion_consolidacion import instalada, abrir, contenido
from tests.test_preproduccion import cliente, post, SIM

CATALOGO = Path(__file__).resolve().parents[1] / "scripts/catalogo-comercial.json"
BAJAS = {"Pepsi lata", "7up lata", "Pollo con papas doble", "Big Mac simple", "Big Mac doble"}


@pytest.fixture
def comercial(instalada):
    plan = actualizar_catalogo(instalada, CATALOGO, validar=True)
    actualizar_catalogo(instalada, CATALOGO, sha256=plan["sha256"])
    with abrir(instalada) as db:
        ids = dict(db.execute("SELECT nombre,id_producto FROM productos"))
    return instalada, ids


def test_composicion_precios_y_cero_stock(comercial):
    carpeta, ids = comercial
    datos = json.loads(CATALOGO.read_text(encoding="utf-8"))
    assert len(ids) == 38
    assert Counter(p["categoria"] for p in datos["productos"]) == {
        "Sándwiches": 6, "Al plato": 9, "Hamburguesas": 5, "Pizzas": 3,
        "Conos": 3, "Postres": 6, "Bebidas": 6}
    precios = {p["nombre"]: p["precio_centavos"] for p in datos["productos"]}
    assert {n: precios[n] for n in ("Pepitos chico", "Pepitos grande", "Fugazzeta", "Mozzarella", "Jamón y morrones")} == {
        "Pepitos chico": 300000, "Pepitos grande": 450000, "Fugazzeta": 1200000,
        "Mozzarella": 1000000, "Jamón y morrones": 1200000}
    assert BAJAS.isdisjoint(ids)
    with abrir(carpeta) as db:
        assert db.execute("SELECT DISTINCT stock FROM productos").fetchall() == [(0,)]
        assert db.execute("SELECT nombre,precio_venta FROM adicionales_catalogo WHERE activo=1 ORDER BY nombre").fetchall() == [
            ("Cheddar extra", 1000), ("Huevo extra", 1000)]
        assert db.execute("SELECT COUNT(*) FROM pos_catalogo_entrenamiento WHERE estado='disponible'").fetchone() == (38,)
        integridad(db)


def test_comercial_hash_distinto_y_categoria_legacy_no_escriben(instalada):
    antes = contenido(instalada)
    with pytest.raises(ValueError, match="SHA-256"):
        actualizar_catalogo(instalada, CATALOGO, sha256="0"*64)
    assert contenido(instalada) == antes
    with abrir(instalada) as db, db:
        db.execute("INSERT INTO productos(nombre,categoria,stock,precio_venta,controla_stock) VALUES ('Grande de pollo individual','Sanguches',7,6500,0)")
    antes = contenido(instalada)
    with pytest.raises(ValueError, match="revisión separada"):
        actualizar_catalogo(instalada, CATALOGO, validar=True)
    assert contenido(instalada) == antes
    assert not list((instalada / "backups").glob("*pre-catalogo.db"))


def test_cli_comercial_no_aplica_sin_hash(instalada):
    import subprocess
    import sys
    antes = contenido(instalada)
    resultado = subprocess.run([sys.executable,"-X","utf8",str(CATALOGO.parent / "abadion_preproduccion.py"),
        "--carpeta",str(instalada),"actualizar-catalogo","--catalogo",str(CATALOGO)],
        capture_output=True,text=True,encoding="utf-8",timeout=20)
    assert resultado.returncode == 1
    assert "--sha256" in resultado.stderr
    assert contenido(instalada) == antes


@pytest.mark.parametrize("cantidades,total,descuento", [
    ((1,0,0),300000,0), ((1,1,0),500000,100000), ((1,1,1),800000,100000),
    ((2,1,1),1000000,200000), ((0,0,4),1000000,200000), ((1,2,2),1300000,200000)])
def test_promo_tres_sabores(comercial, cantidades, total, descuento):
    carpeta, ids = comercial
    c = cliente(carpeta)
    items = [{"id_producto":ids[n], "cantidad":q} for n,q in zip(
        ("Chocotorta chica", "Oreo chico", "Pepitos chico"), cantidades) if q]
    r = c.post("/pos-api/pedidos/validar", json={"items":items})
    assert r.status_code == 200, r.text
    assert r.json()["total_centavos"] == total
    assert r.json().get("descuento_centavos", 0) == descuento


def test_adicionales_venta_mixta_idempotencia_devolucion_y_reinicio(comercial):
    carpeta, ids = comercial
    c = cliente(carpeta)
    # Explicit fictitious count in a NEW test database, never catalogue stock.
    with abrir(carpeta) as db, db:
        db.execute("UPDATE productos SET stock=5 WHERE nombre='Manaos Cola 600ml'")
    for caja in ("comidas", "bebidas_postres"):
        post(c, SIM+f"/caja-diaria/{caja}/apertura", fecha=fecha_local(), inicial_centavos=0)
    items = [{"id_producto":ids["Clásica simple"], "cantidad":1,
              "adicionales_preparacion":[{"tipo":t,"destino":"principal","cantidad":1} for t in ("cheddar","huevo")]},
             {"id_producto":ids["Manaos Cola 600ml"], "cantidad":1},
             {"id_producto":ids["Pepitos chico"], "cantidad":1},
             {"id_producto":ids["Oreo chico"], "cantidad":1}]
    pedido = dict(id_solicitud=str(uuid4()),items=items,total_esperado_centavos=1530000,medio_pago="efectivo")
    r = c.post(SIM+"/ventas",json=pedido)
    assert r.status_code == 200, r.text
    venta = r.json()
    assert venta["cajas_centavos"] == {"comidas":900000,"bebidas_postres":630000}
    assert c.post(SIM+"/ventas",json=pedido).json() == venta
    assert c.get(SIM+"/conciliacion").json()["cuadrado"]
    estable = contenido(carpeta)
    actualizar_catalogo(carpeta, CATALOGO)
    assert contenido(carpeta) == estable
    c = cliente(carpeta)  # fresh app and fresh SQLite connections
    assert c.post(SIM+"/ventas",json=pedido).json() == venta
    assert c.get(SIM+"/contabilidad").json()["devengado_centavos"] == 1530000
    post(c, SIM+f"/ventas/{venta['id_venta']}/anulacion",motivo="Ensayo aislado catálogo")
    assert c.get(SIM+"/contabilidad").json()["devengado_centavos"] == 0
    assert c.get(SIM+"/conciliacion").json()["cuadrado"]
    with abrir(carpeta) as db:
        assert db.execute("SELECT stock FROM productos WHERE nombre='Manaos Cola 600ml'").fetchone() == (5,)
        integridad(db)


def test_actualizacion_desactiva_sin_borrar_historial(instalada, tmp_path):
    viejo = json.loads(CATALOGO.with_name("catalogo-entrenamiento.json").read_text(encoding="utf-8"))
    viejo["adicionales"] = []
    for p in viejo["productos"]:
        p.pop("adicionales",None)
    anterior = tmp_path / "anterior-qa.json"
    anterior.write_text(json.dumps(viejo),encoding="utf-8")
    actualizar_catalogo(instalada, anterior)
    with abrir(instalada) as db, db:
        db.execute("INSERT INTO productos(nombre,categoria,stock,precio_venta,controla_stock) VALUES ('Producto ficticio QA','Comidas',8,99,0)")
        db.execute("INSERT INTO adicionales_catalogo(nombre,precio_venta) VALUES ('Extra de práctica (ejemplo)',500)")
        db.execute("UPDATE productos SET stock=11 WHERE controla_stock=1")
        ids = dict(db.execute("SELECT nombre,id_producto FROM productos"))
    c = cliente(instalada)
    for caja in ("comidas", "bebidas_postres"):
        post(c, SIM+f"/caja-diaria/{caja}/apertura", fecha=fecha_local(), inicial_centavos=0)
    post(c,SIM+"/ventas",items=[{"id_producto":ids["Pepsi lata"],"cantidad":1}],
         total_esperado_centavos=160000,medio_pago="efectivo")
    with abrir(instalada) as db:
        saldos = dict(db.execute("SELECT id_producto,stock FROM productos"))
        tablas = [t for t, in db.execute("SELECT name FROM sqlite_schema WHERE type='table'") if t not in {
            "productos","pos_catalogo_entrenamiento","adicionales_catalogo","pos_adicionales_producto","sqlite_sequence"}]
        historia = {t:db.execute(f'SELECT * FROM "{t}"').fetchall() for t in tablas}
    informe = c.get(SIM+"/contabilidad").json()
    previo = contenido(instalada)
    plan = actualizar_catalogo(instalada,CATALOGO,validar=True)
    assert contenido(instalada) == previo
    assert set(plan["fuera_menu"]) == BAJAS | {"Producto ficticio QA"}
    assert set(plan["nuevos_stock_cero"]) == {"Pepitos chico","Pepitos grande","Fugazzeta"}
    resultado = actualizar_catalogo(instalada,CATALOGO,sha256=plan["sha256"])
    validar_respaldo(instalada,resultado["backup"])
    for nombre in plan["fuera_menu"]:
        r = c.post("/pos-api/pedidos/validar",json={"items":[{"id_producto":ids[nombre],"cantidad":1}]})
        assert r.status_code == 409, r.text
    with abrir(instalada) as db:
        actuales = dict(db.execute("SELECT nombre,id_producto FROM productos"))
        assert db.execute("SELECT activo FROM adicionales_catalogo WHERE nombre='Extra de práctica (ejemplo)'").fetchone() == (0,)
        assert all(actuales[n] == i for n,i in ids.items())
        assert all(stock == saldos[i] for i,stock in db.execute("SELECT id_producto,stock FROM productos") if i in saldos)
        assert {t:db.execute(f'SELECT * FROM "{t}"').fetchall() for t in tablas} == historia
        assert db.execute("SELECT estado FROM pos_catalogo_entrenamiento WHERE id_producto=?",(ids["Pollo con papas simple"],)).fetchone() == ("sin_stock",)
    assert c.get(SIM+"/contabilidad").json() == informe
    assert c.get(SIM+"/conciliacion").json()["cuadrado"]
    estable = contenido(instalada)
    actualizar_catalogo(instalada,CATALOGO)
    assert contenido(instalada) == estable


def test_edge_catalogo_comercial(comercial, tmp_path):
    ejecutable = os.getenv("POS_TEST_BROWSER")
    if not ejecutable:
        pytest.skip("Configurar POS_TEST_BROWSER con Edge")
    import websocket
    from scripts.abadion_preproduccion import crear_app
    from tests.test_pos_web import abrir_navegador, esperar
    carpeta, ids = comercial
    navegador = abrir_navegador(crear_app(carpeta),ejecutable,tmp_path,websocket)
    with closing(navegador):
        evaluar = next(navegador)
        evaluar.cdp("Emulation.setDeviceMetricsOverride",width=1440,height=1000,deviceScaleFactor=1,mobile=False)
        esperar(lambda:evaluar("document.querySelector('#adminAccess')?.getClientRects().length > 0"))
        evaluar("document.querySelector('#adminAccess').click()")
        esperar(lambda:evaluar("document.querySelector('#usuarioPos') !== null"))
        clave = json.loads((carpeta/"credenciales.json").read_text())["admin-preprod"]
        evaluar("document.querySelector('#usuarioPos').value='admin-preprod'; document.querySelector('#claveAdmin').value="+json.dumps(clave)+"; document.querySelector('#accept').click()")
        esperar(lambda:evaluar("document.querySelector('#adminAccess').textContent.includes('Cerrar sesión (admin-preprod)')"))
        esperar(lambda:evaluar("document.querySelector('#cardsReal').textContent.includes('Fugazzeta')"))
        evaluar("fetch('/pos-api/catalogo/productos').then(r=>r.json()).then(d=>window.catalogoQA=d.productos); void 0")
        esperar(lambda:evaluar("window.catalogoQA?.length === 38"))
        texto = evaluar("document.querySelector('#cardsReal').textContent")
        assert "Pepitos" in texto and "Fugazzeta" in texto and "Especial" in texto
        assert all(n not in texto for n in BAJAS)
        assert evaluar("document.querySelector('#entrenamientoAviso').getBoundingClientRect().top === 0")
        def clic(selector):
            esperar(lambda:evaluar("!!document.querySelector("+json.dumps(selector)+") && !document.querySelector("+json.dumps(selector)+").disabled"))
            evaluar("document.querySelector("+json.dumps(selector)+").click(); void 0")
        for familia,nombre in (("Pepitos","Pepitos chico"),("Oreo","Oreo chico")):
            clic('[data-familia="'+familia+'"] button')
            esperar(lambda:evaluar("document.querySelector('#variantesPostre') !== null"))
            if familia == "Pepitos":
                assert evaluar("document.querySelector('[aria-label=\"Aumentar cantidad de Pepitos grande\"]').disabled")
            clic('#variantesPostre [aria-label="Aumentar cantidad de '+nombre+'"]')
            clic('#accept')
            esperar(lambda:evaluar("document.querySelector('#overlay').hidden"))
        clic('#validarPedido')
        esperar(lambda:evaluar("document.querySelector('#estadoPedido').textContent.includes('5.000,00')"))
        assert evaluar("document.querySelector('#estadoPedido').textContent.includes('1.000,00')")
        salida = os.getenv("POS_UI_CAPTURAS")
        if salida:
            destino = Path(salida)
            destino.mkdir(parents=True, exist_ok=True)
            (destino / "abadion-paso-catalogo-comercial.png").write_bytes(evaluar.captura())


def test_worker_catalogo_reinicio_backup_y_recuperacion(comercial, tmp_path):
    import shutil
    from pos_preproduccion import configuracion, restaurar
    from pos_entrenamiento_db import bloquear_entrenamiento
    from tests.test_preproduccion_jornada_v1 import servidor, ingresar
    carpeta, ids = comercial
    def relevar(conexion):
        return {ruta: conexion.get(ruta).raise_for_status().json() for ruta in (
            "/pos-api/catalogo/productos", SIM+"/ventas", SIM+"/contabilidad", SIM+"/conciliacion")}
    with servidor(carpeta) as (conexion, control):
        ingresar(carpeta, conexion, "admin")
        for caja in ("comidas", "bebidas_postres"):
            post(conexion,SIM+f"/caja-diaria/{caja}/apertura",fecha=fecha_local(),inicial_centavos=0)
        post(conexion,SIM+"/ventas",items=[{"id_producto":ids["Pepitos chico"],"cantidad":2}],
             total_esperado_centavos=500000,medio_pago="efectivo")
        antes = relevar(conexion)
        nombre = conexion.post("/_preprod/backup",headers=control).raise_for_status().json()["archivo"]
    with servidor(carpeta) as (conexion, _):
        ingresar(carpeta,conexion,"admin")
        assert relevar(conexion) == antes
    copia = validar_respaldo(carpeta,nombre)
    destino = tmp_path / "recuperacion" / "Preproduccion"
    (destino / "backups").mkdir(parents=True)
    (destino / "instalacion.json").write_text(json.dumps({**configuracion(carpeta),"carpeta":str(destino)}),encoding="utf-8")
    shutil.copyfile(carpeta / "credenciales.json",destino / "credenciales.json")
    for archivo in (copia,copia.with_suffix(".json")):
        shutil.copyfile(archivo,destino / "backups" / archivo.name)
    with bloquear_entrenamiento(destino):
        restaurar(destino,nombre,base_ausente=True)
    with servidor(destino) as (conexion,_):
        ingresar(destino,conexion,"admin")
        assert relevar(conexion) == antes
