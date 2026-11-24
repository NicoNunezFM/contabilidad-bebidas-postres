"""PREPRODUCCIÓN persistente, exclusivamente ficticia y local. Nunca producción."""
import argparse
import asyncio
import json
import os
import secrets
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from contextlib import asynccontextmanager, closing
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from pos_preproduccion import (
    ARCHIVO, MODO, abrir_base, actualizar_catalogo, auditar, carpeta_segura, configuracion, integridad, respaldo, restaurar,
)
from pos_entrenamiento_db import bloquear_entrenamiento, comprobar_archivo

PUERTO = 8078
URL = f"http://127.0.0.1:{PUERTO}"
HTTP = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def preparar(carpeta):
    from scripts.abadion_entrenamiento import Catalogo, construir_base
    from pos_auth import generar_hash

    carpeta = carpeta_segura(carpeta)
    with bloquear_entrenamiento(carpeta):
        if (carpeta / ARCHIVO).exists() or (carpeta / "instalacion.json").exists():
            raise ValueError("La instalación ya existe. Preparar nunca reinicia ni sobrescribe.")
        identidad = str(uuid4())
        usuarios = [("admin-preprod", "admin", secrets.token_urlsafe(24)),
                    ("ventas-preprod", "ventas", secrets.token_urlsafe(24))]
        # Empty catalogue: do not promote old prices, stocks, or fictional history.
        catalogo = Catalogo(aviso=MODO, productos=[dict(nombre="Sin catálogo aprobado", categoria="Comidas",
            precio_centavos=None, controla_stock=True, stock_inicial=0, sin_stock=True)], adicionales=[])
        with TemporaryDirectory(dir=carpeta, prefix="preparar-") as temporal:
            nueva = Path(temporal) / "nueva.db"
            construir_base(nueva, catalogo)
            with closing(sqlite3.connect(nueva)) as db, db:
                db.execute("DROP TABLE pos_entrenamiento")
                db.execute("DELETE FROM usuarios_pos")
                db.executemany("INSERT INTO usuarios_pos(usuario,rol,password_hash) VALUES (?,?,?)",
                               [(u, r, generar_hash(p)) for u, r, p in usuarios])
                db.execute("DELETE FROM pos_adicionales_producto")
                db.execute("DELETE FROM pos_catalogo_entrenamiento")
                db.execute("DELETE FROM productos")
                db.execute("CREATE TABLE pos_preproduccion(modo TEXT NOT NULL, instalacion TEXT NOT NULL)")
                db.execute("INSERT INTO pos_preproduccion VALUES (?,?)", (MODO, identidad))
                db.commit()
                integridad(db)
            datos = {"modo": MODO, "id": identidad, "carpeta": str(carpeta), "control": secrets.token_urlsafe(32)}
            with (carpeta / "credenciales.json").open("x", encoding="utf-8") as archivo:
                json.dump({u: p for u, _, p in usuarios}, archivo)
            with (carpeta / "instalacion.json").open("x", encoding="utf-8") as archivo:
                json.dump(datos, archivo)
            nueva.rename(carpeta / ARCHIVO)
        auditar(carpeta, "instalacion-creada", instalacion=identidad)
        respaldo(carpeta, "inicial")
    return carpeta / ARCHIVO


def crear_app(carpeta, detener=None, *, intervalo=3600):
    from fastapi import FastAPI, Request, HTTPException
    from fastapi.responses import HTMLResponse, RedirectResponse
    from starlette.middleware.trustedhost import TrustedHostMiddleware
    from database import RUTA_ENTRENAMIENTO, RUTA_PREPRODUCCION
    from pos_api import router
    from pos_entrenamiento_web import RUTA_POS, ESTILO

    datos = configuracion(carpeta)
    with closing(abrir_base(carpeta, datos["id"], lectura=True)) as db:
        integridad(db)
    pagina = RUTA_POS.read_text(encoding="utf-8").replace("<title>Abadion POS", "<title>PREPRODUCCIÓN Abadion", 1)
    pagina = pagina.replace("</head>", ESTILO + "</head>", 1).replace("<body>",
        '<body data-pedidos-sencillos="1"><p id="entrenamientoAviso">PREPRODUCCIÓN PERSISTENTE — DATOS FICTICIOS — SIN VALIDEZ CONTABLE</p>', 1)

    @asynccontextmanager
    async def vida(app):
        fin = asyncio.Event()

        async def periodico():
            while not fin.is_set():
                try:
                    await asyncio.wait_for(fin.wait(), timeout=intervalo)
                except TimeoutError:
                    try:
                        await asyncio.to_thread(respaldo, carpeta, "automatico")
                    except Exception as exc:
                        auditar(carpeta, "backup-fallido", error=type(exc).__name__)
        await asyncio.to_thread(respaldo, carpeta, "inicio")
        tarea = asyncio.create_task(periodico())
        auditar(carpeta, "servidor-iniciado")
        try:
            yield
        finally:
            fin.set()
            await tarea  # Wait for any running snapshot before releasing the process lock.
            await asyncio.to_thread(respaldo, carpeta, "detencion")
            auditar(carpeta, "servidor-detenido")

    app = FastAPI(title=MODO, docs_url=None, redoc_url=None, openapi_url=None, lifespan=vida)
    app.state.cookies_pos = ("abadion_preprod_admin", "abadion_preprod_ventas")
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1"])
    app.include_router(router)

    @app.middleware("http")
    async def contexto(request, call_next):
        uno = RUTA_ENTRENAMIENTO.set(carpeta / ARCHIVO)  # Existing fictional POS capability gates.
        dos = RUTA_PREPRODUCCION.set((carpeta, datos["id"]))
        try:
            respuesta = await call_next(request)
            respuesta.headers["X-Abadion-Modo"] = MODO
            return respuesta
        finally:
            RUTA_PREPRODUCCION.reset(dos)
            RUTA_ENTRENAMIENTO.reset(uno)

    @app.get("/")
    def inicio():
        return RedirectResponse("/pos/")

    @app.get("/pos/", response_class=HTMLResponse)
    @app.get("/pos/index.html", response_class=HTMLResponse)
    def pos():
        return HTMLResponse(pagina, headers={"Cache-Control": "no-store"})

    def autorizar(request):
        if not secrets.compare_digest(request.headers.get("Authorization", ""), "Bearer " + datos["control"]):
            raise HTTPException(403)

    @app.get("/_preprod/status")
    def estado(request: Request):
        autorizar(request)
        return {"modo": MODO, "id": datos["id"], "carpeta": str(carpeta)}

    @app.post("/_preprod/stop")
    def stop(request: Request):
        autorizar(request)
        if detener:
            detener()
        return {"id": datos["id"]}

    @app.post("/_preprod/backup")
    def backup(request: Request):
        autorizar(request)
        return {"archivo": respaldo(carpeta).name}

    return app


def consulta(carpeta, accion="status"):
    datos = configuracion(carpeta)
    req = urllib.request.Request(URL + "/_preprod/" + accion,
        headers={"Authorization": "Bearer " + datos["control"]}, method="GET" if accion == "status" else "POST")
    with HTTP.open(req, timeout=20) as respuesta:
        resultado = json.load(respuesta)
    if accion == "status" and resultado != {"modo": MODO, "id": datos["id"], "carpeta": str(carpeta)}:
        raise ValueError("El puerto pertenece a otra instalación.")
    return resultado


def ocupado():
    with socket.socket() as sock:
        return sock.connect_ex(("127.0.0.1", PUERTO)) == 0


def iniciar(carpeta, sin_edge=False):
    if ocupado():
        consulta(carpeta)  # Never reuse a foreign server.
    else:
        env = os.environ.copy()
        for nombre in tuple(env):
            if nombre.startswith(("ABADION_", "NEGOCIO_", "POS_")) or nombre in ("API_URL", "PYTHONPATH"):
                env.pop(nombre)
        env["PYTHON_DOTENV_DISABLED"] = "1"
        comprobar_archivo(carpeta / "servidor.log")
        with (carpeta / "servidor.log").open("a", encoding="utf-8") as log:
            hijo = subprocess.Popen([sys.executable, "-u", str(Path(__file__).resolve()), "--carpeta", str(carpeta), "worker"],
                env=env, cwd=ROOT, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        limite = time.monotonic() + 60
        while time.monotonic() < limite:
            if hijo.poll() is not None:
                raise RuntimeError("Falló el inicio. Revisá servidor.log; no se borraron datos.")
            try:
                consulta(carpeta)
                break
            except (OSError, ValueError):
                time.sleep(.2)
        else:
            raise RuntimeError("Inicio pendiente tras 60 segundos. Revisá estado/log antes de reintentar.")
    if not sin_edge:
        candidatos = [Path(os.getenv(k, "")) / "Microsoft/Edge/Application/msedge.exe"
                      for k in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA")]
        edge = next((p for p in candidatos if p.is_file()), None)
        if not edge:
            raise RuntimeError("Edge no está instalado. Servidor disponible en " + URL + "/pos/")
        subprocess.Popen([str(edge), "--user-data-dir=" + str(carpeta / "Edge"), URL + "/pos/"])
    print(MODO, URL + "/pos/", carpeta / ARCHIVO)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--carpeta", type=Path)
    parser.add_argument("accion", choices=["preparar", "iniciar", "detener", "estado", "backup", "restaurar", "worker",
                                           "validar-catalogo", "actualizar-catalogo"])
    parser.add_argument("--sin-edge", action="store_true")
    parser.add_argument("--archivo")
    parser.add_argument("--catalogo", type=Path)
    parser.add_argument("--sha256", help="Hash del JSON exacto revisado con validar-catalogo")
    parser.add_argument("--base-ausente", action="store_true", help="Recuperar sólo si no existe la base; requiere configuración y backup propios")
    args = parser.parse_args()
    try:
        carpeta = carpeta_segura(args.carpeta or Path(os.getenv("LOCALAPPDATA", str(Path.home()))) / "Abadion" / "Preproduccion")
        if args.accion == "preparar":
            print(preparar(carpeta))
        elif args.accion in ("validar-catalogo", "actualizar-catalogo"):
            if args.carpeta is None:
                raise ValueError("Para mantenimiento de catálogo indicá --carpeta explícita.")
            if not args.catalogo:
                raise ValueError("Indicá --catalogo con un JSON revisado.")
            if args.accion == "actualizar-catalogo" and not args.sha256:
                raise ValueError("Indicá --sha256 con la huella devuelta por validar-catalogo.")
            print(json.dumps(actualizar_catalogo(carpeta, args.catalogo,
                validar=args.accion == "validar-catalogo", sha256=args.sha256), ensure_ascii=False))
        elif args.accion == "worker":
            import uvicorn
            with bloquear_entrenamiento(carpeta):
                servidor = uvicorn.Server(uvicorn.Config(crear_app(carpeta, lambda: setattr(servidor, "should_exit", True)),
                    host="127.0.0.1", port=PUERTO, proxy_headers=False, access_log=False))
                servidor.run()
        elif args.accion == "iniciar":
            iniciar(carpeta, args.sin_edge)
        elif args.accion == "estado":
            print(consulta(carpeta))
        elif args.accion == "detener":
            if ocupado():
                consulta(carpeta)
                consulta(carpeta, "stop")
                limite = time.monotonic() + 45
                while ocupado() and time.monotonic() < limite:
                    time.sleep(.2)
                if ocupado():
                    raise RuntimeError("Cierre pendiente: revisá el log. No se forzó ningún proceso.")
            with bloquear_entrenamiento(carpeta):
                print("PREPRODUCCIÓN detenida. Datos conservados.")
        elif args.accion == "backup" and ocupado():
            consulta(carpeta)
            print(consulta(carpeta, "backup"))
        else:
            with bloquear_entrenamiento(carpeta):
                if args.accion == "backup":
                    print(respaldo(carpeta))
                elif args.accion == "restaurar":
                    if not args.archivo:
                        raise ValueError("Indicá --archivo con el nombre del backup verificado.")
                    restaurar(carpeta, args.archivo, base_ausente=args.base_ausente)
                    print("Restauración verificada. Volvé a iniciar sesión.")
    except (OSError, ValueError, RuntimeError, sqlite3.Error, KeyError) as error:
        parser.exit(1, str(error) + "\n")


if __name__ == "__main__":
    main()
