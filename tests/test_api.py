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


def test_api_comando_venta_manaos_cola_asume_grande(
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

    assert respuesta.status_code == 200

    datos = respuesta.json()

    assert datos["ok"] is True
    assert datos["codigo"] == "COMANDO_VENTA_REGISTRADA"
    assert datos["producto"] == "Manaos Cola 2.25l"
    assert datos["precio_unitario"] == 2000
    assert datos["stock_restante"] == 9


def test_api_menu_whatsapp(
    base_prueba
):
    respuesta = client.post(
        "/comandos",
        json={
            "mensaje": "menu"
        }
    )

    assert respuesta.status_code == 200

    datos = respuesta.json()

    assert datos["ok"] is True
    assert datos["codigo"] == "COMANDO_MENU"
    assert "MENÚ - Lo de Clau" in datos["respuesta"]
    assert "1. Stock" in datos["respuesta"]
    assert "10. Anular última venta" in datos["respuesta"]
    assert "opcion 1" in datos["respuesta"]


def test_api_menu_opcion_stock(
    producto_prueba
):
    respuesta = client.post(
        "/comandos",
        json={
            "mensaje": "opcion 1"
        }
    )

    assert respuesta.status_code == 200

    datos = respuesta.json()

    assert datos["ok"] is True
    assert datos["codigo"] == "COMANDO_STOCK"
    assert "Coca prueba" in datos["respuesta"]


def test_api_menu_opcion_venta_muestra_instrucciones(
    base_prueba
):
    respuesta = client.post(
        "/comandos",
        json={
            "mensaje": "opcion 6"
        }
    )

    assert respuesta.status_code == 200

    datos = respuesta.json()

    assert datos["ok"] is True
    assert datos["codigo"] == "COMANDO_MENU_INSTRUCCION"
    assert "Registrar venta" in datos["respuesta"]
    assert "venta 2 pepsi" in datos["respuesta"]


def test_api_menu_opcion_inexistente(
    base_prueba
):
    respuesta = client.post(
        "/comandos",
        json={
            "mensaje": "opcion 99"
        }
    )

    assert respuesta.status_code == 400

    datos = respuesta.json()

    assert datos["ok"] is False
    assert datos["codigo"] == "OPCION_MENU_INVALIDA"



def test_api_venta_rapida_sandwich_por_precio(
    base_prueba
):
    from database import obtener_conexion

    conexion = obtener_conexion()

    productos = [
        (
            "Grande de carne individual",
            "Sanguches",
            7500,
        ),
        (
            "Chico de pollo + papas",
            "Sanguches",
            6000,
        ),
    ]

    for nombre, categoria, precio in productos:
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
                categoria,
                "Unidad",
                1,
                "unidad",
                1,
                0,
                precio,
                0,
            )
        )

    conexion.commit()
    conexion.close()

    respuesta = client.post(
        "/comandos",
        json={
            "mensaje": "1 sandwich de 7500"
        }
    )

    assert respuesta.status_code == 200

    datos = respuesta.json()

    assert datos["ok"] is True
    assert datos["producto"] == "Grande de carne individual"
    assert datos["total"] == 7500
    assert "Operación: #" in datos["respuesta"]


def test_api_venta_rapida_sandwich_con_acento_y_cantidad(
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
            "Chico de pollo + papas",
            "Sanguches",
            "Unidad",
            1,
            "unidad",
            1,
            0,
            6000,
            0,
        )
    )

    conexion.commit()
    conexion.close()

    respuesta = client.post(
        "/comandos",
        json={
            "mensaje": "2 sándwich de 6000"
        }
    )

    assert respuesta.status_code == 200

    datos = respuesta.json()

    assert datos["ok"] is True
    assert datos["cantidad"] == 2
    assert datos["producto"] == "Chico de pollo + papas"
    assert datos["total"] == 12000


def test_api_venta_rapida_hamburguesa_simple_asume_clasica(
    base_prueba
):
    from database import obtener_conexion

    conexion = obtener_conexion()

    hamburguesas = [
        ("Pollo con papas simple", 5500),
        ("Big mac simple", 7000),
        ("Cheddar y huevo simple", 7000),
        ("Clasica simple", 6500),
    ]

    for nombre, precio in hamburguesas:
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
                "Hamburguesas",
                "Unidad",
                1,
                "unidad",
                1,
                0,
                precio,
                0,
            )
        )

    conexion.commit()
    conexion.close()

    respuesta = client.post(
        "/comandos",
        json={
            "mensaje": "1 hamburguesa simple"
        }
    )

    assert respuesta.status_code == 200

    datos = respuesta.json()

    assert datos["ok"] is True
    assert datos["codigo"] == "COMANDO_VENTA_REGISTRADA"
    assert datos["producto"] == "Clasica simple"
    assert datos["precio_unitario"] == 6500
    assert datos["total"] == 6500


def test_api_venta_rapida_manaos_lima_asume_225l(
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
            "Manaos Lima 2.25l",
            "Bebidas",
            "Botella",
            2.25,
            "Litros",
            1,
            5,
            2000,
            1,
        )
    )

    conexion.commit()
    conexion.close()

    respuesta = client.post(
        "/comandos",
        json={
            "mensaje": "1 manaos lima"
        }
    )

    assert respuesta.status_code == 200

    datos = respuesta.json()

    assert datos["ok"] is True
    assert datos["producto"] == "Manaos Lima 2.25l"
    assert datos["cantidad"] == 1
    assert datos["stock_restante"] == 4



def test_api_manaos_cola_sin_tamano_asume_225l(
    base_prueba
):
    from database import obtener_conexion

    conexion = obtener_conexion()

    productos = [
        ("Manaos Cola 600ml", 1300, 5),
        ("Manaos Cola 2.25l", 2000, 5),
    ]

    for nombre, precio, stock in productos:
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
                stock,
                precio,
                1,
            )
        )

    conexion.commit()
    conexion.close()

    respuesta = client.post(
        "/comandos",
        json={"mensaje": "1 manaos cola"}
    )

    assert respuesta.status_code == 200

    datos = respuesta.json()

    assert datos["producto"] == "Manaos Cola 2.25l"
    assert datos["precio_unitario"] == 2000


def test_api_manaos_pomelo_sin_tamano_asume_225l(
    base_prueba
):
    from database import obtener_conexion

    conexion = obtener_conexion()

    productos = [
        ("Manaos Pomelo 600ml", 1300, 5),
        ("Manaos Pomelo 2.25l", 2000, 5),
    ]

    for nombre, precio, stock in productos:
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
                stock,
                precio,
                1,
            )
        )

    conexion.commit()
    conexion.close()

    respuesta = client.post(
        "/comandos",
        json={"mensaje": "1 manaos pomelo"}
    )

    assert respuesta.status_code == 200

    datos = respuesta.json()

    assert datos["producto"] == "Manaos Pomelo 2.25l"
    assert datos["precio_unitario"] == 2000


def test_api_manaos_chica_requiere_indicar_chica_o_600(
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
            5,
            1300,
            1,
        )
    )

    conexion.commit()
    conexion.close()

    respuesta = client.post(
        "/comandos",
        json={"mensaje": "1 manaos cola chica"}
    )

    assert respuesta.status_code == 200
    assert respuesta.json()["producto"] == "Manaos Cola 600ml"



def test_api_sanguche_chico_asume_pollo_con_papas(
    base_prueba
):
    from database import obtener_conexion

    conexion = obtener_conexion()

    productos = [
        ("Chico de pollo + papas", 6000),
        ("Chico de carne + papas", 7000),
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
                "Sanguches",
                "Unidad",
                1,
                "unidad",
                1,
                0,
                precio,
                0,
            )
        )

    conexion.commit()
    conexion.close()

    respuesta = client.post(
        "/comandos",
        json={"mensaje": "1 sanguche chico"}
    )

    assert respuesta.status_code == 200

    datos = respuesta.json()

    assert datos["producto"] == "Chico de pollo + papas"
    assert datos["precio_unitario"] == 6000


def test_api_sanguche_grande_asume_pollo_con_papas(
    base_prueba
):
    from database import obtener_conexion

    conexion = obtener_conexion()

    productos = [
        ("Grande de pollo + papas", 8000),
        ("Grande de carne + papas", 9000),
        ("Grande de pollo individual", 6500),
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
                "Sanguches",
                "Unidad",
                1,
                "unidad",
                1,
                0,
                precio,
                0,
            )
        )

    conexion.commit()
    conexion.close()

    respuesta = client.post(
        "/comandos",
        json={"mensaje": "2 sándwich grande"}
    )

    assert respuesta.status_code == 200

    datos = respuesta.json()

    assert datos["cantidad"] == 2
    assert datos["producto"] == "Grande de pollo + papas"
    assert datos["precio_unitario"] == 8000
    assert datos["total"] == 16000



def test_api_lenguaje_real_defaults_hamburguesa_y_napo(
    base_prueba
):
    from database import obtener_conexion

    conexion = obtener_conexion()

    productos = [
        ("Clasica simple", "Hamburguesas", 6500),
        ("Big mac simple", "Hamburguesas", 7000),
        ("Napo de pollo con fritas", "Al plato", 9500),
        ("Napo de carne con fritas", "Al plato", 10500),
    ]

    for nombre, categoria, precio in productos:
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
                categoria,
                "Unidad",
                1,
                "unidad",
                1,
                0,
                precio,
                0,
            )
        )

    conexion.commit()
    conexion.close()

    hamburguesa = client.post(
        "/comandos",
        json={"mensaje": "1 hamburguesa simple"}
    )

    assert hamburguesa.status_code == 200
    assert hamburguesa.json()["producto"] == "Clasica simple"

    napo = client.post(
        "/comandos",
        json={"mensaje": "una napo"}
    )

    assert napo.status_code == 200
    assert napo.json()["producto"] == "Napo de pollo con fritas"


def test_api_postre_generico_pregunta_cual(
    base_prueba
):
    from database import obtener_conexion

    conexion = obtener_conexion()

    for nombre in ("Chocotorta", "Oreo"):
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
                "Postres",
                "Unidad",
                1,
                "unidad",
                1,
                5,
                4500,
                1,
            )
        )

    conexion.commit()
    conexion.close()

    respuesta = client.post(
        "/comandos",
        json={"mensaje": "un postre"}
    )

    assert respuesta.status_code == 400
    datos = respuesta.json()

    assert datos["codigo"] == "PRODUCTO_AMBIGUO"
    assert "Chocotorta" in datos["respuesta"]
    assert "Oreo" in datos["respuesta"]


def test_api_mila_sola_define_fritas_pero_pregunta_carne(
    base_prueba
):
    from database import obtener_conexion

    conexion = obtener_conexion()

    for nombre, precio in (
        ("Milanesa de pollo con fritas", 8500),
        ("Milanesa de carne con fritas", 9500),
    ):
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
                "Al plato",
                "Unidad",
                1,
                "unidad",
                1,
                0,
                precio,
                0,
            )
        )

    conexion.commit()
    conexion.close()

    respuesta = client.post(
        "/comandos",
        json={"mensaje": "una mila"}
    )

    assert respuesta.status_code == 400
    datos = respuesta.json()

    assert datos["codigo"] == "PRODUCTO_AMBIGUO"
    assert "Milanesa de pollo con fritas" in datos["respuesta"]
    assert "Milanesa de carne con fritas" in datos["respuesta"]


def test_api_contexto_gastos_registra_lineas_e_ignora_total(
    base_prueba
):
    from database import obtener_conexion

    contexto = {
        "canal": "whatsapp",
        "usuario_numero": "operador-contexto",
        "grupo_id": "grupo-contexto",
    }

    inicio = client.post(
        "/comandos",
        json={
            "mensaje": "Gastos",
            **contexto,
        }
    )

    assert inicio.status_code == 200
    assert inicio.json()["codigo"] == "CONTEXTO_ACTIVADO"

    gasto = client.post(
        "/comandos",
        json={
            "mensaje": "Verdulería 9000",
            **contexto,
        }
    )

    assert gasto.status_code == 200
    assert gasto.json()["codigo"] == "COMANDO_GASTO_REGISTRADO"
    assert gasto.json()["monto"] == 9000

    total = client.post(
        "/comandos",
        json={
            "mensaje": "Total gastado 9000",
            **contexto,
        }
    )

    assert total.status_code == 200
    assert total.json()["codigo"] == "COMANDO_TOTAL_INFORMATIVO"

    conexion = obtener_conexion()

    cantidad = conexion.execute(
        "SELECT COUNT(*) FROM gastos"
    ).fetchone()[0]

    conexion.close()

    assert cantidad == 1


def test_api_bloque_gastos_y_total_no_duplica(
    base_prueba
):
    from database import obtener_conexion

    respuesta = client.post(
        "/comandos",
        json={
            "mensaje": (
                "Gastos:\n"
                "Carne: 20000\n"
                "Verdulería 11000\n"
                "Total gastado: 31000"
            ),
            "canal": "whatsapp",
            "usuario_numero": "operador-bloque",
            "grupo_id": "grupo-bloque",
        }
    )

    assert respuesta.status_code == 200
    assert respuesta.json()["codigo"] == "COMANDO_BLOQUE_PROCESADO"

    conexion = obtener_conexion()

    filas = conexion.execute(
        """
        SELECT descripcion_gasto, valor_final
        FROM gastos
        ORDER BY id_gasto
        """
    ).fetchall()

    conexion.close()

    assert filas == [
        ("carne", 20000),
        ("verduleria", 11000),
    ]


def test_api_venta_por_precio_unico_y_multiple_abreviado(
    base_prueba
):
    from database import obtener_conexion

    conexion = obtener_conexion()

    productos = [
        ("Producto siete", 7000),
        ("Producto ocho", 8000),
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
                "Comida",
                "Unidad",
                1,
                "unidad",
                1,
                0,
                precio,
                0,
            )
        )

    conexion.commit()
    conexion.close()

    respuesta = client.post(
        "/comandos",
        json={"mensaje": "5x8 y 2x7"}
    )

    assert respuesta.status_code == 200

    datos = respuesta.json()

    assert datos["codigo"] == "COMANDO_VENTA_MULTIPLE_REGISTRADA"
    assert datos["total"] == 54000
