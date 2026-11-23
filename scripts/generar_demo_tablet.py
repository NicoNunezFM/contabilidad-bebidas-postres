"""Construye una demo autónoma usando solo la UI y el catálogo ficticio del POS.

No importa la API ni abre bases de datos. El resultado no contiene código operativo.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESTINO = ROOT / "pos-web" / "demo-tablet.html"


def generar():
    fuente = (ROOT / "pos-web" / "index.html").read_text(encoding="utf-8")
    html, script = fuente.split("<script>\n", 1)
    # Conservar estilos y estructura táctil, sin imágenes ni controles del backend.
    html = re.sub(r"<img\b[^>]*>", "", html)
    html = re.sub(r'<aside class="sidebar".*?</aside>', '', html, flags=re.S)
    html = re.sub(r'<div class="catalog-tools">.*?</div>', '', html, flags=re.S)
    html = re.sub(r'<button id="adminAccess".*?</button>', '', html, flags=re.S)
    html = html.replace('<html lang="es-AR">', '<html lang="es-AR" class="tablet-mode">')
    html = html.replace('</head>', '<style>.workspace{display:block}[hidden]{display:none!important} .simulation-banner{position:static} .check{min-height:48px} .check input{width:24px;height:24px}</style>\n</head>')
    html = html.replace('<p id="simulationBanner" class="simulation-banner" hidden>', '<p id="simulationBanner" class="simulation-banner">')
    html = html.replace('Simulación con datos ficticios · Cobros reales deshabilitados', 'DEMO ESTÁTICA v1 · Productos y precios ficticios · No guarda ventas · Al recargar se borra el pedido')
    html = html.replace('Comprobando conexión con Abadion...', 'Iniciando demo. Si no aparecen productos, el navegador no pudo ejecutar JavaScript.')
    html = html.replace('<body>', '<body>\n<noscript>Esta demo necesita JavaScript para mostrar productos. La navegación del carrito por sí sola no valida el catálogo.</noscript>')
    html = html.replace('<title>', '<title>Demo estática · ')
    # Fragmentos ES5 del catálogo de ejemplo, personalizaciones y carrito.
    catalogo = script[script.index('  var catalog ='):script.index('  var photos =')]
    helpers = script[script.index('  function el(id)'):script.index('function mostrarCategoriasReales()')]
    helpers = re.sub(r'var visual = .*?\n\s*: ', 'var visual = ', helpers, count=1, flags=re.S)
    pedido = script[script.index('  function totals()'):script.index('  var sesionAdmin =')]
    pedido = re.sub(r'  if \(modoReal\) \{.*?\n  \}', '', pedido, count=1, flags=re.S)
    pedido = re.sub(r'\s*(revisionPedidoReal\+\+;|validacionPos = null;)', '', pedido)
    listeners = script[script.index("  document.addEventListener('click'"):script.index('    async function iniciarPos()')]
    listeners = listeners.replace('.filter(control => !control.disabled && control.getClientRects().length)', '.filter(function (control) { return !control.disabled && control.getClientRects().length; })')
    checkout = script[script.index("  el('checkout').onclick = function () {"):script.index("  document.addEventListener('click'")]
    checkout = re.sub(r'    if \(modoReal\) \{.*?\n    \}', '', checkout, count=1, flags=re.S)
    inicio = """(function () {
  'use strict';
  var methods = ['Efectivo','Transferencia','Mercado Pago'];
  var category = 'Hamburguesas', cart = [], method = '', trigger, editing;
  var overlay = document.getElementById('overlay');
"""
    controles = """
  el('search').oninput = showProducts;
  el('clearCart').onclick = function () {
    el('dialogBody').onchange = null;
    show('Limpiar pedido ficticio', '<p>Se quitarán todos los productos de esta demo.</p>', 'Limpiar');
    el('accept').onclick = function () { cart = []; method = ''; close(); order(); };
  };
"""
    fin = """
  el('apiStatus').textContent = 'Demo estática lista · Sin conexión a API ni base de datos.';
}());
"""
    resultado = html + '<script>\n' + inicio + catalogo + helpers + pedido + controles + checkout + listeners + fin + '</script>\n</body>\n</html>\n'
    return '\n'.join(linea.rstrip() for linea in resultado.splitlines()) + '\n'


if __name__ == '__main__':
    DESTINO.write_bytes(generar().encode('utf-8'))
    print(DESTINO)
