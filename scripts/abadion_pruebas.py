"""Abadion Pruebas: local, fictional, persistent; explicit release activation."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import secrets
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.request
import zipfile
from uuid import uuid4
from contextlib import closing

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'src')]
from pos_entrenamiento_db import bloquear_entrenamiento, comprobar_archivo
from pos_preproduccion import (MODO_PRUEBAS, abrir_base, actualizar_catalogo, auditar,
    carpeta_segura, configuracion, integridad, respaldo, restaurar, validar_respaldo)
from scripts.abadion_preproduccion import preparar, crear_app

PORT = 8079
HTTP = urllib.request.build_opener(urllib.request.ProxyHandler({}))
ALLOW = ('src/', 'scripts/', 'pos-web/', 'docs/')


def carpeta_pruebas(path):
    return carpeta_segura(path, nombre='Pruebas')


def guardar(path, data):
    comprobar_archivo(path)
    pending = path.with_suffix('.pendiente')
    comprobar_archivo(pending)
    with pending.open('x', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(pending, path)


def comprobar(carpeta):
    datos = configuracion(carpeta)
    if datos['modo'] != MODO_PRUEBAS:
        raise ValueError('Esta acción sólo admite Abadion Pruebas.')
    with closing(abrir_base(carpeta, datos['id'], lectura=True)) as db:
        integridad(db)
    return datos


def consultar(carpeta, accion='status'):
    datos = comprobar(carpeta)
    url = f'http://127.0.0.1:{PORT}'
    req = urllib.request.Request(url + '/_pruebas/' + accion,
        headers={'Authorization': 'Bearer ' + datos['control']},
        method='GET' if accion == 'status' else 'POST')
    with HTTP.open(req, timeout=25) as r:
        result = json.load(r)
    if accion == 'status' and result != {k: datos[k] for k in ('modo', 'id', 'carpeta')}:
        raise ValueError('El puerto pertenece a otra instancia; no se reutiliza.')
    return result


def ocupado():
    with socket.socket() as s:
        return s.connect_ex(('127.0.0.1', PORT)) == 0


def entorno():
    env = {k: v for k, v in os.environ.items() if not k.startswith(('ABADION_', 'NEGOCIO_', 'POS_'))
           and k not in ('API_URL', 'PYTHONPATH', 'PYTHONHOME')}
    env['PYTHON_DOTENV_DISABLED'] = '1'
    env['PYTHONUTF8'] = '1'
    return env


def abrir_edge(carpeta):
    profile = carpeta / 'Edge-Pruebas'
    if profile.resolve() != profile.absolute():
        raise ValueError('Perfil Edge indirecto rechazado.')
    candidates = [Path(os.getenv(k, '')) / 'Microsoft/Edge/Application/msedge.exe'
                  for k in ('ProgramFiles(x86)', 'ProgramFiles', 'LOCALAPPDATA')]
    edge = next((p for p in candidates if p.is_file()), None)
    if not edge:
        raise ValueError('No se encontró Edge. El servidor sigue disponible en http://127.0.0.1:8079/pos/')
    subprocess.Popen([str(edge), '--user-data-dir=' + str(profile), '--no-first-run',
                      'http://127.0.0.1:8079/pos/'], env=entorno())


def iniciar(carpeta, sin_edge=False):
    if ROOT.parent.name == "releases":
        validar_release(ROOT)
    comprobar(carpeta)
    if ocupado():
        consultar(carpeta)
    else:
        logpath = carpeta / 'servidor.log'
        comprobar_archivo(logpath)
        with logpath.open('ab') as log:
            child = subprocess.Popen([sys.executable, '-u', str(Path(__file__).resolve()),
                '--carpeta', str(carpeta), 'worker'], cwd=ROOT, env=entorno(),
                stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            if child.poll() is not None:
                raise ValueError('Falló el inicio. Revisá servidor.log; los datos se conservan.')
            try:
                consultar(carpeta)
                break
            except (OSError, ValueError):
                time.sleep(.2)
        else:
            raise ValueError('Inicio pendiente. Revisá el estado antes de repetir.')
    if not sin_edge:
        abrir_edge(carpeta)
    print('ABADION PRUEBAS — http://127.0.0.1:8079/pos/ — DATOS FICTICIOS')


def ejecutar(args, **kwargs):
    return subprocess.run(args, check=True, env=entorno(), **kwargs)


def release_python(path):
    return path / ('.venv/Scripts/python.exe' if os.name == 'nt' else '.venv/bin/python')


def validar_release(release):
    comprobar_archivo(release / 'release.json')
    meta = json.loads((release / 'release.json').read_text(encoding='utf-8'))
    if meta['commit'] != release.name or not re.fullmatch('[0-9a-f]{40}', release.name):
        raise ValueError('Identidad de versión inválida.')
    for name, sha in meta['archivos'].items():
        p = release / name
        if not p.is_relative_to(release) or '..' in Path(name).parts:
            raise ValueError('Ruta de versión inválida.')
        comprobar_archivo(p)
        if hashlib.sha256(p.read_bytes()).hexdigest() != sha:
            raise ValueError('Código modificado en la versión instalada: ' + name)
    return meta


def preparar_release(carpeta, origen, commit):
    if not re.fullmatch('[0-9a-f]{40}', commit or ''):
        raise ValueError('Indicá un commit completo de 40 caracteres, revisado y con CI aprobada.')
    # Export committed allowlisted files only. Never copy local DBs, .env, bot or credentials.
    archivo = ejecutar(['git', '-C', str(origen), 'archive', '--format=zip', commit], capture_output=True).stdout
    releases = carpeta / 'releases'
    releases.mkdir(exist_ok=True)
    if releases.resolve() != releases.absolute():
        raise ValueError('Carpeta releases indirecta rechazada.')
    final = releases / commit
    if final.exists():
        validar_release(final)
        return final
    staging = releases / ('.stage-' + uuid4().hex)
    destino = staging / commit
    destino.mkdir(parents=True)
    hashes = {}
    with zipfile.ZipFile(io.BytesIO(archivo)) as z:
        for name in z.namelist():
            if name.endswith('/') or not (name.startswith(ALLOW) or name == 'requirements.txt'):
                continue
            if '..' in Path(name).parts or Path(name).is_absolute() or name.endswith(('.db', '.pyc')):
                raise ValueError('Archivo de distribución rechazado: ' + name)
            content = z.read(name)
            p = destino / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(content)
            hashes[name] = hashlib.sha256(content).hexdigest()
    if 'scripts/abadion_pruebas.py' not in hashes:
        raise ValueError('El commit no contiene el entorno Abadion Pruebas.')
    ejecutar([sys.executable, '-m', 'venv', str(destino / '.venv')])
    ejecutar([str(release_python(destino)), '-m', 'pip', 'install', '-r', str(destino / 'requirements.txt')])
    guardar(destino / 'release.json', {'commit': commit, 'archivos': hashes})
    validar_release(destino)
    destino.rename(final)
    staging.rmdir()
    return final


def activar(carpeta, release):
    meta = validar_release(release)
    # Candidate opens DB READ ONLY, checks instance/schema/integrity, never migrates.
    ejecutar([str(release_python(release)), str(release / 'scripts/abadion_pruebas.py'),
              '--carpeta', str(carpeta), 'comprobar'], capture_output=True)
    old = None
    pointer = carpeta / 'activa.json'
    if pointer.exists():
        comprobar_archivo(pointer)
        current = json.loads(pointer.read_text(encoding='utf-8'))
        old = current['commit']
        if current['instancia'] != comprobar(carpeta)['id'] or not re.fullmatch('[0-9a-f]{40}', old):
            raise ValueError('La versión activa no coincide con esta instancia.')
        if old == meta['commit']:
            return  # Repeated activation must preserve the previous rollback target.
    guardar(pointer, {'commit': meta['commit'], 'anterior': old, 'instancia': comprobar(carpeta)['id']})
    auditar(carpeta, 'version-activada', commit=meta['commit'], anterior=old)


def actualizar(carpeta, origen, commit):
    with bloquear_entrenamiento(carpeta):
        comprobar(carpeta)
        copia = respaldo(carpeta, 'pre-actualizacion')
        validar_respaldo(carpeta, copia.name)
        release = preparar_release(carpeta, origen, commit)
        activar(carpeta, release)
        print(json.dumps({'commit': commit, 'backup': copia.name, 'datos': 'conservados'}))


def rollback(carpeta):
    with bloquear_entrenamiento(carpeta):
        datos = comprobar(carpeta)
        comprobar_archivo(carpeta / 'activa.json')
        active = json.loads((carpeta / 'activa.json').read_text(encoding='utf-8'))
        previous = active.get('anterior')
        if active['instancia'] != datos['id'] or not re.fullmatch('[0-9a-f]{40}', previous or ''):
            raise ValueError('No hay versión anterior de esta instancia.')
        copia = respaldo(carpeta, 'pre-rollback')
        validar_respaldo(carpeta, copia.name)
        activar(carpeta, carpeta / 'releases' / previous)
        print('Versión anterior activada. Stock e historial actuales conservados. ' + copia.name)


def recuperar(carpeta, nombre, destino):
    destino = carpeta_pruebas(destino)
    with bloquear_entrenamiento(carpeta):
        # Recovery must remain possible when the live DB is missing or corrupt.
        datos = configuracion(carpeta)
        if datos['modo'] != MODO_PRUEBAS:
            raise ValueError('La recuperación sólo admite Abadion Pruebas.')
        copia = validar_respaldo(carpeta, nombre)
        comprobar_archivo(carpeta / 'credenciales.json')
        if destino.exists():
            raise ValueError('La recuperación requiere una carpeta Pruebas inexistente.')
        destino.mkdir(parents=True)
        if os.name == 'nt':
            usuario = ejecutar(['whoami'], capture_output=True, text=True).stdout.strip()
            ejecutar(['icacls.exe', str(destino), '/inheritance:r', '/grant:r',
                      usuario + ':(OI)(CI)F', '*S-1-5-18:(OI)(CI)F'], capture_output=True)
        (destino / 'backups').mkdir()
        # New control token, same DB identity; restore never touches the source DB.
        guardar(destino / 'instalacion.json', {**datos, 'carpeta': str(destino), 'control': secrets.token_urlsafe(32)})
        for p in (copia, copia.with_suffix('.json')):
            (destino / 'backups' / p.name).write_bytes(p.read_bytes())
        (destino / 'credenciales.json').write_bytes((carpeta / 'credenciales.json').read_bytes())
        with bloquear_entrenamiento(destino):
            restaurar(destino, nombre, base_ausente=True)
        comprobar(destino)
        print('Recuperación aislada verificada: ' + str(destino))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--carpeta', type=Path, required=True)
    p.add_argument('accion', choices=['preparar','iniciar','worker','detener','estado','comprobar','backup',
        'validar-catalogo','aprobar-catalogo','actualizar','rollback','recuperar'])
    p.add_argument('--catalogo', type=Path)
    p.add_argument('--sha256')
    p.add_argument('--aprobar-instancia')
    p.add_argument('--sin-edge', action='store_true')
    p.add_argument('--origen', type=Path)
    p.add_argument('--commit')
    p.add_argument('--archivo')
    p.add_argument('--destino', type=Path)
    a = p.parse_args()
    try:
        carpeta = carpeta_pruebas(a.carpeta)
        os.environ['PYTHON_DOTENV_DISABLED'] = '1'
        if a.accion == 'preparar':
            print(preparar(carpeta, pruebas=True))
        elif a.accion in ('validar-catalogo','aprobar-catalogo'):
            if not a.catalogo:
                raise ValueError('Indicá --catalogo explícito.')
            print(json.dumps(actualizar_catalogo(carpeta, a.catalogo, validar=a.accion=='validar-catalogo',
                sha256=a.sha256, aprobacion=a.aprobar_instancia), ensure_ascii=False))
        elif a.accion == 'worker':
            import uvicorn
            with bloquear_entrenamiento(carpeta):
                comprobar(carpeta)
                server = uvicorn.Server(uvicorn.Config(crear_app(carpeta, lambda: setattr(server,'should_exit',True),
                    pruebas=True), host='127.0.0.1', port=PORT, proxy_headers=False, access_log=False))
                server.run()
        elif a.accion == 'iniciar':
            iniciar(carpeta, a.sin_edge)
        elif a.accion == 'estado':
            print(consultar(carpeta))
        elif a.accion == 'comprobar':
            print(json.dumps({k:v for k,v in comprobar(carpeta).items() if k != 'control'}))
        elif a.accion == 'detener':
            if ocupado():
                consultar(carpeta)
                consultar(carpeta, 'stop')
                end = time.monotonic() + 45
                while ocupado() and time.monotonic() < end:
                    time.sleep(.2)
                if ocupado():
                    raise ValueError('Cierre pendiente; no se forzó ningún proceso.')
            with bloquear_entrenamiento(carpeta):
                comprobar(carpeta)
                print('Abadion Pruebas detenido. Datos conservados.')
        elif a.accion == 'backup':
            if ocupado():
                consultar(carpeta)
                print(json.dumps(consultar(carpeta,'backup')))
            else:
                with bloquear_entrenamiento(carpeta):
                    print(json.dumps({'archivo':respaldo(carpeta).name}))
        elif a.accion == 'actualizar':
            if not a.origen:
                raise ValueError('Indicá --origen con el repositorio revisado.')
            actualizar(carpeta, a.origen, a.commit)
        elif a.accion == 'rollback':
            rollback(carpeta)
        elif a.accion == 'recuperar':
            if not a.archivo or not a.destino:
                raise ValueError('Indicá --archivo y --destino nuevos.')
            recuperar(carpeta, a.archivo, a.destino)
    except (OSError, ValueError, RuntimeError, sqlite3.Error, KeyError, subprocess.CalledProcessError) as e:
        p.exit(1, str(e) + '\n')


if __name__ == '__main__':
    main()
