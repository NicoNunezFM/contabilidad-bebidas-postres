from database import obtener_conexion
from pos_auth import generar_hash, verificar_contrasena, autenticar_usuario
from pos_auth import crear_sesion_pos, obtener_usuario_sesion_pos, revocar_sesion_pos

def test_crear_tabla_usuarios_pos(base_prueba):
    conexion = obtener_conexion()

    try:
        usuarios = conexion.execute(
            "SELECT usuario, rol FROM usuarios_pos"
        ).fetchall()

        assert usuarios == []
    finally:
        conexion.close()

def test_contrasena_correcta():
    contrasena = "ClaveDePrueba123!"
    hash_guardado = generar_hash(contrasena)

    assert contrasena not in hash_guardado
    assert verificar_contrasena(contrasena, hash_guardado)


def test_contrasena_incorrecta():
    hash_guardado = generar_hash("ClaveDePrueba123!")

    assert not verificar_contrasena(
        "OtraClaveIncorrecta",
        hash_guardado
    )


def test_cada_contrasena_tiene_su_propia_sal():
    primer_hash = generar_hash("ClaveDePrueba123!")
    segundo_hash = generar_hash("ClaveDePrueba123!")

    assert primer_hash != segundo_hash


def test_hash_invalido():
    assert not verificar_contrasena("ClaveDePrueba123!", "hash_invalido")


def test_autenticacion_usuarios_pos(base_prueba):
    conexion = obtener_conexion()

    try:
        conexion.execute(
            """
            INSERT INTO usuarios_pos (usuario, rol, password_hash)
            VALUES (?, ?, ?)
            """,
            ("admin", "admin", generar_hash("AdminPrueba123!"))
        )

        conexion.execute(
            """
            INSERT INTO usuarios_pos (usuario, rol, password_hash)
            VALUES (?, ?, ?)
            """,
            ("ventas", "ventas", generar_hash("VentasPrueba123!"))
        )

        conexion.commit()
    finally:
        conexion.close()

    administrador = autenticar_usuario("admin", "AdminPrueba123!")
    operador = autenticar_usuario("ventas", "VentasPrueba123!")

    assert administrador["rol"] == "admin"
    assert operador["rol"] == "ventas"

    assert autenticar_usuario("admin", "ClaveIncorrecta") is None
    assert autenticar_usuario("ventas", "AdminPrueba123!") is None
    assert autenticar_usuario("inexistente", "AdminPrueba123!") is None

    conexion = obtener_conexion()
    try:
        conexion.execute(
            "UPDATE usuarios_pos SET activo = 0 WHERE usuario = ?",
            ("ventas",)
        )
        conexion.commit()
    finally:
        conexion.close()

    assert autenticar_usuario("ventas", "VentasPrueba123!") is None


def test_crear_tabla_sesiones_pos(base_prueba):
    conexion = obtener_conexion()

    try:
        resultado = conexion.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name = 'sesiones_pos'
            """
        ).fetchone()

        assert resultado is not None

        sesiones = conexion.execute(
            "SELECT * FROM sesiones_pos"
        ).fetchall()

        assert sesiones == []

    finally:
        conexion.close()


def test_ciclo_de_sesion_pos(base_prueba):
    conexion = obtener_conexion()

    try:
        cursor = conexion.execute(
            """
            INSERT INTO usuarios_pos
                (usuario, rol, password_hash)
            VALUES (?, ?, ?)
            """,
            ("ventas", "ventas", generar_hash("VentasPrueba123!"))
        )

        id_usuario = cursor.lastrowid
        conexion.commit()
    finally:
        conexion.close()

    # Crear sesión
    token = crear_sesion_pos(id_usuario)

    assert isinstance(token, str)
    assert len(token) > 20

    # Verificar sesión
    usuario = obtener_usuario_sesion_pos(token)

    assert usuario["usuario"] == "ventas"
    assert usuario["rol"] == "ventas"

    # Un token inventado no funciona
    assert obtener_usuario_sesion_pos("token_invalido") is None

    # Cerrar sesión
    assert revocar_sesion_pos(token) is True

    # La sesión cerrada ya no permite acceder
    assert obtener_usuario_sesion_pos(token) is None
    assert revocar_sesion_pos(token) is False


