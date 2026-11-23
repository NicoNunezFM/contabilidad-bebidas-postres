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
from pos_entrenamiento_web import AVISO, crear_app_entrenamiento
from scripts.abadion_entrenamiento import USUARIOS, preparar_base
from scripts.puente_pos_ficticio import copiar_ficticia


def esperar(consulta):
    for _ in range(150):
        resultado = consulta()
        if resultado:
            return resultado
        time.sleep(0.1)
    pytest.fail("El navegador o el servidor no llegó al estado esperado.")


@pytest.fixture
def navegador_pos(base_prueba, monkeypatch, tmp_path, request):
    ejecutable = os.getenv("POS_TEST_BROWSER")
    if not ejecutable:
        pytest.skip("Configurá POS_TEST_BROWSER con la ruta de Edge o Chrome.")
    import websocket
    modo = getattr(request, "param", None)
    if modo == "entrenamiento":
        carpeta = tmp_path / "entrenamiento"
        preparar_base(carpeta)
        app_prueba = crear_app_entrenamiento(carpeta)
    else:
        preparar_simulacion_web(base_prueba, monkeypatch, tmp_path, modo)
        app_prueba = app

    yield from abrir_navegador(app_prueba, ejecutable, tmp_path, websocket)


def preparar_simulacion_web(base_prueba, monkeypatch, tmp_path, modo):
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
    if modo in {"caja_diaria", "contabilidad"}:
        copia = tmp_path / "pos6-ficticio.db"
        copiar_ficticia(base_prueba, copia, caja_diaria=True)
        if modo == "contabilidad":
            integrada = tmp_path / "pos7-ficticio.db"
            copiar_ficticia(copia, integrada, contabilidad=True)
            copia = integrada
            monkeypatch.setenv("ABADION_PUENTE_FICTICIO", "1")
        monkeypatch.setenv("NEGOCIO_DB_PATH", str(copia))


def abrir_navegador(app_prueba, ejecutable, tmp_path, websocket, viewport=None):
    with socket.socket() as red:
        red.bind(("127.0.0.1", 0))
        origen = f"http://127.0.0.1:{red.getsockname()[1]}"
        servidor = uvicorn.Server(uvicorn.Config(app_prueba, log_level="warning"))
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

                    def pagina_disponible():
                        # Edge puede bloquear el archivo mientras publica el puerto de depuración.
                        try:
                            lineas = puerto.read_text().splitlines()
                            if not lineas:
                                return None
                            respuesta = httpx.get(f"http://127.0.0.1:{lineas[0]}/json/list", timeout=1)
                            respuesta.raise_for_status()
                            return next((url for url in respuesta.json() if url["type"] == "page"), None)
                        except (OSError, httpx.HTTPError, ValueError):
                            return None

                    pagina = esperar(pagina_disponible)
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

                        if viewport:
                            cdp("Emulation.setDeviceMetricsOverride", width=viewport[0], height=viewport[1],
                                deviceScaleFactor=1, mobile=True)
                        cdp("Page.navigate", url=f"{origen}/pos/")
                        yield evaluar
                finally:
                    navegador.terminate()
        finally:
            servidor.should_exit = True
            hilo.join(timeout=10)


@pytest.fixture
def controles_pos(navegador_pos):
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

    return evaluar, clic, texto, iniciar_sesion


@pytest.mark.parametrize("navegador_pos", ["entrenamiento"], indirect=True)
def test_pos_web_aviso_de_entrenamiento_visible_al_ingresar(controles_pos):
    evaluar, clic, texto, _ = controles_pos
    texto("#entrenamientoAviso", AVISO)
    texto("#cardsReal", "Manaos")
    assert evaluar("""
        (() => {
            const tarjetas = [...document.querySelectorAll('#cardsReal article')];
            const tarjeta = nombre => tarjetas.find(t => t.querySelector('h3').textContent === nombre);
            const pizza = tarjeta('Mozzarella');
            return pizza.textContent.replace(/\s/g, '').includes('$10.000') && !pizza.querySelector('button').disabled
                && !tarjeta('Hamburguesas').querySelector('button').disabled && !tarjeta('Clásica doble');
        })()
    """)
    clic("#adminAccess")
    assert evaluar("""
        (() => {
            const aviso = document.querySelector('#entrenamientoAviso');
            const rect = aviso.getBoundingClientRect();
            return !document.querySelector('#overlay').hidden
                && document.elementFromPoint(rect.width / 2, rect.height / 2) === aviso;
        })()
    """)
    usuario, _, clave = USUARIOS[0]
    evaluar(f"""
        document.querySelector('#usuarioPos').value = {json.dumps(usuario)};
        document.querySelector('#claveAdmin').value = {json.dumps(clave)};
    """)
    clic("#accept")
    texto("#adminAccess", f"Cerrar sesión ({usuario})")
    clic("#cajaDiariaPos")
    assert evaluar("document.querySelector('#entrenamientoAviso').getBoundingClientRect().top") == 0
    texto("#entrenamientoAviso", AVISO)


@pytest.mark.parametrize("navegador_pos", ["entrenamiento"], indirect=True)
def test_pos_web_menu_tactil_editar_variante_y_resumen(controles_pos):
    evaluar, clic, texto, _ = controles_pos
    texto("#cardsReal", "Milanesas al plato")
    assert evaluar("document.querySelectorAll('#cardsReal [data-familia]').length") == 3

    def tocar_campo(selector, valor):
        evaluar(f"""
            (() => {{
                const campo = document.querySelector({json.dumps(selector)});
                campo.value = {json.dumps(valor)};
                campo.dispatchEvent(new Event('input', {{bubbles: true}}));
                campo.dispatchEvent(new Event('change', {{bubbles: true}}));
            }})()
        """)

    clic("#adminAccess")
    usuario, _, clave = USUARIOS[0]
    tocar_campo("#usuarioPos", usuario)
    tocar_campo("#claveAdmin", clave)
    clic("#accept")
    texto("#adminAccess", f"Cerrar sesión ({usuario})")

    clic('[data-familia="Hamburguesas"] button')
    assert evaluar("""Array.from(document.querySelector('#selectoresMenu select').options)
        .filter(opcion => opcion.disabled).map(opcion => opcion.value)""") == ["Pollo con papas", "Big Mac", "Cheddar y huevo"]
    tocar_campo("#selectoresMenu label:nth-child(2) select", "Doble")
    clic("#accept")
    texto("#estadoPersonalizacion", "9.000")
    tocar_campo("#opcionesReales select", "doble")
    tocar_campo('[data-tipo="cheddar"][data-destino="principal"]', "1")
    tocar_campo('[data-tipo="cheddar"][data-destino="papas"]', "1")
    clic('input[name="quitarReal"][value="Tomate"]')
    tocar_campo("#observacionMenu", "Bien cocida <sin salsa>")
    texto("#totalPersonalizado", "13.000")
    clic("#accept")
    clic("#resumenCocina")
    for detalle in ("Clásica doble", "Papas fritas dobles", "Sin tomate", "Cheddar extra en plato principal",
                    "Cheddar extra en papas fritas", "Bien cocida <sin salsa>"):
        texto("#lineasCocina", detalle)
    assert not evaluar("document.querySelector('#lineasCocina sin') !== null")
    clic("#accept")

    clic('#lines button[aria-label="Editar Clásica doble"]')
    tocar_campo("#selectoresMenu label:nth-child(2) select", "Simple")
    clic("#accept")
    texto("#totalPersonalizado", "11.000")
    assert evaluar("document.querySelector('#observacionMenu').value") == "Bien cocida <sin salsa>"
    tocar_campo("#observacionMenu", "Entregar primero")
    clic("#accept")

    clic('[data-familia="Milanesas al plato"] button')
    tocar_campo("#selectoresMenu label:first-child select", "Carne")
    tocar_campo("#selectoresMenu label:nth-child(2) select", "Napolitana")
    assert evaluar("""Array.from(document.querySelector('#selectoresMenu label:nth-child(3) select').options)
        .map(opcion => opcion.value)""") == ["Papas fritas", "Puré"]
    tocar_campo("#selectoresMenu label:nth-child(3) select", "Puré")
    clic("#accept")
    texto("#estadoPersonalizacion", "11.000")
    assert not evaluar("Boolean(document.querySelector('#opcionesReales select'))")
    assert evaluar("document.querySelector('#observacionMenu').value") == ""
    clic("#accept")

    clic("#validarPedido")
    texto("#estadoPedido", "22.000,00")
    clic("#resumenCocina")
    texto("#lineasCocina", "Clásica simple")
    texto("#lineasCocina", "Entregar primero")
    texto("#lineasCocina", "Napo de carne con puré")
    assert evaluar("document.querySelector('#lineasCocina').children.length") == 2


@pytest.mark.parametrize("navegador_pos", ["caja_diaria"], indirect=True)
def test_pos_web_apertura_arqueo_autorizacion_reintento_e_historial(controles_pos):
    evaluar, clic, texto, iniciar_sesion = controles_pos
    texto("#apiStatus", "Catálogo ficticio de simulación")
    iniciar_sesion("ventas")
    clic("#cajaDiariaPos")
    comidas = '[data-caja-diaria="comidas"]'
    bebidas = '[data-caja-diaria="bebidas_postres"]'

    def boton(caja, nombre):
        esperar(lambda: evaluar(f"""
            (() => {{
              const boton = Array.from(document.querySelectorAll({json.dumps(caja + " button")}))
                .find(b => b.textContent === {json.dumps(nombre)});
              if (!boton) return false;
              boton.click();
              return true;
            }})()
        """))

    for caja, inicial in ((comidas, "300,25"), (bebidas, "0")):
        boton(caja, "Abrir caja")
        evaluar(f"document.querySelector('#importeCajaDiaria').value = {json.dumps(inicial)}")
        clic("#accept")
        texto(caja, "Abierta")
    boton(comidas, "Guardar arqueo")
    evaluar("document.querySelector('#importeCajaDiaria').value = '299,25'")
    evaluar("document.querySelector('#camposOperacionPos textarea').value = 'Falta un peso'")
    clic("#accept")
    texto(comidas, "Administración debe autorizar")
    assert not evaluar(f"Array.from(document.querySelectorAll({json.dumps(comidas + ' button')}))"
                       ".some(b => b.textContent === 'Cerrar caja')")

    clic("#accept")
    clic("#adminAccess")
    texto("#adminAccess", "Iniciar sesión")
    iniciar_sesion("admin")
    clic("#cajaDiariaPos")
    boton(comidas, "Cerrar caja")
    evaluar("""
        const fetchDiarioOriginal = window.fetch;
        window.fetch = async (...args) => {
          const respuesta = await fetchDiarioOriginal(...args);
          if (args[0] === '/pos-api/simulacion/caja-diaria/comidas/cierre') {
            window.fetch = fetchDiarioOriginal;
            throw new TypeError('Respuesta perdida en la prueba');
          }
          return respuesta;
        };
    """)
    clic("#accept")
    texto("#errorOperacionPos", "Confirmación pendiente")
    evaluar("setTimeout(() => location.reload(), 0)")
    texto("#adminAccess", "Cerrar sesión (admin)")
    clic("#cajaDiariaPos")
    boton(comidas, "Reintentar · Cerrar caja")
    clic("#accept")
    texto(comidas, "Cerrada")
    texto(comidas, "Falta un peso")
    texto(bebidas, "Abierta")
    boton(comidas, "Ver historial")
    texto("#consultaPos", "Cerró admin")
    clic("#consultaPos div button")
    texto("#consultaPos", "Falta un peso")
    texto("#consultaPos", "ventas")

    with closing(obtener_conexion()) as db:
        assert db.execute("SELECT COUNT(*) FROM pos_diario_caja WHERE tipo = 'cierre'").fetchone() == (1,)


def test_pos_web_precio_reintento_historial_y_anulacion(controles_pos):
    evaluar, clic, texto, iniciar_sesion = controles_pos
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


def test_pos_web_fiado_pago_combinado_y_abono_con_respuesta_perdida(controles_pos):
    evaluar, clic, texto, iniciar_sesion = controles_pos

    def pedido_mixto():
        for indice in range(1, 3):
            clic(f"#cardsReal .card:nth-child({indice}) button")
            clic("#accept")
        clic("#validarPedido")
        texto("#estadoPedido", "4.000,00")

    texto("#apiStatus", "Catálogo ficticio de simulación")
    iniciar_sesion("ventas")
    pedido_mixto()
    clic("#payments button:nth-child(5)")
    clic("#checkout")
    clic("#accept")
    texto("#errorVentaPos", "Ingresá el cliente")
    evaluar("""
        document.querySelector('#errorVentaPos').previousElementSibling.querySelector('input').value = 'Cliente Edge';
    """)
    evaluar("document.querySelector('#errorVentaPos').previousElementSibling.querySelector('button').click()")
    evaluar("""
        const pagoInicial = document.querySelector('.filaPagoPos');
        pagoInicial.querySelector('select').value = 'transferencia';
        pagoInicial.querySelector('select').dispatchEvent(new Event('change'));
        pagoInicial.querySelectorAll('select')[1].value = 'bebidas_postres_mercado_pago';
        pagoInicial.querySelector('[data-importe-pago]').value = '1200,25';
        pagoInicial.querySelector('[data-importe-pago]').dispatchEvent(new Event('input', {bubbles:true}));
    """)
    texto('#dialogBody p[aria-live="polite"]', "2.799,75")
    clic("#accept")
    texto("#notice", "2.799,75")
    clic("#historialSimulado")
    clic("#dialogBody summary")
    texto("#dialogBody details", "Cliente Edge")
    texto("#dialogBody details", "Bebidas y postres · Cuenta Mercado Pago")
    clic("#dialogBody details button")
    evaluar("""
        const abono = document.querySelector('.filaPagoPos');
        abono.querySelector('select').value = 'mercado_pago';
        abono.querySelector('select').dispatchEvent(new Event('change'));
        abono.querySelectorAll('select')[1].value = 'comidas_banco';
        const fetchAnterior = window.fetch;
        window.fetch = async (...args) => {
          const respuesta = await fetchAnterior(...args);
          if (args[0].endsWith('/abonos') && args[1]?.method === 'POST') throw new TypeError('Respuesta perdida');
          return respuesta;
        };
    """)
    clic("#accept")
    texto("#errorOperacionPos", "Confirmación pendiente")
    evaluar("setTimeout(() => location.reload(), 0)")
    texto("#apiStatus", "Catálogo ficticio de simulación")
    clic("#historialSimulado")
    clic("#dialogBody summary")
    texto("#dialogBody summary", "Saldada")
    clic("#dialogBody details button")
    texto("#camposOperacionPos", "confirmación pendiente")
    clic("#accept")
    texto("#dialogBody", "Abono registrado")
    clic("#accept")

    pedido_mixto()
    clic("#payments button:nth-child(4)")
    clic("#checkout")
    evaluar("""
        const pagos = document.querySelectorAll('[data-importe-pago]');
        pagos[0].value = '1250,05';
        pagos[1].value = '2749,95';
        const segundo = document.querySelectorAll('.filaPagoPos')[1];
        const [medio, receptor] = segundo.querySelectorAll('select');
        medio.value = 'transferencia';
        medio.dispatchEvent(new Event('change'));
        receptor.value = 'bebidas_postres_banco';
    """)
    clic("#accept")
    texto("#notice", "Venta simulada #2 registrada")
    with closing(obtener_conexion()) as db:
        assert db.execute("""
            SELECT receptor, medio_pago, importe_centavos
            FROM pos_movimientos_simulados ORDER BY id_movimiento
        """).fetchall() == [
            ("bebidas_postres_mercado_pago", "transferencia", 120025),
            ("comidas_banco", "mercado_pago", 279975),
            ("comidas_efectivo", "efectivo", 125005),
            ("bebidas_postres_banco", "transferencia", 274995),
        ]

    clic("#adminAccess")
    texto("#adminAccess", "Iniciar sesión")
    iniciar_sesion("admin")
    clic("#cajasSimuladas")
    texto("#dialogBody section:first-child", "Por recibir $ 950,20")
    clic("#consultaPos > .actions button:first-child")
    evaluar("""
        const [origen, destino] = document.querySelectorAll('#camposOperacionPos select');
        origen.value = 'bebidas_postres_banco';
        destino.value = 'comidas_banco';
        document.querySelector('#camposOperacionPos input').value = '950,20';
        document.querySelector('#camposOperacionPos textarea').value = 'Distribución de prueba';
    """)
    clic("#accept")
    texto("#dialogBody", "Transferencia registrada")
    texto("#dialogBody section:first-child", "Por recibir $ 0,00")
    clic("#consultaPos > .actions button:nth-child(2)")
    evaluar("document.querySelector('#camposOperacionPos textarea').value = 'Cierre Edge'")
    clic("#accept")
    texto("#dialogBody", "Se cerró el período 1")
    clic("#accept")

    clic("#historialSimulado")
    clic("#dialogBody summary")
    clic("#dialogBody details button:nth-of-type(2)")
    evaluar("""
        document.querySelector('#camposOperacionPos input').value = 1;
        document.querySelector('#camposOperacionPos textarea').value = 'Devolución Edge';
    """)
    clic("#accept")
    texto("#dialogBody", "Devolución registrada en la venta #2")
    clic("#dialogBody summary")
    texto("#dialogBody details", "Período 2")



@pytest.mark.parametrize("navegador_pos", ["contabilidad"], indirect=True)
def test_pos_web_contabilidad_ficticia_para_administracion(controles_pos):
    evaluar, clic, texto, iniciar_sesion = controles_pos
    texto("#apiStatus", "Catálogo ficticio de simulación")
    iniciar_sesion("ventas")
    assert evaluar("document.querySelector('#contabilidadPos').hidden")
    clic("#adminAccess")
    texto("#adminAccess", "Iniciar sesión")
    iniciar_sesion("admin")
    clic("#contabilidadPos")
    texto("#consultaPos", "Ventas devengadas")
    texto("#consultaPos", "Fiado pendiente")
    texto("#consultaPos", "Diezmo estimado")
    texto("#consultaPos", "Sin cobros en el período.")


@pytest.mark.parametrize("navegador_pos", ["entrenamiento"], indirect=True)
def test_pos_web_entrenamiento_promocion_fiado_devolucion_y_cierre(controles_pos):
    evaluar, clic, texto, _ = controles_pos

    def ingresar(indice):
        usuario, _, clave = USUARIOS[indice]
        clic("#adminAccess")
        evaluar(f"""
            document.querySelector('#usuarioPos').value = {json.dumps(usuario)};
            document.querySelector('#claveAdmin').value = {json.dumps(clave)};
        """)
        clic("#accept")
        texto("#adminAccess", f"Cerrar sesión ({usuario})")
        esperar(lambda: evaluar("document.querySelector('#overlay').hidden"))

    def boton_por_texto(selector, etiqueta):
        esperar(lambda: evaluar(f"""
            (() => {{
                const boton = [...document.querySelectorAll({json.dumps(selector)})]
                    .find(b => b.textContent === {json.dumps(etiqueta)} && !b.disabled && b.getClientRects().length);
                if (!boton) return false;
                boton.click();
                return true;
            }})()
        """))

    caja = '[data-caja-diaria="bebidas_postres"]'
    texto("#entrenamientoAviso", AVISO)
    ingresar(0)
    assert evaluar("document.querySelector('#contabilidadPos').hidden")
    clic("#cajaDiariaPos")
    boton_por_texto(caja + " button", "Abrir caja")
    evaluar("document.querySelector('#importeCajaDiaria').value = '0'")
    clic("#accept")
    texto(caja, "Abierta")
    clic("#accept")

    for nombre in ("Chocotorta chica", "Oreo chico"):
        esperar(lambda: evaluar(f"""
            (() => {{
                const tarjeta = [...document.querySelectorAll('#cardsReal article')]
                    .find(t => t.querySelector('h3').textContent === {json.dumps(nombre)});
                if (!tarjeta) return false;
                tarjeta.querySelector('button').click();
                return true;
            }})()
        """))
        clic("#accept")
    clic("#validarPedido")
    texto("#estadoPedido", "5.000,00")
    texto("#estadoPedido", "1.000,00")
    clic("#payments button:nth-child(5)")
    clic("#checkout")
    clic("#dialogBody details summary")
    evaluar("document.querySelector('#nombreClientePos').value = 'Cliente entrenamiento Edge'")
    clic("#altaRapidaClientePos")
    texto("#clienteElegidoPos", "Cliente entrenamiento Edge")
    boton_por_texto("#dialogBody button", "Agregar pago")
    evaluar("""
        const pago = document.querySelector('.filaPagoPos');
        pago.querySelectorAll('select')[1].value = 'bebidas_postres_efectivo';
        const importe = pago.querySelector('[data-importe-pago]');
        importe.value = '2000';
        importe.dispatchEvent(new Event('input', {bubbles: true}));
    """)
    texto('#clienteElegidoPos ~ p[aria-live="polite"]', "3.000,00")
    clic("#accept")
    texto("#notice", "3.000,00")
    clic("#historialSimulado")
    clic("#dialogBody summary")
    texto("#dialogBody details", "Cliente entrenamiento Edge")
    assert evaluar("""![...document.querySelectorAll('#dialogBody details button')]
        .some(b => b.textContent === 'Devolver productos')""")
    clic("#accept")
    clic("#clientesPos")
    evaluar("document.querySelector('#buscarClientePos').value = 'Cliente entrenamiento Edge'")
    boton_por_texto("#consultaPos button", "Buscar")
    boton_por_texto("#consultaPos button", "Cliente entrenamiento Edge · #1")
    texto("#consultaPos", "3.000,00")
    clic("#abonarClientePos")
    evaluar("""
        const campos = document.querySelector('#camposOperacionPos');
        const [medio, receptor] = campos.querySelectorAll('select');
        medio.value = 'transferencia';
        medio.dispatchEvent(new Event('change'));
        receptor.value = 'comidas_banco';
        campos.querySelector('input').value = '3000';
    """)
    clic("#preverAbonoClientePos")
    texto("#distribucionAbonoClientePos", "Venta #1")
    clic("#accept")
    texto("#consultaPos", "Abono registrado.")
    clic("#accept")

    clic("#adminAccess")
    texto("#adminAccess", "Iniciar sesión")
    ingresar(1)
    clic("#historialSimulado")
    clic("#dialogBody summary")
    texto("#dialogBody summary", "Saldada")
    boton_por_texto("#dialogBody details button", "Devolver productos")
    evaluar("""
        document.querySelector('#camposOperacionPos input[type="number"]').value = 1;
        document.querySelector('#camposOperacionPos textarea').value = 'Devolución de postre Edge';
    """)
    clic("#accept")
    texto("#dialogBody", "Devolución registrada en la venta #1")
    clic("#dialogBody summary")
    texto("#dialogBody details", "Devolución de postre Edge")
    texto("#dialogBody details", "2.500,00")
    clic("#accept")
    clic("#cajaDiariaPos")
    boton_por_texto(caja + " button", "Guardar arqueo")
    evaluar("document.querySelector('#importeCajaDiaria').value = '2000'")
    clic("#accept")
    texto("#consultaPos", "Arqueo registrado")
    boton_por_texto(caja + " button", "Cerrar caja")
    clic("#accept")
    texto(caja, "Cerrada")


@pytest.mark.parametrize("navegador_pos", ["entrenamiento"], indirect=True)
def test_pos_web_seguimiento_retiro_de_mostrador(controles_pos):
    evaluar, clic, texto, _ = controles_pos
    texto("#cardsReal", "Oreo chico")
    clic("#adminAccess")
    usuario, _, clave = USUARIOS[0]
    evaluar(f"""
        document.querySelector('#usuarioPos').value = {json.dumps(usuario)};
        document.querySelector('#claveAdmin').value = {json.dumps(clave)};
    """)
    clic("#accept")
    texto("#adminAccess", usuario)
    evaluar("""
        [...document.querySelectorAll('#cardsReal article')]
            .find(t => t.querySelector('h3')?.textContent === 'Oreo chico').querySelector('button').click();
    """)
    clic("#accept")
    clic("#validarPedido")
    texto("#estadoPedido", "3.000")
    evaluar("""
        [...document.querySelectorAll('#payments button')]
            .find(b => b.textContent.includes('Transferencia')).click();
    """)
    clic("#checkout")
    evaluar("""
        const modo = document.querySelector('#dialogBody select');
        modo.value = 'retiro';
        modo.dispatchEvent(new Event('change', {bubbles: true}));
    """)
    clic("#accept")
    texto("#notice", "registrada")
    clic("#seguimientoPos")
    texto("#consultaPos", "Mostrador")
    clic("#consultaPos details summary")
    texto("#consultaPos details", "Oreo chico")
    evaluar("""
        [...document.querySelectorAll('#consultaPos button')]
            .find(b => b.textContent === 'En preparación').click();
    """)
    clic("#accept")
    texto("#consultaPos", "En preparación")


@pytest.mark.parametrize("navegador_pos", ["entrenamiento"], indirect=True)
def test_pos_web_whatsapp_anonimo_antes_de_confirmar_venta(controles_pos):
    evaluar, clic, texto, _ = controles_pos
    texto("#cardsReal", "Oreo chico")
    clic("#adminAccess")
    usuario, _, clave = USUARIOS[0]
    evaluar(f"""
        document.querySelector('#usuarioPos').value = {json.dumps(usuario)};
        document.querySelector('#claveAdmin').value = {json.dumps(clave)};
    """)
    clic("#accept")
    texto("#adminAccess", usuario)
    evaluar("""
        [...document.querySelectorAll('#cardsReal article')]
            .find(t => t.querySelector('h3')?.textContent === 'Oreo chico').querySelector('button').click();
    """)
    clic("#accept")
    clic("#validarPedido")
    texto("#estadoPedido", "3.000")
    clic("#guardarPedidoAnonimo")
    evaluar("""
        const [modalidad, origen] = document.querySelectorAll('#camposOperacionPos select');
        modalidad.value = 'envio';
        modalidad.dispatchEvent(new Event('change'));
        origen.value = 'whatsapp';
        document.querySelector('#camposOperacionPos input').value = '';
        [...document.querySelectorAll('#camposOperacionPos label')]
          .find(l => l.textContent.trim() === 'Dirección').querySelector('input').value = 'Calle ficticia 43';
    """)
    clic("#accept")
    texto("#notice", "guardado sin venta")
    clic("#seguimientoPos")
    texto("#consultaPos", "WhatsApp")
    clic("#consultaPos details summary")
    texto("#consultaPos details", "Sin venta")
    evaluar("""
        [...document.querySelectorAll('#consultaPos button')]
            .find(b => b.textContent === 'En preparación').click();
    """)
    clic("#accept")
    texto("#consultaPos", "En preparación")
    clic("#consultaPos details summary")
    evaluar("""
        [...document.querySelectorAll('#consultaPos button')]
            .find(b => b.textContent === 'Confirmar venta del pedido').click();
    """)
    texto("#camposOperacionPos", "Total vigente")
    evaluar("""
        const medio = document.querySelector('#camposOperacionPos select');
        medio.value = 'transferencia';
        medio.dispatchEvent(new Event('change'));
    """)
    clic("#accept")
    texto("#consultaPos", "En preparación")
    texto("#consultaPos", "saldado")


@pytest.mark.parametrize("navegador_pos", ["entrenamiento"], indirect=True)
def test_pos_web_tablet_carrito_funciona_sin_javascript(controles_pos):
    """El control nativo de HTML alterna el carrito aun si el JS del POS falla."""
    evaluar, _, texto, _ = controles_pos
    texto("#cardsReal", "Oreo chico")
    assert evaluar("""
        (() => {
            document.documentElement.classList.add('tablet-mode');
            const carrito = document.querySelector('#tabletOrder');
            const catalogo = document.querySelector('#catalog');
            const selector = document.querySelector('#tabletCartState');
            const etiqueta = document.querySelector('label[for="tabletCartState"]');
            if (!selector || !etiqueta) return false;
            const estadoInicial = !selector.checked &&
                getComputedStyle(catalogo).display !== 'none' &&
                getComputedStyle(carrito).display === 'none';
            etiqueta.click();
            const vistaCarrito = selector.checked &&
                getComputedStyle(carrito).display !== 'none' &&
                getComputedStyle(catalogo).display === 'none';
            etiqueta.click();
            const regresoCatalogo = !selector.checked &&
                getComputedStyle(catalogo).display !== 'none' &&
                getComputedStyle(carrito).display === 'none';
            return estadoInicial && vistaCarrito && regresoCatalogo;
        })()
    """)
