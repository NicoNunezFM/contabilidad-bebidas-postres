import os
import json
from pathlib import Path
from contextlib import closing

import pytest

from scripts.abadion_preproduccion import crear_app
from pos_preproduccion import abrir_base, configuracion
from tests.test_lo_de_clau_delivery import circuito, cuadrado
from tests.test_pos_web import abrir_navegador, esperar


@pytest.mark.parametrize('directo', [False, True])
def test_edge_checkout_delivery_y_entrega_sencilla_doble_clic(circuito,tmp_path,directo):
    ejecutable = os.getenv('POS_TEST_BROWSER')
    if not ejecutable:
        pytest.skip('Configurar POS_TEST_BROWSER con Edge')
    import websocket
    carpeta,c,ids = circuito
    navegador = abrir_navegador(crear_app(carpeta),ejecutable,tmp_path,websocket)
    with closing(navegador):
        evaluar = next(navegador)
        def clic(selector):
            esperar(lambda: evaluar(f"document.querySelector({json.dumps(selector)}) && !document.querySelector({json.dumps(selector)}).disabled"))
            evaluar(f"document.querySelector({json.dumps(selector)}).click(); void 0")
        def texto(selector,valor):
            esperar(lambda: evaluar(f"document.querySelector({json.dumps(selector)})?.textContent.includes({json.dumps(valor)})"))
        def boton(texto_boton):
            evaluar("[...document.querySelectorAll('#consultaPos button')].find(b=>b.textContent === " + json.dumps(texto_boton) + ").click(); void 0")
        texto('#cardsReal','Comida QA')
        clic('#adminAccess')
        clave = json.loads((carpeta/'credenciales.json').read_text())['ventas-preprod']
        evaluar("document.querySelector('#usuarioPos').value='ventas-preprod'; document.querySelector('#claveAdmin').value=" + json.dumps(clave))
        clic('#accept')
        texto('#adminAccess','ventas-preprod')
        assert evaluar("[...document.querySelectorAll('#cardsReal article')].find(a=>a.textContent.includes('Comida QA')).querySelector('button').disabled") is False
        evaluar("[...document.querySelectorAll('#cardsReal article')].find(a=>a.textContent.includes('Comida QA')).querySelector('button').click(); void 0")
        esperar(lambda: evaluar("document.querySelector('#totalComplementos') !== null"))
        clic('[aria-label="Aumentar cantidad de Postre QA"]')
        clic('#accept')
        texto('#lines','Comida QA')
        clic('#validarPedido')
        texto('#estadoPedido','12.500')
        evaluar("[...document.querySelectorAll('#payments button')].find(b=>b.textContent.includes('Efectivo')).click(); void 0")
        clic('#checkout')
        evaluar("""
            const modo=document.querySelector('#dialogBody select'); modo.value='envio';
            modo.dispatchEvent(new Event('change',{bubbles:true}));
            const campo=t=>[...document.querySelectorAll('#dialogBody label')].find(l=>l.firstChild.textContent.trim()===t);
            campo('Dirección').querySelector('input').value='Calle QA 123';
            campo('Dirección').querySelector('input').dispatchEvent(new Event('input',{bubbles:true}));
            campo('Receptor').querySelector('select').value='comidas_efectivo';
        """)
        assert evaluar("[...document.querySelectorAll('#dialogBody label')].find(l=>l.firstChild.textContent.trim()==='Importe de envío').querySelector('input').value")=='2000'
        texto('#resumenVentaPos','14.500')
        if directo:
            clic('#envioDirectoPos')
        evaluar("document.querySelector('#accept').click(); document.querySelector('#accept').click(); void 0")
        texto('#notice','registrada')
        clic('#seguimientoPos')
        texto('#consultaPos','Recibido')
        clic('#consultaPos details summary')
        assert evaluar("![...document.querySelectorAll('#consultaPos button')].some(b=>b.textContent==='En preparación')")
        boton('Entregado')
        if directo:
            texto('#camposOperacionPos','ya retuvo el efectivo')
            assert evaluar("document.querySelector('#camposOperacionPos select') === null")
        else:
            texto('#camposOperacionPos','Entregar ahora')
            evaluar("document.querySelector('#camposOperacionPos select').value='comidas_efectivo'")
        evaluar("document.querySelector('#accept').click(); document.querySelector('#accept').click(); void 0")
        esperar(lambda: evaluar("document.querySelector('#consultaPos') && !document.querySelector('#camposOperacionPos')"))
        boton('Ver finalizados')
        texto('#consultaPos','Entregado')
        clic('#consultaPos details summary')
        texto('#consultaPos','Entregado al repartidor')
        assert evaluar("document.querySelector('#entrenamientoAviso').textContent.includes('DATOS FICTICIOS')")
        salida=os.getenv('POS_UI_CAPTURAS')
        if salida:
            Path(salida).mkdir(parents=True,exist_ok=True)
            (Path(salida)/('abadion-paso-delivery-' + ('directo' if directo else 'caja') + '.png')).write_bytes(evaluar.captura())
    with closing(abrir_base(carpeta,configuracion(carpeta)['id'],lectura=True)) as db:
        assert db.execute('SELECT COUNT(*) FROM pos_ventas_simuladas').fetchone()[0]==1
        assert db.execute("SELECT COUNT(*) FROM pos_delivery_movimientos WHERE tipo='entrega'").fetchone()[0]==1
        assert db.execute('SELECT stock FROM productos WHERE id_producto=?',(ids[0],)).fetchone()[0]==9
    cuadrado(c)
