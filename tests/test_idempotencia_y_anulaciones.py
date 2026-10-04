from fastapi.testclient import TestClient

from api import app
from database import obtener_conexion


client = TestClient(app)


def crear_producto(
    nombre,
    precio,
    stock,
    controla_stock=True,
    categoria="Bebidas",
):
    conexion = obtener_conexion()

    cursor = conexion.execute(
        """
        INSERT INTO productos (
            nombre,
            categoria,
            presentacion,
            contenido,
            unidad_medida,
            unidades_por_pack,
            stock,
            precio_venta,
            controla_stock
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            nombre,
            categoria,
            "Unidad",
            1,
            "unidad",
            1,
            stock,
            precio,
            int(controla_stock),
        )
    )

    id_producto = cursor.lastrowid

    conexion.commit()
    conexion.close()

    return id_producto


def obtener_stock(id_producto):
    conexion = obtener_conexion()

    stock = conexion.execute(
        """
        SELECT stock
        FROM productos
        WHERE id_producto = ?
        """,
        (id_producto,)
    ).fetchone()[0]

    conexion.close()

    return stock


def test_comando_whatsapp_duplicado_no_registra_dos_ventas(
    base_prueba
):
    id_pepsi = crear_producto(
        nombre="Pepsi lata",
        precio=1600,
        stock=5,
    )

    cuerpo = {
        "mensaje": "venta 2 pepsi",
        "id_mensaje": "wamid-prueba-001",
        "canal": "whatsapp",
    }

    primera = client.post(
        "/comandos",
        json=cuerpo,
    )

    segunda = client.post(
        "/comandos",
        json=cuerpo,
    )

    assert primera.status_code == 200
    assert segunda.status_code == 200

    primera_json = primera.json()
    segunda_json = segunda.json()

    assert primera_json["ok"] is True
    assert segunda_json["ok"] is True
    assert segunda_json["repetido"] is True

    assert (
        primera_json["id_operacion"]
        == segunda_json["id_operacion"]
    )

    assert obtener_stock(id_pepsi) == 3

    conexion = obtener_conexion()

    cantidad_ventas = conexion.execute(
        """
        SELECT COUNT(*)
        FROM ventas
        WHERE anulada = 0
        """
    ).fetchone()[0]

    mensajes = conexion.execute(
        """
        SELECT COUNT(*)
        FROM mensajes_procesados
        WHERE canal = ?
          AND id_externo = ?
        """,
        (
            "whatsapp",
            "wamid-prueba-001",
        )
    ).fetchone()[0]

    conexion.close()

    assert cantidad_ventas == 1
    assert mensajes == 1


def test_anular_ultima_venta_restaura_todo_el_stock(
    base_prueba
):
    id_pepsi = crear_producto(
        nombre="Pepsi lata",
        precio=1600,
        stock=5,
    )

    id_oreo = crear_producto(
        nombre="Oreo",
        precio=4500,
        stock=3,
        categoria="Postres",
    )

    id_bigmac = crear_producto(
        nombre="Big mac doble",
        precio=9000,
        stock=0,
        controla_stock=False,
        categoria="Hamburguesas",
    )

    venta = client.post(
        "/comandos",
        json={
            "mensaje": (
                "venta 2 pepsi, 1 oreo "
                "y 1 bigmac doble"
            ),
            "id_mensaje": "wamid-venta-002",
            "canal": "whatsapp",
        },
    )

    assert venta.status_code == 200

    venta_json = venta.json()
    id_operacion = venta_json["id_operacion"]

    assert obtener_stock(id_pepsi) == 3
    assert obtener_stock(id_oreo) == 2
    assert obtener_stock(id_bigmac) == 0

    anulacion = client.post(
        "/comandos",
        json={
            "mensaje": "anular ultima venta",
            "id_mensaje": "wamid-anulacion-003",
            "canal": "whatsapp",
        },
    )

    assert anulacion.status_code == 200

    datos = anulacion.json()

    assert datos["ok"] is True
    assert datos["codigo"] == "ACCION_ULTIMA_VENTA_ANULADA"
    assert datos["id_operacion"] == id_operacion
    assert datos["total_anulado"] == 16700

    assert obtener_stock(id_pepsi) == 5
    assert obtener_stock(id_oreo) == 3
    assert obtener_stock(id_bigmac) == 0

    conexion = obtener_conexion()

    operacion = conexion.execute(
        """
        SELECT anulada
        FROM ventas_operaciones
        WHERE id_operacion = ?
        """,
        (id_operacion,)
    ).fetchone()[0]

    lineas_activas = conexion.execute(
        """
        SELECT COUNT(*)
        FROM ventas
        WHERE id_operacion = ?
          AND anulada = 0
        """,
        (id_operacion,)
    ).fetchone()[0]

    conexion.close()

    assert operacion == 1
    assert lineas_activas == 0


def test_anular_operacion_especifica(
    base_prueba
):
    id_pepsi = crear_producto(
        nombre="Pepsi lata",
        precio=1600,
        stock=5,
    )

    venta = client.post(
        "/comandos",
        json={
            "mensaje": "venta 1 pepsi",
        },
    )

    assert venta.status_code == 200

    id_operacion = venta.json()["id_operacion"]

    anulacion = client.post(
        "/comandos",
        json={
            "mensaje": (
                f"anular operacion {id_operacion}"
            ),
        },
    )

    assert anulacion.status_code == 200

    datos = anulacion.json()

    assert datos["ok"] is True
    assert datos["codigo"] == "ACCION_OPERACION_VENTA_ANULADA"
    assert datos["id_operacion"] == id_operacion
    assert obtener_stock(id_pepsi) == 5


def test_anulacion_duplicada_por_mismo_mensaje_no_restaura_dos_veces(
    base_prueba
):
    id_pepsi = crear_producto(
        nombre="Pepsi lata",
        precio=1600,
        stock=5,
    )

    venta = client.post(
        "/comandos",
        json={
            "mensaje": "venta 2 pepsi",
            "id_mensaje": "wamid-venta-004",
            "canal": "whatsapp",
        },
    )

    assert venta.status_code == 200
    assert obtener_stock(id_pepsi) == 3

    cuerpo_anulacion = {
        "mensaje": "anular ultima venta",
        "id_mensaje": "wamid-anulacion-005",
        "canal": "whatsapp",
    }

    primera = client.post(
        "/comandos",
        json=cuerpo_anulacion,
    )

    segunda = client.post(
        "/comandos",
        json=cuerpo_anulacion,
    )

    assert primera.status_code == 200
    assert segunda.status_code == 200
    assert segunda.json()["repetido"] is True
    assert obtener_stock(id_pepsi) == 5
