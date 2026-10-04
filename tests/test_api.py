from fastapi.testclient import TestClient

from api import app

from fastapi.responses import JSONResponse


client = TestClient(app)

def responder_resultado(
    resultado,
    codigo_exito=200,
    codigo_error=400
):

    if resultado.get("ok") is False:

        return JSONResponse(
            status_code=codigo_error,
            content=resultado
        )

    return JSONResponse(
        status_code=codigo_exito,
        content=resultado
    )

def test_api_rechaza_venta_sin_stock_codigo(
    producto_prueba
):

    respuesta = client.post(
        "/ventas",
        json={
            "id_producto": producto_prueba,
            "cantidad": 20,
            "precio_unitario": 3000
        }
    )

    assert respuesta.status_code == 409

    datos = respuesta.json()

    assert datos["ok"] is False
    assert datos["codigo"] == "STOCK_INSUFICIENTE"

def test_api_venta_producto_inexistente(
    base_prueba
):

    respuesta = client.post(
        "/ventas",
        json={
            "id_producto": 9999,
            "cantidad": 1,
            "precio_unitario": 3000
        }
    )

    assert respuesta.status_code == 404

    datos = respuesta.json()

    assert datos["ok"] is False
    assert datos["codigo"] == "PRODUCTO_NO_ENCONTRADO"
    
def test_api_venta_descuenta_stock_y_anulacion_lo_devuelve(
    producto_prueba
):

    respuesta_venta = client.post(
        "/ventas",
        json={
            "id_producto": producto_prueba,
            "cantidad": 2,
            "precio_unitario": 3000
        }
    )

    assert respuesta_venta.status_code == 201

    venta = respuesta_venta.json()

    assert venta["ok"] is True

    id_venta = venta["id_venta"]

    # Verificamos que la API muestre stock 8.
    respuesta_stock = client.get("/stock")

    stock = respuesta_stock.json()["stock"][0]["stock"]

    assert stock == 8

    # Anulamos la venta por API.
    respuesta_anulacion = client.patch(
        f"/ventas/{id_venta}/anular",
        json={
            "motivo": "Prueba automática API"
        }
    )

    assert respuesta_anulacion.status_code == 200

    anulacion = respuesta_anulacion.json()

    assert anulacion["ok"] is True

    # El stock debe volver a 10.
    respuesta_stock_final = client.get("/stock")

    stock_final = (
        respuesta_stock_final
        .json()["stock"][0]["stock"]
    )

    assert stock_final == 10

def test_api_rechaza_venta_con_cantidad_cero(
    producto_prueba
):

    respuesta = client.post(
        "/ventas",
        json={
            "id_producto": producto_prueba,
            "cantidad": 0,
            "precio_unitario": 3000
        }
    )

    assert respuesta.status_code == 422

def test_api_rechaza_venta_sin_stock(
    producto_prueba
):

    respuesta = client.post(
        "/ventas",
        json={
            "id_producto": producto_prueba,
            "cantidad": 20,
            "precio_unitario": 3000
        }
    )

    assert respuesta.status_code == 409

    datos = respuesta.json()

    assert datos["ok"] is False

def test_api_anular_venta_inexistente(
    base_prueba
):

    respuesta = client.patch(
        "/ventas/9999/anular",
        json={
            "motivo": "Prueba automática"
        }
    )

    assert respuesta.status_code == 404

    datos = respuesta.json()

    assert datos["ok"] is False
    assert datos["codigo"] == "VENTA_NO_ENCONTRADA"

def test_api_no_permite_anular_venta_dos_veces(
    producto_prueba
):

    respuesta_venta = client.post(
        "/ventas",
        json={
            "id_producto": producto_prueba,
            "cantidad": 1,
            "precio_unitario": 3000
        }
    )

    assert respuesta_venta.status_code == 201

    id_venta = respuesta_venta.json()["id_venta"]

    primera = client.patch(
        f"/ventas/{id_venta}/anular",
        json={
            "motivo": "Primera anulación"
        }
    )

    assert primera.status_code == 200

    segunda = client.patch(
        f"/ventas/{id_venta}/anular",
        json={
            "motivo": "Segunda anulación"
        }
    )

    assert segunda.status_code == 409

    datos = segunda.json()

    assert datos["ok"] is False
    assert datos["codigo"] == "VENTA_YA_ANULADA"

def test_api_compra_aumenta_stock(
    producto_prueba
):

    respuesta = client.post(
        "/compras",
        json={
            "id_producto": producto_prueba,
            "cantidad": 5,
            "precio_unitario": 1500
        }
    )

    assert respuesta.status_code == 201

    datos = respuesta.json()

    assert datos["ok"] is True
    assert datos["codigo"] == "COMPRA_REGISTRADA"

    respuesta_stock = client.get("/stock")

    stock = respuesta_stock.json()["stock"][0]["stock"]

    assert stock == 15

def test_api_compra_producto_inexistente(
    base_prueba
):

    respuesta = client.post(
        "/compras",
        json={
            "id_producto": 9999,
            "cantidad": 5,
            "precio_unitario": 1500
        }
    )

    assert respuesta.status_code == 404

    datos = respuesta.json()

    assert datos["ok"] is False
    assert datos["codigo"] == "PRODUCTO_NO_ENCONTRADO"

def test_api_anular_compra_inexistente(
    base_prueba
):

    respuesta = client.patch(
        "/compras/9999/anular",
        json={
            "motivo": "Prueba automática"
        }
    )

    assert respuesta.status_code == 404

    datos = respuesta.json()

    assert datos["ok"] is False
    assert datos["codigo"] == "COMPRA_NO_ENCONTRADA"

def test_api_no_permite_anular_compra_dos_veces(
    producto_prueba
):

    compra = client.post(
        "/compras",
        json={
            "id_producto": producto_prueba,
            "cantidad": 5,
            "precio_unitario": 1500
        }
    )

    assert compra.status_code == 201

    id_compra = compra.json()["id_compra"]

    primera = client.patch(
        f"/compras/{id_compra}/anular",
        json={
            "motivo": "Primera anulación"
        }
    )

    assert primera.status_code == 200

    segunda = client.patch(
        f"/compras/{id_compra}/anular",
        json={
            "motivo": "Segunda anulación"
        }
    )

    assert segunda.status_code == 409

    datos = segunda.json()

    assert datos["ok"] is False
    assert datos["codigo"] == "COMPRA_YA_ANULADA"

def test_api_registra_aporte(
    base_prueba
):

    respuesta = client.post(
        "/caja/aportes",
        json={
            "descripcion": "Aporte API",
            "monto": 5000
        }
    )

    assert respuesta.status_code == 201

    datos = respuesta.json()

    assert datos["ok"] is True
    assert (
        datos["codigo"]
        == "MOVIMIENTO_CAJA_REGISTRADO"
    )

    caja = client.get("/caja").json()

    assert caja["aportes"] == 5000
    assert caja["saldo_caja"] == 5000

def test_api_registra_retiro(
    base_prueba
):

    aporte = client.post(
        "/caja/aportes",
        json={
            "descripcion": "Aporte inicial",
            "monto": 5000
        }
    )

    assert aporte.status_code == 201

    respuesta = client.post(
        "/caja/retiros",
        json={
            "descripcion": "Retiro API",
            "monto": 1500
        }
    )

    assert respuesta.status_code == 201

    datos = respuesta.json()

    assert datos["ok"] is True
    assert (
        datos["codigo"]
        == "MOVIMIENTO_CAJA_REGISTRADO"
    )

    caja = client.get("/caja").json()

    assert caja["aportes"] == 5000
    assert caja["retiros"] == 1500
    assert caja["saldo_caja"] == 3500

def test_api_anular_movimiento_caja_inexistente(
    base_prueba
):

    respuesta = client.patch(
        "/caja/movimientos/9999/anular",
        json={
            "motivo": "Prueba automática"
        }
    )

    assert respuesta.status_code == 404

    datos = respuesta.json()

    assert datos["ok"] is False
    assert (
        datos["codigo"]
        == "MOVIMIENTO_CAJA_NO_ENCONTRADO"
    )

def test_api_no_permite_anular_movimiento_caja_dos_veces(
    base_prueba
):

    retiro = client.post(
        "/caja/retiros",
        json={
            "descripcion": "Retiro para anular",
            "monto": 1500
        }
    )

    assert retiro.status_code == 201

    id_movimiento = retiro.json()["id_movimiento"]

    primera = client.patch(
        f"/caja/movimientos/{id_movimiento}/anular",
        json={
            "motivo": "Primera anulación"
        }
    )

    assert primera.status_code == 200

    segunda = client.patch(
        f"/caja/movimientos/{id_movimiento}/anular",
        json={
            "motivo": "Segunda anulación"
        }
    )

    assert segunda.status_code == 409

    datos = segunda.json()

    assert datos["ok"] is False
    assert (
        datos["codigo"]
        == "MOVIMIENTO_CAJA_YA_ANULADO"
    )

# ============================================================
# COMANDOS
# ============================================================

def test_api_comando_stock(
    producto_prueba
):

    respuesta = client.post(
        "/comandos",
        json={
            "mensaje": "stock"
        }
    )

    assert respuesta.status_code == 200

    datos = respuesta.json()

    assert datos["ok"] is True
    assert datos["codigo"] == "COMANDO_STOCK"
    assert "Coca prueba" in datos["respuesta"]
    assert "10" in datos["respuesta"]


def test_api_comando_normaliza_acentos_y_mayusculas(
    base_prueba
):

    respuesta = client.post(
        "/comandos",
        json={
            "mensaje": "  RESÚMEN   MES  "
        }
    )

    assert respuesta.status_code == 200

    datos = respuesta.json()

    assert datos["ok"] is True
    assert datos["codigo"] == "COMANDO_RESUMEN_MES"


def test_api_comando_no_reconocido(
    base_prueba
):

    respuesta = client.post(
        "/comandos",
        json={
            "mensaje": "esto no existe"
        }
    )

    assert respuesta.status_code == 400

    datos = respuesta.json()

    assert datos["ok"] is False
    assert datos["codigo"] == "COMANDO_NO_RECONOCIDO"


def test_api_comando_vacio_rechazado_por_pydantic():

    respuesta = client.post(
        "/comandos",
        json={
            "mensaje": ""
        }
    )

    assert respuesta.status_code == 422


def test_api_comando_stock_muestra_solo_productos_inventariables(
    base_prueba
):
    from database import obtener_conexion

    conexion = obtener_conexion()

    conexion.execute(
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
            "Manaos Cola 600ml",
            "Bebidas",
            "Unidad",
            1,
            "unidad",
            1,
            4,
            1300,
            1
        )
    )

    conexion.execute(
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
            "Big mac doble",
            "Hamburguesas",
            "Unidad",
            1,
            "unidad",
            1,
            0,
            9000,
            0
        )
    )

    conexion.commit()
    conexion.close()

    respuesta = client.post(
        "/comandos",
        json={"mensaje": "stock"}
    )

    assert respuesta.status_code == 200

    datos = respuesta.json()

    assert "Manaos Cola 600ml" in datos["respuesta"]
    assert "Big mac doble" not in datos["respuesta"]


def test_api_comando_venta_usa_precio_configurado_y_descuenta_stock(
    base_prueba
):
    from database import obtener_conexion

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
            "Manaos Cola 600ml",
            "Bebidas",
            "Unidad",
            1,
            "unidad",
            1,
            5,
            1300,
            1
        )
    )

    id_producto = cursor.lastrowid

    conexion.commit()
    conexion.close()

    respuesta = client.post(
        "/comandos",
        json={"mensaje": "venta 2 manaos cola 600"}
    )

    assert respuesta.status_code == 200

    datos = respuesta.json()

    assert datos["ok"] is True
    assert datos["codigo"] == "COMANDO_VENTA_REGISTRADA"
    assert datos["cantidad"] == 2
    assert datos["precio_unitario"] == 1300
    assert datos["total"] == 2600
    assert datos["stock_restante"] == 3

    conexion = obtener_conexion()

    stock = conexion.execute(
        "SELECT stock FROM productos WHERE id_producto = ?",
        (id_producto,)
    ).fetchone()[0]

    conexion.close()

    assert stock == 3


def test_api_comando_venta_producto_sin_stock_no_descuenta(
    base_prueba
):
    from database import obtener_conexion

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
            "Big mac doble",
            "Hamburguesas",
            "Unidad",
            1,
            "unidad",
            1,
            0,
            9000,
            0
        )
    )

    id_producto = cursor.lastrowid

    conexion.commit()
    conexion.close()

    respuesta = client.post(
        "/comandos",
        json={"mensaje": "venta bigmac doble"}
    )

    assert respuesta.status_code == 200

    datos = respuesta.json()

    assert datos["ok"] is True
    assert datos["total"] == 9000
    assert datos["stock_restante"] is None

    conexion = obtener_conexion()

    stock = conexion.execute(
        "SELECT stock FROM productos WHERE id_producto = ?",
        (id_producto,)
    ).fetchone()[0]

    conexion.close()

    assert stock == 0


def test_api_comando_venta_detecta_producto_ambiguo(
    base_prueba
):
    from database import obtener_conexion

    conexion = obtener_conexion()

    productos = [
        ("Manaos Cola 600ml", 1300),
        ("Manaos Cola 2.25l", 2000),
    ]

    for nombre, precio in productos:
        conexion.execute(
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
                "Bebidas",
                "Unidad",
                1,
                "unidad",
                1,
                10,
                precio,
                1
            )
        )

    conexion.commit()
    conexion.close()

    respuesta = client.post(
        "/comandos",
        json={"mensaje": "venta manaos cola"}
    )

    assert respuesta.status_code == 400

    datos = respuesta.json()

    assert datos["ok"] is False
    assert datos["codigo"] == "PRODUCTO_AMBIGUO"
