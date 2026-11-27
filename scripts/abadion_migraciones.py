"""Migraciones offline exclusivamente de instalaciones ficticias; no activa producción."""
import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import sys

ROOT=Path(__file__).resolve().parents[1]
os.environ['PYTHON_DOTENV_DISABLED']='1'
sys.path[:0]=[str(ROOT),str(ROOT/'src')]
from migraciones import migrar,diagnosticar,comprobar_archivos,identidad,integridad,verificar_version,validar_catalogo,_respaldo_reservado
from pos_entrenamiento_db import bloquear_entrenamiento


def preparar_nueva(carpeta,*,pruebas=True):
    from scripts.abadion_preproduccion import preparar
    if Path(carpeta).exists():
        raise ValueError('La instalación limpia requiere un destino inexistente.')
    preparar(carpeta,pruebas=pruebas)
    return migrar(carpeta)


def recuperar_actual(carpeta,destino):
    from scripts.abadion_pruebas import _recuperar_bajo_bloqueo
    from pos_preproduccion import carpeta_segura,MODO_PRUEBAS
    with bloquear_entrenamiento(Path(carpeta)):
        cfg,ruta=comprobar_archivos(carpeta)
        destino=carpeta_segura(destino,nombre='Pruebas' if cfg['modo']==MODO_PRUEBAS else 'Preproduccion')
        if destino.exists(): raise ValueError('El destino debe ser nuevo; nunca se sobrescribe.')
        with closing(sqlite3.connect(ruta.as_uri()+'?mode=rw',uri=True,timeout=0)) as db:
            db.execute('PRAGMA foreign_keys=ON')
            with db:
                db.execute('BEGIN IMMEDIATE')
                identidad(db,cfg['id'])
                integridad(db)
                version=verificar_version(db)
                validar_catalogo(db,gestionado=version==5)
                copia=_respaldo_reservado(carpeta,db,ruta,cfg)
                _recuperar_bajo_bloqueo(carpeta,copia.name,destino,minimo_destino=version,permitir_preproduccion=True)
    return {'destino':str(destino),'version':version,'backup':copia.name,
            'origen_conservado':True,'produccion_habilitada':False}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('accion',choices=['diagnosticar','migrar','preparar','recuperar-actual'])
    p.add_argument('--carpeta',type=Path,required=True)
    p.add_argument('--destino',type=Path)
    p.add_argument('--preproduccion',action='store_true')
    a=p.parse_args()
    if a.accion=='diagnosticar': resultado=diagnosticar(a.carpeta)
    elif a.accion=='migrar': resultado=migrar(a.carpeta)
    elif a.accion=='preparar': resultado=preparar_nueva(a.carpeta,pruebas=not a.preproduccion)
    elif a.destino is None: p.error('Recuperar requiere --destino nuevo.')
    else: resultado=recuperar_actual(a.carpeta,a.destino)
    print(json.dumps(resultado,ensure_ascii=False))


if __name__=='__main__': main()
