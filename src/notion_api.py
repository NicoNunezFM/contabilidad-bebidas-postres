import os
import requests
from dotenv import load_dotenv


load_dotenv()

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_VERSION = "2026-03-11"


# ============================================================
# FUNCIONES GENERALES DE NOTION
# ============================================================

def obtener_headers():
    """
    Devuelve los headers necesarios para comunicarse con Notion.
    """

    if NOTION_TOKEN is None:
        print("No se encontró el token de Notion.")
        return None

    return {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": NOTION_VERSION
    }


def consultar_data_source(data_source_id):
    """
    Consulta cualquier Data Source de Notion y devuelve
    el JSON convertido a un diccionario de Python.
    """

    if data_source_id is None:
        print("No se recibió un Data Source ID válido.")
        return None

    headers = obtener_headers()

    if headers is None:
        return None

    url = (
        "https://api.notion.com/v1/data_sources/"
        f"{data_source_id}/query"
    )

    try:
        respuesta = requests.post(
            url,
            headers=headers,
            json={},
            timeout=15
        )

    except requests.RequestException as error:
        print(f"Error de conexión con Notion: {error}")
        return None

    if respuesta.status_code == 200:
        return respuesta.json()

    print(f"Error al consultar Notion: {respuesta.status_code}")
    print(respuesta.text)

    return None


# ============================================================
# FUNCIONES AUXILIARES PARA LEER PROPIEDADES
# ============================================================

def obtener_texto_titulo(propiedad):
    """
    Extrae el texto de una propiedad de tipo Title.
    """

    titulo = propiedad.get("title", [])

    if not titulo:
        return ""

    return titulo[0].get("plain_text", "")


def obtener_numero(propiedad):
    """
    Extrae el valor de una propiedad de tipo Number.
    """

    return propiedad.get("number")


def obtener_seleccion(propiedad):
    """
    Extrae el nombre de una propiedad de tipo Select.
    """

    seleccion = propiedad.get("select")

    if seleccion is None:
        return None

    return seleccion.get("name")


def obtener_fecha(propiedad):
    """
    Extrae la fecha inicial de una propiedad de tipo Date.
    """

    fecha = propiedad.get("date")

    if fecha is None:
        return None

    return fecha.get("start")


# ============================================================
# PRODUCTOS
# ============================================================

def obtener_productos():

    productos_data_source_id = os.getenv("PRODUCTOS_DATA_SOURCE_ID")

    if productos_data_source_id is None:
        print("No se encontró el ID de Productos.")
        return []

    datos = consultar_data_source(productos_data_source_id)

    if datos is None:
        return []

    productos_notion = datos.get("results", [])
    productos_python = []

    for producto in productos_notion:

        propiedades = producto.get("properties", {})

        nombre = obtener_texto_titulo(
            propiedades.get("Nombre", {})
        )

        categoria = obtener_seleccion(
            propiedades.get("Categoria", {})
        )

        presentacion = obtener_seleccion(
            propiedades.get("Presentacion", {})
        )

        contenido = obtener_numero(
            propiedades.get("Contenido", {})
        )

        unidad_medida = obtener_seleccion(
            propiedades.get("Unidad de medida", {})
        )

        unidades_por_pack = obtener_numero(
            propiedades.get("Unidades por pack", {})
        )

        stock = obtener_numero(
            propiedades.get("Stock", {})
        )

        producto_python = {
            "notion_id": producto.get("id"),
            "nombre": nombre,
            "categoria": categoria,
            "presentacion": presentacion,
            "contenido": contenido,
            "unidad_medida": unidad_medida,
            "unidades_por_pack": unidades_por_pack,
            "stock": stock
        }

        productos_python.append(producto_python)

    return productos_python


# ============================================================
# COMPRAS
# ============================================================

def obtener_compras():

    compras_data_source_id = os.getenv("COMPRAS_DATA_SOURCE_ID")

    if compras_data_source_id is None:
        print("No se encontró el ID de Compras.")
        return []

    datos = consultar_data_source(compras_data_source_id)

    if datos is None:
        return []

    compras_notion = datos.get("results", [])
    compras_python = []

    for compra in compras_notion:

        propiedades = compra.get("properties", {})

        producto = obtener_texto_titulo(
            propiedades.get("Producto", {})
        )

        fecha = obtener_fecha(
            propiedades.get("Fecha", {})
        )

        cantidad = obtener_numero(
            propiedades.get("Cantidad", {})
        )

        precio_unitario = obtener_numero(
            propiedades.get("Precio unitario", {})
        )

        estado = obtener_seleccion(
            propiedades.get("Estado", {})
        )

        if cantidad is not None and precio_unitario is not None:
            total = cantidad * precio_unitario
        else:
            total = 0

        compra_python = {
            "notion_id": compra.get("id"),
            "producto": producto,
            "fecha": fecha,
            "cantidad": cantidad,
            "precio_unitario": precio_unitario,
            "total": total,
            "estado": estado
        }

        compras_python.append(compra_python)

    return compras_python


# ============================================================
# PRUEBAS
# ============================================================

if __name__ == "__main__":

    print("\n========== PRODUCTOS ==========")

    productos = obtener_productos()

    for producto in productos:
        print(producto)

    print("\n========== COMPRAS ==========")

    compras = obtener_compras()

    for compra in compras:
        print(compra)