"""Inventario sin lifespan: importa rutas, no abre bases ni inicia bot/servidor."""
import argparse
import inspect
import json
import os
from pathlib import Path
import sys

RAIZ=Path(__file__).resolve().parents[1]
os.environ['PYTHON_DOTENV_DISABLED']='1'
sys.path.insert(0,str(RAIZ/'src'))
from fastapi.routing import APIRoute
from api import app
from pos_seguridad import RutaPosSegura

PUBLICAS={
    '/': 'Shell público, sin datos comerciales',
    '/pos-api/login': 'Público: Origin exacto y límite temporal de intentos',
    '/pos-api/logout': 'Origin exacto; revoca cookie presentada, idempotente sin sesión',
    '/pos-api/simulacion/estado': 'Público: capacidades ficticias sin datos personales',
    '/pos-api/catalogo/productos': 'Público solo con marca ficticia válida; sesión en legado',
    '/pos-api/catalogo/adicionales': 'Público solo con marca ficticia válida; sesión en legado',
    '/pos-api/catalogo/productos/{id_producto}/personalizaciones': 'Público solo con marca ficticia válida; sesión en legado',
}


def dependencias(nodo):
    nombres=set()
    for d in nodo.dependencies:
        nombres.add(getattr(d.call,'__name__',type(d.call).__name__))
        nombres.update(dependencias(d))
    return nombres


def inventario():
    filas=[]
    for r in app.routes:
        if not isinstance(r,APIRoute):
            continue
        deps=dependencias(r.dependant)
        ruta=r.path
        if ruta in PUBLICAS:
            permiso=PUBLICAS[ruta]
        elif 'exigir_administrador_pos' in deps:
            permiso='Administración'
        elif 'exigir_usuario_pos' in deps:
            permiso='Administración o Ventas'
        elif 'exigir_integracion' in deps:
            permiso='Bearer integración; cookie POS y token bot insuficientes'
        elif 'exigir_comandos' in deps:
            permiso='Bearer bot o integración; identidad humana pendiente (bot sin cambios)'
        else:
            raise AssertionError(f'Ruta sin contrato de autorización: {ruta}')
        csrf='No aplica (lectura o Bearer explícito)'
        if ruta.startswith('/pos-api/'):
            assert isinstance(r,RutaPosSegura),ruta
            if r.methods-{'GET','HEAD','OPTIONS'}:
                assert 'comprobar_origen' in deps or ruta in ('/pos-api/login','/pos-api/logout'),ruta
                csrf='Origin exacto, sin duplicados, Sec-Fetch-Site; SameSite strict'
        archivo=Path(inspect.getsourcefile(r.endpoint)).relative_to(RAIZ).as_posix()
        linea=inspect.getsourcelines(r.endpoint)[1]
        filas.append({'ruta':ruta,'metodos':sorted(r.methods),'permiso':permiso,
                      'csrf':csrf,'archivo':archivo,'linea':linea,'dependencias':sorted(deps)})
    return filas


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--generar',action='store_true')
    args=parser.parse_args()
    filas=inventario()
    carpeta=RAIZ/'docs/seguridad'
    datos=carpeta/'endpoints-consolidados.json'
    if args.generar:
        datos.write_text(json.dumps(filas,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        lineas=['# Matriz de endpoints y permisos','',
                'Generada desde las rutas efectivas; controles de factories y perímetro en el informe técnico.',
                'La API general conserva docs/OpenAPI públicos de desarrollo; no deben publicarse como perímetro productivo.',
                'El shell estático `/pos/` es público. GET no autoriza escrituras ni cambios de privilegios.','',
                '| Método/ruta | Permiso | CSRF | Referencia |','| --- | --- | --- | --- |']
        for f in filas:
            metodos=', '.join(f['metodos'])
            lineas.append(f"| `{metodos} {f['ruta']}` | {f['permiso']} | {f['csrf']} | [{f['archivo']}:{f['linea']}](../../{f['archivo']}#L{f['linea']}) |")
        (carpeta/'matriz-endpoints.md').write_text('\n'.join(lineas)+'\n',encoding='utf-8')
    else:
        assert json.loads(datos.read_text(encoding='utf-8'))==filas, 'Regenerar y revisar el inventario: cambió una ruta o referencia.'
    print(f'{sum(len(f["metodos"]) for f in filas)} combinaciones método/ruta verificadas.')


if __name__=='__main__':
    main()
