"""Preparación offline de una candidata bloqueada. No incluye activación ni servidor."""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'src')]
from pos_entrenamiento_db import comprobar_archivo
from pos_preproduccion import integridad, leer_catalogo_preproduccion

ARCHIVO = 'abadion-produccion-candidata.db'
MODO = 'PRODUCCION-CANDIDATA-BLOQUEADA-V1'
APP_ID = 0x41424331
CATALOGO_SHA = '36bb753a5980a9fa445728ae13471e56b7325edea047e9e4b48a98eecff43486'
CONFIG = {'productos', 'adicionales_catalogo', 'usuarios_pos',
          'pos_catalogo_entrenamiento', 'pos_adicionales_producto',
          'pos_inicio_caja_diaria', 'candidata_corte', 'candidata_validaciones'}
PENDIENTES = ('efectivo_comidas', 'efectivo_bebidas_postres', 'cuentas_digitales',
              'stock_controlado', 'deudas_vigentes', 'corte_y_exclusion_bot')


def huella(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ruta_segura(path):
    path = Path(path).absolute()
    if (path.name != 'ProduccionCandidata' or path.resolve() != path
            or str(path).startswith(('\\\\', '//'))
            or any(p.casefold().startswith('onedrive') for p in path.parts)):
        raise ValueError('Se requiere carpeta local directa ProduccionCandidata fuera de sincronización.')
    for key in ('OneDrive', 'OneDriveConsumer', 'OneDriveCommercial'):
        if os.getenv(key) and path.is_relative_to(Path(os.environ[key]).resolve()):
            raise ValueError('No se admite una carpeta sincronizada.')
    for item in (path, *path.parents):
        if item.exists() and (item.is_symlink() or item.is_junction()):
            raise ValueError('No se admiten enlaces ni junctions.')
    return path


def carpeta_nueva(path):
    path = ruta_segura(path)
    # Exclusive mkdir also rejects empty existing installations and concurrent preparation.
    path.mkdir(parents=True, exist_ok=False)
    if os.name == 'nt':
        sid = subprocess.check_output(['whoami', '/user', '/fo', 'csv', '/nh'], text=True).strip().split(',')[-1].strip('"')
        subprocess.run(['icacls.exe', str(path), '/inheritance:r', '/grant:r',
                        f'*{sid}:(OI)(CI)F', '*S-1-5-18:(OI)(CI)F'], check=True, capture_output=True)
    else:
        path.chmod(0o700)
    verificar_permisos(path)
    return path


def verificar_permisos(path):
    if os.name != 'nt':
        if path.stat().st_mode & 0o077:
            raise ValueError('La carpeta no es privada.')
        return
    sid = subprocess.check_output(['whoami', '/user', '/fo', 'csv', '/nh'], text=True).strip().split(',')[-1].strip('"')
    with TemporaryDirectory(prefix='abadion-acl-') as temp:
        saved = Path(temp) / 'acl.txt'
        subprocess.run(['icacls.exe', str(path), '/save', str(saved)], check=True, capture_output=True)
        acl = saved.read_text(encoding='utf-16-le').lstrip('\ufeff')
    dacl = acl.split('D:', 1)[-1].split('S:', 1)[0].strip()
    entries = re.findall(r'\(([^)]+)\)', dacl)
    if not dacl.startswith('P') or sorted(entries) != sorted((f'A;OICI;FA;;;{sid}', 'A;OICI;FA;;;SY')):
        raise ValueError('No se pudo verificar acceso exclusivo del usuario y SYSTEM.')


def tablas(db):
    return [n for n, in db.execute("SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%'")]


def validar_catalogo(db):
    archivo = ROOT / 'scripts/catalogo-comercial.json'
    if huella(archivo) != CATALOGO_SHA:
        raise ValueError('Catálogo distribuido alterado.')
    catalogo = leer_catalogo_preproduccion(archivo.read_bytes())
    esperado = sorted((p.nombre, p.categoria, p.precio_centavos / 100,
                       int(p.controla_stock), 0) for p in catalogo.productos)
    actual = db.execute('SELECT nombre,categoria,precio_venta,controla_stock,stock FROM productos ORDER BY nombre').fetchall()
    if sorted(actual) != esperado:
        raise ValueError('La base difiere de los precios, variantes o control de stock aprobados.')
    extras = db.execute('SELECT nombre,precio_venta,activo FROM adicionales_catalogo').fetchall()
    if sorted(extras) != sorted((a.nombre, a.precio_centavos / 100, 1) for a in catalogo.adicionales):
        raise ValueError('Adicionales no coincidentes.')
    promos = db.execute('SELECT p.nombre,c.estado,c.grupo_promo FROM productos p JOIN pos_catalogo_entrenamiento c USING(id_producto)').fetchall()
    if sorted(promos) != sorted((p.nombre, 'sin_stock' if p.sin_stock else 'disponible',
                                'todos' if p.promo_postres_chicos else None) for p in catalogo.productos):
        raise ValueError('Promociones o disponibilidad no coincidentes.')
    links = db.execute('SELECT p.nombre,a.nombre FROM pos_adicionales_producto x JOIN productos p USING(id_producto) JOIN adicionales_catalogo a USING(id_adicional_catalogo)').fetchall()
    if sorted(links) != sorted((p.nombre, a) for p in catalogo.productos for a in p.adicionales):
        raise ValueError('Complementos no coincidentes.')


def validar_db(db):
    from pos_simulacion import VERSION_ESQUEMA_SIMULACION
    integridad(db)
    validar_catalogo(db)
    if (db.execute('PRAGMA application_id').fetchone()[0] != APP_ID
            or db.execute('PRAGMA user_version').fetchone()[0] != VERSION_ESQUEMA_SIMULACION):
        raise ValueError('Identidad o esquema ajeno.')
    corte = db.execute('SELECT * FROM candidata_corte').fetchall()
    if len(corte) != 1 or corte[0][1] != MODO or corte[0][3] is not None or corte[0][4] != CATALOGO_SHA:
        raise ValueError('Corte no pendiente o catálogo ajeno.')
    if db.execute('SELECT clave, valor FROM candidata_validaciones ORDER BY clave').fetchall() != sorted((k, None) for k in PENDIENTES):
        raise ValueError('Las validaciones deben continuar pendientes.')
    for table in tablas(db):
        if table not in CONFIG and db.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]:
            raise ValueError('La candidata contiene movimientos o datos no permitidos.')
        for action in ('INSERT', 'UPDATE', 'DELETE'):
            name = f'bloqueo_candidata_{table}_{action}'
            expected = trigger_sql(table, action)
            row = db.execute('SELECT sql FROM sqlite_schema WHERE type=\'trigger\' AND name=?', (name,)).fetchone()
            if not row or row[0] != expected:
                raise ValueError('Falta un bloqueo de escritura.')
    if (db.execute('SELECT COUNT(*) FROM productos').fetchone()[0] != 38
            or db.execute('SELECT COUNT(*) FROM productos WHERE stock != 0').fetchone()[0]
            or db.execute('SELECT rol, activo FROM usuarios_pos ORDER BY rol').fetchall() != [('admin', 0), ('ventas', 0)]):
        raise ValueError('Catálogo, stock o permisos inválidos.')
    return {'modo': MODO, 'id': corte[0][0], 'productos': 38,
            'transacciones': 0, 'habilitada': False, 'corte_efectivo': None,
            'pendientes': list(PENDIENTES), 'catalogo_sha256': CATALOGO_SHA}


def trigger_sql(table, action):
    return (f'CREATE TRIGGER "bloqueo_candidata_{table}_{action}" BEFORE {action} ON "{table}" '
            "BEGIN SELECT RAISE(ABORT, 'Candidata bloqueada: requiere corte y validacion real'); END")


def abrir(path):
    path = ruta_segura(path)
    verificar_permisos(path)
    archivo = path / ARCHIVO
    comprobar_archivo(archivo)
    for suffix in ('-wal', '-shm', '-journal'):
        auxiliar = archivo.with_name(archivo.name + suffix)
        if auxiliar.exists() or auxiliar.is_symlink():
            raise ValueError('Se requiere snapshot offline sin auxiliares SQLite.')
    return sqlite3.connect(archivo.as_uri() + '?mode=ro', uri=True)


def comprobar(path):
    with closing(abrir(path)) as db:
        return validar_db(db)


def preparar(path):
    from scripts.abadion_entrenamiento import construir_base
    from database import RUTA_ENTRENAMIENTO, RUTA_PREPRODUCCION
    from pos_auth import generar_hash
    if RUTA_ENTRENAMIENTO.get() or RUTA_PREPRODUCCION.get():
        raise ValueError('No preparar desde un contexto operativo.')
    catalogo_path = ROOT / 'scripts/catalogo-comercial.json'
    if huella(catalogo_path) != CATALOGO_SHA:
        raise ValueError('El catálogo difiere del aprobado.')
    catalogo = leer_catalogo_preproduccion(catalogo_path.read_bytes())
    path = carpeta_nueva(path)
    usuarios = [('administracion', 'admin', secrets.token_urlsafe(24)),
                ('ventas', 'ventas', secrets.token_urlsafe(24))]
    # Failures leave an unpublishable folder for diagnosis; never retry over it.
    with TemporaryDirectory(dir=path, prefix='.preparar-') as temp:
        nueva = Path(temp) / ARCHIVO
        construir_base(nueva, catalogo)
        with closing(sqlite3.connect(nueva)) as db, db:
            db.execute('PRAGMA foreign_keys=ON')
            for table in ('pos_entrenamiento', 'pos_puente_ficticio'):
                db.execute(f'DROP TABLE {table}')
            db.execute('DELETE FROM pos_inicio_contable')
            db.execute('DELETE FROM adicionales_catalogo WHERE activo=0')
            db.execute('DELETE FROM usuarios_pos')
            db.executemany('INSERT INTO usuarios_pos(usuario,rol,password_hash,activo) VALUES (?,?,?,0)',
                           [(u, r, generar_hash(p)) for u, r, p in usuarios])
            db.execute('CREATE TABLE candidata_corte(id TEXT PRIMARY KEY, modo TEXT NOT NULL, preparada_utc TEXT NOT NULL, corte_efectivo TEXT, catalogo_sha256 TEXT NOT NULL)')
            db.execute('INSERT INTO candidata_corte VALUES (?,?,?,NULL,?)',
                       (str(uuid4()), MODO, datetime.now(timezone.utc).isoformat(), CATALOGO_SHA))
            db.execute('CREATE TABLE candidata_validaciones(clave TEXT PRIMARY KEY, valor TEXT CHECK(valor IS NULL))')
            db.executemany('INSERT INTO candidata_validaciones VALUES (?,NULL)', [(k,) for k in PENDIENTES])
            db.execute(f'PRAGMA application_id={APP_ID}')
            for table in tablas(db):
                for action in ('INSERT', 'UPDATE', 'DELETE'):
                    db.execute(trigger_sql(table, action))
            db.commit()
            validar_db(db)
        # Credentials never enter reports, backups, Git or command output; users stay disabled.
        with (path / 'credenciales.json').open('x', encoding='utf-8') as f:
            json.dump({u: p for u, _, p in usuarios}, f)
            f.flush()
            os.fsync(f.fileno())
        nueva.rename(path / ARCHIVO)
    backup(path)
    return comprobar(path)


def backup(path):
    path = ruta_segura(path)
    comprobar(path)
    # Every snapshot uses a new directory; partial pairs are never accepted.
    destino = path / ('backup-' + uuid4().hex)
    destino.mkdir()
    copia = destino / ARCHIVO
    with closing(abrir(path)) as origen, closing(sqlite3.connect(copia)) as db:
        origen.backup(db)
        estado = validar_db(db)
    with copia.open('r+b') as f:
        os.fsync(f.fileno())
    meta = {'sha256': huella(copia), 'id': estado['id'], 'modo': MODO}
    with (destino / 'manifiesto.json').open('x', encoding='utf-8') as f:
        json.dump(meta, f)
        f.flush()
        os.fsync(f.fileno())
    return destino


def restaurar(origen, destino):
    origen = Path(origen).absolute()
    for file in (origen / ARCHIVO, origen / 'manifiesto.json'):
        comprobar_archivo(file)
    meta = json.loads((origen / 'manifiesto.json').read_text(encoding='utf-8'))
    copia = origen / ARCHIVO
    if any(copia.with_name(copia.name + s).exists() or copia.with_name(copia.name + s).is_symlink()
           for s in ('-wal', '-shm', '-journal')):
        raise ValueError('Snapshot con auxiliares rechazado.')
    if meta.get('sha256') != huella(copia):
        raise ValueError('Backup alterado.')
    with closing(sqlite3.connect(copia.as_uri() + '?mode=ro', uri=True)) as db:
        estado = validar_db(db)
        if meta != {'sha256': huella(copia), 'id': estado['id'], 'modo': MODO}:
            raise ValueError('Backup de identidad ajena.')
        destino = carpeta_nueva(destino)
        with closing(sqlite3.connect(destino / ARCHIVO)) as nueva:
            db.backup(nueva)
            validar_db(nueva)
    return comprobar(destino)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('accion', choices=('preparar', 'comprobar', 'backup', 'restaurar'))
    parser.add_argument('--carpeta', type=Path, required=True)
    parser.add_argument('--respaldo', type=Path)
    args = parser.parse_args()
    try:
        if args.accion == 'restaurar':
            if not args.respaldo:
                raise ValueError('Se requiere --respaldo.')
            result = restaurar(args.respaldo, args.carpeta)
        elif args.accion == 'backup':
            result = {'backup': backup(args.carpeta).name, 'habilitada': False}
        else:
            result = (preparar if args.accion == 'preparar' else comprobar)(args.carpeta)
        print(json.dumps(result, ensure_ascii=False))
    except (OSError, ValueError, sqlite3.Error, subprocess.SubprocessError):
        parser.exit(1, 'Candidata rechazada. No se habilitaron operaciones; conservar carpeta para diagnóstico.\n')


if __name__ == '__main__':
    main()
