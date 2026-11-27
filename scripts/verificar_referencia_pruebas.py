"""Compara identidades JUnit con los 647 casos de #41; no toca DB ni servidores."""
import argparse
import json
from pathlib import Path
import xml.etree.ElementTree as ET


def comparar(archivo, *, windows=False):
    raiz=Path(__file__).resolve().parents[1]
    referencia=json.loads((raiz/'docs/seguridad/casos-referencia-647.json').read_text(encoding='utf-8'))
    esperados=set(referencia['casos'])
    casos=list(ET.parse(archivo).iter('testcase'))
    actuales={c.get('classname')+'::'+c.get('name'):c for c in casos}
    faltantes=sorted(esperados-actuales.keys())
    fallidos=sorted(k for k,c in actuales.items() if c.find('failure') is not None or c.find('error') is not None)
    omitidos=sorted(k for k,c in actuales.items() if c.find('skipped') is not None)
    resultado={'referencia':referencia['base'],'casos_referencia':len(esperados),
               'casos_actuales':len(casos),'nuevos':len(actuales.keys()-esperados),
               'faltantes':faltantes,'fallidos':fallidos,'omitidos':omitidos,
               'duplicados':len(casos)-len(actuales),'windows_edge':windows}
    resultado['conforme']=(len(esperados)==647 and not faltantes and not fallidos
                           and not resultado['duplicados'] and (not windows or not omitidos))
    return resultado


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('junit',type=Path)
    parser.add_argument('--windows-edge',action='store_true')
    parser.add_argument('--salida',type=Path,required=True)
    args=parser.parse_args()
    resultado=comparar(args.junit,windows=args.windows_edge)
    args.salida.write_text(json.dumps(resultado,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in resultado.items() if not isinstance(v,list)}))
    return 0 if resultado['conforme'] else 1


if __name__=='__main__':
    raise SystemExit(main())
