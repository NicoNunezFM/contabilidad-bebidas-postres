import base64
import hashlib
import hmac
import secrets
import binascii

from datetime import datetime, timedelta, timezone
from database import obtener_conexion


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


def autenticar_usuario(usuario: str, contrasena: str) -> dict | None:
    if not isinstance(usuario, str) or not isinstance(contrasena, str):
        return None

    conexion = obtener_conexion()

    try:
        fila = conexion.execute(
            """
            SELECT id_usuario, usuario, rol, password_hash
            FROM usuarios_pos
            WHERE usuario = ? AND activo = 1
            """,
            (usuario.strip(),)
        ).fetchone()
    finally:
        conexion.close()

    if fila is None:
        return None

    if not verificar_contrasena(contrasena, fila[3]):
        return None

    return {
        "id_usuario": fila[0],
        "usuario": fila[1],
        "rol": fila[2]
    }


def crear_sesion_pos(id_usuario: int) -> str:
    """
    Crea una sesión para un usuario activo.
    Debe llamarse después de autenticar su contraseña.
    """
    conexion = obtener_conexion()

    try:
        fila = conexion.execute(
            """
            SELECT rol
            FROM usuarios_pos
            WHERE id_usuario = ? AND activo = 1
            """,
            (id_usuario,)
        ).fetchone()

        if fila is None:
            raise ValueError("Usuario inexistente o inactivo.")

        rol = fila[0]

        if rol == "admin":
            duracion = timedelta(hours=8)
        elif rol == "ventas":
            duracion = timedelta(days=30)
        else:
            raise ValueError("Rol no permitido.")

        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(
            token.encode("utf-8")
        ).hexdigest()

        vencimiento = (
            datetime.now(timezone.utc) + duracion
        ).isoformat()

        conexion.execute(
            """
            INSERT INTO sesiones_pos
                (id_usuario, token_hash, expira_en)
            VALUES (?, ?, ?)
            """,
            (id_usuario, token_hash, vencimiento)
        )

        conexion.commit()
        return token

    finally:
        conexion.close()


def obtener_usuario_sesion_pos(token: str) -> dict | None:
    """
    Verifica que la sesión exista, esté activa
    y no haya vencido.
    """
    if not isinstance(token, str) or not token or len(token) > 256:
        return None

    token_hash = hashlib.sha256(
        token.encode("utf-8")
    ).hexdigest()

    ahora = datetime.now(timezone.utc).isoformat()

    conexion = obtener_conexion()

    try:
        fila = conexion.execute(
            """
            SELECT u.id_usuario, u.usuario, u.rol
            FROM sesiones_pos AS s
            JOIN usuarios_pos AS u
                ON u.id_usuario = s.id_usuario
            WHERE s.token_hash = ?
              AND s.revocada = 0
              AND s.expira_en > ?
              AND u.activo = 1
            """,
            (token_hash, ahora)
        ).fetchone()
    finally:
        conexion.close()

    if fila is None:
        return None

    return {
        "id_usuario": fila[0],
        "usuario": fila[1],
        "rol": fila[2]
    }


def revocar_sesion_pos(token: str) -> bool:
    """
    Invalida una sesión, por ejemplo al cerrar sesión.
    """
    if not isinstance(token, str) or not token or len(token) > 256:
        return False

    token_hash = hashlib.sha256(
        token.encode("utf-8")
    ).hexdigest()

    conexion = obtener_conexion()

    try:
        cursor = conexion.execute(
            """
            UPDATE sesiones_pos
            SET revocada = 1
            WHERE token_hash = ?
              AND revocada = 0
            """,
            (token_hash,)
        )

        conexion.commit()
        return cursor.rowcount == 1

    finally:
        conexion.close()
