"""Actualización explícita de instalaciones ficticias. Nunca importa ni repara libros."""
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
from tempfile import NamedTemporaryFile
from uuid import UUID, uuid4

VERSION=5
ID_POS=0x41425031
ID_PASO='0005-garantias-39-42'
MODOS=('PREPRODUCCION-FICTICIA-V1','ABADION-PRUEBAS-FICTICIAS-V1')
META={'abadion_esquema','abadion_migraciones','abadion_esquema_update','abadion_esquema_delete',
      'abadion_migraciones_update','abadion_migraciones_delete'}


def normalizar(sql):
    # Conserva literales: nunca colapsar espacios dentro de CHECK o mensajes de trigger.
    return ' '.join(re.findall(r"'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|\[[^\]]*\]|`[^`]*`|[\w]+|[^\s]",sql))


def objetos(db):
    return {nombre:{'tipo':tipo,'tabla':tabla,'sql':normalizar(sql)} for tipo,nombre,tabla,sql in
            db.execute("SELECT type,name,tbl_name,sql FROM sqlite_schema WHERE sql IS NOT NULL AND name NOT GLOB 'sqlite_*' ORDER BY name")}


def contrato():
    return json.loads(Path(__file__).with_name('migraciones_contrato.json').read_text(encoding='utf-8'))


def digest(valor):
    return hashlib.sha256(json.dumps(valor,ensure_ascii=True,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def checksum():
    c=contrato()
    return digest({'paso':ID_PASO,'de':4,'a':5,'huellas':'tipos-rowid-multiplicidad-sha256-v1','contrato':c})


def integridad(db):
    from pos_preproduccion import integridad as verificar
    verificar(db)


def validar_catalogo(db, *, gestionado=False):
    c=contrato()
    presentes=objetos(db)
    nombres=set(presentes)-META
    if not set(c['core'])<=nombres or nombres-set(c['objetos']):
        raise ValueError('Esquema incompleto o con objetos desconocidos; requiere revisión.')
    if any(presentes[n]!=c['objetos'][n] for n in nombres):
        raise ValueError('Contrato estructural alterado; no se repara automáticamente.')
    for grupo,miembros in c['grupos'].items():
        encontrados=set(miembros)&nombres
        if encontrados and encontrados!=set(miembros):
            raise ValueError('Módulo incompleto: '+grupo)
    if gestionado and not set(c['grupos']['seguridad']+c['grupos']['costos']+c['grupos']['insumos'])<=nombres:
        raise ValueError('Faltan garantías de la versión gestionada.')


def identidad(db,esperada=None):
    if db.execute('PRAGMA application_id').fetchone()[0]!=ID_POS:
        raise ValueError('Tipo de base ajeno; no se convierte por nombre de archivo.')
    presentes=objetos(db)
    if any(n in presentes for n in ('candidata_corte','pos_entrenamiento','pos_tablet_laboratorio','saldos_iniciales_caja')):
        raise ValueError('Familia incompatible o candidata bloqueada.')
    if 'pos_preproduccion' not in presentes:
        raise ValueError('Falta la identidad de instalación persistente ficticia.')
    filas=db.execute('SELECT modo,instalacion FROM pos_preproduccion').fetchall()
    if len(filas)!=1 or filas[0][0] not in MODOS or str(UUID(filas[0][1]))!=filas[0][1]:
        raise ValueError('Marcador de instalación inválido.')
    modo,instancia=filas[0]
    if esperada is not None and instancia!=esperada:
        raise ValueError('Identidad de instalación incorrecta.')
    if modo==MODOS[1] and 'pos_pruebas_catalogo' not in presentes:
        raise ValueError('Falta aprobación de catálogo del modo Pruebas.')
    return modo,instancia


def crear_registro(db):
    db.execute('''CREATE TABLE abadion_esquema (
        id INTEGER PRIMARY KEY CHECK(id=1), instancia TEXT NOT NULL UNIQUE,
        modo TEXT NOT NULL, version INTEGER NOT NULL CHECK(version>=5),
        minimo_codigo INTEGER NOT NULL CHECK(minimo_codigo>=5))''')
    db.execute('''CREATE TABLE abadion_migraciones (
        id TEXT PRIMARY KEY, instancia TEXT NOT NULL REFERENCES abadion_esquema(instancia),
        desde INTEGER NOT NULL, hasta INTEGER NOT NULL, checksum TEXT NOT NULL,
        aplicada_utc TEXT NOT NULL, esquema_antes TEXT NOT NULL,
        esquema_despues TEXT NOT NULL, datos_antes TEXT NOT NULL)''')
    for tabla in ('abadion_esquema','abadion_migraciones'):
        for accion in ('update','delete'):
            db.execute(f'''CREATE TRIGGER {tabla}_{accion} BEFORE {accion.upper()} ON {tabla}
                BEGIN SELECT RAISE(ABORT,'Registro de migraciones inmutable'); END''')


def esquema_registro():
    with closing(sqlite3.connect(':memory:')) as db:
        crear_registro(db)
        return objetos(db)


def verificar_version(db,version_legacy=4):
    """Solo lectura. El esquema 4 sigue siendo responsabilidad de sus gates históricos."""
    v=db.execute('PRAGMA user_version').fetchone()[0]
    meta={n for n, in db.execute("SELECT name FROM sqlite_schema WHERE name LIKE 'abadion_%'")}&META
    if version_legacy!=4:
        raise ValueError('Código de contrato incompatible.')
    if v==4 and not meta:
        return 4
    if v!=VERSION or meta!=META:
        raise ValueError('Versión futura, anterior o migración incompleta; no abrir para escribir.')
    presentes=objetos(db)
    modo,instancia=identidad(db)
    if {n:presentes[n] for n in META}!=esquema_registro():
        raise ValueError('Registro de migraciones alterado.')
    if db.execute('SELECT * FROM abadion_esquema').fetchall()!=[(1,instancia,modo,5,5)]:
        raise ValueError('Versión e identidad de registro incompatibles.')
    rows=db.execute('SELECT id,instancia,desde,hasta,checksum,esquema_antes,esquema_despues,datos_antes FROM abadion_migraciones').fetchall()
    if len(rows)!=1 or rows[0][:5]!=(ID_PASO,instancia,4,5,checksum()) or any(not re.fullmatch('[0-9a-f]{64}',x) for x in rows[0][5:]):
        raise ValueError('Historial de migraciones incompleto o checksum desconocido.')
    validar_catalogo(db,gestionado=True)
    return v


def valor(v):
    if v is None: return ['null']
    if isinstance(v,bytes): return ['blob',v.hex()]
    if isinstance(v,float): return ['real',v.hex()]
    if isinstance(v,int): return ['integer',str(v)]
    return ['text',v]


def datos(db,tablas=None):
    tablas=tablas or [n for n, in db.execute("SELECT name FROM sqlite_schema WHERE type='table' ORDER BY name") if n not in ('abadion_esquema','abadion_migraciones')]
    resultado={}
    for n in tablas:
        quoted='"'+n.replace('"','""')+'"'
        sin_rowid=db.execute('PRAGMA table_list('+quoted+')').fetchone()[4]
        columnas='*' if sin_rowid else '_rowid_,*'
        filas=sorted(digest([valor(v) for v in f]) for f in db.execute('SELECT '+columnas+' FROM '+quoted))
        resultado[n]={'filas':len(filas),'sha256':digest(filas)}
    return resultado


def comprobar_archivos(carpeta):
    from pos_preproduccion import configuracion,perfil
    from pos_entrenamiento_db import comprobar_archivo
    cfg=configuracion(carpeta)
    if cfg.get('esquema_minimo',4) not in (4,5):
        raise ValueError('Instalación de una versión superior o desconocida.')
    ruta=Path(carpeta).absolute()/perfil(carpeta)[1]
    if not ruta.is_file(): raise ValueError('No se crea una base ausente al migrar.')
    for sufijo in ('','-journal','-wal','-shm'):
        comprobar_archivo(ruta.with_name(ruta.name+sufijo))
    return cfg,ruta


def diagnosticar(carpeta):
    cfg,ruta=comprobar_archivos(carpeta)
    with closing(sqlite3.connect(ruta.as_uri()+'?mode=ro',uri=True)) as db:
        modo,instancia=identidad(db,cfg['id'])
        if modo!=cfg['modo']: raise ValueError('Modos de instalación distintos.')
        integridad(db)
        v=verificar_version(db)
        validar_catalogo(db,gestionado=v==5)
        return {'instancia':instancia,'modo':modo,'version':v,'destino':VERSION,
                'esquema_sha256':digest(objetos(db)),'migrable':v==4,'produccion_habilitada':False}


def _respaldo_reservado(carpeta,db,ruta,cfg):
    """El llamador mantiene BEGIN IMMEDIATE sin escribir; leer desde otra conexión."""
    from backups import _publicar_respaldo
    from pos_entrenamiento_db import comprobar_archivo
    directorio=Path(carpeta)/'backups'
    directorio.mkdir(exist_ok=True)
    if directorio.resolve()!=directorio.absolute(): raise ValueError('Directorio de backup indirecto.')
    destino=directorio/('migracion-'+uuid4().hex+'.db')
    temporal=None
    try:
        with NamedTemporaryFile(dir=directorio,suffix='.tmp',delete=False) as f: temporal=Path(f.name)
        with closing(sqlite3.connect(ruta.as_uri()+'?mode=ro',uri=True)) as origen,closing(sqlite3.connect(temporal)) as copia:
            origen.backup(copia)
            integridad(copia)
            if objetos(copia)!=objetos(db) or datos(copia)!=datos(db):
                raise ValueError('El respaldo no representa el corte reservado.')
        meta={'modo':cfg['modo'],'id':cfg['id'],'sha256':hashlib.sha256(temporal.read_bytes()).hexdigest()}
        with temporal.open('r+b') as f: os.fsync(f.fileno())
        _publicar_respaldo(temporal,destino)
        temporal.unlink(missing_ok=True)  # POSIX publica con hardlink; validar solo tras quedar un enlace.
        manifiesto=destino.with_suffix('.json')
        comprobar_archivo(manifiesto)
        with manifiesto.open('x',encoding='utf-8') as f:
            json.dump(meta,f); f.flush(); os.fsync(f.fileno())
        # Reutiliza el validador público de identidad, hash, integridad y FK.
        from pos_preproduccion import validar_respaldo
        validar_respaldo(carpeta,destino.name)
        return destino
    finally:
        if temporal is not None: temporal.unlink(missing_ok=True)


def aplicar_paso(db):
    from database import crear_esquema_operaciones_insumos
    from pos_costos_historicos import crear_esquema
    from pos_seguridad import preparar_esquema
    crear_esquema_operaciones_insumos(db)
    crear_esquema(db)
    preparar_esquema(db)


def migrar(carpeta):
    from pos_entrenamiento_db import bloquear_entrenamiento
    with bloquear_entrenamiento(Path(carpeta)):
        cfg,ruta=comprobar_archivos(carpeta)
        if cfg.get('esquema_minimo',4) not in (4,5):
            raise ValueError('Instalación de una versión superior o desconocida.')
        with closing(sqlite3.connect(ruta.as_uri()+'?mode=rw',uri=True,timeout=0)) as db:
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('PRAGMA synchronous=FULL')
            with db:
                db.execute('BEGIN IMMEDIATE')
                modo,instancia=identidad(db,cfg['id'])
                if modo!=cfg['modo']: raise ValueError('Modos distintos.')
                integridad(db)
                v=verificar_version(db)
                validar_catalogo(db,gestionado=v==5)
                if v==5: return {'version':5,'aplicada':False,'produccion_habilitada':False}
                antes=datos(db)
                esquema_antes=digest(objetos(db))
                copia=_respaldo_reservado(carpeta,db,ruta,cfg)
                # Piso externo conservador, publicado antes del cambio SQLite. Si
                # hay caída, el código nuevo exige continuar la migración, no servir
                # silenciosamente un esquema anterior. El libro SQLite es la autoridad.
                from scripts.abadion_pruebas import guardar
                guardar(Path(carpeta)/'instalacion.json',{**cfg,'esquema_minimo':5})
                aplicar_paso(db)
                if datos(db,list(antes))!=antes:
                    raise ValueError('La actualización alteró registros existentes; reversión obligatoria.')
                if any(v['filas'] for n,v in datos(db).items() if n not in antes):
                    raise ValueError('La migración inventó registros históricos.')
                crear_registro(db)
                db.execute('PRAGMA user_version=5')
                db.execute('INSERT INTO abadion_esquema VALUES(1,?,?,5,5)',(instancia,modo))
                db.execute('INSERT INTO abadion_migraciones VALUES(?,?,?,?,?,?,?,?,?)',
                    (ID_PASO,instancia,4,5,checksum(),datetime.now(timezone.utc).isoformat(),
                     esquema_antes,digest(objetos(db)),digest(antes)))
                integridad(db)
                verificar_version(db)
            return {'version':5,'aplicada':True,'backup':copia.name,
                    'datos_sha256':digest(antes),'produccion_habilitada':False}
