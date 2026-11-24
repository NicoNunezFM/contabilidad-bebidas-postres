import json
import os
from contextlib import closing

import pytest

from pos_preproduccion import actualizar_catalogo
from scripts.abadion_preproduccion import crear_app
from tests.test_preproduccion_consolidacion import instalada, archivo


def test_edge_catalogo_actualizado_conserva_aviso_e_identificadores(instalada, archivo, tmp_path):
    ejecutable = os.getenv("POS_TEST_BROWSER")
    if not ejecutable:
        pytest.skip("Configurar POS_TEST_BROWSER con Edge")
    import websocket
    from tests.test_pos_web import abrir_navegador, esperar

    resultado = actualizar_catalogo(instalada, archivo)
    assert resultado["nuevos_stock_cero"] == ["Bebida QA", "Comida QA"]
    navegador = abrir_navegador(crear_app(instalada), ejecutable, tmp_path, websocket)
    with closing(navegador):
        evaluar = next(navegador)
        esperar(lambda: evaluar("document.querySelector('#adminAccess')?.getClientRects().length > 0"))
        evaluar("document.querySelector('#adminAccess').click()")
        esperar(lambda: evaluar("document.querySelector('#usuarioPos') !== null"))
        clave = json.loads((instalada / "credenciales.json").read_text())["admin-preprod"]
        evaluar("document.querySelector('#usuarioPos').value = 'admin-preprod'; "
                "document.querySelector('#claveAdmin').value = " + json.dumps(clave) +
                "; document.querySelector('#accept').click()")
        esperar(lambda: evaluar("document.querySelector('#adminAccess').textContent.includes('Cerrar sesión (admin-preprod)')"))
        esperar(lambda: evaluar("document.querySelector('#productCount').textContent === '2 de 2 productos'"))
        assert evaluar("document.querySelector('#cardsReal').textContent.includes('Bebida QA')")
        assert evaluar("document.querySelector('#cardsReal').textContent.includes('Comida QA')")
        assert evaluar("document.querySelector('#entrenamientoAviso').getBoundingClientRect().top === 0")
