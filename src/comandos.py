from datetime import datetime
import re
import unicodedata

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

    # Facilita comparar "600ml" con "600 ml" y "2.25l" con "2.25 l".
    texto = re.sub(r"(?<=\d)(?=[a-z])", " ", texto)
    texto = re.sub(r"(?<=[a-z])(?=\d)", " ", texto)

    # Los signos no son relevantes para identificar productos.
    texto = texto.replace("+", " ")
    texto = texto.replace("-", " ")
    texto = texto.replace("/", " ")

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


def formatear_stock():
    productos = [
        producto
        for producto in obtener_productos()
        if producto.get("controla_stock") is True
    ]

    if not productos:
        return "No hay productos con control de stock."

    lineas = ["*Stock actual*"]

    for producto in productos:
        lineas.append(
            f"- {producto['nombre']}: {producto['stock']}"
        )

    return "\n".join(lineas)


def formatear_resumen(titulo, resumen):
    return "\n".join([
        f"*{titulo}*",
        f"Ventas: {formatear_pesos(resumen['ventas'])}",
        f"Compras: {formatear_pesos(resumen['compras'])}",
        f"Gastos: {formatear_pesos(resumen['gastos'])}",
        (
            "Resultado negocio: "
            f"{formatear_pesos(resumen['resultado_negocio'])}"
        ),
        f"Aportes: {formatear_pesos(resumen['aportes'])}",
        f"Retiros: {formatear_pesos(resumen['retiros'])}",
        f"Saldo de caja: {formatear_pesos(resumen['saldo_caja'])}",
    ])


def formatear_caja():
    estado = obtener_estado_caja()

    return "\n".join([
        "*Estado de caja*",
        f"Ventas: {formatear_pesos(estado['ventas'])}",
        f"Compras: {formatear_pesos(estado['compras'])}",
        f"Gastos: {formatear_pesos(estado['gastos'])}",
        (
            "Resultado negocio: "
            f"{formatear_pesos(estado['resultado_negocio'])}"
        ),
        f"Aportes: {formatear_pesos(estado['aportes'])}",
        f"Retiros: {formatear_pesos(estado['retiros'])}",
        f"Saldo de caja: {formatear_pesos(estado['saldo_caja'])}",
        f"Diezmo reservado: {formatear_pesos(estado['diezmo_reservado'])}",
        f"Diezmo entregado: {formatear_pesos(estado['diezmo_entregado'])}",
        f"Saldo físico: {formatear_pesos(estado['saldo_fisico'])}",
        f"Saldo disponible: {formatear_pesos(estado['saldo_disponible'])}",
    ])


def formatear_precios():
    productos = obtener_productos()

    con_precio = [
        producto
        for producto in productos
        if producto.get("precio_venta") is not None
    ]

    if not con_precio:
        return "No hay precios configurados."

    categorias = {}

    for producto in con_precio:
        categoria = producto["categoria"]
        categorias.setdefault(categoria, []).append(producto)

    lineas = ["*Lista de precios*"]

    for categoria, items in categorias.items():
        lineas.append(f"\n*{categoria}*")

        for producto in items:
            lineas.append(
                f"- {producto['nombre']}: "
                f"{formatear_pesos(producto['precio_venta'])}"
            )

    return "\n".join(lineas)


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

    # Coincidencia exacta.
    for producto, nombre_normalizado in normalizados:
        if consulta == nombre_normalizado:
            return {
                "ok": True,
                "producto": producto,
            }

    # Coincidencia por palabras: permite "chico pollo papas",
    # "manaos cola 600", etc.
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
        nombres = ", ".join(
            producto["nombre"]
            for producto in candidatos
        )

        return {
            "ok": False,
            "codigo": "PRODUCTO_AMBIGUO",
            "mensaje": (
                "El producto es ambiguo. "
                f"Coincide con: {nombres}."
            ),
        }

    return {
        "ok": False,
        "codigo": "PRODUCTO_NO_ENCONTRADO",
        "mensaje": (
            f"No encontré un producto que coincida con "
            f"'{texto_producto.strip()}'."
        ),
    }


def interpretar_venta(texto):
    contenido = texto[len("venta"):].strip()

    if not contenido:
        return {
            "ok": False,
            "codigo": "FORMATO_VENTA_INVALIDO",
            "mensaje": (
                "Indicá el producto. "
                "Ejemplo: venta 2 manaos cola 600"
            ),
        }

    cantidad = 1
    texto_producto = contenido

    # Formatos aceptados:
    # venta 2 manaos cola 600
    # venta x2 manaos cola 600
    coincidencia_inicio = re.match(
        r"^x?(\d+)\s+(.+)$",
        contenido
    )

    if coincidencia_inicio:
        cantidad = int(coincidencia_inicio.group(1))
        texto_producto = coincidencia_inicio.group(2).strip()

    else:
        # venta manaos cola 600 x2
        coincidencia_final = re.match(
            r"^(.+?)\s+x(\d+)$",
            contenido
        )

        if coincidencia_final:
            texto_producto = coincidencia_final.group(1).strip()
            cantidad = int(coincidencia_final.group(2))

    if cantidad <= 0:
        return {
            "ok": False,
            "codigo": "FORMATO_VENTA_INVALIDO",
            "mensaje": "La cantidad de la venta debe ser mayor que cero.",
        }

    resolucion = resolver_producto(texto_producto)

    if not resolucion["ok"]:
        return {
            "ok": False,
            "codigo": resolucion["codigo"],
            "respuesta": resolucion["mensaje"],
        }

    producto = resolucion["producto"]

    resultado = registrar_venta(
        id_producto=producto["id_producto"],
        cantidad=cantidad,
    )

    if not resultado["ok"]:
        return {
            "ok": False,
            "codigo": resultado["codigo"],
            "respuesta": resultado["mensaje"],
        }

    lineas = [
        "*Venta registrada*",
        f"{resultado['cantidad']} x {resultado['producto']}",
        f"Precio unitario: {formatear_pesos(resultado['precio_unitario'])}",
        f"Total: {formatear_pesos(resultado['total'])}",
    ]

    if resultado["controla_stock"]:
        lineas.append(
            f"Stock restante: {resultado['stock_restante']}"
        )

    return {
        "ok": True,
        "codigo": "COMANDO_VENTA_REGISTRADA",
        "respuesta": "\n".join(lineas),
        "id_venta": resultado["id_venta"],
        "id_producto": producto["id_producto"],
        "producto": resultado["producto"],
        "cantidad": resultado["cantidad"],
        "precio_unitario": resultado["precio_unitario"],
        "total": resultado["total"],
        "stock_restante": resultado["stock_restante"],
    }


def mensaje_ayuda():
    return "\n".join([
        "*Comandos disponibles*",
        "- venta 2 manaos cola 600",
        "- venta big mac doble",
        "- stock",
        "- ver stock",
        "- precios",
        "- caja",
        "- balance hoy",
        "- resumen hoy",
        "- ventas hoy",
        "- compras hoy",
        "- gastos hoy",
        "- balance semana",
        "- resumen semana",
        "- balance mes",
        "- resumen mes",
        "- ayuda",
    ])


def procesar_comando(mensaje):
    texto = normalizar_texto(mensaje)

    if not texto:
        return {
            "ok": False,
            "codigo": "MENSAJE_VACIO",
            "respuesta": "El mensaje no puede estar vacío.",
        }

    if texto.startswith("venta"):
        return interpretar_venta(texto)

    if texto in {"ayuda", "menu", "comandos"}:
        return {
            "ok": True,
            "codigo": "COMANDO_AYUDA",
            "respuesta": mensaje_ayuda(),
        }

    if texto in {"stock", "ver stock"}:
        return {
            "ok": True,
            "codigo": "COMANDO_STOCK",
            "respuesta": formatear_stock(),
        }

    if texto in {"precios", "ver precios"}:
        return {
            "ok": True,
            "codigo": "COMANDO_PRECIOS",
            "respuesta": formatear_precios(),
        }

    if texto == "caja":
        return {
            "ok": True,
            "codigo": "COMANDO_CAJA",
            "respuesta": formatear_caja(),
        }

    if texto in {"balance hoy", "resumen hoy"}:
        fecha_hoy = datetime.now().strftime("%Y-%m-%d")

        resumen = resumen_por_periodo(
            fecha_hoy,
            fecha_hoy,
        )

        return {
            "ok": True,
            "codigo": "COMANDO_RESUMEN_HOY",
            "respuesta": formatear_resumen(
                "Resumen de hoy",
                resumen,
            ),
        }

    if texto in {"balance semana", "resumen semana"}:
        resumen = resumen_semana_actual()

        return {
            "ok": True,
            "codigo": "COMANDO_RESUMEN_SEMANA",
            "respuesta": formatear_resumen(
                "Resumen de la semana",
                resumen,
            ),
        }

    if texto in {"balance mes", "resumen mes"}:
        resumen = resumen_mes_actual()

        return {
            "ok": True,
            "codigo": "COMANDO_RESUMEN_MES",
            "respuesta": formatear_resumen(
                "Resumen del mes",
                resumen,
            ),
        }

    if texto in {"ventas hoy", "compras hoy", "gastos hoy"}:
        fecha_hoy = datetime.now().strftime("%Y-%m-%d")

        resumen = resumen_por_periodo(
            fecha_hoy,
            fecha_hoy,
        )

        campo = texto.split()[0]

        etiquetas = {
            "ventas": "Ventas de hoy",
            "compras": "Compras de hoy",
            "gastos": "Gastos de hoy",
        }

        return {
            "ok": True,
            "codigo": f"COMANDO_{campo.upper()}_HOY",
            "respuesta": (
                f"*{etiquetas[campo]}*\n"
                f"{formatear_pesos(resumen[campo])}"
            ),
        }

    return {
        "ok": False,
        "codigo": "COMANDO_NO_RECONOCIDO",
        "respuesta": (
            "No entendí el comando. "
            "Escribí 'ayuda' para ver las opciones disponibles."
        ),
    }
