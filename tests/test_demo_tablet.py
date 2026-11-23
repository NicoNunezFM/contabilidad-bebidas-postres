"""Demo sin API: aislamiento HTTP y recorrido completo en Microsoft Edge."""
import os
import re
import shutil
import subprocess
from threading import Thread

import httpx
import pytest
from starlette.applications import Starlette
from starlette.responses import HTMLResponse
from starlette.routing import Route

from scripts.generar_demo_tablet import DESTINO, generar
from scripts.servir_demo_tablet import CSP, crear_servidor
from tests.test_pos_web import abrir_navegador, controles_pos, esperar


def test_demo_generada_sin_codigo_operativo():
    html = DESTINO.read_text(encoding='utf-8')
    assert html == generar()
    for prohibido in ('fetch(', 'XMLHttpRequest', '/pos-api', 'sessionStorage', 'localStorage', 'crypto.', 'iniciarPos', '=>', 'modoReal'):
        assert prohibido not in html
    if shutil.which('node'):
        for script in re.findall(r'<script[^>]*>(.*?)</script>', html, re.S):
            resultado = subprocess.run(['node', '--check'], input=script, text=True, encoding='utf-8', capture_output=True)
            assert resultado.returncode == 0, resultado.stderr


def test_servidor_solo_entrega_demo_y_rechaza_escrituras():
    with crear_servidor(port=0) as servidor:
        hilo = Thread(target=servidor.serve_forever, daemon=True)
        hilo.start()
        try:
            with httpx.Client(base_url=f'http://127.0.0.1:{servidor.server_port}', trust_env=False) as cliente:
                respuesta = cliente.get('/')
                assert respuesta.content == DESTINO.read_bytes()
                assert respuesta.headers['cache-control'] == 'no-store'
                assert "connect-src 'none'" in respuesta.headers['content-security-policy']
                for ruta in ('/pos-api/catalogo/productos', '/negocio.db', '/../src/api.py', '/index.html'):
                    assert cliente.get(ruta).status_code == 404
                for metodo in ('POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS', 'HEAD'):
                    assert cliente.request(metodo, '/').status_code == 405
        finally:
            servidor.shutdown()
            hilo.join(timeout=5)


@pytest.fixture
def navegador_pos(tmp_path, request):
    ejecutable = os.environ.get('POS_TEST_BROWSER')
    if not ejecutable:
        pytest.skip('Configurá POS_TEST_BROWSER con Microsoft Edge.')
    import websocket

    async def pagina(request):
        return HTMLResponse(DESTINO.read_bytes(), headers={'Content-Security-Policy': CSP})

    app = Starlette(routes=[Route('/pos/', pagina)])
    yield from abrir_navegador(app, ejecutable, tmp_path, websocket, viewport=request.param)


@pytest.mark.parametrize('navegador_pos', [(1024,600), (600,1024)], indirect=True)
def test_demo_edge_personalizar_editar_copiar_totales_y_reiniciar(controles_pos):
    evaluar, clic, texto, *_ = controles_pos
    # Simular Chrome sin UUID/timeout modernos y sin acceso a servicios de Abadion.
    esperar(lambda: evaluar("document.querySelectorAll('#cards .card').length === 7"))
    assert evaluar("document.querySelector('#apiStatus').textContent.includes('Demo estática lista')")
    assert evaluar("innerWidth === 1024 || innerWidth === 600")
    assert evaluar("getComputedStyle(document.querySelector('.tablet-cart-toggle')).display !== 'none'")
    assert evaluar("document.documentElement.scrollWidth <= innerWidth")
    evaluar("window.fetch = function () { throw new Error('Red prohibida en demo'); }; window.crypto.randomUUID = undefined; AbortSignal.timeout = undefined;")
    clic('[data-product="0"]')
    clic('input[name="removed"][value="Tomate"]')
    clic('input[name="added"][value="queso"]')
    texto('#unitPrice', '6.600')
    clic('#accept')
    clic('label[for="tabletCartState"]')
    assert evaluar("getComputedStyle(document.querySelector('#tabletOrder')).display !== 'none'")
    assert evaluar("getComputedStyle(document.querySelector('#catalog')).display === 'none'")
    texto('#lines', 'Sin tomate')
    texto('#lines', '+ Queso extra')
    texto('#foodTotal', '6.600')
    clic('[data-edit="0"]')
    clic('input[name="added"][value="bacon"]')
    clic('#accept')
    texto('#foodTotal', '7.600')
    clic('[data-copy="0"]')
    texto('#foodTotal', '15.200')
    clic('[data-remove="1"]')
    texto('#foodTotal', '7.600')
    clic('label[for="tabletCartState"]')
    clic('#tabs [data-category="Bebidas"]')
    clic('[data-product="0"]')
    clic('#accept')
    clic('#tabs [data-category="Postres"]')
    clic('[data-product="0"]')
    clic('input[name="added"][value="dulce"]')
    clic('#accept')
    clic('label[for="tabletCartState"]')
    texto('#otherTotal', '5.200')
    texto('#foodTotal', '7.600')
    texto('#total', '12.800')
    assert evaluar("document.querySelector('#checkout').disabled")
    clic('[data-payment="Efectivo"]')
    clic('#checkout')
    clic('#cancel')
    texto('#count', '3 unidades')
    clic('#checkout')
    clic('#accept')
    texto('#count', '0 unidades')
    texto('#notice', 'Cobro simulado')
    clic('label[for="tabletCartState"]')
    clic('[data-product="0"]')
    clic('#accept')
    clic('label[for="tabletCartState"]')
    clic('#clearCart')
    clic('#cancel')
    texto('#count', '1 unidad')
    clic('#clearCart')
    clic('#accept')
    texto('#count', '0 unidades')
    evaluar('location.reload()')
    esperar(lambda: evaluar("document.querySelector('#count')?.textContent === '0 unidades'"))
