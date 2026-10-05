import re

from acciones import (
    ejecutar_accion,
    formatear_pesos,
    normalizar_texto,
)
from contexto_conversacion import (
    activar_contexto,
    obtener_contexto_activo,
    tocar_contexto,
)
from productos import obtener_productos


def error_comando(resultado):
    if resultado.get("codigo") == "PRODUCTO_AMBIGUO":
        candidatos = resultado.get("candidatos", [])

        opciones = []

        for candidato in candidatos:
            texto = candidato["nombre"]

            if candidato.get("precio_venta") is not None:
                texto += (
                    " "
                    f"({formatear_pesos(candidato['precio_venta'])})"
                )

            opciones.append(texto)

        respuesta = (
            "Necesito que especifiques cuál producto. "
            "Opciones: "
            + ", ".join(opciones)
            + "."
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


def interpretar_venta(
    texto,
    contexto=None
):
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

        datos_accion = dict(item)
        datos_accion["contexto"] = contexto or {}

        resultado = ejecutar_accion({
            "accion": "registrar_venta",
            "datos": datos_accion,
        })

        if not resultado["ok"]:
            return error_comando(resultado)

        datos = resultado["datos"]

        lineas = [
            "*Venta registrada*",
            f"Operación: #{datos['id_operacion']}",
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
            "contexto": contexto or {},
        },
    })

    if not resultado["ok"]:
        return error_comando(resultado)

    datos = resultado["datos"]

    lineas = [
        "*Venta registrada*",
        f"Operación: #{datos['id_operacion']}",
    ]

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


def interpretar_anulacion_venta(
    texto,
    contexto=None
):
    if texto in {
        "anular ultima venta",
        "anular ultimo",
        "borrar ultima venta",
        "borrar ultimo",
        "eliminar ultima venta",
        "eliminar ultimo",
    }:
        resultado = ejecutar_accion({
            "accion": "anular_ultima_venta",
            "datos": {
                "motivo": "Corrección solicitada por WhatsApp",
                "contexto": contexto or {},
            },
        })

    else:
        coincidencia = re.match(
            r"^anular\s+operacion\s+(\d+)$",
            texto
        )

        if not coincidencia:
            return {
                "ok": False,
                "codigo": "FORMATO_ANULACION_INVALIDO",
                "respuesta": (
                    "Usá 'anular ultima venta' o "
                    "'anular operacion 14'."
                ),
            }

        resultado = ejecutar_accion({
            "accion": "anular_operacion_venta",
            "datos": {
                "id_operacion": int(
                    coincidencia.group(1)
                ),
                "motivo": "Corrección solicitada por WhatsApp",
                "contexto": contexto or {},
            },
        })

    if not resultado["ok"]:
        return error_comando(resultado)

    datos = resultado["datos"]

    lineas = [
        "*Venta anulada*",
        f"Operación: #{datos['id_operacion']}",
    ]

    for item in datos["items"]:
        lineas.append(
            f"- {item['cantidad']} x {item['producto']}: "
            f"{formatear_pesos(item['subtotal'])}"
        )

    lineas.append(
        f"*Total anulado: "
        f"{formatear_pesos(datos['total_anulado'])}*"
    )

    return {
        **datos,
        "ok": True,
        "codigo": resultado["codigo"],
        "respuesta": "\n".join(lineas),
    }



PALABRAS_CANTIDAD = {
    "un": 1,
    "una": 1,
    "uno": 1,
    "dos": 2,
    "tres": 3,
    "cuatro": 4,
    "cinco": 5,
    "seis": 6,
}


def normalizar_cantidad_escrita(texto):
    partes = texto.split()

    if not partes:
        return texto

    primera = partes[0]

    if primera in PALABRAS_CANTIDAD:
        partes[0] = str(
            PALABRAS_CANTIDAD[primera]
        )

    return " ".join(partes)


def normalizar_importe(texto):
    if texto is None:
        return None

    valor = normalizar_texto(
        str(texto)
    )

    valor = valor.replace("$", "").strip()
    valor = valor.replace("mil", "000")
    valor = valor.replace(".", "")
    valor = valor.replace(" ", "")

    if not valor.isdigit():
        return None

    numero = int(valor)

    # En el grupo "6", "7", "8", "9", etc. significan miles.
    if 1 <= numero < 100:
        numero *= 1000

    return numero


def _categoria_precio_coincide(
    producto,
    contexto_activo
):
    categoria = normalizar_texto(
        producto.get("categoria")
    )

    if contexto_activo == "postres":
        return categoria == "postres"

    if contexto_activo == "bebidas":
        return categoria == "bebidas"

    if contexto_activo == "comida":
        return categoria not in {
            "postres",
            "bebidas",
        }

    return True


def resolver_producto_por_precio(
    precio,
    contexto_activo=None
):
    candidatos = [
        producto
        for producto in obtener_productos()
        if producto.get("precio_venta") is not None
        and float(producto["precio_venta"]) == float(precio)
        and _categoria_precio_coincide(
            producto,
            contexto_activo
        )
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
            "candidatos": [
                {
                    "id_producto": producto["id_producto"],
                    "nombre": producto["nombre"],
                    "precio_venta": producto["precio_venta"],
                }
                for producto in candidatos
            ],
            "mensaje": (
                "Ese precio coincide con más de un producto."
            ),
        }

    return {
        "ok": False,
        "codigo": "PRODUCTO_NO_ENCONTRADO",
        "mensaje": (
            "No encontré un producto con precio "
            f"{formatear_pesos(precio)}."
        ),
    }


def interpretar_venta_por_precio(
    texto,
    contexto=None,
    contexto_activo=None
):
    texto = normalizar_cantidad_escrita(
        normalizar_texto(texto)
    )

    coincidencia = re.match(
        r"^(\d+)\s*(?:x|de|-)?\s*(.+)$",
        texto
    )

    if not coincidencia:
        return None

    cantidad = int(coincidencia.group(1))
    resto = coincidencia.group(2).strip()

    precio = normalizar_importe(resto)

    if precio is None:
        return None

    resolucion = resolver_producto_por_precio(
        precio,
        contexto_activo=contexto_activo,
    )

    if not resolucion["ok"]:
        return error_comando(resolucion)

    producto = resolucion["producto"]

    resultado = ejecutar_accion({
        "accion": "registrar_venta",
        "datos": {
            "producto": producto["nombre"],
            "cantidad": cantidad,
            "contexto": contexto or {},
        },
    })

    if not resultado["ok"]:
        return error_comando(resultado)

    datos = resultado["datos"]

    return {
        **datos,
        "ok": True,
        "codigo": "COMANDO_VENTA_REGISTRADA",
        "respuesta": "\n".join([
            "*Venta registrada*",
            f"Operación: #{datos['id_operacion']}",
            f"{datos['cantidad']} x {datos['producto']}",
            f"Total: {formatear_pesos(datos['total'])}",
        ]),
    }


def detectar_encabezado_contexto(texto):
    limpio = normalizar_texto(texto).rstrip(":").strip()

    if limpio in {"gasto", "gastos", "gastos 2"}:
        return "gastos"

    if limpio in {"postre", "postres"}:
        return "postres"

    if limpio in {"bebida", "bebidas"}:
        return "bebidas"

    if limpio in {"comida", "comidas"}:
        return "comida"

    return None


def es_total_informativo(texto):
    normalizado = normalizar_texto(texto)

    return bool(
        re.match(
            r"^(?:total|total gastado|gasto total)\b",
            normalizado
        )
    )


def interpretar_gasto_natural(
    texto,
    contexto=None,
    forzar=False
):
    normalizado = normalizar_texto(texto)

    if es_total_informativo(normalizado):
        return {
            "ok": True,
            "codigo": "COMANDO_TOTAL_INFORMATIVO",
            "respuesta": (
                "Total informado detectado. "
                "No lo registré como un gasto adicional."
            ),
        }

    tiene_palabra_gasto = bool(
        re.search(r"\bgastos?\b", normalizado)
    )

    if not forzar and not tiene_palabra_gasto:
        return None

    limpio = re.sub(
        r"\bgastos?\b",
        " ",
        normalizado
    )
    limpio = " ".join(limpio.split())

    coincidencias = list(
        re.finditer(
            r"\b\d[\d\.]*\s*(?:mil)?\b",
            limpio
        )
    )

    if not coincidencias:
        return {
            "ok": False,
            "codigo": "FORMATO_GASTO_INVALIDO",
            "respuesta": (
                "Indicá el gasto y el monto. "
                "Ejemplo: verdulería 9000"
            ),
        }

    ultima = coincidencias[-1]
    importe_texto = ultima.group(0)
    monto = normalizar_importe(importe_texto)

    if monto is None:
        return None

    descripcion = (
        limpio[:ultima.start()]
        + " "
        + limpio[ultima.end():]
    )
    descripcion = " ".join(
        descripcion.replace(":", " ").split()
    )
    descripcion = re.sub(
        r"^(?:en|de)\s+",
        "",
        descripcion
    ).strip()

    if not descripcion:
        return {
            "ok": False,
            "codigo": "GASTO_SIN_DESCRIPCION",
            "respuesta": (
                f"Detecté un gasto de {formatear_pesos(monto)}, "
                "pero necesito saber en qué fue."
            ),
        }

    resultado = ejecutar_accion({
        "accion": "registrar_gasto",
        "datos": {
            "descripcion": descripcion,
            "monto": monto,
            "categoria": "Otros",
            "contexto": contexto or {},
        },
    })

    if not resultado["ok"]:
        return error_comando(resultado)

    datos = resultado["datos"]

    return {
        **datos,
        "ok": True,
        "codigo": "COMANDO_GASTO_REGISTRADO",
        "respuesta": (
            "*Gasto registrado*\n"
            f"{datos['descripcion']}: "
            f"{formatear_pesos(datos['monto'])}"
        ),
    }


def procesar_bloque(
    mensaje,
    contexto=None
):
    lineas = [
        linea.strip()
        for linea in str(mensaje).splitlines()
        if linea.strip()
    ]

    if len(lineas) <= 1:
        return None

    respuestas = []
    ok_general = True

    for linea in lineas:
        resultado = procesar_comando(
            linea,
            contexto=contexto,
            _desde_bloque=True,
        )

        if resultado.get("respuesta"):
            respuestas.append(
                resultado["respuesta"]
            )

        if resultado.get("ok") is False:
            ok_general = False

    return {
        "ok": ok_general,
        "codigo": (
            "COMANDO_BLOQUE_PROCESADO"
            if ok_general
            else "COMANDO_BLOQUE_CON_OBSERVACIONES"
        ),
        "respuesta": "\n\n".join(respuestas),
    }


def parece_venta_rapida(texto):
    """
    Detecta mensajes operativos cortos del grupo, por ejemplo:
    - 1 pepsi
    - 2 sandwich de 6000
    - 1 hamburguesa simple

    No convierte conversaciones normales en ventas: exige
    que el mensaje empiece con una cantidad.
    """
    texto = normalizar_cantidad_escrita(texto)

    return bool(
        re.match(
            r"^x?\d+\s+\S+",
            texto
        )
    )


def interpretar_venta_rapida(
    texto,
    contexto=None
):
    return interpretar_venta(
        "venta " + normalizar_cantidad_escrita(texto),
        contexto=contexto,
    )


def mensaje_menu():
    return "\n".join([
        "*MENÚ - Lo de Clau*",
        "",
        "*Consultas rápidas*",
        "1. Stock",
        "2. Precios",
        "3. Caja",
        "4. Resumen de hoy",
        "5. Ventas de hoy",
        "",
        "*Movimientos*",
        "6. Registrar venta",
        "7. Registrar merma",
        "8. Consumo interno",
        "9. Inventario físico",
        "10. Anular última venta",
        "",
        "Escribí *opcion N* para seleccionar.",
        "Ejemplo: *opcion 1*",
        "",
        "También podés escribir *ayuda* para ver todos los comandos."
    ])


def interpretar_opcion_menu(
    texto,
    contexto=None
):
    coincidencia = re.match(
        r"^(?:opcion|opción)\s+(\d+)$",
        texto
    )

    if not coincidencia:
        return {
            "ok": False,
            "codigo": "OPCION_MENU_INVALIDA",
            "respuesta": (
                "Usá el formato 'opcion N'. "
                "Ejemplo: opcion 1"
            ),
        }

    opcion = int(coincidencia.group(1))

    comandos_directos = {
        1: "stock",
        2: "precios",
        3: "caja",
        4: "resumen hoy",
        5: "ventas hoy",
    }

    if opcion in comandos_directos:
        return procesar_comando(
            comandos_directos[opcion],
            contexto=contexto,
        )

    instrucciones = {
        6: (
            "*Registrar venta*\n"
            "Ejemplos:\n"
            "- venta 2 pepsi\n"
            "- venta 2 pepsi, 1 chocotorta y 1 big mac doble"
        ),
        7: (
            "*Registrar merma*\n"
            "Ejemplo: merma 2 pepsi"
        ),
        8: (
            "*Consumo interno*\n"
            "Ejemplo: consumo 1 oreo"
        ),
        9: (
            "*Inventario físico*\n"
            "Indicá la cantidad real contada.\n"
            "Ejemplo: inventario pepsi 8"
        ),
        10: (
            "*Anular última venta*\n"
            "Escribí: anular ultima venta"
        ),
    }

    if opcion in instrucciones:
        return {
            "ok": True,
            "codigo": "COMANDO_MENU_INSTRUCCION",
            "respuesta": instrucciones[opcion],
        }

    return {
        "ok": False,
        "codigo": "OPCION_MENU_INVALIDA",
        "respuesta": (
            "Esa opción no existe. "
            "Escribí 'menu' para ver las opciones disponibles."
        ),
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
        "- anular ultima venta",
        "- anular operacion 14",
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


def procesar_comando(
    mensaje,
    contexto=None,
    _desde_bloque=False
):
    if not _desde_bloque:
        bloque = procesar_bloque(
            mensaje,
            contexto=contexto,
        )

        if bloque is not None:
            return bloque

    texto = normalizar_texto(mensaje)

    if not texto:
        return {
            "ok": False,
            "codigo": "MENSAJE_VACIO",
            "respuesta": "El mensaje no puede estar vacío.",
        }

    encabezado = detectar_encabezado_contexto(
        texto
    )

    if encabezado:
        activar_contexto(
            contexto or {},
            encabezado,
        )

        nombres = {
            "gastos": "gastos",
            "postres": "postres",
            "bebidas": "bebidas",
            "comida": "comida",
        }

        return {
            "ok": True,
            "codigo": "CONTEXTO_ACTIVADO",
            "contexto": encabezado,
            "respuesta": (
                f"Contexto de {nombres[encabezado]} activado "
                "por 15 minutos."
            ),
        }

    if es_total_informativo(texto):
        return {
            "ok": True,
            "codigo": "COMANDO_TOTAL_INFORMATIVO",
            "respuesta": (
                "Total informado detectado. "
                "No lo registré como un movimiento adicional."
            ),
        }

    # Los gastos explícitos se detectan antes que las ventas rápidas.
    if (
        re.search(r"\bgastos?\b", texto)
        and texto not in {"gastos hoy"}
    ):
        gasto = interpretar_gasto_natural(
            texto,
            contexto=contexto,
            forzar=True,
        )

        if gasto is not None:
            return gasto

    contexto_activo = obtener_contexto_activo(
        contexto or {}
    )

    comandos_fuera_de_contexto = {
        "menu",
        "ayuda",
        "comandos",
        "stock",
        "ver stock",
        "precios",
        "ver precios",
        "caja",
        "gastos hoy",
        "ventas hoy",
        "compras hoy",
        "balance hoy",
        "resumen hoy",
        "balance semana",
        "resumen semana",
        "balance mes",
        "resumen mes",
    }

    if (
        contexto_activo == "gastos"
        and texto not in comandos_fuera_de_contexto
        and not texto.startswith(
            (
                "anular ",
                "borrar ",
                "eliminar ",
                "merma ",
                "perdida ",
                "consumo ",
                "inventario",
            )
        )
    ):
        gasto = interpretar_gasto_natural(
            texto,
            contexto=contexto,
            forzar=True,
        )

        if gasto is not None:
            tocar_contexto(contexto or {})
            return gasto

    venta_precio = interpretar_venta_por_precio(
        texto,
        contexto=contexto,
        contexto_activo=contexto_activo,
    )

    if venta_precio is not None:
        if contexto_activo:
            tocar_contexto(contexto or {})
        return venta_precio

    if texto.startswith("venta"):
        return interpretar_venta(
            texto,
            contexto=contexto,
        )

    if parece_venta_rapida(texto):
        if contexto_activo:
            tocar_contexto(contexto or {})

        return interpretar_venta_rapida(
            texto,
            contexto=contexto,
        )

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

    if (
        texto.startswith("anular ")
        or texto.startswith("borrar ")
        or texto.startswith("eliminar ")
    ):
        return interpretar_anulacion_venta(
            texto,
            contexto=contexto,
        )

    if texto == "menu":
        return {
            "ok": True,
            "codigo": "COMANDO_MENU",
            "respuesta": mensaje_menu(),
        }

    if texto.startswith("opcion ") or texto.startswith("opción "):
        return interpretar_opcion_menu(
            texto,
            contexto=contexto,
        )

    if texto in {"ayuda", "comandos"}:
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
            "Podés escribir 'menu' para ver las opciones disponibles."
        ),
    }
