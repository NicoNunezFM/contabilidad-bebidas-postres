
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from pos_auth import (
    autenticar_usuario,
    crear_sesion_pos,
    obtener_usuario_sesion_pos,
    revocar_sesion_pos,
)


router = APIRouter(prefix="/pos-api", tags=["POS - Sesiones"])

COOKIE_ADMIN = "abadion_pos_admin"
COOKIE_VENTAS = "abadion_pos_ventas"


class LoginEntrada(BaseModel):
    usuario: str = Field(min_length=1, max_length=40)
    contrasena: str = Field(min_length=1, max_length=256)


def comprobar_origen(request: Request):
    origen = request.headers.get("origin")
    esperado = f"{request.url.scheme}://{request.url.netloc}"

    if origen != esperado:
        raise HTTPException(
            status_code=403,
            detail="Origen no permitido."
        )


@router.post("/login")
def iniciar_sesion(
    datos: LoginEntrada,
    request: Request,
    response: Response,
):
    comprobar_origen(request)

    usuario = autenticar_usuario(
        datos.usuario,
        datos.contrasena
    )

    if usuario is None:
        raise HTTPException(
            status_code=401,
            detail="Usuario o contraseña incorrectos."
        )

    token = crear_sesion_pos(usuario["id_usuario"])

    es_admin = usuario["rol"] == "admin"
    nombre_cookie = COOKIE_ADMIN if es_admin else COOKIE_VENTAS
    duracion = 8 * 3600 if es_admin else 30 * 24 * 3600

    response.set_cookie(
        key=nombre_cookie,
        value=token,
        max_age=duracion,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="strict",
        path="/pos-api",
    )

    return {
        "ok": True,
        "usuario": usuario["usuario"],
        "rol": usuario["rol"]
    }


@router.get("/yo")
def usuario_actual(request: Request):
    for nombre_cookie, rol in (
        (COOKIE_ADMIN, "admin"),
        (COOKIE_VENTAS, "ventas"),
    ):
        token = request.cookies.get(nombre_cookie)

        if not token:
            continue

        usuario = obtener_usuario_sesion_pos(token)

        if usuario is not None and usuario["rol"] == rol:
            return {"ok": True, "usuario": usuario}

    raise HTTPException(
        status_code=401,
        detail="No hay una sesión válida."
    )


@router.post("/logout")
def cerrar_sesion(request: Request, response: Response):
    comprobar_origen(request)

    for nombre_cookie in (COOKIE_ADMIN, COOKIE_VENTAS):
        token = request.cookies.get(nombre_cookie)

        if token:
            revocar_sesion_pos(token)
            response.delete_cookie(
                key=nombre_cookie,
                path="/pos-api",
                samesite="strict",
            )

            return {"ok": True, "mensaje": "Sesión cerrada."}

    return {"ok": True, "mensaje": "No había una sesión abierta."}
