import json
import os
import socket
import subprocess
import time
from contextlib import closing
from threading import Thread

import httpx
import pytest
import uvicorn

from api import app
from database import obtener_conexion
from pos_auth import generar_hash
from pos_simulacion import crear_esquema_simulacion


def esperar(consulta):
    for _ in range(150):
        resultado = consulta()
        if resultado:
            return resultado
        time.sleep(0.1)
    pytest.fail("El navegador o el servidor no llegó al estado esperado.")


@pytest.fixture
def navegador_pos(base_prueba, monkeypatch, tmp_path):
    ejecutable = os.getenv("POS_TEST_BROWSER")
    if not ejecutable:
        pytest.skip("Configurá POS_TEST_BROWSER con la ruta de Edge o Chrome.")
    import websocket
    monkeypatch.setenv("POS_V1_SIMULACION", "1")
    with closing(obtener_conexion()) as db, db:
        crear_esquema_simulacion(db)
        clave = generar_hash("clave-ficticia-pos")
        db.executemany(
            "INSERT INTO usuarios_pos (usuario, rol, password_hash) VALUES (?, ?, ?)",
            [("admin", "admin", clave), ("ventas", "ventas", clave)],
        )
        db.executemany(
            "INSERT INTO productos (nombre, categoria, stock, precio_venta) VALUES (?, ?, ?, ?)",
            [("Comida ficticia", "Comidas", 10, 2500), ("Bebida ficticia", "Bebidas", 20, 1500)],
        )

    with socket.socket() as red:
        red.bind(("127.0.0.1", 0))
        origen = f"http://127.0.0.1:{red.getsockname()[1]}"
        servidor = uvicorn.Server(uvicorn.Config(app, log_level="warning"))
        hilo = Thread(target=servidor.run, kwargs={"sockets": [red]}, daemon=True)
        hilo.start()
        try:
            esperar(lambda: servidor.started)
            perfil = tmp_path / "perfil-navegador"
            opciones = [
                ejecutable, "--headless", "--no-first-run", "--disable-background-networking",
                "--no-proxy-server", "--remote-debugging-port=0", f"--user-data-dir={perfil}", "about:blank",
            ]
            with subprocess.Popen(
                opciones, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            ) as navegador:
                try:
                    puerto = perfil / "DevToolsActivePort"
                    esperar(puerto.is_file)
                    urls = httpx.get(
                        f"http://127.0.0.1:{puerto.read_text().splitlines()[0]}/json/list"
                    ).json()
                    pagina = next(url for url in urls if url["type"] == "page")
                    with closing(websocket.create_connection(
                        pagina["webSocketDebuggerUrl"], suppress_origin=True, timeout=10
                    )) as canal:
                        id_mensaje = 0

                        def cdp(metodo, **params):
                            nonlocal id_mensaje
                            id_mensaje += 1
                            canal.send(json.dumps({"id": id_mensaje, "method": metodo, "params": params}))
                            while True:
                                mensaje = json.loads(canal.recv())
                                if mensaje.get("id") == id_mensaje:
                                    assert "error" not in mensaje, mensaje
                                    return mensaje["result"]

                        def evaluar(expresion):
                            resultado = cdp("Runtime.evaluate", expression=expresion, returnByValue=True)
                            assert "exceptionDetails" not in resultado, resultado
                            return resultado["result"].get("value")

                        cdp("Page.navigate", url=f"{origen}/pos/")
                        yield evaluar
                finally:
                    navegador.terminate()
        finally:
            servidor.should_exit = True
            hilo.join(timeout=10)


def test_pos_web_precio_reintento_historial_y_anulacion(navegador_pos):
    evaluar = navegador_pos

    def clic(selector):
        esperar(lambda: evaluar(f"""
            (() => {{
                const boton = document.querySelector({json.dumps(selector)});
                if (!boton || boton.disabled || !boton.getClientRects().length) return false;
                boton.click();
                return true;
            }})()
        """))

    def texto(selector, contenido):
        expresion = f"document.querySelector({json.dumps(selector)})?.textContent.includes({json.dumps(contenido)})"
        esperar(lambda: evaluar(expresion))

    def iniciar_sesion(usuario):
        clic("#adminAccess")
        evaluar(f"""
            document.querySelector('#usuarioPos').value = {json.dumps(usuario)};
            document.querySelector('#claveAdmin').value = 'clave-ficticia-pos';
        """)
        clic("#accept")
        texto("#adminAccess", f"Cerrar sesión ({usuario})")
        esperar(lambda: evaluar("document.querySelector('#overlay').hidden"))

    texto("#apiStatus", "Catálogo ficticio de simulación")
    assert evaluar("!document.querySelector('#simulationBanner').hidden")
    iniciar_sesion("ventas")
    assert evaluar("document.querySelector('#cajasSimuladas').hidden")

    for indice in range(1, 3):
        clic(f"#cardsReal .card:nth-child({indice}) button")
        clic("#accept")
    clic("#payments button:nth-child(2)")
    assert evaluar("document.querySelector('#checkout').disabled")
    clic("#validarPedido")
    texto("#estadoPedido", "4.000,00")

    with closing(obtener_conexion()) as db, db:
        db.execute("UPDATE productos SET precio_venta = 3000 WHERE nombre = 'Comida ficticia'")
    clic("#checkout")
    clic("#accept")
    texto("#estadoPedido", "Cambió el total")
    assert evaluar("document.querySelector('#checkout').disabled")
    clic("#validarPedido")
    texto("#estadoPedido", "4.500,00")

    # El servidor registra la venta, pero la página recibe un fallo de conexión.
    evaluar("""
        const fetchOriginal = window.fetch;
        window.fetch = async (...args) => {
          const respuesta = await fetchOriginal(...args);
          if (args[0] === '/pos-api/simulacion/ventas' && args[1]?.method === 'POST') {
            throw new TypeError('Respuesta perdida en la prueba');
          }
          return respuesta;
        };
    """)
    clic("#checkout")
    clic("#accept")
    texto("#estadoPedido", "No se pudo confirmar el resultado")
    assert evaluar("document.querySelector('#lines').inert")
    evaluar("setTimeout(() => location.reload(), 0)")
    texto("#estadoPedido", "Venta pendiente")
    clic("#checkout")
    texto("#notice", "Venta simulada #1 registrada")
    with closing(obtener_conexion()) as db:
        assert db.execute("SELECT COUNT(*) FROM pos_ventas_simuladas").fetchone() == (1,)
        assert db.execute("SELECT COUNT(*) FROM pos_movimientos_simulados").fetchone() == (2,)
        assert db.execute("SELECT stock FROM productos ORDER BY id_producto").fetchall() == [(9,), (19,)]

    clic("#historialSimulado")
    texto("#dialogBody", "Venta #1")
    clic("#dialogBody summary")
    assert evaluar("!document.querySelector('#dialogBody details button')")
    clic("#accept")
    clic("#adminAccess")
    texto("#adminAccess", "Iniciar sesión")
    iniciar_sesion("admin")
    clic("#cajasSimuladas")
    texto("#dialogBody section:first-child", "Transferencia · $ 3.000,00")
    texto("#dialogBody section:nth-child(2)", "Transferencia · $ 1.500,00")
    texto("#dialogBody section:first-child", "Venta #1")
    texto("#dialogBody section:nth-child(2)", "Venta #1")
    clic("#accept")
    clic("#historialSimulado")
    clic("#dialogBody summary")
    clic("#dialogBody details button")
    evaluar("document.querySelector('#motivoAnulacion').value = '   '")
    clic("#accept")
    texto("#errorAnulacionPos", "Ingresá un motivo")
    evaluar("document.querySelector('#motivoAnulacion').value = 'Pedido ficticio duplicado'")
    clic("#accept")
    texto("#dialogBody", "Se anuló la venta simulada #1")
    clic("#dialogBody summary")
    texto("#dialogBody", "Pedido ficticio duplicado")
    clic("#accept")
    clic("#cajasSimuladas")
    texto("#dialogBody section:first-child", "Anulación #1")
    texto("#dialogBody section:nth-child(2)", "Anulación #1")
    texto("#dialogBody section:first-child", "Transferencia · $ 0,00")
    texto("#dialogBody section:nth-child(2)", "Transferencia · $ 0,00")
    with closing(obtener_conexion()) as db:
        assert db.execute("SELECT stock FROM productos ORDER BY id_producto").fetchall() == [(10,), (20,)]
