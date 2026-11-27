import base64
import hashlib
import hmac
import secrets
import binascii

from datetime import datetime, timedelta, timezone
from database import obtener_conexion


ITERACIONES = 600_000


def generar_hash(contrasena: str) -> str:
    if not isinstance(contrasena, str) or not 12 <= len(contrasena) <= 256:
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

    except (ValueError, TypeError, binascii.Error, UnicodeError):
        return False


def _leer_usuario(usuario):
    conexion = obtener_conexion()
    try:
        return conexion.execute(
            "SELECT id_usuario,usuario,rol,password_hash,activo FROM usuarios_pos WHERE usuario=? AND activo=1",
            (usuario.strip(),)).fetchone()
    finally:
        conexion.close()


# Sal y hash ficticios para igualar el trabajo de verificación ante usuario inexistente.
_HASH_FICTICIO = "pbkdf2_sha256$600000$AAAAAAAAAAAAAAAAAAAAAA==$AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="


def autenticar_usuario(usuario: str, contrasena: str) -> dict | None:
    if not isinstance(usuario,str) or not isinstance(contrasena,str) or len(contrasena)>256:
        return None
    fila=_leer_usuario(usuario)
    valido=verificar_contrasena(contrasena,fila[3] if fila else _HASH_FICTICIO)
    if fila is None or not valido or fila[2] not in ('admin','ventas'):
        return None
    return {'id_usuario':fila[0],'usuario':fila[1],'rol':fila[2]}


def autenticar_y_crear_sesion(usuario,contrasena):
    if not isinstance(usuario,str) or not isinstance(contrasena,str) or len(contrasena)>256:
        return None
    fila=_leer_usuario(usuario)
    valido=verificar_contrasena(contrasena,fila[3] if fila else _HASH_FICTICIO)
    if fila is None or not valido or fila[2] not in ('admin','ventas'):
        return None
    from pos_seguridad import huella_usuario
    try:
        token=crear_sesion_pos(fila[0],_huella_esperada=huella_usuario(fila))
    except ValueError:
        return None
    return {'id_usuario':fila[0],'usuario':fila[1],'rol':fila[2]},token


def _duracion(rol):
    if rol=='admin':
        return timedelta(hours=8)
    if rol=='ventas':
        return timedelta(days=30)
    raise ValueError('Rol no permitido.')


def crear_sesion_pos(id_usuario: int, *, _huella_esperada=None) -> str:
    """Llamador interno de confianza; el login verifica la clave y su estado de emisión."""
    from pos_seguridad import preparar_esquema,huella_usuario,guardar_evento
    conexion=obtener_conexion()
    try:
        with conexion:
            conexion.execute('BEGIN IMMEDIATE')
            preparar_esquema(conexion)
            fila=conexion.execute('SELECT id_usuario,usuario,rol,password_hash,activo FROM usuarios_pos WHERE id_usuario=? AND activo=1',(id_usuario,)).fetchone()
            if fila is None:
                raise ValueError('Usuario inexistente o inactivo.')
            huella=huella_usuario(fila)
            if _huella_esperada is not None and not hmac.compare_digest(huella,_huella_esperada):
                raise ValueError('Cambió el estado de autenticación.')
            ahora=datetime.now(timezone.utc)
            vencimiento=(ahora+_duracion(fila[2])).isoformat()
            token=secrets.token_urlsafe(32)
            token_hash=hashlib.sha256(token.encode()).hexdigest()
            cursor=conexion.execute('INSERT INTO sesiones_pos(id_usuario,token_hash,creada_en,expira_en) VALUES(?,?,?,?)',
                                   (id_usuario,token_hash,ahora.isoformat(),vencimiento))
            if cursor.rowcount!=1:
                raise ValueError('No se guardó la sesión.')
            cursor=conexion.execute('INSERT INTO sesiones_pos_contexto VALUES(?,?)',(token_hash,huella))
            if cursor.rowcount!=1:
                raise ValueError('No se guardó el estado de la sesión.')
            guardar_evento(conexion,'sesion_emitida',id_usuario)
        return token
    finally:
        conexion.close()


def leer_sesion_en_db(conexion, token_hash):
    from pos_seguridad import huella_usuario
    if not conexion.execute("SELECT 1 FROM sqlite_schema WHERE name='sesiones_pos_contexto'").fetchone():
        return None  # Sesión anterior sin vínculo de emisión: exigir login, nunca reconstruir.
    fila=conexion.execute("""SELECT u.id_usuario,u.usuario,u.rol,u.password_hash,u.activo,
        s.creada_en,s.expira_en,c.huella FROM sesiones_pos s
        JOIN usuarios_pos u USING(id_usuario) JOIN sesiones_pos_contexto c USING(token_hash)
        WHERE s.token_hash=? AND s.revocada=0 AND u.activo=1""",(token_hash,)).fetchone()
    if fila is None or not isinstance(fila[7],str) or not hmac.compare_digest(huella_usuario(fila[:5]),fila[7]):
        return None
    try:
        creada=datetime.fromisoformat(fila[5])
        if creada.tzinfo is None:
            creada=creada.replace(tzinfo=timezone.utc)  # Formato SQLite histórico UTC.
        expira=datetime.fromisoformat(fila[6])
        ahora=datetime.now(timezone.utc)
        if (expira.utcoffset() is None or creada>ahora+timedelta(seconds=1)
                or not ahora<expira<=creada+_duracion(fila[2])+timedelta(seconds=1)):
            return None
    except (ValueError,TypeError,OverflowError):
        return None
    return {'id_usuario':fila[0],'usuario':fila[1],'rol':fila[2]}


def _hash_token(token):
    if not isinstance(token,str) or not token or len(token)>256:
        return None
    try:
        return hashlib.sha256(token.encode('utf-8')).hexdigest()
    except UnicodeError:
        return None


def obtener_usuario_sesion_pos(token: str) -> dict | None:
    token_hash=_hash_token(token)
    if token_hash is None:
        return None
    conexion=obtener_conexion()
    try:
        return leer_sesion_en_db(conexion,token_hash)
    finally:
        conexion.close()


def revocar_sesion_pos(token: str) -> bool:
    token_hash=_hash_token(token)
    if token_hash is None:
        return False
    from pos_seguridad import guardar_evento,preparar_esquema
    conexion=obtener_conexion()
    try:
        with conexion:
            conexion.execute('BEGIN IMMEDIATE')
            preparar_esquema(conexion)
            fila=conexion.execute('SELECT id_usuario FROM sesiones_pos WHERE token_hash=? AND revocada=0',(token_hash,)).fetchone()
            cursor=conexion.execute('UPDATE sesiones_pos SET revocada=1 WHERE token_hash=? AND revocada=0',(token_hash,))
            if cursor.rowcount and fila:
                guardar_evento(conexion,'sesion_revocada',fila[0])
        return cursor.rowcount==1
    finally:
        conexion.close()
