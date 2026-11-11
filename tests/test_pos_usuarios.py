from database import obtener_conexion
from pos_auth import generar_hash, verificar_contrasena

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

