import unicodedata

from caja import obtener_estado_caja
from productos import obtener_productos
from reportes import (
    resumen_mes_actual,
    resumen_por_periodo,
    resumen_semana_actual,
)
from datetime import datetime


def normalizar_texto(texto):
    if not isinstance(texto, str):
        return ""

    texto = texto.strip().lower()

    texto = "".join(
        caracter
        for caracter in unicodedata.normalize("NFD", texto)
        if unicodedata.category(caracter) != "Mn"
    )

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
    productos = obtener_productos()

    if not productos:
        return "No hay productos registrados."

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


def mensaje_ayuda():
    return "\n".join([
        "*Comandos disponibles*",
        "- stock",
        "- ver stock",
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
