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
from ventas import (
    anular_operacion_venta,
    anular_ultima_operacion_venta,
    registrar_venta,
    registrar_venta_multiple,
)


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
    "sandwich": "sanguche",
    "sándwich": "sanguche",
    "sandwiches": "sanguche",
    "sanguches": "sanguche",
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


def _categoria_coincide(producto, tipo):
    categoria = normalizar_texto(
        producto.get("categoria")
    )

    equivalencias = {
        "sanguche": {"sanguches", "sanguche"},
        "hamburguesa": {"hamburguesas", "hamburguesa"},
        "bebida": {"bebidas", "bebida"},
        "postre": {"postres", "postre"},
    }

    if tipo in equivalencias:
        return categoria in equivalencias[tipo]

    return False


def _resolver_por_tipo_y_precio(consulta, productos):
    coincidencia = re.match(
        r"^(sanguche|sandwich|hamburguesa|bebida|postre)"
        r"(?:\s+de)?\s+\$?(\d[\d\.]*)$",
        consulta
    )

    if not coincidencia:
        return None

    tipo = coincidencia.group(1)

    if tipo == "sandwich":
        tipo = "sanguche"

    precio_texto = coincidencia.group(2).replace(".", "")

    try:
        precio = float(precio_texto)
    except ValueError:
        return None

    candidatos = [
        producto
        for producto in productos
        if _categoria_coincide(producto, tipo)
        and producto.get("precio_venta") is not None
        and float(producto["precio_venta"]) == precio
    ]

    if len(candidatos) == 1:
        return {
            "ok": True,
            "producto": candidatos[0],
        }

    if len(candidatos) > 1:
        return {
            "ok": False,
            "codigo": "PRODUCTO_AMBIGUO",
            "mensaje": (
                "Hay más de un producto de ese tipo con ese precio."
            ),
            "candidatos": [
                {
                    "id_producto": producto["id_producto"],
                    "nombre": producto["nombre"],
                    "precio_venta": producto["precio_venta"],
                }
                for producto in candidatos
            ],
        }

    return {
        "ok": False,
        "codigo": "PRODUCTO_NO_ENCONTRADO",
        "mensaje": (
            f"No encontré un {tipo} con precio "
            f"{formatear_pesos(precio)}."
        ),
    }


def _resolver_categoria_generica(consulta, productos):
    tipos = {
        "hamburguesa": "hamburguesa",
        "hamburguesa simple": "hamburguesa",
        "hamburguesa doble": "hamburguesa",
        "sanguche": "sanguche",
        "sandwich": "sanguche",
        "postre": "postre",
        "bebida": "bebida",
    }

    tipo = None
    resto = consulta

    for prefijo, tipo_equivalente in sorted(
        tipos.items(),
        key=lambda item: len(item[0]),
        reverse=True
    ):
        if consulta == prefijo or consulta.startswith(prefijo + " "):
            tipo = tipo_equivalente
            resto = consulta[len(prefijo):].strip()

            if "simple" in prefijo:
                resto = "simple " + resto
            elif "doble" in prefijo:
                resto = "doble " + resto

            break

    if not tipo:
        return None

    candidatos = [
        producto
        for producto in productos
        if _categoria_coincide(producto, tipo)
    ]

    if resto:
        tokens = set(resto.split())
        filtrados = []

        for producto in candidatos:
            nombre = normalizar_texto(producto["nombre"])
            if tokens.issubset(set(nombre.split())):
                filtrados.append(producto)

        candidatos = filtrados

    if len(candidatos) == 1:
        return {
            "ok": True,
            "producto": candidatos[0],
        }

    if len(candidatos) > 1:
        return {
            "ok": False,
            "codigo": "PRODUCTO_AMBIGUO",
            "mensaje": "Necesito que especifiques cuál producto.",
            "candidatos": [
                {
                    "id_producto": producto["id_producto"],
                    "nombre": producto["nombre"],
                    "precio_venta": producto["precio_venta"],
                }
                for producto in candidatos
            ],
        }

    return None


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

    por_tipo_y_precio = _resolver_por_tipo_y_precio(
        consulta,
        productos
    )

    if por_tipo_y_precio is not None:
        return por_tipo_y_precio

    por_categoria = _resolver_categoria_generica(
        consulta,
        productos
    )

    if por_categoria is not None:
        return por_categoria

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
        contexto=datos.get("contexto"),
    )

    if not resultado["ok"]:
        return resultado

    return {
        "ok": True,
        "codigo": "ACCION_VENTA_REGISTRADA",
        "datos": {
            "id_venta": resultado["id_venta"],
            "id_operacion": resultado["id_operacion"],
            "estado_pago": resultado["estado_pago"],
            "id_producto": producto["id_producto"],
            "producto": resultado["producto"],
            "cantidad": resultado["cantidad"],
            "precio_unitario": resultado["precio_unitario"],
            "total": resultado["total"],
            "stock_restante": resultado["stock_restante"],
            "controla_stock": resultado["controla_stock"],
        },
    }




def accion_registrar_venta_multiple(datos):
    items = datos.get("items")

    if not isinstance(items, list) or not items:
        return {
            "ok": False,
            "codigo": "DATOS_ACCION_INVALIDOS",
            "mensaje": "La venta debe contener al menos un producto.",
        }

    items_resueltos = []

    for indice, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            return {
                "ok": False,
                "codigo": "DATOS_ACCION_INVALIDOS",
                "mensaje": (
                    f"El item {indice} de la venta no es válido."
                ),
            }

        producto_texto = item.get("producto")
        cantidad = item.get("cantidad", 1)

        if (
            not isinstance(producto_texto, str)
            or not producto_texto.strip()
        ):
            return {
                "ok": False,
                "codigo": "DATOS_ACCION_INVALIDOS",
                "mensaje": (
                    f"El item {indice} debe indicar un producto."
                ),
            }

        if isinstance(cantidad, bool) or not isinstance(cantidad, int):
            return {
                "ok": False,
                "codigo": "DATOS_ACCION_INVALIDOS",
                "mensaje": (
                    f"La cantidad del item {indice} "
                    "debe ser un número entero."
                ),
            }

        if cantidad <= 0:
            return {
                "ok": False,
                "codigo": "DATOS_ACCION_INVALIDOS",
                "mensaje": (
                    f"La cantidad del item {indice} "
                    "debe ser mayor que cero."
                ),
            }

        resolucion = resolver_producto(producto_texto)

        if not resolucion["ok"]:
            resultado = dict(resolucion)
            resultado["item"] = indice
            return resultado

        producto = resolucion["producto"]

        item_resuelto = {
            "id_producto": producto["id_producto"],
            "cantidad": cantidad,
        }

        precio_unitario = item.get("precio_unitario")

        if precio_unitario is not None:
            item_resuelto["precio_unitario"] = precio_unitario

        items_resueltos.append(item_resuelto)

    resultado = registrar_venta_multiple(
        items=items_resueltos,
        contexto=datos.get("contexto"),
    )

    if not resultado["ok"]:
        return resultado

    datos_resultado = {
        clave: valor
        for clave, valor in resultado.items()
        if clave not in {"ok", "codigo", "mensaje"}
    }

    return {
        "ok": True,
        "codigo": "ACCION_VENTA_MULTIPLE_REGISTRADA",
        "datos": datos_resultado,
    }


def accion_anular_operacion_venta(datos):
    id_operacion = datos.get("id_operacion")
    motivo = (
        datos.get("motivo")
        or "Corrección solicitada por el usuario"
    )

    resultado = anular_operacion_venta(
        id_operacion=id_operacion,
        motivo=motivo,
        contexto=datos.get("contexto"),
    )

    if not resultado["ok"]:
        return resultado

    datos_resultado = {
        clave: valor
        for clave, valor in resultado.items()
        if clave not in {"ok", "codigo", "mensaje"}
    }

    return {
        "ok": True,
        "codigo": "ACCION_OPERACION_VENTA_ANULADA",
        "datos": datos_resultado,
    }


def accion_anular_ultima_venta(datos):
    motivo = (
        datos.get("motivo")
        or "Corrección de última venta"
    )

    resultado = anular_ultima_operacion_venta(
        motivo=motivo,
        contexto=datos.get("contexto"),
    )

    if not resultado["ok"]:
        return resultado

    datos_resultado = {
        clave: valor
        for clave, valor in resultado.items()
        if clave not in {"ok", "codigo", "mensaje"}
    }

    return {
        "ok": True,
        "codigo": "ACCION_ULTIMA_VENTA_ANULADA",
        "datos": datos_resultado,
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

    datos_resultado = {
        clave: valor
        for clave, valor in resultado.items()
        if clave not in {"ok", "codigo", "mensaje"}
    }

    return {
        "ok": True,
        "codigo": "ACCION_MERMA_REGISTRADA",
        "datos": datos_resultado,
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

    datos_resultado = {
        clave: valor
        for clave, valor in resultado.items()
        if clave not in {"ok", "codigo", "mensaje"}
    }

    return {
        "ok": True,
        "codigo": "ACCION_CONSUMO_INTERNO_REGISTRADO",
        "datos": datos_resultado,
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

    datos_resultado = {
        clave: valor
        for clave, valor in resultado.items()
        if clave not in {"ok", "codigo", "mensaje"}
    }

    return {
        "ok": True,
        "codigo": "ACCION_INVENTARIO_REGISTRADO",
        "datos": datos_resultado,
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
        if "items" in datos:
            return accion_registrar_venta_multiple(datos)

        return accion_registrar_venta(datos)

    if accion == "registrar venta multiple":
        return accion_registrar_venta_multiple(datos)

    if accion == "anular operacion venta":
        return accion_anular_operacion_venta(datos)

    if accion == "anular ultima venta":
        return accion_anular_ultima_venta(datos)

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
