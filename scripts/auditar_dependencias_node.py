"""Consulta solo nombres/versiones del lock público; no instala ni ejecuta Node/bot.

Salida no cero ante asesorías o error de red. No lee npmrc, .env ni credenciales.
"""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import urllib.request


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--salida',type=Path,required=True)
    args=parser.parse_args()
    raiz=Path(__file__).resolve().parents[1]
    lock=json.loads((raiz/'whatsapp-bot/package-lock.json').read_text(encoding='utf-8'))
    paquetes=defaultdict(set)
    for ruta,p in lock['packages'].items():
        if 'node_modules/' in ruta and p.get('version'):
            paquetes[p.get('name') or ruta.rsplit('node_modules/',1)[1]].add(p['version'])
    datos=json.dumps({k:sorted(v) for k,v in paquetes.items()}).encode()
    peticion=urllib.request.Request('https://registry.npmjs.org/-/npm/v1/security/advisories/bulk',
        data=datos,headers={'Content-Type':'application/json','User-Agent':'abadion-auditoria-aislada'})
    # No enviar proxies/autenticación heredados; únicamente endpoint público fijo HTTPS.
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(peticion,timeout=60) as respuesta:
        asesorias=json.load(respuesta)
    args.salida.parent.mkdir(parents=True,exist_ok=True)
    args.salida.write_text(json.dumps({'fuente':'npm-registry-bulk','paquetes':len(paquetes),
                                     'asesorias':asesorias},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'{len(paquetes)} paquetes; {len(asesorias)} paquetes con avisos. Bot/lock sin cambios.')
    return 1 if asesorias else 0


if __name__=='__main__':
    raise SystemExit(main())
