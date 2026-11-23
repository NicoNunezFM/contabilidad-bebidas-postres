"""Compatibilidad del POS con Chrome 101 y la pantalla de 7 pulgadas.

Los tests no necesitan una base real ni un servidor accesible desde la red.
"""
import shutil
import subprocess
from pathlib import Path

import pytest

POS = Path(__file__).resolve().parents[1] / "pos-web" / "index.html"
ENTRENAMIENTO = Path(__file__).resolve().parents[1] / "src" / "pos_entrenamiento_web.py"


def codigo_pos():
    html = POS.read_text(encoding="utf-8")
    inicio = html.index("<script>") + len("<script>")
    fin = html.index("</script>", inicio)
    return html, html[inicio:fin]


def test_tablet_no_modifica_interfaz_de_escritorio():
    html, _ = codigo_pos()
    assert 'id="abadion-tablet-layout"' in html
    assert "@media (max-width:1100px)" in html
    assert '.tablet-cart-toggle{display:none}' in html
    assert 'aria-controls="tabletOrder"' in html
    assert 'aria-expanded="false"' in html
    assert 'body.tablet-order-open .order{display:block}' in html
    assert 'body.tablet-order-open .menu{display:none}' in html
    assert "(min-width:1101px)" in ENTRENAMIENTO.read_text(encoding="utf-8")


def test_no_quedan_llamadas_no_compatibles_sin_alternativa():
    _, script = codigo_pos()
    assert "AbortSignal.timeout(12000)" not in script
    assert "senalTiempoPos(12000)" in script
    assert script.count("crypto.randomUUID()") == 1  # Solo en la rama nativa del helper.
    assert script.count("uuidPos()") >= 5
    assert "window.isSecureContext" in script
    assert "window.crypto.getRandomValues(bytes)" in script
    assert "Math.random()" not in script


@pytest.mark.skipif(shutil.which("node") is None, reason="Node no instalado")
def test_script_pos_y_fallbacks_en_node():
    _, script = codigo_pos()
    sintaxis = subprocess.run(
        ["node", "--check"], input=script, text=True, capture_output=True, check=False
    )
    assert sintaxis.returncode == 0, sintaxis.stderr

    inicio = script.index("  function senalTiempoPos(ms) {")
    fin = script.index("\n\n  var tabletCartButton", inicio)
    funciones = script[inicio:fin]
    # Entorno sin AbortSignal.timeout y sin crypto.randomUUID, como Chrome 101.
    control = r"""
const assert = require('node:assert/strict');
const webcrypto = require('node:crypto').webcrypto;
globalThis.window = {
    isSecureContext: true,
    crypto: {getRandomValues: (buffer) => webcrypto.getRandomValues(buffer)}
};
globalThis.AbortSignal = {}; // Chrome 101 no soporta .timeout
const ids = [uuidPos(), uuidPos()];
assert.match(ids[0], /^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/);
assert.notEqual(ids[0], ids[1]);
const signal = senalTiempoPos(1);
window.isSecureContext = false;
assert.throws(() => uuidPos(), /HTTPS/);
setTimeout(() => { assert.equal(signal.aborted, true); }, 10);
"""
    resultado = subprocess.run(
        ["node", "-e", funciones + "\n" + control],
        text=True, capture_output=True, check=False
    )
    assert resultado.returncode == 0, resultado.stderr
