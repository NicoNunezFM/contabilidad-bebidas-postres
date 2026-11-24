import json
import os
import shutil
import socket
import subprocess
import sys
import time
from contextlib import closing, contextmanager
from pathlib import Path
from uuid import uuid4

import httpx

from pos_contabilidad import fecha_local
from pos_entrenamiento_db import bloquear_entrenamiento
from pos_preproduccion import abrir_base, configuracion, integridad, restaurar, validar_respaldo
from scripts.abadion_preproduccion import preparar
from tests.test_preproduccion import SIM, post

CAJAS = ("comidas", "bebidas_postres")
ROOT = Path(__file__).resolve().parents[1]


@contextmanager
def servidor(carpeta):
    # El worker real corre en otro proceso y usa un puerto de ensayo independiente de 8078.
    with socket.socket() as reserva:
        reserva.bind(("127.0.0.1", 0))
        puerto = reserva.getsockname()[1]
    codigo = (
        "import sys; from scripts import abadion_preproduccion as p; "
        "p.PUERTO = int(sys.argv.pop(1)); p.main()"
    )
    datos = configuracion(carpeta)
    control = {"Authorization": "Bearer " + datos["control"]}
    url = f"http://127.0.0.1:{puerto}"
    with (carpeta / "jornada-servidor.log").open("ab") as log, httpx.Client(
        base_url=url, headers={"Origin": url}, timeout=2, trust_env=False,
    ) as cliente:
        proceso = subprocess.Popen(
            [sys.executable, "-X", "utf8", "-c", codigo, str(puerto), "--carpeta", str(carpeta), "worker"],
            cwd=ROOT, stdout=log, stderr=log, env={**os.environ, "PYTHON_DOTENV_DISABLED": "1"},
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        try:
            limite = time.monotonic() + 30
            while proceso.poll() is None and time.monotonic() < limite:
                try:
                    estado = cliente.get("/_preprod/status", headers=control)
                    if estado.is_success and estado.json()["id"] == datos["id"]:
                        break
                except httpx.TransportError:
                    pass
                time.sleep(0.1)
            else:
                raise AssertionError((carpeta / "jornada-servidor.log").read_text(encoding="utf-8"))
            try:
                yield cliente, control
            finally:
                cliente.post("/_preprod/stop", headers=control).raise_for_status()
                assert proceso.wait(timeout=30) == 0
        finally:
            if proceso.poll() is None:
                proceso.kill()
                proceso.wait(timeout=10)


def ingresar(carpeta, conexion, rol):
    usuario = rol + "-preprod"
    clave = json.loads((carpeta / "credenciales.json").read_text(encoding="utf-8"))[usuario]
    conexion.cookies.clear()
    conexion.post("/pos-api/login", json={"usuario": usuario, "contrasena": clave}).raise_for_status()


def relevar(carpeta, conexion, jornadas, id_cliente):
    rutas = ["contabilidad", "conciliacion", "ventas", f"clientes/{id_cliente}"]
    rutas += [f"caja-diaria/{caja}/historial/{jornadas[caja]}" for caja in CAJAS]
    estado = {ruta: conexion.get(SIM + "/" + ruta).raise_for_status().json() for ruta in rutas}
    with closing(abrir_base(carpeta, configuracion(carpeta)["id"], lectura=True)) as db:
        integridad(db)
        estado["stock"] = db.execute("SELECT nombre, stock FROM productos ORDER BY id_producto").fetchall()
    return estado


def test_jornada_v1_proceso_reinicio_y_restore_aislado(tmp_path):
    origen = tmp_path / "Preproduccion"
    preparar(origen)
    datos = configuracion(origen)
    with closing(abrir_base(origen, datos["id"])) as db, db:
        db.executemany(
            "INSERT INTO productos(nombre,categoria,precio_venta,controla_stock,stock) VALUES (?,?,?,1,10)",
            [("Comida QA", "Comidas", 10), ("Bebida QA", "Bebidas", 20)],
        )
        comida, bebida = [fila[0] for fila in db.execute("SELECT id_producto FROM productos ORDER BY id_producto")]

    with servidor(origen) as (conexion, control):
        ingresar(origen, conexion, "ventas")
        jornadas = {caja: post(conexion, SIM + f"/caja-diaria/{caja}/apertura",
                              fecha=fecha_local(), inicial_centavos=10000)["id_jornada"] for caja in CAJAS}
        venta = {"id_solicitud": str(uuid4()), "items": [{"id_producto": comida, "cantidad": 1},
                 {"id_producto": bebida, "cantidad": 2}], "total_esperado_centavos": 5000, "medio_pago": "efectivo"}
        primera = conexion.post(SIM + "/ventas", json=venta).raise_for_status().json()
        assert conexion.post(SIM + "/ventas", json=venta).raise_for_status().json() == primera
        devolver = SIM + f"/ventas/{primera['id_venta']}/devoluciones"
        devolucion = {"id_solicitud": str(uuid4()), "motivo": "Devolución QA",
                      "items": [{"linea": 2, "cantidad": 1}]}
        assert conexion.post(devolver, json=devolucion).status_code == 403

        ingresar(origen, conexion, "admin")
        devuelta = conexion.post(devolver, json=devolucion).raise_for_status().json()
        assert conexion.post(devolver, json=devolucion).raise_for_status().json() == devuelta
        post(conexion, SIM + "/compras", id_producto=bebida, cantidad=2, precio_unitario_centavos=100,
             pagado_centavos=200, pagador="comidas_efectivo", medio_pago="efectivo")
        post(conexion, SIM + "/caja-diaria/comidas/movimientos", id_jornada=jornadas["comidas"],
             tipo="gasto", importe_centavos=300, motivo="Gasto QA")
        id_cliente = post(conexion, SIM + "/clientes", nombre="Cliente jornada QA")["id_cliente"]

        ingresar(origen, conexion, "ventas")
        fiado = post(conexion, SIM + "/ventas", items=[{"id_producto": comida, "cantidad": 2}],
                     total_esperado_centavos=2000, pagos=[], fiado=True, id_cliente=id_cliente)
        assert fiado["saldo_pendiente_centavos"] == 2000
        post(conexion, SIM + f"/ventas/{fiado['id_venta']}/abonos",
             pagos=[{"receptor": "comidas_efectivo", "medio_pago": "efectivo", "importe_centavos": 500}])
        for caja, saldo in zip(CAJAS, (11000, 12000), strict=True):
            ruta = SIM + f"/caja-diaria/{caja}"
            estado = conexion.get(SIM + "/caja-diaria").raise_for_status().json()["cajas"][caja]
            assert estado["esperado_centavos"] == saldo
            arqueo = post(conexion, ruta + "/arqueo", id_jornada=jornadas[caja],
                          revision_efectivo=estado["revision_efectivo"], contado_centavos=saldo)
            post(conexion, ruta + "/cierre", id_jornada=jornadas[caja], id_arqueo=arqueo["id_evento"])

        ingresar(origen, conexion, "admin")
        antes = relevar(origen, conexion, jornadas, id_cliente)
        assert antes["conciliacion"]["cuadrado"]
        assert antes["stock"] == [("Comida QA", 7), ("Bebida QA", 11)]
        ventas = {v["id_venta"]: v for v in antes["ventas"]["ventas"]}
        assert set(ventas) == {primera["id_venta"], fiado["id_venta"]}
        assert ventas[fiado["id_venta"]]["saldo_pendiente_centavos"] == 1500
        nombre = conexion.post("/_preprod/backup", headers=control).raise_for_status().json()["archivo"]

    copia = validar_respaldo(origen, nombre)
    with servidor(origen) as (conexion, _):
        ingresar(origen, conexion, "admin")
        assert relevar(origen, conexion, jornadas, id_cliente) == antes

    # Recuperación de la misma identidad en una carpeta temporal independiente.
    destino = tmp_path / "recuperacion" / "Preproduccion"
    (destino / "backups").mkdir(parents=True)
    (destino / "instalacion.json").write_text(json.dumps({**datos, "carpeta": str(destino)}), encoding="utf-8")
    shutil.copyfile(origen / "credenciales.json", destino / "credenciales.json")
    for archivo in (copia, copia.with_suffix(".json")):
        shutil.copyfile(archivo, destino / "backups" / archivo.name)
    with bloquear_entrenamiento(destino):
        restaurar(destino, nombre, base_ausente=True)
    with servidor(destino) as (conexion, _):
        ingresar(destino, conexion, "admin")
        assert relevar(destino, conexion, jornadas, id_cliente) == antes
    eventos = [json.loads(l)["evento"] for l in (destino / "auditoria.jsonl").read_text(encoding="utf-8").splitlines()]
    assert {"restore-verificado", "backup-verificado", "servidor-iniciado", "servidor-detenido"} <= set(eventos)
