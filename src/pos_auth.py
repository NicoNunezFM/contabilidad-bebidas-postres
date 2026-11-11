
import base64
import hashlib
import hmac
import secrets
import binascii


ITERACIONES = 600_000


def generar_hash(contrasena: str) -> str:
    if not isinstance(contrasena, str) or len(contrasena) < 12:
        raise ValueError("La contraseña debe tener al menos 12 caracteres.")

    sal = secrets.token_bytes(16)

    resultado = hashlib.pbkdf2_hmac(
        "sha256",
        contrasena.encode("utf-8"),
        sal,
        ITERACIONES
    )

    sal_texto = base64.b64encode(sal).decode("ascii")
    hash_texto = base64.b64encode(resultado).decode("ascii")

    return f"pbkdf2_sha256${ITERACIONES}${sal_texto}${hash_texto}"


def verificar_contrasena(contrasena: str, hash_guardado: str) -> bool:
    if not isinstance(contrasena, str) or not isinstance(hash_guardado, str):
        return False

    try:
        algoritmo, iteraciones, sal_texto, hash_texto = hash_guardado.split("$")

        if algoritmo != "pbkdf2_sha256":
            return False

        if int(iteraciones) != ITERACIONES:
            return False

        sal = base64.b64decode(sal_texto, validate=True)
        hash_original = base64.b64decode(hash_texto, validate=True)

        if len(sal) != 16 or len(hash_original) != 32:
            return False

        resultado = hashlib.pbkdf2_hmac(
            "sha256",
            contrasena.encode("utf-8"),
            sal,
            ITERACIONES
        )

        return hmac.compare_digest(resultado, hash_original)

    except (ValueError, TypeError, binascii.Error):
        return False
