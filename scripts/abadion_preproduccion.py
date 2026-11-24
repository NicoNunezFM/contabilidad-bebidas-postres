"""POS persistente de preproducción, sin comandos WhatsApp ni acceso de red."""
import argparse
import asyncio
from contextlib import asynccontextmanager, closing
from getpass import getpass
import logging
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware
from database import RUTA_ENTRENAMIENTO
from pos_api import router
from pos_entrenamiento_web import ESTILO, RUTA_POS
from pos_preproduccion import (
    ARCHIVO, abrir_base, actualizar_catalogo, carpeta_local, carpeta_segura,
    mantenimiento, preparar, respaldo, restaurar,
)

logger = logging.getLogger("uvicorn.error")


def crear_app(carpeta, intervalo=3600):
    with closing(abrir_base(carpeta, lectura=True)):
        pass

    @asynccontextmanager
    async def vida(app):
        # Las operaciones periódicas y finales se serializan en la misma tarea.
        await asyncio.to_thread(respaldo, carpeta)
        detener = asyncio.Event()

        async def copias():
            while not detener.is_set():
                try:
                    await asyncio.wait_for(detener.wait(), timeout=intervalo)
                except TimeoutError:
                    try:
                        await asyncio.to_thread(respaldo, carpeta)
                    except Exception:
                        logger.exception("FALLÓ EL RESPALDO DE PREPRODUCCIÓN")

        tarea = asyncio.create_task(copias())
        try:
            yield
        finally:
            detener.set()
            await tarea
            await asyncio.to_thread(respaldo, carpeta)

    app = FastAPI(title="Abadion Preproducción", lifespan=vida, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.cookies_pos = ("abadion_preproduccion_admin", "abadion_preproduccion_ventas")
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1"])
    app.include_router(router)

    @app.middleware("http")
    async def base_local(request, call_next):
        token = RUTA_ENTRENAMIENTO.set(carpeta / ARCHIVO)
        try:
            return await call_next(request)
        finally:
            RUTA_ENTRENAMIENTO.reset(token)

    pagina = RUTA_POS.read_text(encoding="utf-8").replace("</head>", ESTILO + "</head>", 1).replace(
        "<body>", '<body><p id="entrenamientoAviso">PREPRODUCCIÓN PERSISTENTE — SOLO ENSAYOS</p>', 1)

    @app.get("/")
    def inicio():
        return RedirectResponse("/pos/")

    @app.get("/pos/", response_class=HTMLResponse)
    @app.get("/pos/index.html", response_class=HTMLResponse)
    def pos():
        return HTMLResponse(pagina, headers={"Cache-Control": "no-store"})

    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--carpeta", type=Path)
    comandos = parser.add_subparsers(dest="comando", required=True)
    alta = comandos.add_parser("preparar")
    alta.add_argument("--catalogo", type=Path, required=True)
    comandos.add_parser("servir")
    comandos.add_parser("respaldar")
    recuperar = comandos.add_parser("restaurar")
    recuperar.add_argument("--respaldo", type=Path, required=True)
    recuperar.add_argument("--confirmar", choices=["RESTAURAR PREPRODUCCION"], required=True)
    catalogo = comandos.add_parser("actualizar-catalogo")
    catalogo.add_argument("--catalogo", type=Path, required=True)
    args = parser.parse_args()
    try:
        carpeta = carpeta_segura(args.carpeta) if args.carpeta else carpeta_local()
        if args.comando == "preparar":
            admin = getpass("Contraseña nueva para admin-preproduccion: ")
            ventas = getpass("Contraseña nueva para ventas-preproduccion: ")
            print(preparar(carpeta, args.catalogo.resolve(), admin, ventas))
        elif args.comando == "servir":
            with mantenimiento(carpeta):
                uvicorn.run(crear_app(carpeta), host="127.0.0.1", port=8077, proxy_headers=False)
        elif args.comando == "respaldar":
            with mantenimiento(carpeta):
                print(respaldo(carpeta))
        elif args.comando == "restaurar":
            print("Restaurada. Copia anterior conservada en:", restaurar(carpeta, args.respaldo.resolve()))
        else:
            print("Catálogo aplicado. Copia previa:", actualizar_catalogo(carpeta, args.catalogo.resolve()))
    except Exception as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
