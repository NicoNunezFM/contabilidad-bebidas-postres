from datetime import datetime
import re
import unicodedata

from ajustes_stock import (
    registrar_consumo_interno,
    registrar_inventario_fisico,
    registrar_merma,
)
from caja import obtener_estado_caja
from productos import obtener_productos
from reportes import (
    resumen_mes_actual,
    resumen_por_periodo,
    resumen_semana_actual,
)
from ventas import registrar_venta


ALIASES_PRODUCTOS = {
    "manaos cola chica": "manaos cola 600 ml",
    "manaos pomelo chica": "manaos pomelo 600 ml",
    "manaos cola grande": "manaos cola 2.25 l",
    "manaos naranja grande": "manaos naranja 2.25 l",
    "manaos manzana grande": "manaos manzana 2.25 l",
    "manaos pomelo grande": "manaos pomelo 2.25 l",
    "pepsi": "pepsi lata",
    "7 up": "7 up lata",
    "postre oreo": "oreo",
    "postre chocotorta": "chocotorta",
    "bigmac simple": "big mac simple",
    "bigmac doble": "big mac doble",
}


def normalizar_texto(texto):
    if not isinstance(texto, str):
        return ""

    texto = texto.strip().lower()

    texto = "".join(
        caracter
        for caracter in unicodedata.normalize("NFD", texto)
        if unicodedata.category(caracter) != "Mn"
    )

    texto = re.sub(r"(?<=\d)(?=[a-z])", " ", texto)
    texto = re.sub(r"(?<=[a-z])(?=\d)", " ", texto)

    texto = texto.replace("+", " ")
    texto = texto.replace("-", " ")
    texto = texto.replace("/", " ")
    texto = texto.replace("_", " ")

    return " ".join(texto.split())


def formatear_pesos(valor):
    numero = float(valor)

    formato = f"{numero:,.2f}"

    return (
        "$"
        + formato
        .replace(",", "X")
        .replace(".", ",")
        .replace("X", ".")
    )


def resolver_producto(texto_producto):
    consulta = normalizar_texto(texto_producto)

    if not consulta:
        return {
            "ok": False,
            "codigo": "PRODUCTO_NO_ENCONTRADO",
            "mensaje": "No se indicó un producto.",
        }

    consulta = ALIASES_PRODUCTOS.get(consulta, consulta)

    productos = obtener_productos()

    normalizados = [
        (producto, normalizar_texto(producto["nombre"]))
        for producto in productos
    ]

    for producto, nombre_normalizado in normalizados:
        if consulta == nombre_normalizado:
            return {
                "ok": True,
                "producto": producto,
            }

    tokens_consulta = set(consulta.split())

    candidatos = []

    for producto, nombre_normalizado in normalizados:
        tokens_producto = set(nombre_normalizado.split())

        if tokens_consulta.issubset(tokens_producto):
            candidatos.append(producto)

    if len(candidatos) == 1:
        return {
            "ok": True,
            "producto": candidatos[0],
        }

    if len(candidatos) > 1:
        return {
            "ok": False,
            "codigo": "PRODUCTO_AMBIGUO",
            "mensaje": "El producto coincide con más de una opción.",
            "candidatos": [
                {
                    "id_producto": producto["id_producto"],
                    "nombre": producto["nombre"],
                }
                for producto in candidatos
            ],
        }

    return {
        "ok": False,
        "codigo": "PRODUCTO_NO_ENCONTRADO",
        "mensaje": (
            f"No encontré un producto que coincida con "
            f"'{texto_producto.strip()}'."
        ),
    }


def accion_consultar_stock(datos):
    producto_buscado = datos.get("producto")

    productos = [
        producto
        for producto in obtener_productos()
        if producto.get("controla_stock") is True
    ]

    if producto_buscado:
        resolucion = resolver_producto(producto_buscado)

        if not resolucion["ok"]:
            return resolucion

        producto = resolucion["producto"]

        if not producto["controla_stock"]:
            return {
                "ok": False,
                "codigo": "PRODUCTO_SIN_CONTROL_STOCK",
                "mensaje": (
                    f"{producto['nombre']} no utiliza control "
                    "de stock por unidades."
                ),
            }

        return {
            "ok": True,
            "codigo": "ACCION_STOCK",
            "datos": {
                "productos": [producto],
            },
        }

    return {
        "ok": True,
        "codigo": "ACCION_STOCK",
        "datos": {
            "productos": productos,
        },
    }


def accion_consultar_precios(datos):
    producto_buscado = datos.get("producto")

    productos = [
        producto
        for producto in obtener_productos()
        if producto.get("precio_venta") is not None
    ]

    if producto_buscado:
        resolucion = resolver_producto(producto_buscado)

        if not resolucion["ok"]:
            return resolucion

        producto = resolucion["producto"]

        return {
            "ok": True,
            "codigo": "ACCION_PRECIOS",
            "datos": {
                "productos": [producto],
            },
        }

    return {
        "ok": True,
        "codigo": "ACCION_PRECIOS",
        "datos": {
            "productos": productos,
        },
    }


def accion_consultar_caja():
    return {
        "ok": True,
        "codigo": "ACCION_CAJA",
        "datos": obtener_estado_caja(),
    }


def accion_consultar_resumen(datos):
    periodo = normalizar_texto(datos.get("periodo"))

    if periodo == "hoy":
        fecha_hoy = datetime.now().strftime("%Y-%m-%d")

        resumen = resumen_por_periodo(
            fecha_hoy,
            fecha_hoy,
        )

    elif periodo == "semana":
        resumen = resumen_semana_actual()

    elif periodo == "mes":
        resumen = resumen_mes_actual()

    else:
        return {
            "ok": False,
            "codigo": "PERIODO_INVALIDO",
            "mensaje": (
                "El período debe ser 'hoy', 'semana' o 'mes'."
            ),
        }

    return {
        "ok": True,
        "codigo": "ACCION_RESUMEN",
        "datos": {
            "periodo": periodo,
            "resumen": resumen,
        },
    }


def accion_consultar_total(datos):
    tipo = normalizar_texto(datos.get("tipo"))
    periodo = normalizar_texto(datos.get("periodo"))

    if tipo not in {"ventas", "compras", "gastos"}:
        return {
            "ok": False,
            "codigo": "TIPO_RESUMEN_INVALIDO",
            "mensaje": (
                "El tipo debe ser 'ventas', 'compras' o 'gastos'."
            ),
        }

    resumen_resultado = accion_consultar_resumen(
        {"periodo": periodo}
    )

    if not resumen_resultado["ok"]:
        return resumen_resultado

    resumen = resumen_resultado["datos"]["resumen"]

    return {
        "ok": True,
        "codigo": "ACCION_TOTAL",
        "datos": {
            "tipo": tipo,
            "periodo": periodo,
            "total": resumen[tipo],
        },
    }


def accion_registrar_venta(datos):
    producto_texto = datos.get("producto")
    cantidad = datos.get("cantidad", 1)

    if not isinstance(producto_texto, str) or not producto_texto.strip():
        return {
            "ok": False,
            "codigo": "DATOS_ACCION_INVALIDOS",
            "mensaje": "La venta debe indicar un producto.",
        }

    if isinstance(cantidad, bool) or not isinstance(cantidad, int):
        return {
            "ok": False,
            "codigo": "DATOS_ACCION_INVALIDOS",
            "mensaje": "La cantidad debe ser un número entero.",
        }

    if cantidad <= 0:
        return {
            "ok": False,
            "codigo": "DATOS_ACCION_INVALIDOS",
            "mensaje": "La cantidad debe ser mayor que cero.",
        }

    resolucion = resolver_producto(producto_texto)

    if not resolucion["ok"]:
        return resolucion

    producto = resolucion["producto"]

    resultado = registrar_venta(
        id_producto=producto["id_producto"],
        cantidad=cantidad,
    )

    if not resultado["ok"]:
        return resultado

    return {
        "ok": True,
        "codigo": "ACCION_VENTA_REGISTRADA",
        "datos": {
            "id_venta": resultado["id_venta"],
            "id_producto": producto["id_producto"],
            "producto": resultado["producto"],
            "cantidad": resultado["cantidad"],
            "precio_unitario": resultado["precio_unitario"],
            "total": resultado["total"],
            "stock_restante": resultado["stock_restante"],
            "controla_stock": resultado["controla_stock"],
        },
    }




def accion_registrar_merma(datos):
    producto_texto = datos.get("producto")
    cantidad = datos.get("cantidad")
    motivo = datos.get("motivo") or "Merma"

    if not isinstance(producto_texto, str) or not producto_texto.strip():
        return {
            "ok": False,
            "codigo": "DATOS_ACCION_INVALIDOS",
            "mensaje": "La merma debe indicar un producto.",
        }

    if isinstance(cantidad, bool) or not isinstance(cantidad, int):
        return {
            "ok": False,
            "codigo": "DATOS_ACCION_INVALIDOS",
            "mensaje": "La cantidad debe ser un número entero.",
        }

    if cantidad <= 0:
        return {
            "ok": False,
            "codigo": "DATOS_ACCION_INVALIDOS",
            "mensaje": "La cantidad debe ser mayor que cero.",
        }

    resolucion = resolver_producto(producto_texto)

    if not resolucion["ok"]:
        return resolucion

    producto = resolucion["producto"]

    resultado = registrar_merma(
        id_producto=producto["id_producto"],
        cantidad=cantidad,
        motivo=motivo,
    )

    if not resultado["ok"]:
        return resultado

    return {
        "ok": True,
        "codigo": "ACCION_MERMA_REGISTRADA",
        "datos": resultado,
    }


def accion_registrar_consumo_interno(datos):
    producto_texto = datos.get("producto")
    cantidad = datos.get("cantidad")
    motivo = datos.get("motivo") or "Consumo interno"

    if not isinstance(producto_texto, str) or not producto_texto.strip():
        return {
            "ok": False,
            "codigo": "DATOS_ACCION_INVALIDOS",
            "mensaje": "El consumo interno debe indicar un producto.",
        }

    if isinstance(cantidad, bool) or not isinstance(cantidad, int):
        return {
            "ok": False,
            "codigo": "DATOS_ACCION_INVALIDOS",
            "mensaje": "La cantidad debe ser un número entero.",
        }

    if cantidad <= 0:
        return {
            "ok": False,
            "codigo": "DATOS_ACCION_INVALIDOS",
            "mensaje": "La cantidad debe ser mayor que cero.",
        }

    resolucion = resolver_producto(producto_texto)

    if not resolucion["ok"]:
        return resolucion

    producto = resolucion["producto"]

    resultado = registrar_consumo_interno(
        id_producto=producto["id_producto"],
        cantidad=cantidad,
        motivo=motivo,
    )

    if not resultado["ok"]:
        return resultado

    return {
        "ok": True,
        "codigo": "ACCION_CONSUMO_INTERNO_REGISTRADO",
        "datos": resultado,
    }


def accion_registrar_inventario(datos):
    producto_texto = datos.get("producto")
    cantidad_real = datos.get("cantidad_real")

    if not isinstance(producto_texto, str) or not producto_texto.strip():
        return {
            "ok": False,
            "codigo": "DATOS_ACCION_INVALIDOS",
            "mensaje": "El inventario debe indicar un producto.",
        }

    if isinstance(cantidad_real, bool) or not isinstance(cantidad_real, int):
        return {
            "ok": False,
            "codigo": "DATOS_ACCION_INVALIDOS",
            "mensaje": "La cantidad real debe ser un número entero.",
        }

    if cantidad_real < 0:
        return {
            "ok": False,
            "codigo": "DATOS_ACCION_INVALIDOS",
            "mensaje": "La cantidad real no puede ser negativa.",
        }

    resolucion = resolver_producto(producto_texto)

    if not resolucion["ok"]:
        return resolucion

    producto = resolucion["producto"]

    resultado = registrar_inventario_fisico(
        id_producto=producto["id_producto"],
        cantidad_real=cantidad_real,
    )

    if not resultado["ok"]:
        return resultado

    return {
        "ok": True,
        "codigo": "ACCION_INVENTARIO_REGISTRADO",
        "datos": resultado,
    }

def ejecutar_accion(solicitud):
    """
    Punto único de entrada para ejecutar acciones del negocio.

    Este contrato está pensado para ser utilizado desde:
    - WhatsApp
    - IA
    - voz / dispositivo tipo Jarvis
    - una interfaz web
    - integraciones futuras
    """

    if not isinstance(solicitud, dict):
        return {
            "ok": False,
            "codigo": "DATOS_ACCION_INVALIDOS",
            "mensaje": "La acción debe enviarse como un objeto.",
        }

    accion = normalizar_texto(solicitud.get("accion"))
    datos = solicitud.get("datos") or {}

    if not isinstance(datos, dict):
        return {
            "ok": False,
            "codigo": "DATOS_ACCION_INVALIDOS",
            "mensaje": "El campo datos debe ser un objeto.",
        }

    if accion == "consultar stock":
        return accion_consultar_stock(datos)

    if accion == "consultar precios":
        return accion_consultar_precios(datos)

    if accion == "consultar caja":
        return accion_consultar_caja()

    if accion == "consultar resumen":
        return accion_consultar_resumen(datos)

    if accion == "consultar total":
        return accion_consultar_total(datos)

    if accion == "registrar venta":
        return accion_registrar_venta(datos)

    if accion == "registrar merma":
        return accion_registrar_merma(datos)

    if accion == "registrar consumo interno":
        return accion_registrar_consumo_interno(datos)

    if accion == "registrar inventario":
        return accion_registrar_inventario(datos)

    return {
        "ok": False,
        "codigo": "ACCION_NO_RECONOCIDA",
        "mensaje": f"No existe la acción '{solicitud.get('accion')}'.",
    }
