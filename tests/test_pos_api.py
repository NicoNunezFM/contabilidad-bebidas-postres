
from fastapi.testclient import TestClient

from api import app
from database import obtener_conexion
from pos_auth import generar_hash


def test_login_y_cierre_de_sesiones(base_prueba):
    conexion = obtener_conexion()

    try:
        for usuario, rol, clave in (
            ("admin", "admin", "AdminPrueba123!"),
            ("ventas", "ventas", "VentasPrueba123!"),
        ):
            conexion.execute(
                """
                INSERT INTO usuarios_pos (usuario, rol, password_hash)
                VALUES (?, ?, ?)
                """,
                (usuario, rol, generar_hash(clave))
            )

        conexion.commit()
    finally:
        conexion.close()

    cliente = TestClient(app)
    encabezados = {"Origin": "http://testserver"}

    # Sin sesión, el acceso debe rechazarse.
    assert cliente.get("/pos-api/yo").status_code == 401

    # Iniciar sesión de ventas.
    respuesta = cliente.post(
        "/pos-api/login",
        json={
            "usuario": "ventas",
            "contrasena": "VentasPrueba123!"
        },
        headers=encabezados
    )

    assert respuesta.status_code == 200
    assert cliente.get("/pos-api/yo").json()["usuario"]["rol"] == "ventas"

    # Abrir administración sin perder la sesión de ventas.
    respuesta = cliente.post(
        "/pos-api/login",
        json={
            "usuario": "admin",
            "contrasena": "AdminPrueba123!"
        },
        headers=encabezados
    )

    assert respuesta.status_code == 200
    assert cliente.get("/pos-api/yo").json()["usuario"]["rol"] == "admin"

    # Cerrar administración: vuelve a ventas.
    respuesta = cliente.post(
        "/pos-api/logout",
        headers=encabezados
    )

    assert respuesta.status_code == 200
    assert cliente.get("/pos-api/yo").json()["usuario"]["rol"] == "ventas"

    # Cerrar ventas: ya no hay acceso.
    cliente.post("/pos-api/logout", headers=encabezados)
    assert cliente.get("/pos-api/yo").status_code == 401
