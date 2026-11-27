"""Genera un catálogo revisable exclusivamente mediante una instalación ficticia nueva."""
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from contextlib import closing

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'src')]
os.environ['PYTHON_DOTENV_DISABLED']='1'


def generar():
    from scripts.abadion_preproduccion import preparar
    from pos_preproduccion import abrir_base,configuracion
    from migraciones import objetos
    from pos_costos_historicos import crear_esquema as costos
    from pos_seguimiento import crear_seguimiento
    from pos_envios import crear_libro_reparto
    from pos_delivery import crear as delivery
    from pos_cobros import crear_rendiciones
    from pos_compras_caja import preparar_compras_caja
    from pos_saldo_unificado import crear_esquema as unificado
    with TemporaryDirectory(prefix='abadion-contrato-ficticio-') as temporal:
        carpeta=Path(temporal)/'Pruebas'
        preparar(carpeta,pruebas=True)
        with closing(abrir_base(carpeta,configuracion(carpeta)['id'])) as db,db:
            todos=objetos(db)
            seguridad={n for n in todos if n.startswith('seguridad_') or n in ('sesiones_pos_contexto','eventos_seguridad_pos')}
            grupos={'seguridad':sorted(seguridad),'insumos':['operaciones_compras_insumos']}
            core=set(todos)-seguridad-{'operaciones_compras_insumos','pos_pruebas_catalogo'}
            for nombre,crear in [('costos',costos),('seguimiento',crear_seguimiento),('fondos',crear_libro_reparto),
                ('delivery',delivery),('rendiciones',crear_rendiciones),('compras_caja',preparar_compras_caja),('unificado',unificado)]:
                antes=set(objetos(db))
                crear(db)
                grupos[nombre]=sorted(set(objetos(db))-antes)
            return {'procedencia':'PR42 1ec1ab98755a248f86c3a50ba3164320e4381448; fixtures nuevos',
                    'core':sorted(core),'grupos':grupos,'objetos':objetos(db)}


if __name__=='__main__':
    resultado=generar()
    (ROOT/'src/migraciones_contrato.json').write_text(json.dumps(resultado,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f"Contrato: {len(resultado['objetos'])} objetos; sin datos de la base ficticia.")
