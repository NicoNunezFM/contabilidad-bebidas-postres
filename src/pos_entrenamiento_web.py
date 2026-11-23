from contextlib import closing
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from database import RUTA_ENTRENAMIENTO
from pos_api import router
from pos_entrenamiento_db import ARCHIVO_BASE, abrir_base_entrenamiento


AVISO = "MODO ENTRENAMIENTO - SIN VALIDEZ CONTABLE"
RUTA_POS = Path(__file__).resolve().parents[1] / "pos-web" / "index.html"
ESTILO = """
<style>
#entrenamientoAviso {position:fixed; inset:0 0 auto; z-index:10000; min-height:3rem;
  display:grid; place-items:center; text-align:center; padding:.35rem .75rem;
  margin:0; background:#8a240d; color:white; font-size:clamp(.78rem, 2.6vw, 1rem); font-weight:800}
body {padding-top:3rem}
#simulationBanner {display:none}
#overlay {top:3rem}
#overlay .dialog {max-height:calc(100vh - 4.5rem)}
@media (min-width:1101px) {
  .sidebar {top:3rem; height:calc(100vh - 3rem)}
  .order {top:calc(3rem + 12px)}
}
@media print {#entrenamientoAviso {position:static; background:white; color:black}}
</style>
"""


def crear_app_entrenamiento(carpeta, *, hosts_permitidos=("127.0.0.1",), aviso=AVISO):
    ruta = carpeta / ARCHIVO_BASE
    with closing(abrir_base_entrenamiento(ruta, solo_lectura=True)):
        pass
    fuente = RUTA_POS.read_text(encoding="utf-8")
    if fuente.count("<body>") != 1 or fuente.count("</head>") != 1:
        raise ValueError("No se pudo incorporar el aviso de entrenamiento al POS.")
    pagina = fuente.replace("<title>Abadion POS", "<title>Abadion Entrenamiento", 1)
    pagina = pagina.replace("</head>", ESTILO + "</head>", 1).replace(
        "<body>", f'<body><p id="entrenamientoAviso">{aviso}</p>', 1
    )
    app = FastAPI(title="Abadion Entrenamiento", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.cookies_pos = ("abadion_entrenamiento_admin", "abadion_entrenamiento_ventas")
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(hosts_permitidos))
    app.include_router(router)

    @app.middleware("http")
    async def usar_base_entrenamiento(request, call_next):
        contexto = RUTA_ENTRENAMIENTO.set(ruta)
        try:
            return await call_next(request)
        finally:
            RUTA_ENTRENAMIENTO.reset(contexto)

    @app.get("/")
    def inicio():
        return RedirectResponse("/pos/")

    @app.get("/pos/", response_class=HTMLResponse)
    @app.get("/pos/index.html", response_class=HTMLResponse)
    def pos():
        return HTMLResponse(pagina, headers={"Cache-Control": "no-store"})

    return app
