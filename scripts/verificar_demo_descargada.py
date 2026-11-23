"""Comparación binaria reproducible; no modifica el archivo descargado."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESCARGA = 'bdfa181d535014cd42b40b07529091c98ca0f6c2'
PR18 = '59b4810d8c9564e70abfeeadb423de5e4b423669'


def comparar(archivo):
    descarga = Path(archivo).read_bytes()  # Fallar si no está accesible; nunca inferir igualdad.
    fuentes = {'archivo_descargado': descarga}
    for ref in (DESCARGA, PR18):
        fuentes['git:' + ref] = subprocess.check_output(
            ['git', 'show', ref + ':pos-web/index.html'], cwd=ROOT)
    fuentes['working_tree:pos-web/index.html'] = (ROOT / 'pos-web/index.html').read_bytes()
    return {
        'url_historial': f'https://raw.githubusercontent.com/NicoNunezFM/contabilidad-bebidas-postres/{DESCARGA}/pos-web/index.html',
        'fuentes': {nombre: {
            'bytes': len(datos), 'sha256': hashlib.sha256(datos).hexdigest(),
            'igual_byte_a_byte_descarga': datos == descarga,
            'igual_normalizando_crlf_descarga': datos.replace(b'\r\n', b'\n') == descarga.replace(b'\r\n', b'\n'),
        } for nombre, datos in fuentes.items()},
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archivo', type=Path)
    args = parser.parse_args()
    print(json.dumps(comparar(args.archivo), indent=2))
