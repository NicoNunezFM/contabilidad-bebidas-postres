"""Sólo directorios temporales, saldos desconocidos y ataques con datos ficticios."""
from contextlib import closing
import json
import io
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import zipfile
from tempfile import TemporaryDirectory

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import abadion_candidata as c


@pytest.fixture(scope='module')
def candidata():
    with TemporaryDirectory(prefix='abadion-candidata-ficticia-') as temp:
        path = Path(temp) / 'ProduccionCandidata'
        c.preparar(path)
        yield path


def test_vacia_catalogo_roles_y_corte(candidata):
    result = c.comprobar(candidata)
    assert result['habilitada'] is False and result['transacciones'] == 0
    assert result['corte_efectivo'] is None and len(result['pendientes']) == 6
    with closing(c.abrir(candidata)) as db:
        assert db.execute('SELECT COUNT(*) FROM productos WHERE controla_stock=1').fetchone()[0] == 9
        assert db.execute('SELECT COUNT(*) FROM adicionales_catalogo').fetchone()[0] == 2
        assert db.execute('SELECT COUNT(*) FROM sesiones_pos').fetchone()[0] == 0
        assert db.execute('SELECT COUNT(*) FROM pos_inicio_contable').fetchone()[0] == 0
        assert not db.execute("SELECT 1 FROM sqlite_schema WHERE name IN ('pos_entrenamiento','pos_preproduccion','pos_puente_ficticio')").fetchall()
        assert db.execute("SELECT nombre,precio_venta FROM adicionales_catalogo ORDER BY nombre").fetchall() == [('Cheddar extra', 1000.0), ('Huevo extra', 1000.0)]


@pytest.mark.parametrize('table', ['ventas', 'compras', 'gastos', 'movimientos_caja',
    'cuentas_deuda_negocio', 'pos_ventas_simuladas', 'pos_diario_caja',
    'productos', 'usuarios_pos', 'candidata_corte', 'candidata_validaciones',
    'pos_saldos_iniciales', 'pos_deudas_apertura', 'pos_pagos_deuda_apertura',
    'pos_stock_progresivo', 'pos_validaciones_stock'])
def test_sql_directo_bloqueado(candidata, table):
    before = c.huella(candidata / c.ARCHIVO)
    with closing(sqlite3.connect(candidata / c.ARCHIVO)) as db:
        with pytest.raises(sqlite3.IntegrityError, match='Candidata bloqueada'):
            # DELETE triggers only fire on existing rows; insert always exercises guard.
            db.execute(f'INSERT INTO "{table}" DEFAULT VALUES')
        db.rollback()
    assert c.huella(candidata / c.ARCHIVO) == before


def test_reinicio_proceso_readonly_y_sin_inicio(candidata):
    script = str(c.ROOT / 'scripts/abadion_candidata.py')
    before = c.huella(candidata / c.ARCHIVO)
    for _ in range(2):
        result = subprocess.run([sys.executable, script, 'comprobar', '--carpeta', str(candidata)], capture_output=True, text=True, check=True)
        assert json.loads(result.stdout)['habilitada'] is False
    result = subprocess.run([sys.executable, script, 'iniciar', '--carpeta', str(candidata)], capture_output=True)
    assert result.returncode != 0
    assert c.huella(candidata / c.ARCHIVO) == before


def test_no_reutiliza_ni_carpeta_vacia(candidata):
    before = c.huella(candidata / c.ARCHIVO)
    with pytest.raises(FileExistsError):
        c.preparar(candidata)
    with TemporaryDirectory() as temp:
        path = Path(temp) / 'ProduccionCandidata'
        path.mkdir()
        with pytest.raises(FileExistsError):
            c.carpeta_nueva(path)
    assert before == c.huella(candidata / c.ARCHIVO)


def test_restore_sin_original(candidata):
    snapshot = c.backup(candidata)
    with TemporaryDirectory() as temp:
        # Recovery only depends on snapshot, not the original config/DB/credentials.
        recovery = Path(temp) / 'ProduccionCandidata'
        assert c.restaurar(snapshot, recovery) == c.comprobar(candidata)
        with closing(c.abrir(recovery)) as restored, closing(c.abrir(candidata)) as original:
            assert list(restored.iterdump()) == list(original.iterdump())
        assert not (recovery / 'credenciales.json').exists()
        with pytest.raises(FileExistsError):
            c.restaurar(snapshot, recovery)


@pytest.mark.parametrize('attack', ['hash', 'identity', 'foreign', 'wal', 'guard'])
def test_backup_invalido_rechazado(candidata, attack):
    snapshot = c.backup(candidata)
    with TemporaryDirectory() as temp:
        source = Path(temp) / 'backup'
        shutil.copytree(snapshot, source)
        dbpath = source / c.ARCHIVO
        meta = json.loads((source / 'manifiesto.json').read_text())
        if attack == 'hash':
            with dbpath.open('ab') as f:
                f.write(b'ficticio')
        elif attack == 'identity':
            meta['id'] = 'identidad-ficticia-ajena'
        elif attack == 'wal':
            dbpath.with_name(dbpath.name + '-wal').touch()
        else:
            with closing(sqlite3.connect(dbpath)) as db:
                if attack == 'foreign':
                    db.execute('PRAGMA application_id=1')
                else:
                    db.execute('DROP TRIGGER bloqueo_candidata_ventas_INSERT')
                db.commit()
            meta['sha256'] = c.huella(dbpath)
        (source / 'manifiesto.json').write_text(json.dumps(meta))
        dest = Path(temp) / 'ProduccionCandidata'
        with pytest.raises(ValueError):
            c.restaurar(source, dest)
        assert not dest.exists()


@pytest.mark.parametrize('name', ['Pruebas', 'Preproduccion', 'OneDrive/ProduccionCandidata', 'negocio.db'])
def test_rutas_rechazadas(name):
    with TemporaryDirectory() as temp, pytest.raises(ValueError):
        c.ruta_segura(Path(temp) / name)


def test_database_generica_rechaza_incluso_renombrada(candidata, monkeypatch, tmp_path):
    import database
    dest = tmp_path / 'copia-ficticia.db'
    shutil.copyfile(candidata / c.ARCHIVO, dest)
    monkeypatch.setenv('NEGOCIO_DB_PATH', str(dest))
    with pytest.raises(ValueError, match='bloqueada'):
        database.obtener_conexion()


def test_catalogo_alterado_no_crea_carpeta(monkeypatch):
    monkeypatch.setattr(c, 'CATALOGO_SHA', '0' * 64)
    with TemporaryDirectory() as temp:
        path = Path(temp) / 'ProduccionCandidata'
        with pytest.raises(ValueError, match='catálogo'):
            c.preparar(path)
        assert not path.exists()


def test_permisos_privados(candidata):
    import os
    if os.name == 'nt':
        with TemporaryDirectory() as temp:
            saved = Path(temp) / 'acl.txt'
            subprocess.run(['icacls.exe', str(candidata), '/save', str(saved)], check=True, capture_output=True)
            acl = saved.read_text(encoding='utf-16-le')
            assert 'D:P' in acl and acl.count('(A;OICI;FA;;;') == 2
            assert ';ID;' not in acl  # No inherited ACEs.
    else:
        assert candidata.stat().st_mode & 0o077 == 0


def test_fallo_permisos_no_crea_db_ni_credenciales(monkeypatch):
    def fallo(_):
        raise ValueError('Permisos ficticios inseguros')
    monkeypatch.setattr(c, 'verificar_permisos', fallo)
    with TemporaryDirectory() as temp:
        path = Path(temp) / 'ProduccionCandidata'
        with pytest.raises(ValueError, match='Permisos'):
            c.preparar(path)
        assert not (path / c.ARCHIVO).exists()
        assert not (path / 'credenciales.json').exists()


def test_entorno_no_importa_base_fuente(monkeypatch):
    with TemporaryDirectory() as temp:
        source = Path(temp) / 'legado-ficticio.db'
        source.write_bytes(b'sentinel-ficticio-no-es-una-base-real')
        monkeypatch.setenv('NEGOCIO_DB_PATH', str(source))
        monkeypatch.setenv('POS_V1_SIMULACION', '1')
        path = Path(temp) / 'ProduccionCandidata'
        assert c.preparar(path)['transacciones'] == 0
        assert source.read_bytes() == b'sentinel-ficticio-no-es-una-base-real'


def test_catalogo_db_alterado_rechazado(candidata):
    with TemporaryDirectory() as temp:
        path = Path(temp) / 'copia.db'
        shutil.copyfile(candidata / c.ARCHIVO, path)
        with closing(sqlite3.connect(path)) as db:
            db.execute('DROP TRIGGER bloqueo_candidata_productos_UPDATE')
            db.execute('UPDATE productos SET precio_venta=1')
            db.execute(c.trigger_sql('productos', 'UPDATE'))
            db.commit()
            with pytest.raises(ValueError, match='precios'):
                c.validar_db(db)


def test_catalogo_exportado_independiente_de_autocrlf():
    archive = subprocess.check_output(['git', '-c', 'core.autocrlf=false', 'archive',
        '--format=zip', 'HEAD', 'scripts/catalogo-comercial.json'], cwd=c.ROOT)
    with zipfile.ZipFile(io.BytesIO(archive)) as content:
        assert c.hashlib.sha256(content.read('scripts/catalogo-comercial.json')).hexdigest() == c.CATALOGO_SHA


def test_saldos_y_deudas_no_precargados(candidata):
    with closing(c.abrir(candidata)) as db:
        assert db.execute('SELECT * FROM pos_saldos_iniciales ORDER BY caja').fetchall() == [
            ('bebidas_postres', None, None, None), ('comidas', None, None, None)]
        for tabla in ('pos_deudas_apertura','pos_pagos_deuda_apertura','pos_validaciones_stock'):
            assert db.execute(f'SELECT COUNT(*) FROM {tabla}').fetchone() == (0,)
        assert not db.execute('SELECT 1 FROM pos_stock_progresivo WHERE habilitado<>0').fetchall()


@pytest.mark.skipif(sys.platform != 'win32', reason='Alias 8.3 de Windows')
def test_ruta_temporal_windows_abreviada(candidata):
    import ctypes
    buffer = ctypes.create_unicode_buffer(32768)
    assert ctypes.windll.kernel32.GetShortPathNameW(str(candidata.parent), buffer, len(buffer))
    alias = Path(buffer.value) / 'ProduccionCandidata'
    assert c.ruta_segura(alias) == candidata.resolve()
    assert c.comprobar(alias)['habilitada'] is False


@pytest.mark.skipif(sys.platform != 'win32', reason='ACL nativa de Windows')
@pytest.mark.parametrize('reglas', [
    ['/grant', '*S-1-1-0:(OI)(CI)R'],
    ['/inheritance:e'],
])
def test_acl_extra_o_heredada_se_rechaza(reglas):
    with TemporaryDirectory() as temp:
        carpeta = c.carpeta_nueva(Path(temp) / 'ProduccionCandidata')
        subprocess.run(['icacls.exe', str(carpeta), *reglas], check=True, capture_output=True)
        with pytest.raises(ValueError, match='acceso exclusivo'):
            c.verificar_permisos(carpeta)


@pytest.mark.skipif(sys.platform != 'win32', reason='ACL nativa de Windows')
def test_creacion_reemplaza_reglas_explicitas_del_directorio_nuevo():
    with TemporaryDirectory() as temp:
        carpeta = Path(temp).resolve() / 'ProduccionCandidata'
        carpeta.mkdir()
        subprocess.run(['icacls.exe', str(carpeta), '/grant', '*S-1-1-0:(OI)(CI)R'], check=True, capture_output=True)
        sid = subprocess.check_output(['whoami','/user','/fo','csv','/nh'],text=True).strip().split(',')[-1].strip('"')
        c.restringir_permisos_windows(carpeta, sid)
        c.verificar_permisos(carpeta)
        protegida, reglas = c.permisos_windows(carpeta)
        assert protegida and len(reglas) == 2
