import re

from acciones import (
    ejecutar_accion,
    formatear_pesos,
    normalizar_texto,
)


def error_comando(resultado):
    if resultado.get("codigo") == "PRODUCTO_AMBIGUO":
        candidatos = resultado.get("candidatos", [])

        nombres = ", ".join(
            candidato["nombre"]
            for candidato in candidatos
        )

        respuesta = (
            "El producto es ambiguo. "
            f"Coincide con: {nombres}."
        )

    else:
        respuesta = resultado.get(
            "mensaje",
            "No se pudo ejecutar la acción."
        )

    return {
        "ok": False,
        "codigo": resultado.get(
            "codigo",
            "ERROR_COMANDO"
        ),
        "respuesta": respuesta,
    }


def formatear_stock(productos):
    if not productos:
        return "No hay productos con control de stock."

    lineas = ["*Stock actual*"]

    for producto in productos:
        lineas.append(
            f"- {producto['nombre']}: {producto['stock']}"
        )

    return "\n".join(lineas)


def formatear_precios(productos):
    if not productos:
        return "No hay precios configurados."

    categorias = {}

    for producto in productos:
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


def formatear_caja(estado):
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




def interpretar_salida_stock(texto, accion, prefijos, titulo):
    prefijo_usado = next(
        (
            prefijo
            for prefijo in prefijos
            if texto.startswith(prefijo)
        ),
        None
    )

    if prefijo_usado is None:
        return {
            "ok": False,
            "codigo": "FORMATO_MOVIMIENTO_STOCK_INVALIDO",
            "respuesta": "No se pudo interpretar el movimiento de stock.",
        }

    contenido = texto[len(prefijo_usado):].strip()

    coincidencia = re.match(
        r"^x?(\d+)\s+(.+)$",
        contenido
    )

    if not coincidencia:
        return {
            "ok": False,
            "codigo": "FORMATO_MOVIMIENTO_STOCK_INVALIDO",
            "respuesta": (
                "Usá cantidad y producto. "
                "Ejemplo: merma 2 pepsi"
            ),
        }

    cantidad = int(coincidencia.group(1))
    producto = coincidencia.group(2).strip()

    resultado = ejecutar_accion({
        "accion": accion,
        "datos": {
            "producto": producto,
            "cantidad": cantidad,
        },
    })

    if not resultado["ok"]:
        return error_comando(resultado)

    datos = resultado["datos"]

    return {
        **datos,
        "ok": True,
        "codigo": resultado["codigo"],
        "respuesta": "\n".join([
            f"*{titulo}*",
            f"{cantidad} x {datos['producto']}",
            f"Stock anterior: {datos['stock_anterior']}",
            f"Stock actual: {datos['stock_nuevo']}",
            f"Motivo: {datos['motivo']}",
        ]),
    }


def interpretar_inventario(texto):
    contenido = texto[len("inventario"):].strip()

    if not contenido:
        return {
            "ok": False,
            "codigo": "FORMATO_INVENTARIO_INVALIDO",
            "respuesta": (
                "Indicá producto y cantidad contada. "
                "Ejemplo: inventario pepsi 8"
            ),
        }

    coincidencia = re.match(
        r"^(.+?)\s+(\d+)$",
        contenido
    )

    if not coincidencia:
        return {
            "ok": False,
            "codigo": "FORMATO_INVENTARIO_INVALIDO",
            "respuesta": (
                "Usá producto y cantidad contada. "
                "Ejemplo: inventario pepsi 8"
            ),
        }

    producto = coincidencia.group(1).strip()
    cantidad_real = int(coincidencia.group(2))

    resultado = ejecutar_accion({
        "accion": "registrar_inventario",
        "datos": {
            "producto": producto,
            "cantidad_real": cantidad_real,
        },
    })

    if not resultado["ok"]:
        return error_comando(resultado)

    datos = resultado["datos"]

    if datos.get("ajuste") == 0:
        respuesta = "\n".join([
            "*Inventario verificado*",
            f"{datos['producto']}: {datos['stock_contado']}",
            "Sin diferencias con el sistema.",
        ])

    else:
        respuesta = "\n".join([
            "*Inventario actualizado*",
            f"{datos['producto']}",
            f"Stock anterior: {datos['stock_anterior']}",
            f"Stock contado: {cantidad_real}",
            f"Ajuste: {datos['ajuste']:+d}",
            f"Stock actual: {datos['stock_nuevo']}",
        ])

    return {
        **datos,
        "ok": True,
        "codigo": resultado["codigo"],
        "respuesta": respuesta,
    }

def interpretar_item_venta(texto_item):
    texto_item = texto_item.strip()

    if not texto_item:
        return None

    cantidad = 1
    texto_producto = texto_item

    coincidencia_inicio = re.match(
        r"^x?(\d+)\s+(.+)$",
        texto_item
    )

    if coincidencia_inicio:
        cantidad = int(coincidencia_inicio.group(1))
        texto_producto = coincidencia_inicio.group(2).strip()

    else:
        coincidencia_final = re.match(
            r"^(.+?)\s+x(\d+)$",
            texto_item
        )

        if coincidencia_final:
            texto_producto = coincidencia_final.group(1).strip()
            cantidad = int(coincidencia_final.group(2))

    return {
        "producto": texto_producto,
        "cantidad": cantidad,
    }


def interpretar_venta(texto):
    contenido = texto[len("venta"):].strip()

    if not contenido:
        return {
            "ok": False,
            "codigo": "FORMATO_VENTA_INVALIDO",
            "respuesta": (
                "Indicá el producto. "
                "Ejemplo: venta 2 manaos cola 600"
            ),
        }

    partes = re.split(
        r",\s*|\s+y\s+(?=x?\d+\s)",
        contenido
    )

    items = [
        interpretar_item_venta(parte)
        for parte in partes
        if parte.strip()
    ]

    if not items:
        return {
            "ok": False,
            "codigo": "FORMATO_VENTA_INVALIDO",
            "respuesta": "No se pudo interpretar la venta.",
        }

    if len(items) == 1:
        item = items[0]

        resultado = ejecutar_accion({
            "accion": "registrar_venta",
            "datos": item,
        })

        if not resultado["ok"]:
            return error_comando(resultado)

        datos = resultado["datos"]

        lineas = [
            "*Venta registrada*",
            f"{datos['cantidad']} x {datos['producto']}",
            (
                "Precio unitario: "
                f"{formatear_pesos(datos['precio_unitario'])}"
            ),
            f"Total: {formatear_pesos(datos['total'])}",
        ]

        if datos["controla_stock"]:
            lineas.append(
                f"Stock restante: {datos['stock_restante']}"
            )

        return {
            **datos,
            "ok": True,
            "codigo": "COMANDO_VENTA_REGISTRADA",
            "respuesta": "\n".join(lineas),
        }

    resultado = ejecutar_accion({
        "accion": "registrar_venta",
        "datos": {
            "items": items,
        },
    })

    if not resultado["ok"]:
        return error_comando(resultado)

    datos = resultado["datos"]

    lineas = ["*Venta registrada*"]

    for item in datos["items"]:
        linea = (
            f"- {item['cantidad']} x {item['producto']}: "
            f"{formatear_pesos(item['subtotal'])}"
        )

        if item["controla_stock"]:
            linea += (
                f" | stock: {item['stock_restante']}"
            )

        lineas.append(linea)

    lineas.append(
        f"*Total: {formatear_pesos(datos['total'])}*"
    )

    return {
        **datos,
        "ok": True,
        "codigo": "COMANDO_VENTA_MULTIPLE_REGISTRADA",
        "respuesta": "\n".join(lineas),
    }


def mensaje_ayuda():
    return "\n".join([
        "*Comandos disponibles*",
        "- venta 2 manaos cola 600",
        "- venta big mac doble",
        "- venta 2 pepsi, 1 chocotorta y 2 big mac doble",
        "- merma 2 pepsi",
        "- consumo 1 oreo",
        "- inventario pepsi 8",
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

    if texto.startswith("merma ") or texto.startswith("perdida "):
        return interpretar_salida_stock(
            texto=texto,
            accion="registrar_merma",
            prefijos=("merma", "perdida"),
            titulo="Merma registrada",
        )

    if (
        texto.startswith("consumo interno ")
        or texto.startswith("consumo ")
    ):
        return interpretar_salida_stock(
            texto=texto,
            accion="registrar_consumo_interno",
            prefijos=("consumo interno", "consumo"),
            titulo="Consumo interno registrado",
        )

    if texto.startswith("inventario"):
        return interpretar_inventario(texto)

    if texto in {"ayuda", "menu", "comandos"}:
        return {
            "ok": True,
            "codigo": "COMANDO_AYUDA",
            "respuesta": mensaje_ayuda(),
        }

    if texto in {"stock", "ver stock"}:
        resultado = ejecutar_accion({
            "accion": "consultar_stock",
            "datos": {},
        })

        if not resultado["ok"]:
            return error_comando(resultado)

        return {
            "ok": True,
            "codigo": "COMANDO_STOCK",
            "respuesta": formatear_stock(
                resultado["datos"]["productos"]
            ),
        }

    if texto in {"precios", "ver precios"}:
        resultado = ejecutar_accion({
            "accion": "consultar_precios",
            "datos": {},
        })

        if not resultado["ok"]:
            return error_comando(resultado)

        return {
            "ok": True,
            "codigo": "COMANDO_PRECIOS",
            "respuesta": formatear_precios(
                resultado["datos"]["productos"]
            ),
        }

    if texto == "caja":
        resultado = ejecutar_accion({
            "accion": "consultar_caja",
            "datos": {},
        })

        if not resultado["ok"]:
            return error_comando(resultado)

        return {
            "ok": True,
            "codigo": "COMANDO_CAJA",
            "respuesta": formatear_caja(
                resultado["datos"]
            ),
        }

    resumenes = {
        "balance hoy": ("hoy", "Resumen de hoy", "COMANDO_RESUMEN_HOY"),
        "resumen hoy": ("hoy", "Resumen de hoy", "COMANDO_RESUMEN_HOY"),
        "balance semana": (
            "semana",
            "Resumen de la semana",
            "COMANDO_RESUMEN_SEMANA",
        ),
        "resumen semana": (
            "semana",
            "Resumen de la semana",
            "COMANDO_RESUMEN_SEMANA",
        ),
        "balance mes": (
            "mes",
            "Resumen del mes",
            "COMANDO_RESUMEN_MES",
        ),
        "resumen mes": (
            "mes",
            "Resumen del mes",
            "COMANDO_RESUMEN_MES",
        ),
    }

    if texto in resumenes:
        periodo, titulo, codigo = resumenes[texto]

        resultado = ejecutar_accion({
            "accion": "consultar_resumen",
            "datos": {
                "periodo": periodo,
            },
        })

        if not resultado["ok"]:
            return error_comando(resultado)

        return {
            "ok": True,
            "codigo": codigo,
            "respuesta": formatear_resumen(
                titulo,
                resultado["datos"]["resumen"],
            ),
        }

    if texto in {"ventas hoy", "compras hoy", "gastos hoy"}:
        tipo = texto.split()[0]

        resultado = ejecutar_accion({
            "accion": "consultar_total",
            "datos": {
                "tipo": tipo,
                "periodo": "hoy",
            },
        })

        if not resultado["ok"]:
            return error_comando(resultado)

        etiquetas = {
            "ventas": "Ventas de hoy",
            "compras": "Compras de hoy",
            "gastos": "Gastos de hoy",
        }

        return {
            "ok": True,
            "codigo": f"COMANDO_{tipo.upper()}_HOY",
            "respuesta": (
                f"*{etiquetas[tipo]}*\n"
                f"{formatear_pesos(resultado['datos']['total'])}"
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
