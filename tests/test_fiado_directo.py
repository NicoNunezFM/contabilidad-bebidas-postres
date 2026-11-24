"""Fiado directo en Pruebas; sólo instancias, perfiles y SQLite temporales."""
import json
import os
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path

import pytest

from pos_contabilidad import fecha_local
from pos_preproduccion import abrir_base, configuracion, integridad
from scripts.abadion_preproduccion import crear_app, preparar
from tests.test_abadion_pruebas import conexion
from tests.test_pos_qa_integrado import solicitud
from tests.test_pos_web import abrir_navegador, esperar
from tests.test_preproduccion import SIM, post

CLIENTES = SIM + '/clientes'


@pytest.fixture
def fiado(tmp_path):
    carpeta = tmp_path / 'Pruebas'
    preparar(carpeta, pruebas=True)
    with closing(abrir_base(carpeta, configuracion(carpeta)['id'])) as db, db:
        producto = db.execute("INSERT INTO productos(nombre,categoria,precio_venta,controla_stock,stock) "
                              "VALUES ('Comida fiado QA','Comidas',9000,1,10)").lastrowid
    c = conexion(carpeta, 'ventas')
    post(c, SIM + '/caja-diaria/comidas/apertura', fecha=fecha_local(), inicial_centavos=0)
    return carpeta, c, producto


@pytest.mark.parametrize('rol', ['ventas', 'admin'])
def test_api_onchi_alta_concurrente_fiado_abono_roles(fiado, rol):
    carpeta, _, producto = fiado
    c = conexion(carpeta, rol)
    alta = solicitud(nombre='Onchi')
    with ThreadPoolExecutor(max_workers=2) as equipo:
        respuestas = list(equipo.map(lambda _: c.post(CLIENTES, json=alta), range(2)))
    assert [r.status_code for r in respuestas] == [200, 200]
    assert respuestas[0].json() == respuestas[1].json()
    titular = respuestas[0].json()['id_cliente']
    assert c.post(CLIENTES, json={**alta, 'nombre': 'Otro'}).status_code == 409
    homonimo = post(c, CLIENTES, nombre='Onchi', referencia='Otra persona ficticia')['id_cliente']
    venta = solicitud(items=[{'id_producto': producto, 'cantidad': 1}], fiado=True,
                      id_cliente=titular, pagos=[], total_esperado_centavos=900_000)
    with ThreadPoolExecutor(max_workers=2) as equipo:
        respuestas = list(equipo.map(lambda _: c.post(SIM + '/ventas', json=venta), range(2)))
    assert [r.status_code for r in respuestas] == [200, 200]
    assert respuestas[0].json() == respuestas[1].json()
    ruta = CLIENTES + f'/{titular}'
    assert c.get(ruta).json()['saldo_centavos'] == 900_000
    pago = {'medio_pago': 'efectivo', 'receptor': 'comidas_efectivo', 'importe_centavos': 400_000}
    vista = c.post(ruta + '/abonos/vista-previa', json=pago).json()
    abono = solicitud(pago=pago, vista_previa=vista['vista_previa'])
    with ThreadPoolExecutor(max_workers=2) as equipo:
        respuestas = list(equipo.map(lambda _: c.post(ruta + '/abonos', json=abono), range(2)))
    assert [r.status_code for r in respuestas] == [200, 200]
    assert respuestas[0].json() == respuestas[1].json()
    assert c.get(ruta).json()['saldo_centavos'] == 500_000
    assert c.get(CLIENTES + f'/{homonimo}').json()['saldo_centavos'] == 0
    assert c.get(SIM + '/caja-diaria').json()['cajas']['comidas']['esperado_centavos'] == 400_000
    if rol == 'ventas':
        assert c.post(ruta + '/abonos/' + abono['id_solicitud'] + '/correccion',
                      json=solicitud(motivo='No autorizado')).status_code == 403
        assert c.get(SIM + '/conciliacion').status_code == 403
    assert conexion(carpeta, 'admin').get(SIM + '/conciliacion').json()['cuadrado']
    assert c.post('/pos-api/logout').status_code == 200
    assert c.post(CLIENTES, json=solicitud(nombre='Sin sesión')).status_code == 401
    with closing(abrir_base(carpeta, configuracion(carpeta)['id'], lectura=True)) as db:
        integridad(db)
        assert db.execute('SELECT COUNT(*) FROM pos_clientes').fetchone()[0] == 2
        assert db.execute('SELECT COUNT(*) FROM pos_ventas_simuladas').fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM pos_solicitudes_clientes WHERE tipo='abono'").fetchone()[0] == 1


@pytest.mark.parametrize('viewport,rol', [((1280, 900), 'ventas'), ((600, 1024), 'admin')])
def test_edge_fiado_directo_teclado_tacto_homonimos_y_reintento(fiado, tmp_path, viewport, rol):
    browser = os.getenv('POS_TEST_BROWSER')
    if not browser:
        pytest.skip('Configurar POS_TEST_BROWSER con Edge')
    import websocket
    carpeta, c, _ = fiado
    navegador = abrir_navegador(crear_app(carpeta, pruebas=True), browser, tmp_path, websocket, viewport=viewport)
    with closing(navegador):
        evaluar = next(navegador)

        def clic(selector):
            esperar(lambda: evaluar(f"document.querySelector({json.dumps(selector)}) && !document.querySelector({json.dumps(selector)}).disabled"))
            evaluar(f"document.querySelector({json.dumps(selector)}).click(); void 0")

        def texto(selector, contenido):
            esperar(lambda: evaluar(f"document.querySelector({json.dumps(selector)})?.textContent.includes({json.dumps(contenido)})"))

        def escribir(selector, valor):
            evaluar(f"document.querySelector({json.dumps(selector)}).value={json.dumps(valor)}; "
                    f"document.querySelector({json.dumps(selector)}).dispatchEvent(new Event('input',{{bubbles:true}}))")

        texto('#cardsReal', 'Comida fiado QA')
        clic('#adminAccess')
        clave = json.loads((carpeta / 'credenciales.json').read_text())[rol + '-pruebas']
        escribir('#usuarioPos', rol + '-pruebas')
        escribir('#claveAdmin', clave)
        clic('#accept')
        texto('#adminAccess', rol + '-pruebas')

        def abrir_fiado():
            clic('#cardsReal article button')
            esperar(lambda: evaluar("document.querySelector('#totalComplementos') !== null"))
            clic('#accept')
            clic('#validarPedido')
            texto('#estadoPedido', '9.000')
            evaluar("[...document.querySelectorAll('#payments button')].find(b=>b.textContent.includes('Fiado')).click(); void 0")
            clic('#checkout')
            esperar(lambda: evaluar("document.activeElement.id === 'buscarClientePos'"))

        abrir_fiado()
        texto('#saldoFiadoPos', 'Total $ 9.000,00')
        texto('#saldoFiadoPos', 'Pagado $ 0,00')
        texto('#accept', 'Confirmar fiado')
        # Enter en el nombre no confirma la venta. El alta no exige teléfono.
        escribir('#buscarClientePos', 'Onchi')
        evaluar("document.querySelector('#buscarClientePos').dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',cancelable:true}))")
        texto('#coincidenciasClientePos', 'Cliente nuevo')
        assert evaluar("document.querySelector('#overlay').hidden") is False
        assert evaluar("document.querySelector('#altaRapidaClientePos').getBoundingClientRect().height >= 44")
        # Simular respuesta perdida después de que el servidor confirmó el alta.
        evaluar("""
            window.fetchOriginalQA=window.fetch;
            window.perderAltaQA=true;
            window.fetch=async (...args)=>{
                const r=await window.fetchOriginalQA(...args);
                if(window.perderAltaQA && String(args[0]).endsWith('/simulacion/clientes') && args[1]?.method==='POST') {
                    window.perderAltaQA=false; throw new TypeError('Respuesta perdida ficticia');
                }
                return r;
            };
            document.querySelector('#altaRapidaClientePos').click();
            document.querySelector('#altaRapidaClientePos').click();
        """)
        texto('#altaRapidaClientePos', 'Reintentar la misma alta')
        assert evaluar("document.querySelector('#buscarClientePos').disabled")
        clic('#accept')
        texto('#errorVentaPos', 'reintentá')
        clic('#altaRapidaClientePos')
        texto('#clienteElegidoPos', 'Cliente seleccionado: Onchi')
        assert evaluar("document.activeElement.id") == 'accept'
        # Botones táctiles y ausencia de desbordamiento horizontal.
        assert evaluar("!document.querySelector('#altaRapidaClientePos').getClientRects().length")
        assert evaluar("document.querySelector('.dialog').scrollWidth <= document.querySelector('.dialog').clientWidth")
        if salida := os.getenv('POS_UI_CAPTURAS'):
            Path(salida).mkdir(parents=True, exist_ok=True)
            (Path(salida) / f'abadion-paso-fiado-{rol}.png').write_bytes(evaluar.captura())
        evaluar("document.querySelector('#accept').click(); document.querySelector('#accept').click(); void 0")
        texto('#notice', 'registrada')
        titular = c.get(CLIENTES, params={'q': 'Onchi'}).json()['clientes'][0]['id_cliente']
        assert c.get(CLIENTES + f'/{titular}').json()['saldo_centavos'] == 900_000
        clic('#clientesPos')
        escribir('#buscarClientePos', 'Onchi')
        evaluar("[...document.querySelectorAll('#consultaPos button')].find(b=>b.textContent==='Buscar').click(); void 0")
        texto('#consultaPos', 'Onchi · #')
        evaluar("[...document.querySelectorAll('#consultaPos button')].find(b=>b.textContent.startsWith('Onchi · #')).click(); void 0")
        texto('#consultaPos', '9.000,00')
        clic('#abonarClientePos')
        escribir('#camposOperacionPos input', '4000')
        evaluar("document.querySelectorAll('#camposOperacionPos select')[1].value='comidas_efectivo'")
        clic('#preverAbonoClientePos')
        texto('#distribucionAbonoClientePos', '4.000,00')
        evaluar("document.querySelector('#accept').click(); document.querySelector('#accept').click(); void 0")
        texto('#consultaPos', 'Abono registrado.')
        texto('#consultaPos', '5.000,00')
        clic('#accept')

        homonimo = post(c, CLIENTES, nombre='Onchi', referencia='Otra persona QA')['id_cliente']
        abrir_fiado()
        # Fallo de búsqueda: nunca habilitar un alta a ciegas. Respuestas viejas no reemplazan la actual.
        evaluar("""
            window.fetch=async (...args)=>{
                if(String(args[0]).includes('q=FallaQA')) throw new TypeError('Búsqueda fallida ficticia');
                const r=await window.fetchOriginalQA(...args);
                if(String(args[0]).includes('q=DemoradaQA'))
                    return new Promise(resolve=>{window.devolverBusquedaQA=()=>resolve(r)});
                return r;
            };
        """)
        escribir('#buscarClientePos', 'FallaQA')
        texto('#coincidenciasClientePos', 'reintentar')
        assert evaluar("document.querySelector('#altaRapidaClientePos').disabled")
        escribir('#buscarClientePos', 'DemoradaQA')
        esperar(lambda: evaluar("typeof window.devolverBusquedaQA === 'function'"))
        escribir('#buscarClientePos', 'Onchi')
        esperar(lambda: evaluar("document.querySelectorAll('#coincidenciasClientePos button').length === 2"))
        evaluar('window.devolverBusquedaQA(); void 0')
        assert evaluar("document.querySelectorAll('#coincidenciasClientePos button').length") == 2
        clic('#accept')
        texto('#errorVentaPos', 'Elegí un cliente')
        clic('#altaRapidaClientePos')
        texto('#dialogBody', 'Ya existe ese nombre')
        assert evaluar("document.activeElement.closest('label').textContent.includes('Referencia')")
        # Elegir explícitamente el ID correcto con teclado.
        evaluar("document.querySelector('#coincidenciasClientePos button').focus()")
        assert evaluar("document.activeElement.textContent.startsWith('Seleccionar Onchi')")
        evaluar.cdp('Input.dispatchKeyEvent', type='keyDown', key='Enter', code='Enter', text='\r', windowsVirtualKeyCode=13)
        evaluar.cdp('Input.dispatchKeyEvent', type='keyUp', key='Enter', code='Enter', windowsVirtualKeyCode=13)
        texto('#clienteElegidoPos', f'#{titular}')
        # Cambiar el nombre invalida la selección previa inmediatamente.
        escribir('#buscarClientePos', 'Persona nueva QA')
        clic('#accept')
        texto('#errorVentaPos', 'Elegí un cliente')
        texto('#coincidenciasClientePos', 'Cliente nuevo')
        # Alta con toque emulado, sin selección manual posterior.
        evaluar("document.querySelector('#altaRapidaClientePos').scrollIntoView({block:'center'})")
        punto = evaluar("(()=>{const r=document.querySelector('#altaRapidaClientePos').getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})()")
        evaluar.cdp('Emulation.setTouchEmulationEnabled', enabled=True)
        evaluar.cdp('Input.dispatchTouchEvent', type='touchStart', touchPoints=[punto])
        evaluar.cdp('Input.dispatchTouchEvent', type='touchEnd', touchPoints=[])
        texto('#clienteElegidoPos', 'Cliente seleccionado: Persona nueva QA')
        clic('#closeDialog')
        assert c.get(CLIENTES + f'/{homonimo}').json()['saldo_centavos'] == 0
    with closing(abrir_base(carpeta, configuracion(carpeta)['id'], lectura=True)) as db:
        integridad(db)
        assert db.execute('SELECT COUNT(*) FROM pos_ventas_simuladas').fetchone()[0] == 1
        assert db.execute('SELECT COUNT(*) FROM pos_clientes').fetchone()[0] == 3
        assert db.execute('SELECT stock FROM productos').fetchone()[0] == 9
    assert conexion(carpeta, 'admin').get(SIM + '/conciliacion').json()['cuadrado']
