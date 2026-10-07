from fastapi.testclient import TestClient

from api import app
from costos_postres import inicializar_costos_postres
from database import obtener_conexion


client = TestClient(app)


def _crear_postre_oreo(stock=0):
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
            "Oreo",
            "Postres",
            "Unidad",
            1,
            "unidad",
            1,
            stock,
            4500,
            1,
        )
    )

    conexion.commit()
    conexion.close()


def _cargar_oreo_completo():
    mensajes = [
        "insumo galletitas oreo 800 g 8000 Carrefour",
        "insumo dulce de leche 900 g 9000 Carrefour",
        "insumo crema de leche 600 ml 6000 Carrefour",
        "insumo leche 300 ml 300 Carrefour",
        "insumo pote 10 unidades 3000 Papelera",
    ]

    for mensaje in mensajes:
        respuesta = client.post(
            "/comandos",
            json={"mensaje": mensaje}
        )
        assert respuesta.status_code == 200


def test_compra_insumo_suma_stock_fisico(
    base_prueba
):
    inicializar_costos_postres()

    respuesta = client.post(
        "/comandos",
        json={
            "mensaje": (
                "insumo dulce de leche 2 kg "
                "10000 Carrefour"
            )
        }
    )

    assert respuesta.status_code == 200

    datos = respuesta.json()

    assert datos["stock_anterior"] == 0
    assert datos["stock_nuevo"] == 2000
    assert datos["unidad_base"] == "g"

    conexion = obtener_conexion()

    stock = conexion.execute(
        """
        SELECT stock_base
        FROM insumos
        WHERE nombre = 'Dulce de leche'
        """
    ).fetchone()[0]

    conexion.close()

    assert stock == 2000


def test_compra_paquetes_oreo_suma_gramos_a_stock(
    base_prueba
):
    inicializar_costos_postres()

    respuesta = client.post(
        "/comandos",
        json={
            "mensaje": (
                "insumo oreo 3 paquetes 118g "
                "4288 Carrefour"
            )
        }
    )

    assert respuesta.status_code == 200

    datos = respuesta.json()

    assert datos["cantidad_base_total"] == 354
    assert datos["stock_anterior"] == 0
    assert datos["stock_nuevo"] == 354
    assert datos["unidad_base"] == "g"


def test_stock_insumos_muestra_existencias(
    base_prueba
):
    inicializar_costos_postres()

    client.post(
        "/comandos",
        json={
            "mensaje": (
                "insumo dulce de leche 1500 g "
                "9000 Carrefour"
            )
        }
    )

    respuesta = client.post(
        "/comandos",
        json={"mensaje": "stock insumos"}
    )

    assert respuesta.status_code == 200

    datos = respuesta.json()

    dulce = next(
        item
        for item in datos["insumos"]
        if item["nombre"] == "Dulce de leche"
    )

    assert dulce["stock_base"] == 1500
    assert dulce["unidad_base"] == "g"
    assert dulce["controla_stock"] is True
    assert dulce["equivalencias_paquetes"] == []


def test_stock_oreo_muestra_equivalencias_de_paquetes(
    base_prueba
):
    inicializar_costos_postres()

    compra = client.post(
        "/comandos",
        json={
            "mensaje": (
                "insumo oreo 3 paquetes 118g "
                "4288 Carrefour"
            )
        }
    )

    assert compra.status_code == 200

    respuesta = client.post(
        "/comandos",
        json={"mensaje": "stock insumos"}
    )

    assert respuesta.status_code == 200

    datos = respuesta.json()

    oreo = next(
        item
        for item in datos["insumos"]
        if item["nombre"] == "Galletitas Oreo"
    )

    equivalencias = {
        item["presentacion"]:
            item["paquetes_equivalentes"]
        for item in oreo["equivalencias_paquetes"]
    }

    assert equivalencias["118g"] == 3
    assert equivalencias["354g tripack"] == 1
    assert "3.00 x 118g" in datos["respuesta"]
    assert "1.00 x 354g tripack" in datos["respuesta"]


def test_inventario_insumo_corrige_stock_y_audita(
    base_prueba
):
    inicializar_costos_postres()

    client.post(
        "/comandos",
        json={
            "mensaje": (
                "insumo oreo 3 paquetes 118g "
                "4288 Carrefour"
            )
        }
    )

    respuesta = client.post(
        "/comandos",
        json={
            "mensaje": "inventario insumo oreo 300g",
            "canal": "whatsapp",
            "usuario_numero": "operador-stock",
            "grupo_id": "grupo-stock",
            "id_mensaje": "inv-insumo-1",
        }
    )

    assert respuesta.status_code == 200

    datos = respuesta.json()

    assert datos["stock_anterior"] == 354
    assert datos["stock_nuevo"] == 300
    assert datos["diferencia"] == -54

    conexion = obtener_conexion()

    ajuste = conexion.execute(
        """
        SELECT
            cantidad_anterior,
            cantidad_nueva,
            diferencia,
            usuario_origen,
            grupo_origen,
            id_mensaje_origen
        FROM ajustes_stock_insumos
        """
    ).fetchone()

    conexion.close()

    assert ajuste == (
        354.0,
        300.0,
        -54.0,
        "operador-stock",
        "grupo-stock",
        "inv-insumo-1",
    )


def test_produccion_descuenta_insumos_y_suma_postres(
    base_prueba
):
    inicializar_costos_postres()
    _crear_postre_oreo(stock=2)
    _cargar_oreo_completo()

    respuesta = client.post(
        "/comandos",
        json={
            "mensaje": "produccion 10 oreo"
        }
    )

    assert respuesta.status_code == 200

    datos = respuesta.json()

    assert datos["stock_anterior"] == 2
    assert datos["stock_nuevo"] == 12

    consumos = {
        item["insumo"]: item
        for item in datos["detalle_insumos"]
    }

    assert consumos["Galletitas Oreo"]["stock_anterior"] == 800
    assert consumos["Galletitas Oreo"]["stock_nuevo"] == 0
    assert consumos["Dulce de leche"]["stock_nuevo"] == 0
    assert consumos["Crema de leche"]["stock_nuevo"] == 0
    assert consumos["Leche"]["stock_nuevo"] == 0
    assert consumos["Pote"]["stock_nuevo"] == 0

    conexion = obtener_conexion()

    stocks = dict(
        conexion.execute(
            """
            SELECT nombre, stock_base
            FROM insumos
            WHERE nombre IN (
                'Galletitas Oreo',
                'Dulce de leche',
                'Crema de leche',
                'Leche',
                'Pote'
            )
            """
        ).fetchall()
    )

    conexion.close()

    assert all(
        valor == 0
        for valor in stocks.values()
    )


def test_produccion_sin_stock_suficiente_es_atomica(
    base_prueba
):
    inicializar_costos_postres()
    _crear_postre_oreo(stock=1)

    compras = [
        "insumo galletitas oreo 400 g 4000 Carrefour",
        "insumo dulce de leche 900 g 9000 Carrefour",
        "insumo crema de leche 600 ml 6000 Carrefour",
        "insumo leche 300 ml 300 Carrefour",
        "insumo pote 10 unidades 3000 Papelera",
    ]

    for mensaje in compras:
        assert client.post(
            "/comandos",
            json={"mensaje": mensaje}
        ).status_code == 200

    respuesta = client.post(
        "/comandos",
        json={
            "mensaje": "produccion 10 oreo"
        }
    )

    assert respuesta.status_code == 400

    datos = respuesta.json()

    assert (
        datos["codigo"]
        == "STOCK_INSUMOS_INSUFICIENTE"
    )

    faltante_oreo = next(
        item
        for item in datos["faltantes_stock"]
        if item["insumo"] == "Galletitas Oreo"
    )

    assert faltante_oreo["necesario"] == 800
    assert faltante_oreo["disponible"] == 400
    assert faltante_oreo["faltante"] == 400

    conexion = obtener_conexion()

    stock_oreo = conexion.execute(
        """
        SELECT stock_base
        FROM insumos
        WHERE nombre = 'Galletitas Oreo'
        """
    ).fetchone()[0]

    stock_postre = conexion.execute(
        """
        SELECT stock
        FROM productos
        WHERE nombre = 'Oreo'
        """
    ).fetchone()[0]

    producciones = conexion.execute(
        """
        SELECT COUNT(*)
        FROM producciones_postres
        """
    ).fetchone()[0]

    conexion.close()

    assert stock_oreo == 400
    assert stock_postre == 1
    assert producciones == 0


def test_necesidades_produccion_compara_con_stock(
    base_prueba
):
    inicializar_costos_postres()

    compras = [
        "insumo galletitas oreo 1000 g 10000 Carrefour",
        "insumo dulce de leche 1000 g 10000 Carrefour",
        "insumo crema de leche 500 ml 5000 Carrefour",
        "insumo leche 1000 ml 1000 Carrefour",
        "insumo pote 12 unidades 3600 Papelera",
    ]

    for mensaje in compras:
        assert client.post(
            "/comandos",
            json={"mensaje": mensaje}
        ).status_code == 200

    respuesta = client.post(
        "/comandos",
        json={
            "mensaje": (
                "que necesito para hacer 20 oreos"
            )
        }
    )

    assert respuesta.status_code == 200

    datos = respuesta.json()

    assert datos["puede_producir"] is False

    faltantes = {
        item["insumo"]: item
        for item in datos["faltantes"]
    }

    assert faltantes["Galletitas Oreo"]["faltante"] == 600
    assert faltantes["Dulce de leche"]["faltante"] == 800
    assert faltantes["Crema de leche"]["faltante"] == 700
    assert faltantes["Pote"]["faltante"] == 8
    assert "Leche" not in faltantes


def test_cafe_con_leche_preparado_no_controla_stock(
    base_prueba
):
    inicializar_costos_postres()

    conexion = obtener_conexion()

    fila = conexion.execute(
        """
        SELECT controla_stock, stock_base
        FROM insumos
        WHERE nombre = 'Café con leche preparado'
        """
    ).fetchone()

    conexion.close()

    assert fila == (
        0,
        0,
    )
