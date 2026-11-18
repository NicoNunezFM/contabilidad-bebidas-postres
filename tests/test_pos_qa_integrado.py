"""QA del flujo integrado sobre instalaciones de entrenamiento descartables."""
import sqlite3
from contextlib import closing
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from pos_caja_diaria import ahora_local
from pos_entrenamiento_db import ARCHIVO_BASE, abrir_base_entrenamiento, bloquear_entrenamiento
from pos_entrenamiento_web import crear_app_entrenamiento
from scripts.abadion_entrenamiento import USUARIOS, activar_contabilidad, preparar_base
from tests.test_pos_entrenamiento import ORIGEN


POS = "/pos-api"
SIM = POS + "/simulacion"


def cliente(carpeta, indice):
    usuario, _, clave = USUARIOS[indice]
    navegador = TestClient(crear_app_entrenamiento(carpeta), base_url=ORIGEN, headers={"Origin": ORIGEN})
    post(navegador, POS + "/login", {"usuario": usuario, "contrasena": clave})
    return navegador


def post(navegador, ruta, datos):
    respuesta = navegador.post(ruta, json=datos)
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()


def solicitud(**campos):
    return {"id_solicitud": str(uuid4()), **campos}


def catalogo(navegador):
    return {p["nombre"]: p for p in navegador.get(POS + "/catalogo/productos").json()["productos"]}


def alta_promocion(navegador):
    productos = catalogo(navegador)
    items = [{"id_producto": productos[nombre]["id_producto"], "cantidad": 1}
             for nombre in ("Chocotorta chica", "Oreo chico")]
    cotizacion = post(navegador, POS + "/pedidos/validar", {"items": items})
    assert cotizacion["descuento_centavos"] == 100000
    assert cotizacion["total_centavos"] == 500000
    post(navegador, SIM + "/caja-diaria/bebidas_postres/apertura",
         solicitud(fecha=ahora_local()[:10], inicial_centavos=0))
    venta = post(navegador, SIM + "/ventas", solicitud(
        items=items, total_esperado_centavos=500000, fiado=True, deudor="Cliente QA",
        pagos=[{"medio_pago": "efectivo", "receptor": "bebidas_postres_efectivo",
                "importe_centavos": 200000}],
    ))
    assert venta["saldo_pendiente_centavos"] == 300000
    return productos, f"{SIM}/ventas/{venta['id_venta']}"


def abonar(navegador, ruta, importe):
    return post(navegador, ruta + "/abonos", solicitud(pagos=[
        {"medio_pago": "transferencia", "receptor": "comidas_banco",
         "importe_centavos": importe, "referencia": "abono-qa"},
    ]))


@pytest.mark.parametrize("abono_previo", [False, True], ids=["antes-del-abono", "despues-del-abono"])
def test_devolucion_parcial_promocion_con_fiado(tmp_path, abono_previo):
    ruta_db = preparar_base(tmp_path)
    with closing(sqlite3.connect(ruta_db)) as db, db:
        db.execute("""
            UPDATE productos SET controla_stock = 1, stock = 8
            WHERE nombre IN ('Chocotorta chica', 'Oreo chico')
        """)
    ventas, admin = cliente(tmp_path, 0), cliente(tmp_path, 1)
    originales, ruta = alta_promocion(ventas)
    vendidos = catalogo(ventas)
    for nombre in ("Chocotorta chica", "Oreo chico"):
        assert vendidos[nombre]["stock"] == originales[nombre]["stock"] - 1
    if abono_previo:
        abonar(ventas, ruta, 300000)

    reversion = solicitud(motivo="Devolución ficticia", items=[{"linea": 1, "cantidad": 1}])
    assert ventas.post(ruta + "/devoluciones", json=reversion).status_code == 403
    resultado = post(admin, ruta + "/devoluciones", reversion)
    assert post(admin, ruta + "/devoluciones", reversion) == resultado
    assert admin.post(ruta + "/devoluciones", json={**reversion, **solicitud()}).status_code == 409
    assert resultado["importe_vigente_centavos"] == 250000
    assert resultado["reembolsado_centavos"] == (250000 if abono_previo else 0)
    assert resultado["saldo_pendiente_centavos"] == (0 if abono_previo else 50000)
    cobrado = 250000 if abono_previo else 200000
    assert resultado["cobrado_centavos"] == cobrado
    informe = admin.get(SIM + "/contabilidad").json()
    assert informe["devengado_centavos"] == 250000
    assert informe["fiado_al_cierre_centavos"] == 250000 - cobrado
    assert informe["cobrado_neto_centavos"] == cobrado
    assert informe["diezmo_centavos"] == cobrado // 10
    historia = admin.get(SIM + "/ventas").json()["ventas"][0]
    assert historia["items"][0]["id_producto"] == originales["Chocotorta chica"]["id_producto"]
    devoluciones = [e for e in historia["historial"] if e["tipo"] == "devolucion"]
    assert len(devoluciones) == 1
    movimientos = devoluciones[0]["movimientos"]
    if abono_previo:
        abono = historia["historial"][1]["movimientos"][0]
        assert len(movimientos) == 1
        assert movimientos[0]["revierte"] == abono["id_movimiento"]
        assert (movimientos[0]["receptor"], movimientos[0]["importe_centavos"]) == ("comidas_banco", -250000)
    else:
        assert movimientos == []
        assert abonar(ventas, ruta, 50000)["saldo_pendiente_centavos"] == 0
    actual = catalogo(admin)
    for nombre, diferencia in (("Chocotorta chica", 0), ("Oreo chico", 1)):
        assert actual[nombre]["stock"] == originales[nombre]["stock"] - diferencia
    assert admin.get(SIM + "/conciliacion").json()["cuadrado"] is True


def test_migracion_con_datos_respaldo_recuperable_y_reapertura(tmp_path):
    carpeta = tmp_path / "origen"
    ruta_db = preparar_base(carpeta)
    # Recrea el esquema anterior a etapa 7 conservando el resto de la instalación.
    with closing(sqlite3.connect(ruta_db)) as db, db:
        for (nombre,) in db.execute(
            "SELECT name FROM sqlite_schema WHERE type = 'trigger' AND name LIKE 'pos_contable_%'"
        ).fetchall():
            db.execute(f'DROP TRIGGER "{nombre}"')
        for tabla in ("pos_inicio_contable", "pos_costos_contables", "pos_cierres_contables"):
            db.execute(f"DROP TABLE {tabla}")
    ventas = cliente(carpeta, 0)
    _, ruta = alta_promocion(ventas)
    anteriores = ventas.get(SIM + "/ventas").json()
    stock = catalogo(ventas)
    caja = ventas.get(SIM + "/caja-diaria").json()

    with bloquear_entrenamiento(carpeta), pytest.raises(ValueError, match="en uso"):
        activar_contabilidad(carpeta)
    assert not list(carpeta.glob("*.pre-etapa7-*.db"))
    respaldo = activar_contabilidad(carpeta)
    assert activar_contabilidad(carpeta) is None
    assert list(carpeta.glob("*.pre-etapa7-*.db")) == [respaldo]

    restaurada = tmp_path / "restaurada"
    restaurada.mkdir()
    with closing(sqlite3.connect(respaldo)) as copia, closing(sqlite3.connect(restaurada / ARCHIVO_BASE)) as db:
        assert copia.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
        assert copia.execute("PRAGMA foreign_key_check").fetchall() == []
        copia.backup(db)

    for instalacion in (carpeta, restaurada):
        reinicio = cliente(instalacion, 0)
        assert reinicio.get(SIM + "/ventas").json() == anteriores
        assert catalogo(reinicio) == stock
        assert reinicio.get(SIM + "/caja-diaria").json() == caja
    admin = cliente(carpeta, 1)
    antes = admin.get(SIM + "/contabilidad").json()
    assert antes["devengado_centavos"] == antes["cobrado_neto_centavos"] == antes["diezmo_centavos"] == 0
    assert antes["fiado_al_cierre_centavos"] == 300000
    assert abonar(cliente(carpeta, 0), ruta, 300000)["saldo_pendiente_centavos"] == 0
    despues = admin.get(SIM + "/contabilidad").json()
    assert despues["devengado_centavos"] == 0
    assert despues["cobrado_neto_centavos"] == 300000
    assert despues["diezmo_centavos"] == 30000
    assert cliente(restaurada, 0).get(SIM + "/ventas").json() == anteriores


def test_migracion_rechaza_base_no_marcada_y_ruta_oficial_ficticia(tmp_path):
    oficial_ficticia = tmp_path / "negocio.db"
    with closing(sqlite3.connect(oficial_ficticia)) as db, db:
        db.execute("CREATE TABLE testigo (id INTEGER PRIMARY KEY)")
    original = oficial_ficticia.read_bytes()
    with pytest.raises(ValueError, match=ARCHIVO_BASE):
        abrir_base_entrenamiento(oficial_ficticia)
    (tmp_path / ARCHIVO_BASE).write_bytes(original)
    with pytest.raises(ValueError, match="marcador"):
        activar_contabilidad(tmp_path)
    assert not list(tmp_path.glob("*.pre-etapa7-*.db"))
    assert oficial_ficticia.read_bytes() == (tmp_path / ARCHIVO_BASE).read_bytes() == original



def test_conciliacion_entrenamiento_detecta_desvio_sin_repararlo(tmp_path):
    ruta_db = preparar_base(tmp_path)
    admin = cliente(tmp_path, 1)
    alta_promocion(admin)
    conciliacion = SIM + "/conciliacion"
    assert admin.get(conciliacion).json()["cuadrado"] is True
    with closing(sqlite3.connect(ruta_db)) as db, db:
        cursor = db.execute("""
            UPDATE pos_diario_caja SET importe_centavos = importe_centavos + 1
            WHERE id_movimiento_pos IS NOT NULL
        """)
        assert cursor.rowcount == 1
    diferencia = admin.get(conciliacion).json()
    assert diferencia["cuadrado"] is False
    assert {d["codigo"] for d in diferencia["diferencias"]} == {"MOVIMIENTO_FISICO_SIN_CONCILIAR"}
    assert admin.get(conciliacion).json() == diferencia


def test_migracion_rechaza_escritura_bloqueada_sin_generar_respaldo(tmp_path, monkeypatch):
    from scripts import abadion_entrenamiento

    destino = preparar_base(tmp_path)
    # Fuerza la ruta de migración de una instalación anterior.
    with closing(sqlite3.connect(destino)) as db, db:
        db.execute("DELETE FROM pos_inicio_contable")
    anterior = destino.read_bytes()

    def abrir_sin_espera(ruta, **opciones):
        conexion = abrir_base_entrenamiento(ruta, **opciones)
        conexion.execute("PRAGMA busy_timeout = 0")
        return conexion

    monkeypatch.setattr(abadion_entrenamiento, "abrir_base_entrenamiento", abrir_sin_espera)
    with closing(sqlite3.connect(destino)) as ocupado:
        ocupado.execute("BEGIN IMMEDIATE")
        with pytest.raises(sqlite3.OperationalError, match="locked"):
            activar_contabilidad(tmp_path)
    assert not list(tmp_path.glob("*.pre-etapa7-*.db"))
    assert destino.read_bytes() == anterior

def test_devolucion_de_comida_personalizada_fiada_con_abono(tmp_path):
    ruta_db = preparar_base(tmp_path)
    with closing(sqlite3.connect(ruta_db)) as db, db:
        db.execute(
            "UPDATE productos SET controla_stock = 1, stock = 8 WHERE nombre = ?",
            ("Clásica doble",),
        )
    ventas, admin = cliente(tmp_path, 0), cliente(tmp_path, 1)
    productos = catalogo(ventas)
    comida = productos["Clásica doble"]
    bebida = productos["Manaos Cola 600ml"]
    items = [
        {"id_producto": comida["id_producto"], "cantidad": 1,
         "observacion": "Entregar por separado",
         "adicionales_preparacion": [{"tipo": "cheddar", "destino": "principal", "cantidad": 1}]},
        {"id_producto": bebida["id_producto"], "cantidad": 1},
    ]
    total = 1_130_000
    cotizacion = post(ventas, POS + "/pedidos/validar", {"items": items})
    assert cotizacion["total_centavos"] == total
    post(ventas, SIM + "/caja-diaria/bebidas_postres/apertura",
         solicitud(fecha=ahora_local()[:10], inicial_centavos=0))
    venta = post(ventas, SIM + "/ventas", solicitud(
        items=items, total_esperado_centavos=total, fiado=True, deudor="Cliente QA",
        pagos=[{"medio_pago": "efectivo", "receptor": "bebidas_postres_efectivo",
                "importe_centavos": 130_000}],
    ))
    assert venta["cajas_centavos"] == {"comidas": 1_000_000, "bebidas_postres": 130_000}
    assert venta["saldo_pendiente_centavos"] == 1_000_000
    assert catalogo(ventas)["Clásica doble"]["stock"] == comida["stock"] - 1
    ruta = f"{SIM}/ventas/{venta['id_venta']}"
    assert abonar(ventas, ruta, 1_000_000)["saldo_pendiente_centavos"] == 0
    reversion = solicitud(motivo="Devolución ficticia", items=[{"linea": 1, "cantidad": 1}])
    resultado = post(admin, ruta + "/devoluciones", reversion)
    assert post(admin, ruta + "/devoluciones", reversion) == resultado
    assert resultado["importe_vigente_centavos"] == 130_000
    assert resultado["reembolsado_centavos"] == 1_000_000
    assert catalogo(admin)["Clásica doble"]["stock"] == comida["stock"]
    assert catalogo(admin)["Manaos Cola 600ml"]["stock"] == bebida["stock"] - 1

    historia = admin.get(SIM + "/ventas").json()["ventas"][0]
    assert historia["items"][0]["observacion"] == "Entregar por separado"
    assert historia["items"][0]["adicionales_preparacion"][0]["precio_unitario_centavos"] == 100_000
    devolucion = next(e for e in historia["historial"] if e["tipo"] == "devolucion")
    movimiento, = devolucion["movimientos"]
    assert (movimiento["receptor"], movimiento["importe_centavos"]) == ("comidas_banco", -1_000_000)
    informe = admin.get(SIM + "/contabilidad").json()
    assert informe["devengado_centavos"] == informe["cobrado_neto_centavos"] == 130_000
    assert informe["fiado_al_cierre_centavos"] == 0
    assert informe["diezmo_centavos"] == 13_000
    assert admin.get(SIM + "/conciliacion").json()["cuadrado"] is True
