import hmac
import os
import re

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer


bearer = HTTPBearer(auto_error=False)
FORMATO_CLAVE = re.compile(r"[A-Za-z0-9_-]{43,128}")


def _exigir_credencial(credencial, *, admite_bot=False):
    interna = os.getenv("ABADION_API_TOKEN", "")
    bot = os.getenv("ABADION_BOT_TOKEN", "")
    token = credencial.credentials if credencial else ""
    if FORMATO_CLAVE.fullmatch(token) and interna != bot:
        claves = (interna, bot) if admite_bot else (interna,)
        for clave in claves:
            if FORMATO_CLAVE.fullmatch(clave) and hmac.compare_digest(token, clave):
                return
    raise HTTPException(
        status_code=401,
        detail="Se requiere una credencial de API válida.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def exigir_integracion(credencial: HTTPAuthorizationCredentials | None = Depends(bearer)):
    _exigir_credencial(credencial)


def exigir_comandos(credencial: HTTPAuthorizationCredentials | None = Depends(bearer)):
    _exigir_credencial(credencial, admite_bot=True)
