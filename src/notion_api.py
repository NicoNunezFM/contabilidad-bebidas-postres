import os
import requests
from dotenv import load_dotenv

load_dotenv()

token = os.getenv("NOTION_TOKEN")

def obtener_productos():
   
    if token is None:
        print("No se encontro el token.")
        return []

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Notion-Version": "2026-03-11"
    }
    productos_data_source_id = os.getenv("PRODUCTOS_DATA_SOURCE_ID")

    if productos_data_source_id is None:
            print("No se encontró el ID de la fuente de datos Productos.")
            return

    url = (
    "https://api.notion.com/v1/data_sources/"
    f"{productos_data_source_id}/query"
    )
    respuesta = requests.post(
    url,
    headers=headers,
    json={}
    )

    print(respuesta.status_code)

    productos_python = []

    if respuesta.status_code == 200:
        print("Conexion exitosa.")

        datos = respuesta.json()
        productos = datos["results"]
        print(f"Cantidad de productos encontrados: {len(productos)}")

        for producto in productos:
            # producto["properties"]["Nombre"]["title"][0]["plain_text"]
            propiedades = producto["properties"]
            nombre_propiedad = propiedades["Nombre"]
            titulo = nombre_propiedad["title"]
            primer_elemento = titulo[0]
            nombre = primer_elemento["plain_text"]

            unidades_por_pack = propiedades["Unidades por pack"]["number"]

            producto_python = {
                "nombre": nombre,
                "unidades_por_pack" : unidades_por_pack
            }

            productos_python.append(producto_python)

        return productos_python

    else:
        print(f"Error: {respuesta.status_code}")

if __name__ == "__main__":
    productos = obtener_productos()
    print(productos)
    


             
     