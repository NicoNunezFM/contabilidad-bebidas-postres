import re

from adicionales import resolver_adicional
from acciones import (
    ejecutar_accion,
    formatear_pesos,
    normalizar_texto,
    resolver_producto,
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

    error = {
        "ok": False,
        "codigo": resultado.get(
            "codigo",
            "ERROR_COMANDO"
        ),
        "respuesta": respuesta,
    }

    # Conservar datos estructurados útiles para que la interfaz
    # pueda explicar qué falta o qué opciones existen.
    for campo in (
        "candidatos",
        "faltantes",
        "costo_parcial_conocido",
        "presentaciones",
        "faltantes_stock",
    ):
        if campo in resultado:
            error[campo] = resultado[campo]

    return error


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


def formatear_caja_seccion(estado):
    lineas = [
        f"*Caja {estado['nombre']}*",
    ]

    if estado["seccion"] == "bebidas_postres":
        lineas.extend([
            (
                "Recaudado bebidas: "
                f"{formatear_pesos(estado['recaudado_bebidas'])}"
            ),
            (
                "Recaudado postres: "
                f"{formatear_pesos(estado['recaudado_postres'])}"
            ),
        ])

    else:
        lineas.append(
            "Recaudado comidas: "
            f"{formatear_pesos(estado['recaudado_comidas'])}"
        )

    lineas.extend([
        (
            "Ventas de la sección: "
            f"{formatear_pesos(estado['ventas'])}"
        ),
        (
            "Compras directas: "
            f"{formatear_pesos(estado['compras_directas'])}"
        ),
        (
            "Gastos asignados: "
            f"{formatear_pesos(estado.get('gastos_seccion', 0))}"
        ),
        (
            "Saldo operativo: "
            f"{formatear_pesos(estado['saldo_operativo'])}"
        ),
        "",
        (
            "_Los gastos sin sección continúan únicamente "
            "en la caja general._"
        ),
    ])

    return "\n".join(lineas)




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

def _extraer_adicional_reconocido(texto_producto):
    """
    Separa adicionales configurados sin confundir guarniciones que
    forman parte del producto base (por ejemplo, 'mila con pure').
    """
    coincidencia = re.match(
        r"^(.+?)\s+con\s+(.+)$",
        texto_producto
    )

    if not coincidencia:
        return {
            "producto": texto_producto,
            "adicionales": [],
        }

    producto_base = coincidencia.group(1).strip()
    detalle = coincidencia.group(2).strip()
    detalle_normalizado = normalizar_texto(
        detalle
    )

    precio_total = None
    detalle_sin_precio = detalle_normalizado

    parentesis = re.search(
        r"\((\d[\d\.]*)\)\s*$",
        detalle
    )

    if parentesis:
        precio_total = normalizar_importe(
            parentesis.group(1)
        )
        detalle_sin_precio = normalizar_texto(
            detalle[:parentesis.start()]
        )

    else:
        precio_final = re.search(
            r"\s+(\d[\d\.]*\s*(?:mil)?)\s*$",
            detalle_normalizado
        )

        if precio_final:
            bruto = precio_final.group(1).strip()
            digitos = re.sub(
                r"\D",
                "",
                bruto
            )

            if (
                "mil" in bruto
                or (
                    digitos
                    and int(digitos) >= 100
                )
            ):
                precio_total = normalizar_importe(
                    bruto
                )
                detalle_sin_precio = (
                    detalle_normalizado[
                        :precio_final.start()
                    ].strip()
                )

    cantidad_adicional = 1
    descripcion = detalle_sin_precio

    cantidad_numero = re.match(
        r"^(\d+)\s+(.+)$",
        detalle_sin_precio
    )

    if cantidad_numero:
        cantidad_adicional = int(
            cantidad_numero.group(1)
        )
        descripcion = cantidad_numero.group(2)

    else:
        cantidades = {
            "un": 1,
            "una": 1,
            "uno": 1,
            "dos": 2,
            "tres": 3,
            "cuatro": 4,
        }

        partes = detalle_sin_precio.split()

        if (
            partes
            and partes[0] in cantidades
            and len(partes) > 1
        ):
            cantidad_adicional = cantidades[
                partes[0]
            ]
            descripcion = " ".join(
                partes[1:]
            )

    resolucion = resolver_adicional(
        descripcion
    )

    if not resolucion["ok"]:
        return {
            "producto": texto_producto,
            "adicionales": [],
        }

    adicional = resolucion["adicional"]
    descripcion = adicional["nombre"]

    if precio_total is None:
        precio_unitario = adicional.get(
            "precio_venta"
        )

        if precio_unitario is None:
            return {
                "producto": producto_base,
                "adicionales": [],
                "error_adicional": {
                    "descripcion": descripcion,
                    "cantidad": cantidad_adicional,
                },
            }

        precio_total = (
            precio_unitario
            * cantidad_adicional
        )

    return {
        "producto": producto_base,
        "adicionales": [
            {
                "descripcion": descripcion,
                "cantidad": cantidad_adicional,
                "precio_total": precio_total,
            }
        ],
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

    adicional = _extraer_adicional_reconocido(
        texto_producto
    )

    item = {
        "producto": adicional["producto"],
        "cantidad": cantidad,
    }

    if adicional.get("adicionales"):
        item["adicionales"] = adicional[
            "adicionales"
        ]

    if adicional.get("error_adicional"):
        item["error_adicional"] = adicional[
            "error_adicional"
        ]

    return item


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

    for item in items:
        error_adicional = item.pop(
            "error_adicional",
            None
        )

        if error_adicional:
            cantidad_extra = error_adicional[
                "cantidad"
            ]
            descripcion_extra = error_adicional[
                "descripcion"
            ]

            return {
                "ok": False,
                "codigo": "PRECIO_ADICIONAL_REQUERIDO",
                "respuesta": (
                    "Detecté el adicional "
                    f"'{cantidad_extra} x {descripcion_extra}', "
                    "pero necesito su precio. "
                    "Podés escribirlo al final, por ejemplo: "
                    "'1 sanguche grande con 2 huevos (1000)'."
                ),
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

        for adicional in datos.get(
            "adicionales",
            []
        ):
            lineas.append(
                "+ "
                f"{adicional['cantidad']} x "
                f"{adicional['descripcion']}: "
                f"{formatear_pesos(adicional['precio_total'])}"
            )

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

        for adicional in item.get(
            "adicionales",
            []
        ):
            lineas.append(
                "  + "
                f"{adicional['cantidad']} x "
                f"{adicional['descripcion']}: "
                f"{formatear_pesos(adicional['precio_total'])}"
            )

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


def _parsear_segmento_precio(texto):
    original = normalizar_cantidad_escrita(
        normalizar_texto(texto)
    )

    pista = None
    coincidencia_pista = re.search(
        r"\(([^)]+)\)",
        original
    )

    if coincidencia_pista:
        pista = coincidencia_pista.group(1).strip()
        original = re.sub(
            r"\([^)]+\)",
            "",
            original
        ).strip()

    importe_solo = normalizar_importe(original)

    if importe_solo is not None:
        return {
            "cantidad": 1,
            "precio": importe_solo,
            "pista": pista,
        }

    coincidencia = re.match(
        r"^(\d+)\s*(?:x|de|-)?\s*(.+)$",
        original
    )

    if not coincidencia:
        return None

    cantidad = int(coincidencia.group(1))
    precio = normalizar_importe(
        coincidencia.group(2).strip()
    )

    if precio is None:
        return None

    return {
        "cantidad": cantidad,
        "precio": precio,
        "pista": pista,
    }


def interpretar_venta_por_precio(
    texto,
    contexto=None,
    contexto_activo=None
):
    normalizado = normalizar_texto(texto)

    segmentos = [
        segmento.strip()
        for segmento in re.split(
            r"\s+y\s+",
            normalizado
        )
        if segmento.strip()
    ]

    items_resueltos = []

    for segmento in segmentos:
        datos_segmento = _parsear_segmento_precio(
            segmento
        )

        if datos_segmento is None:
            return None

        if datos_segmento["pista"]:
            resolucion = resolver_producto(
                datos_segmento["pista"]
            )
        else:
            resolucion = resolver_producto_por_precio(
                datos_segmento["precio"],
                contexto_activo=contexto_activo,
            )

        if not resolucion["ok"]:
            return error_comando(resolucion)

        producto = resolucion["producto"]

        items_resueltos.append({
            "producto": producto["nombre"],
            "cantidad": datos_segmento["cantidad"],
        })

    if not items_resueltos:
        return None

    if len(items_resueltos) == 1:
        item = items_resueltos[0]

        resultado = ejecutar_accion({
            "accion": "registrar_venta",
            "datos": {
                **item,
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

    resultado = ejecutar_accion({
        "accion": "registrar_venta",
        "datos": {
            "items": items_resueltos,
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
        lineas.append(
            f"- {item['cantidad']} x {item['producto']}: "
            f"{formatear_pesos(item['subtotal'])}"
        )

    lineas.append(
        f"*Total: {formatear_pesos(datos['total'])}*"
    )

    return {
        **datos,
        "ok": True,
        "codigo": "COMANDO_VENTA_MULTIPLE_REGISTRADA",
        "respuesta": "\n".join(lineas),
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


def interpretar_compra_pack(
    texto,
    contexto=None
):
    normalizado = normalizar_texto(texto)

    coincidencia = re.match(
        r"^compra\s+"
        r"(\d+|un|una|uno|dos|tres|cuatro|cinco|seis)\s+"
        r"packs?\s+(?:de\s+)?"
        r"(.+?)\s+"
        r"(por|total|a)\s+"
        r"(\d[\d\.]*\s*(?:mil)?)"
        r"(?:\s+(?:cada\s+pack|c/u|cada uno))?$",
        normalizado
    )

    if not coincidencia:
        # Caso útil para explicar el costo faltante.
        sin_costo = re.match(
            r"^compra\s+"
            r"(\d+|un|una|uno|dos|tres|cuatro|cinco|seis)\s+"
            r"packs?\s+(?:de\s+)?(.+)$",
            normalizado
        )

        if sin_costo:
            return {
                "ok": False,
                "codigo": "COSTO_COMPRA_REQUERIDO",
                "respuesta": (
                    "Indicá también cuánto costó la compra. "
                    "Ejemplos: 'compra 2 packs manaos cola por 17000' "
                    "o 'compra 2 packs manaos cola a 8500 cada pack'."
                ),
            }

        return None

    cantidad_texto = coincidencia.group(1)

    if cantidad_texto.isdigit():
        cantidad_packs = int(
            cantidad_texto
        )
    else:
        cantidad_packs = PALABRAS_CANTIDAD[
            cantidad_texto
        ]

    producto = coincidencia.group(2).strip()
    modalidad = coincidencia.group(3)
    importe = normalizar_importe(
        coincidencia.group(4)
    )

    if importe is None:
        return {
            "ok": False,
            "codigo": "FORMATO_COMPRA_PACK_INVALIDO",
            "respuesta": "No pude interpretar el costo de la compra.",
        }

    datos_accion = {
        "producto": producto,
        "cantidad_packs": cantidad_packs,
        "contexto": contexto or {},
    }

    if modalidad == "a":
        datos_accion["precio_pack"] = importe
    else:
        datos_accion["costo_total"] = importe

    resultado = ejecutar_accion({
        "accion": "registrar_compra_pack",
        "datos": datos_accion,
    })

    if not resultado["ok"]:
        return error_comando(resultado)

    datos = resultado["datos"]

    return {
        **datos,
        "ok": True,
        "codigo": "COMANDO_COMPRA_PACK_REGISTRADA",
        "respuesta": "\n".join([
            "*Compra registrada*",
            (
                f"{datos['cantidad_packs']} pack(s) x "
                f"{datos['unidades_por_pack']} unidades"
            ),
            f"Producto: {datos['producto']}",
            (
                "Unidades agregadas al stock: "
                f"{datos['cantidad_unidades']}"
            ),
            f"Total compra: {formatear_pesos(datos['total'])}",
            f"Stock actual: {datos['stock_actual']}",
        ]),
    }


def interpretar_compra_insumo_paquetes(
    texto,
    contexto=None
):
    normalizado = normalizar_texto(texto)

    coincidencia = re.match(
        r"^(?:(?:compra|gasto)\s+(?:postres\s+)?(?:insumo\s+)?|insumo\s+)"
        r"(.+?)\s+"
        r"(\d+)\s+"
        r"(?:paquetes?|packs?)\s+"
        r"(?:de\s+)?"
        r"(?:(?:cada\s+uno\s+)?"
        r"(?:"
        r"((?:118|170|250|258|354)\s*g)"
        r"|"
        r"(x\s*[34]|tripack)"
        r"))\s+"
        r"(?:por\s+)?"
        r"(\d[\d\.]*\s*(?:mil)?)"
        r"(?:\s+(?:en\s+)?(.+))?$",
        normalizado
    )

    if not coincidencia:
        return None

    insumo = coincidencia.group(1).strip()
    cantidad_paquetes = int(
        coincidencia.group(2)
    )
    presentacion = (
        coincidencia.group(3)
        or coincidencia.group(4)
    )
    costo = normalizar_importe(
        coincidencia.group(5)
    )
    comercio = (
        coincidencia.group(6).strip()
        if coincidencia.group(6)
        else None
    )

    if costo is None:
        return {
            "ok": False,
            "codigo": "COSTO_INSUMO_INVALIDO",
            "respuesta": "No pude interpretar el costo de los paquetes.",
        }

    resultado = ejecutar_accion({
        "accion": "registrar compra insumo paquetes",
        "datos": {
            "insumo": insumo,
            "cantidad_paquetes": cantidad_paquetes,
            "presentacion": presentacion,
            "costo_total": costo,
            "comercio": comercio,
            "contexto": contexto or {},
        },
    })

    if not resultado["ok"]:
        return error_comando(resultado)

    datos = resultado["datos"]

    lineas = [
        "*Compra de insumo registrada*",
        (
            f"{datos['cantidad_paquetes']} paquete(s) de "
            f"{datos['insumo']} "
            f"({datos['presentacion']})"
        ),
        (
            "Cantidad total para receta: "
            f"{datos['cantidad_base_total']:g} "
            f"{datos['unidad_base']}"
        ),
        (
            "Costo total: "
            f"{formatear_pesos(datos['costo_total'])}"
        ),
        (
            "Costo por paquete: "
            f"{formatear_pesos(datos['costo_por_paquete'])}"
        ),
    ]

    if datos.get("comercio"):
        lineas.append(
            f"Comercio: {datos['comercio']}"
        )

    if datos.get("controla_stock"):
        lineas.append(
            "Stock: "
            f"{datos['stock_anterior']:g} -> "
            f"{datos['stock_nuevo']:g} "
            f"{datos['unidad_base']}"
        )

    return {
        **datos,
        "ok": True,
        "codigo": "COMANDO_COMPRA_INSUMO_PAQUETES_REGISTRADA",
        "respuesta": "\n".join(lineas),
    }


def interpretar_compra_insumo(
    texto,
    contexto=None
):
    normalizado = normalizar_texto(texto)

    coincidencia = re.match(
        r"^(?:(?:compra|gasto)\s+(?:postres\s+)?(?:insumo\s+)?|insumo\s+)"
        r"(.+?)\s+"
        r"(\d+(?:[\.,]\d+)?)\s*"
        r"(kg|kilos?|g|gr|gramos?|l|lt|litros?|ml|mililitros?|un|u|unidad|unidades)\s+"
        r"(\d[\d\.]*\s*(?:mil)?)"
        r"(?:\s+(?:en\s+)?(.+))?$",
        normalizado
    )

    if not coincidencia:
        return None

    insumo = coincidencia.group(1).strip()
    cantidad = float(
        coincidencia.group(2)
        .replace(",", ".")
    )
    unidad = coincidencia.group(3)
    costo = normalizar_importe(
        coincidencia.group(4)
    )
    comercio = (
        coincidencia.group(5).strip()
        if coincidencia.group(5)
        else None
    )

    if costo is None:
        return {
            "ok": False,
            "codigo": "COSTO_INSUMO_INVALIDO",
            "respuesta": "No pude interpretar el costo del insumo.",
        }

    resultado = ejecutar_accion({
        "accion": "registrar_compra_insumo",
        "datos": {
            "insumo": insumo,
            "cantidad": cantidad,
            "unidad": unidad,
            "costo_total": costo,
            "comercio": comercio,
            "contexto": contexto or {},
        },
    })

    if not resultado["ok"]:
        return error_comando(resultado)

    datos = resultado["datos"]

    respuesta = [
        "*Insumo de postres registrado*",
        f"{datos['insumo']}: {cantidad:g} {unidad}",
        f"Costo: {formatear_pesos(datos['costo_total'])}",
    ]

    if datos.get("comercio"):
        respuesta.append(
            f"Comercio: {datos['comercio']}"
        )

    if datos.get("controla_stock"):
        respuesta.append(
            "Stock: "
            f"{datos['stock_anterior']:g} -> "
            f"{datos['stock_nuevo']:g} "
            f"{datos['unidad_base']}"
        )

    respuesta.append(
        "Se agregó al historial de costos de postres."
    )

    return {
        **datos,
        "ok": True,
        "codigo": "COMANDO_COMPRA_INSUMO_REGISTRADA",
        "respuesta": "\n".join(respuesta),
    }


def formatear_stock_insumos(insumos):
    lineas = [
        "*Stock de insumos*",
    ]

    for insumo in insumos:
        if not insumo["controla_stock"]:
            continue

        linea = (
            f"- {insumo['nombre']}: "
            f"{insumo['stock_base']:g} "
            f"{insumo['unidad_base']}"
        )

        equivalencias = insumo.get(
            "equivalencias_paquetes",
            []
        )

        if equivalencias:
            partes = []

            for equivalencia in equivalencias:
                cantidad = equivalencia.get(
                    "paquetes_equivalentes"
                )

                if cantidad is None:
                    continue

                partes.append(
                    f"{cantidad:.2f} x "
                    f"{equivalencia['presentacion']}"
                )

            if partes:
                linea += (
                    "\n  ≈ "
                    + " / ".join(partes)
                )

        lineas.append(linea)

    return "\n".join(lineas)


def interpretar_inventario_insumo(
    texto,
    contexto=None
):
    coincidencia = re.match(
        r"^inventario\s+insumo\s+(.+?)\s+"
        r"(\d+(?:[\.,]\d+)?)\s*"
        r"(kg|kilos?|g|gr|gramos?|l|lt|litros?|ml|mililitros?|un|u|unidad|unidades)$",
        texto
    )

    if not coincidencia:
        return None

    insumo = coincidencia.group(1).strip()
    cantidad = float(
        coincidencia.group(2).replace(",", ".")
    )
    unidad = coincidencia.group(3)

    resultado = ejecutar_accion({
        "accion": "registrar inventario insumo",
        "datos": {
            "insumo": insumo,
            "cantidad": cantidad,
            "unidad": unidad,
            "contexto": contexto or {},
        },
    })

    if not resultado["ok"]:
        return error_comando(resultado)

    datos = resultado["datos"]

    return {
        **datos,
        "ok": True,
        "codigo": "COMANDO_INVENTARIO_INSUMO_REGISTRADO",
        "respuesta": "\n".join([
            "*Inventario de insumo actualizado*",
            f"Insumo: {datos['insumo']}",
            (
                "Stock anterior: "
                f"{datos['stock_anterior']:g} "
                f"{datos['unidad_base']}"
            ),
            (
                "Stock actual: "
                f"{datos['stock_nuevo']:g} "
                f"{datos['unidad_base']}"
            ),
            (
                "Diferencia: "
                f"{datos['diferencia']:+g} "
                f"{datos['unidad_base']}"
            ),
        ]),
    }


def interpretar_necesidades_produccion(texto):
    patrones = [
        r"^que\s+necesito\s+para\s+hacer\s+(\d+)\s+(.+)$",
        r"^que\s+me\s+falta\s+para\s+hacer\s+(\d+)\s+(.+)$",
        r"^faltantes\s+(\d+)\s+(.+)$",
    ]

    coincidencia = None

    for patron in patrones:
        coincidencia = re.match(
            patron,
            texto
        )

        if coincidencia:
            break

    if not coincidencia:
        return None

    cantidad = int(
        coincidencia.group(1)
    )
    producto = coincidencia.group(2).strip()

    resultado = ejecutar_accion({
        "accion": "consultar necesidades produccion",
        "datos": {
            "producto": producto,
            "cantidad": cantidad,
        },
    })

    if not resultado["ok"]:
        return error_comando(resultado)

    datos = resultado["datos"]

    lineas = [
        (
            f"*Necesario para {cantidad} "
            f"{datos['producto']}*"
        ),
        f"Receta: v{datos['version_receta']}",
    ]

    for item in datos["detalle"]:
        if not item["controla_stock"]:
            lineas.append(
                f"- {item['insumo']}: "
                f"{item['necesario']:g} {item['unidad']} "
                "(preparación, sin stock físico)"
            )
            continue

        if item["suficiente"]:
            lineas.append(
                f"- {item['insumo']}: "
                f"{item['necesario']:g} {item['unidad']} "
                f"| tenés {item['disponible']:g} "
                f"{item['unidad']} ✓"
            )
        else:
            lineas.append(
                f"- {item['insumo']}: "
                f"{item['necesario']:g} {item['unidad']} "
                f"| tenés {item['disponible']:g} "
                f"| faltan {item['faltante']:g} "
                f"{item['unidad']}"
            )

    if datos["puede_producir"]:
        lineas.append(
            "*Stock suficiente para producir.*"
        )
    else:
        lineas.append(
            "*Faltan insumos antes de producir.*"
        )

    return {
        **datos,
        "ok": True,
        "codigo": "COMANDO_NECESIDADES_PRODUCCION",
        "respuesta": "\n".join(lineas),
    }


def interpretar_deudas_negocio(texto):
    if texto in {
        "deudas",
        "deudas negocio",
        "deudas del negocio",
        "cuanto debemos en tarjetas",
        "cuanto debemos de mercaderia",
        "cuanto debemos por mercaderia",
    }:
        resultado = ejecutar_accion({
            "accion": "consultar deudas negocio",
            "datos": {},
        })

        if not resultado["ok"]:
            return error_comando(resultado)

        datos = resultado["datos"]
        cuentas = datos["cuentas"]

        if not cuentas:
            return {
                "ok": True,
                "codigo": "COMANDO_DEUDAS_NEGOCIO",
                "cuentas": [],
                "total_ars": 0,
                "respuesta": (
                    "Todavía no hay deudas del negocio registradas."
                ),
            }

        lineas = [
            "*Deudas del negocio*",
        ]

        for cuenta in cuentas:
            linea = (
                f"- {cuenta['nombre']}: "
                f"{formatear_pesos(cuenta['saldo'])}"
            )

            if cuenta.get(
                "proximo_vencimiento"
            ):
                linea += (
                    " | vence "
                    f"{cuenta['proximo_vencimiento']}"
                )

            lineas.append(linea)

        lineas.extend([
            "",
            (
                "*Total pendiente ARS: "
                f"{formatear_pesos(datos['total_ars'])}*"
            ),
        ])

        return {
            **datos,
            "ok": True,
            "codigo": "COMANDO_DEUDAS_NEGOCIO",
            "respuesta": "\n".join(lineas),
        }

    if texto in {
        "que deuda vence primero",
        "cual deuda vence primero",
        "cual tarjeta vence primero",
    }:
        resultado = ejecutar_accion({
            "accion": "consultar deuda vence primero",
            "datos": {},
        })

        if not resultado["ok"]:
            return error_comando(resultado)

        datos = resultado["datos"]
        cuenta = datos.get("cuenta")

        if not cuenta:
            return {
                "ok": True,
                "codigo": "COMANDO_SIN_VENCIMIENTOS_DEUDA",
                "respuesta": (
                    "No hay deudas pendientes con vencimiento configurado."
                ),
            }

        return {
            **cuenta,
            "ok": True,
            "codigo": "COMANDO_DEUDA_VENCE_PRIMERO",
            "respuesta": (
                "*Próximo vencimiento*\n"
                f"{cuenta['nombre']}: "
                f"{formatear_pesos(cuenta['saldo'])}\n"
                f"Vence: {cuenta['proximo_vencimiento']}"
            ),
        }

    coincidencia = re.match(
        r"^(?:saldo inicial deuda|deuda inicial)\s+"
        r"(.+?)\s+(\d[\d\.]*\s*(?:mil)?)$",
        texto
    )

    if coincidencia:
        cuenta = coincidencia.group(1).strip()
        monto = normalizar_importe(
            coincidencia.group(2)
        )

        resultado = ejecutar_accion({
            "accion": "registrar saldo inicial deuda",
            "datos": {
                "cuenta": cuenta,
                "monto": monto,
            },
        })

        if not resultado["ok"]:
            return error_comando(resultado)

        datos = resultado["datos"]

        return {
            **datos,
            "ok": True,
            "codigo": "COMANDO_SALDO_INICIAL_DEUDA",
            "respuesta": (
                "*Saldo inicial de deuda registrado*\n"
                f"{datos['cuenta']}: "
                f"{formatear_pesos(datos['saldo'])}"
            ),
        }

    coincidencia = re.match(
        r"^pago deuda\s+(.+?)\s+"
        r"(\d[\d\.]*\s*(?:mil)?)$",
        texto
    )

    if not coincidencia:
        coincidencia_pago = re.match(
            r"^pagamos\s+"
            r"(\d[\d\.]*\s*(?:mil)?)\s+"
            r"de\s+(.+)$",
            texto
        )

        if coincidencia_pago:
            monto = normalizar_importe(
                coincidencia_pago.group(1)
            )
            cuenta = coincidencia_pago.group(2).strip()
        else:
            cuenta = None
            monto = None
    else:
        cuenta = coincidencia.group(1).strip()
        monto = normalizar_importe(
            coincidencia.group(2)
        )

    if cuenta is not None:
        resultado = ejecutar_accion({
            "accion": "registrar pago deuda",
            "datos": {
                "cuenta": cuenta,
                "monto": monto,
                "afecta_caja": True,
            },
        })

        if not resultado["ok"]:
            return error_comando(resultado)

        datos = resultado["datos"]

        return {
            **datos,
            "ok": True,
            "codigo": "COMANDO_PAGO_DEUDA",
            "respuesta": "\n".join([
                "*Pago de deuda registrado*",
                f"Cuenta: {datos['cuenta']}",
                (
                    "Pago: "
                    f"{formatear_pesos(datos['monto'])}"
                ),
                (
                    "Saldo pendiente: "
                    f"{formatear_pesos(datos['saldo'])}"
                ),
                "El pago se descontó de la caja del negocio.",
            ]),
        }

    coincidencia = re.match(
        r"^compra deuda\s+(.+?)\s+"
        r"(\d[\d\.]*\s*(?:mil)?)"
        r"(?:\s+(.+))?$",
        texto
    )

    if coincidencia:
        cuenta = coincidencia.group(1).strip()
        monto = normalizar_importe(
            coincidencia.group(2)
        )
        descripcion = (
            coincidencia.group(3).strip()
            if coincidencia.group(3)
            else None
        )

        resultado = ejecutar_accion({
            "accion": "registrar compra deuda",
            "datos": {
                "cuenta": cuenta,
                "monto": monto,
                "descripcion": descripcion,
            },
        })

        if not resultado["ok"]:
            return error_comando(resultado)

        datos = resultado["datos"]

        return {
            **datos,
            "ok": True,
            "codigo": "COMANDO_COMPRA_DEUDA",
            "respuesta": (
                "*Compra financiada registrada*\n"
                f"Cuenta: {datos['cuenta']}\n"
                f"Compra: {formatear_pesos(datos['monto'])}\n"
                f"Saldo pendiente: {formatear_pesos(datos['saldo'])}"
            ),
        }

    coincidencia = re.match(
        r"^ajustar deuda\s+(.+?)\s+"
        r"(\d[\d\.]*\s*(?:mil)?)$",
        texto
    )

    if coincidencia:
        cuenta = coincidencia.group(1).strip()
        saldo = normalizar_importe(
            coincidencia.group(2)
        )

        resultado = ejecutar_accion({
            "accion": "ajustar deuda negocio",
            "datos": {
                "cuenta": cuenta,
                "saldo": saldo,
            },
        })

        if not resultado["ok"]:
            return error_comando(resultado)

        datos = resultado["datos"]

        return {
            **datos,
            "ok": True,
            "codigo": "COMANDO_DEUDA_AJUSTADA",
            "respuesta": (
                "*Deuda ajustada*\n"
                f"{datos['cuenta']}: "
                f"{formatear_pesos(datos['saldo_anterior'])} -> "
                f"{formatear_pesos(datos['saldo'])}"
            ),
        }

    coincidencia = re.match(
        r"^vencimiento deuda\s+(.+?)\s+"
        r"(\d{4}-\d{2}-\d{2})$",
        texto
    )

    if coincidencia:
        cuenta = coincidencia.group(1).strip()
        fecha_vencimiento = coincidencia.group(2)

        resultado = ejecutar_accion({
            "accion": "configurar vencimiento deuda",
            "datos": {
                "cuenta": cuenta,
                "fecha_vencimiento": fecha_vencimiento,
            },
        })

        if not resultado["ok"]:
            return error_comando(resultado)

        datos = resultado["datos"]

        return {
            **datos,
            "ok": True,
            "codigo": "COMANDO_VENCIMIENTO_DEUDA",
            "respuesta": (
                "*Vencimiento configurado*\n"
                f"{datos['cuenta']}: "
                f"{datos['proximo_vencimiento']}"
            ),
        }

    coincidencia = re.match(
        r"^historial deuda\s+(.+)$",
        texto
    )

    if coincidencia:
        cuenta = coincidencia.group(1).strip()

        resultado = ejecutar_accion({
            "accion": "historial deuda negocio",
            "datos": {
                "cuenta": cuenta,
                "limite": 20,
            },
        })

        if not resultado["ok"]:
            return error_comando(resultado)

        datos = resultado["datos"]
        lineas = [
            f"*Historial deuda - {datos['cuenta']}*",
        ]

        for movimiento in datos["movimientos"]:
            signo = (
                "+"
                if movimiento["importe"] >= 0
                else "-"
            )

            lineas.append(
                f"- {movimiento['fecha_hora']} | "
                f"{movimiento['tipo']} | "
                f"{signo}{formatear_pesos(abs(movimiento['importe']))}"
            )

        lineas.append(
            "*Saldo actual: "
            f"{formatear_pesos(datos['saldo'])}*"
        )

        return {
            **datos,
            "ok": True,
            "codigo": "COMANDO_HISTORIAL_DEUDA",
            "respuesta": "\n".join(lineas),
        }

    coincidencia = re.match(
        r"^(?:deuda|cuanto falta pagar de)\s+(.+)$",
        texto
    )

    if coincidencia:
        cuenta = coincidencia.group(1).strip()

        resultado = ejecutar_accion({
            "accion": "consultar deuda negocio",
            "datos": {
                "cuenta": cuenta,
            },
        })

        if not resultado["ok"]:
            return error_comando(resultado)

        datos = resultado["datos"]
        lineas = [
            f"*Deuda - {datos['cuenta']}*",
            (
                "Saldo pendiente: "
                f"{formatear_pesos(datos['saldo'])}"
            ),
        ]

        if datos.get(
            "proximo_vencimiento"
        ):
            lineas.append(
                "Próximo vencimiento: "
                f"{datos['proximo_vencimiento']}"
            )

        return {
            **datos,
            "ok": True,
            "codigo": "COMANDO_DETALLE_DEUDA",
            "respuesta": "\n".join(lineas),
        }

    return None


def interpretar_adicionales(texto):
    if texto in {
        "adicionales",
        "ver adicionales",
        "catalogo adicionales",
    }:
        resultado = ejecutar_accion({
            "accion": "consultar adicionales",
            "datos": {},
        })

        if not resultado["ok"]:
            return error_comando(resultado)

        adicionales = resultado["datos"][
            "adicionales"
        ]
        lineas = [
            "*Adicionales*",
        ]

        for adicional in adicionales:
            precio = (
                formatear_pesos(
                    adicional["precio_venta"]
                )
                if adicional["precio_venta"] is not None
                else "sin configurar"
            )
            costo = (
                formatear_pesos(
                    adicional["costo_unitario"]
                )
                if adicional["costo_unitario"] is not None
                else "sin configurar"
            )

            lineas.append(
                f"- {adicional['nombre']} | "
                f"venta: {precio} | costo: {costo}"
            )

        return {
            "ok": True,
            "codigo": "COMANDO_ADICIONALES",
            "adicionales": adicionales,
            "respuesta": "\n".join(lineas),
        }

    coincidencia = re.match(
        r"^(?:configurar\s+)?adicional\s+"
        r"(.+?)(?=\s+(?:precio|costo)\s+)"
        r"(.+)$",
        texto
    )

    if not coincidencia:
        return None

    nombre = coincidencia.group(1).strip()
    parametros = coincidencia.group(2).strip()

    precio_venta = None
    costo_unitario = None

    precio = re.search(
        r"(?:^|\s)precio\s+"
        r"(\d[\d\.]*\s*(?:mil)?)",
        parametros
    )

    costo = re.search(
        r"(?:^|\s)costo\s+"
        r"(\d[\d\.]*\s*(?:mil)?)",
        parametros
    )

    if precio:
        precio_venta = normalizar_importe(
            precio.group(1)
        )

    if costo:
        costo_unitario = normalizar_importe(
            costo.group(1)
        )

    if precio_venta is None and costo_unitario is None:
        return {
            "ok": False,
            "codigo": "FORMATO_ADICIONAL_INVALIDO",
            "respuesta": (
                "Indicá precio, costo o ambos. "
                "Ejemplo: adicional huevo precio 1000 costo 300"
            ),
        }

    resultado = ejecutar_accion({
        "accion": "configurar adicional",
        "datos": {
            "nombre": nombre,
            "precio_venta": precio_venta,
            "costo_unitario": costo_unitario,
        },
    })

    if not resultado["ok"]:
        return error_comando(resultado)

    datos = resultado["datos"]
    lineas = [
        "*Adicional configurado*",
        f"Adicional: {datos['nombre']}",
        (
            "Precio de venta: "
            + (
                formatear_pesos(
                    datos["precio_venta"]
                )
                if datos["precio_venta"] is not None
                else "sin configurar"
            )
        ),
        (
            "Costo unitario: "
            + (
                formatear_pesos(
                    datos["costo_unitario"]
                )
                if datos["costo_unitario"] is not None
                else "sin configurar"
            )
        ),
    ]

    return {
        **datos,
        "ok": True,
        "codigo": "COMANDO_ADICIONAL_CONFIGURADO",
        "respuesta": "\n".join(lineas),
    }


def formatear_rentabilidad_producto(datos):
    lineas = [
        f"*Rentabilidad - {datos['producto']}*",
    ]

    if datos.get("precio_venta") is not None:
        lineas.append(
            "Precio de venta: "
            f"{formatear_pesos(datos['precio_venta'])}"
        )
    else:
        lineas.append(
            "Precio de venta: sin configurar"
        )

    if datos.get("completo"):
        lineas.extend([
            (
                "Costo unitario actual: "
                f"{formatear_pesos(datos['costo_unitario'])}"
            ),
            (
                "Ganancia bruta por unidad: "
                f"{formatear_pesos(datos['ganancia_unitaria'])}"
            ),
            (
                "Margen sobre venta: "
                f"{datos['margen_sobre_venta_pct']:.1f}%"
            ),
            (
                "Markup sobre costo: "
                f"{datos['markup_sobre_costo_pct']:.1f}%"
            ),
            (
                f"Fuente del costo actual: "
                f"{datos['fuente_costo']}"
            ),
        ])
    else:
        lineas.append(
            "Costo unitario actual: sin datos suficientes"
        )

        faltantes = datos.get(
            "faltantes_costo",
            []
        )

        if faltantes:
            lineas.append(
                "Faltan costos de: "
                + ", ".join(faltantes)
            )

    if datos.get("unidades_vendidas", 0) > 0:
        lineas.extend([
            "",
            "*Histórico de ventas*",
            (
                "Unidades vendidas: "
                f"{datos['unidades_vendidas']}"
            ),
            (
                "Ingresos: "
                f"{formatear_pesos(datos['ingresos'])}"
            ),
        ])

        if datos.get(
            "rentabilidad_historica_exacta"
        ):
            costo_historico = datos.get(
                "costo_ventas_historico",
                0,
            )
            ganancia_historica = datos.get(
                "ganancia_bruta_historica",
                0,
            )
            margen_historico = (
                (
                    ganancia_historica
                    / datos["ingresos"]
                ) * 100
                if datos["ingresos"] > 0
                else 0
            )

            lineas.extend([
                (
                    "Costo histórico de ventas: "
                    f"{formatear_pesos(costo_historico)}"
                ),
                (
                    "Ganancia bruta histórica: "
                    f"{formatear_pesos(ganancia_historica)}"
                ),
                (
                    "Margen histórico: "
                    f"{margen_historico:.1f}%"
                ),
                (
                    "_Calculado con el costo congelado "
                    "al momento de cada venta._"
                ),
            ])
        else:
            lineas.append(
                "Costo histórico conocido: "
                f"{formatear_pesos(datos.get('costo_ventas_historico_conocido', 0))}"
            )

            if datos.get(
                "unidades_sin_snapshot",
                0
            ) > 0:
                lineas.extend([
                    (
                        "Unidades antiguas sin costo congelado: "
                        f"{datos.get('unidades_sin_snapshot', 0)}"
                    ),
                    (
                        "_Las ventas nuevas ya guardan el costo "
                        "al momento de vender. Las ventas anteriores "
                        "a esta función no pueden reconstruirse con "
                        "precisión sin datos históricos adicionales._"
                    ),
                ])

            if datos.get(
                "adicionales_sin_costo_snapshot",
                0
            ) > 0:
                lineas.append(
                    "_Hay adicionales vendidos sin costo congelado. "
                    "Configurá su costo para que las ventas futuras "
                    "queden con rentabilidad histórica exacta._"
                )

            if datos.get("completo"):
                lineas.extend([
                    (
                        "Estimación usando costo actual: "
                        f"{formatear_pesos(datos['ganancia_bruta_estimada'])}"
                    ),
                ])

    return "\n".join(lineas)


def formatear_rentabilidad_categoria(datos):
    lineas = [
        f"*Rentabilidad - {datos['nombre']}*",
    ]

    for producto in datos["productos"]:
        if producto.get("completo"):
            lineas.append(
                f"- {producto['producto']}: "
                f"{formatear_pesos(producto['costo_unitario'])} costo | "
                f"{formatear_pesos(producto['precio_venta'])} venta | "
                f"{producto['margen_sobre_venta_pct']:.1f}% margen"
            )
        else:
            lineas.append(
                f"- {producto['producto']}: "
                "costo incompleto"
            )

    lineas.extend([
        "",
        (
            "Ingresos registrados: "
            f"{formatear_pesos(datos['ingresos'])}"
        ),
    ])

    if datos.get(
        "rentabilidad_historica_exacta"
    ):
        lineas.extend([
            (
                "Costo histórico de ventas: "
                f"{formatear_pesos(datos['costo_ventas_historico'])}"
            ),
            (
                "Ganancia bruta histórica: "
                f"{formatear_pesos(datos['ganancia_bruta_historica'])}"
            ),
        ])

        if datos.get(
            "margen_bruto_historico_pct"
        ) is not None:
            lineas.append(
                "Margen bruto histórico: "
                f"{datos['margen_bruto_historico_pct']:.1f}%"
            )

        lineas.append(
            "_Calculado con costos congelados al momento "
            "de cada venta._"
        )
    else:
        lineas.extend([
            (
                "Costo histórico conocido: "
                f"{formatear_pesos(datos['costo_ventas_historico_conocido'])}"
            ),
            (
                "_Hay ventas antiguas sin costo congelado o "
                "ventas con adicionales sin costo modelado. "
                "Las ventas nuevas del producto base sí guardan "
                "su costo al momento de vender._"
            ),
        ])

        if datos.get("completo"):
            lineas.append(
                "Ganancia estimada con costos actuales: "
                f"{formatear_pesos(datos['ganancia_bruta_estimada'])}"
            )

    return "\n".join(lineas)



def interpretar_rentabilidad(texto):
    categorias = {
        "bebidas": "bebidas",
        "postres": "postres",
        "bebidas postres": "bebidas_postres",
        "bebidas y postres": "bebidas_postres",
        "postres y bebidas": "bebidas_postres",
    }

    coincidencia = re.match(
        r"^(?:rentabilidad|ganancia|margen)\s+(.+)$",
        texto
    )

    if not coincidencia:
        return None

    objetivo = coincidencia.group(1).strip()

    if objetivo in categorias:
        resultado = ejecutar_accion({
            "accion": "consultar rentabilidad categoria",
            "datos": {
                "categoria": categorias[objetivo],
            },
        })

        if not resultado["ok"]:
            return error_comando(resultado)

        datos = resultado["datos"]

        return {
            **datos,
            "ok": True,
            "codigo": "COMANDO_RENTABILIDAD_CATEGORIA",
            "respuesta": formatear_rentabilidad_categoria(
                datos
            ),
        }

    resultado = ejecutar_accion({
        "accion": "consultar rentabilidad producto",
        "datos": {
            "producto": objetivo,
        },
    })

    if not resultado["ok"]:
        return error_comando(resultado)

    datos = resultado["datos"]

    return {
        **datos,
        "ok": True,
        "codigo": "COMANDO_RENTABILIDAD_PRODUCTO",
        "respuesta": formatear_rentabilidad_producto(
            datos
        ),
    }


def interpretar_produccion_postre(
    texto,
    contexto=None
):
    coincidencia = re.match(
        r"^produccion\s+(\d+)\s+(.+)$",
        texto
    )

    if not coincidencia:
        return None

    cantidad = int(
        coincidencia.group(1)
    )
    producto = coincidencia.group(2).strip()

    resultado = ejecutar_accion({
        "accion": "registrar_produccion_postre",
        "datos": {
            "producto": producto,
            "cantidad": cantidad,
            "contexto": contexto or {},
        },
    })

    if not resultado["ok"]:
        return error_comando(resultado)

    datos = resultado["datos"]

    lineas = [
        "*Producción registrada*",
        f"Producción: #{datos['id_produccion']}",
        (
            f"{datos['cantidad_producida']} x "
            f"{datos['producto']}"
        ),
        f"Receta: v{datos['version_receta']}",
        (
            "Costo de insumos: "
            f"{formatear_pesos(datos['costo_insumos'])}"
        ),
        (
            "Costo de elaboración: "
            f"{formatear_pesos(datos['costo_fijo'])}"
        ),
        (
            "*Costo total estimado: "
            f"{formatear_pesos(datos['costo_total'])}*"
        ),
        (
            "Costo por unidad: "
            f"{formatear_pesos(datos['costo_unitario'])}"
        ),
        (
            f"Stock {datos['producto']}: "
            f"{datos['stock_anterior']} -> {datos['stock_nuevo']}"
        ),
        "",
        "*Insumos consumidos*",
    ]

    for item in datos["detalle_insumos"]:
        if item["controla_stock"]:
            lineas.append(
                f"- {item['insumo']}: "
                f"{item['stock_anterior']:g} -> "
                f"{item['stock_nuevo']:g} "
                f"{item['unidad']} "
                f"(-{item['cantidad']:g})"
            )
        else:
            lineas.append(
                f"- {item['insumo']}: "
                f"{item['cantidad']:g} {item['unidad']} "
                "(preparación, sin stock físico)"
            )

    return {
        **datos,
        "ok": True,
        "codigo": "COMANDO_PRODUCCION_POSTRE_REGISTRADA",
        "respuesta": "\n".join(lineas),
    }


def interpretar_historial_producciones_postres(
    texto
):
    if texto not in {
        "historial produccion",
        "historial producciones",
        "historial produccion postres",
        "producciones postres",
    }:
        return None

    resultado = ejecutar_accion({
        "accion": "historial_producciones_postres",
        "datos": {
            "limite": 10,
        },
    })

    if not resultado["ok"]:
        return error_comando(resultado)

    producciones = resultado["datos"][
        "producciones"
    ]

    if not producciones:
        return {
            "ok": True,
            "codigo": "COMANDO_HISTORIAL_PRODUCCIONES_POSTRES",
            "producciones": [],
            "respuesta": (
                "Todavía no hay producciones de postres registradas."
            ),
        }

    lineas = [
        "*Últimas producciones de postres*",
    ]

    for produccion in producciones:
        lineas.append(
            f"- #{produccion['id_produccion']} | "
            f"{produccion['fecha_hora']} | "
            f"{produccion['cantidad_producida']} x "
            f"{produccion['producto']} | "
            f"{formatear_pesos(produccion['costo_total'])} "
            f"({formatear_pesos(produccion['costo_unitario'])}/u)"
        )

    return {
        "ok": True,
        "codigo": "COMANDO_HISTORIAL_PRODUCCIONES_POSTRES",
        "producciones": producciones,
        "respuesta": "\n".join(lineas),
    }


def interpretar_receta_postre(texto):
    coincidencia = re.match(
        r"^receta\s+(.+)$",
        texto
    )

    if not coincidencia:
        return None

    producto = coincidencia.group(1).strip()

    resultado = ejecutar_accion({
        "accion": "consultar_receta",
        "datos": {
            "producto": producto,
        },
    })

    if not resultado["ok"]:
        return error_comando(resultado)

    receta = resultado["datos"]

    lineas = [
        f"*Receta {receta['producto']}*",
        f"Versión: {receta['version']}",
        (
            f"Rendimiento base: "
            f"{receta['rendimiento']:g} postres"
        ),
    ]

    for insumo in receta["insumos"]:
        lineas.append(
            f"- {insumo['nombre']}: "
            f"{insumo['cantidad_base']:g} "
            f"{insumo['unidad_base']}"
        )

    lineas.append(
        "Costo fijo por postre: "
        f"{formatear_pesos(receta['costo_fijo_por_unidad'])}"
    )

    if receta.get("notas"):
        lineas.extend([
            "",
            "*Notas*",
            receta["notas"],
        ])

    return {
        "ok": True,
        "codigo": "COMANDO_RECETA_POSTRE",
        "receta": receta,
        "respuesta": "\n".join(lineas),
    }


def interpretar_costo_postre(texto):
    patrones = [
        r"^costo\s+(\d+)\s+(.+)$",
        r"^cuanto\s+cuesta\s+hacer\s+(\d+)\s+(.+)$",
        r"^cuanto\s+me\s+vale\s+hacer\s+(\d+)\s+(.+)$",
        r"^cuanto\s+sale\s+hacer\s+(\d+)\s+(.+)$",
    ]

    coincidencia = None

    for patron in patrones:
        coincidencia = re.match(
            patron,
            texto
        )

        if coincidencia:
            break

    if not coincidencia:
        return None

    cantidad = int(
        coincidencia.group(1)
    )
    producto = coincidencia.group(2).strip()

    resultado = ejecutar_accion({
        "accion": "estimar_costo_receta",
        "datos": {
            "producto": producto,
            "cantidad": cantidad,
        },
    })

    if not resultado["ok"]:
        return error_comando(resultado)

    datos = resultado["datos"]

    lineas = [
        (
            f"*Costo estimado: "
            f"{cantidad} {datos['producto']}*"
        ),
    ]

    for item in datos["detalle"]:
        cantidad_texto = (
            f"{item['cantidad']:g} {item['unidad']}"
        )

        if item["costo_estimado"] is None:
            lineas.append(
                f"- {item['insumo']}: "
                f"{cantidad_texto} | sin historial de precio"
            )
        else:
            lineas.append(
                f"- {item['insumo']}: "
                f"{cantidad_texto} | "
                f"{formatear_pesos(item['costo_estimado'])}"
            )

    lineas.extend([
        (
            "Costo fijo de elaboración: "
            f"{formatear_pesos(datos['costo_fijo'])}"
        ),
    ])

    if datos["costo_total_estimado"] is not None:
        lineas.append(
            "*Total estimado: "
            f"{formatear_pesos(datos['costo_total_estimado'])}*"
        )
        costo_por_unidad = (
            datos["costo_total_estimado"]
            / cantidad
        )
        lineas.append(
            "Costo estimado por unidad: "
            f"{formatear_pesos(costo_por_unidad)}"
        )
    else:
        lineas.append(
            "Costo parcial conocido: "
            f"{formatear_pesos(datos['costo_parcial_conocido'])}"
        )
        lineas.append(
            "Faltan precios de: "
            + ", ".join(datos["faltantes"])
        )

    lineas.append(
        "_Estimación basada en el promedio ponderado "
        "de las últimas 3 compras de cada insumo._"
    )
    lineas.append(
        f"_Receta v{datos['version_receta']}. "
        "Los consumos indicados como 'a ojo' no se suman "
        "hasta tener una cantidad medible._"
    )

    return {
        **datos,
        "ok": True,
        "codigo": datos["codigo"],
        "respuesta": "\n".join(lineas),
    }


def interpretar_historial_gastos_postres(texto):
    if texto not in {
        "historial gastos postres",
        "historial de gastos postres",
        "gastos postres historial",
    }:
        return None

    resultado = ejecutar_accion({
        "accion": "historial_gastos_postres",
        "datos": {
            "limite": 10,
        },
    })

    if not resultado["ok"]:
        return error_comando(resultado)

    gastos = resultado["datos"]["gastos"]

    if not gastos:
        return {
            "ok": True,
            "codigo": "COMANDO_HISTORIAL_GASTOS_POSTRES",
            "gastos": [],
            "respuesta": (
                "Todavía no hay gastos asignados a Bebidas + Postres."
            ),
        }

    lineas = [
        "*Últimos gastos de Bebidas + Postres*",
    ]

    for gasto in gastos:
        lineas.append(
            f"- {gasto['fecha']} | "
            f"{gasto['descripcion']}: "
            f"{formatear_pesos(gasto['monto'])}"
        )

    return {
        "ok": True,
        "codigo": "COMANDO_HISTORIAL_GASTOS_POSTRES",
        "gastos": gastos,
        "respuesta": "\n".join(lineas),
    }


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

    seccion = None
    subseccion = None

    for (
        prefijo,
        seccion_detectada,
        subseccion_detectada,
    ) in (
        (
            "bebidas y postres ",
            "bebidas_postres",
            None,
        ),
        (
            "bebidas postres ",
            "bebidas_postres",
            None,
        ),
        (
            "postres ",
            "bebidas_postres",
            "postres",
        ),
        (
            "bebidas ",
            "bebidas_postres",
            "bebidas",
        ),
        (
            "comidas ",
            "comidas",
            "comidas",
        ),
        (
            "comida ",
            "comidas",
            "comidas",
        ),
    ):
        if limpio.startswith(prefijo):
            seccion = seccion_detectada
            subseccion = subseccion_detectada
            limpio = limpio[len(prefijo):].strip()
            break

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
            "seccion": seccion,
            "subseccion": subseccion,
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
            + (
                "\nCaja: Bebidas + Postres"
                if datos.get("seccion") == "bebidas_postres"
                else (
                    "\nCaja: Comidas"
                    if datos.get("seccion") == "comidas"
                    else ""
                )
            )
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
        "3. Caja general",
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
        "",
        "*Cajas por sección*",
        "- caja bebidas postres",
        "- caja comidas",
        "- recaudado bebidas",
        "- recaudado postres",
        "- recaudado comidas",
        "",
        "*Costos de postres*",
        "- insumo crema de leche 1 l 9000 Carrefour",
        "- receta oreo",
        "- costo 10 oreos",
        "- historial gastos postres",
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
        "- compra 2 packs manaos cola por 17000",
        "- compra 1 pack manaos cola chica a 8500 cada pack",
        "- venta 2 manaos cola 600",
        "- venta big mac doble",
        "- venta 2 pepsi, 1 chocotorta y 2 big mac doble",
        "- merma 2 pepsi",
        "- consumo 1 oreo",
        "- inventario pepsi 8",
        "- insumo oreo 3 paquetes 118g 4288 Carrefour",
        "- insumo chocolinas 4 paquetes 250g 12000 Carrefour",
        "- produccion 10 oreo",
        "- produccion 10 chocotorta",
        "- historial produccion",
        "- stock insumos",
        "- inventario insumo oreo 1350g",
        "- que necesito para hacer 20 oreos",
        "- rentabilidad oreo",
        "- rentabilidad chocotorta",
        "- rentabilidad bebidas",
        "- rentabilidad postres",
        "- rentabilidad bebidas postres",
        "- adicionales",
        "- adicional huevo precio 1000 costo 300",
        "- deudas negocio",
        "- saldo inicial deuda naranja 100000",
        "- deuda naranja",
        "- historial deuda naranja",
        "- pago deuda naranja 30000",
        "- vencimiento deuda naranja 2026-10-20",
        "- anular ultima venta",
        "- anular operacion 14",
        "- stock",
        "- ver stock",
        "- precios",
        "- caja",
        "- caja bebidas postres",
        "- caja comidas",
        "- recaudado bebidas",
        "- recaudado postres",
        "- recaudado comidas",
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

    compra_insumo_paquetes = interpretar_compra_insumo_paquetes(
        texto,
        contexto=contexto,
    )

    if compra_insumo_paquetes is not None:
        return compra_insumo_paquetes

    compra_insumo = interpretar_compra_insumo(
        texto,
        contexto=contexto,
    )

    if compra_insumo is not None:
        return compra_insumo

    inventario_insumo = interpretar_inventario_insumo(
        texto,
        contexto=contexto,
    )

    if inventario_insumo is not None:
        return inventario_insumo

    necesidades = interpretar_necesidades_produccion(
        texto
    )

    if necesidades is not None:
        return necesidades

    if texto in {
        "stock insumos",
        "ver stock insumos",
        "stock de insumos",
    }:
        resultado = ejecutar_accion({
            "accion": "consultar stock insumos",
            "datos": {},
        })

        if not resultado["ok"]:
            return error_comando(resultado)

        insumos = resultado["datos"]["insumos"]

        return {
            "ok": True,
            "codigo": "COMANDO_STOCK_INSUMOS",
            "insumos": insumos,
            "respuesta": formatear_stock_insumos(
                insumos
            ),
        }

    deudas = interpretar_deudas_negocio(
        texto
    )

    if deudas is not None:
        return deudas

    adicionales = interpretar_adicionales(
        texto
    )

    if adicionales is not None:
        return adicionales

    rentabilidad = interpretar_rentabilidad(
        texto
    )

    if rentabilidad is not None:
        return rentabilidad

    produccion_postre = interpretar_produccion_postre(
        texto,
        contexto=contexto,
    )

    if produccion_postre is not None:
        return produccion_postre

    historial_produccion = interpretar_historial_producciones_postres(
        texto
    )

    if historial_produccion is not None:
        return historial_produccion

    receta_postre = interpretar_receta_postre(
        texto
    )

    if receta_postre is not None:
        return receta_postre

    costo_postre = interpretar_costo_postre(
        texto
    )

    if costo_postre is not None:
        return costo_postre

    historial_postres = interpretar_historial_gastos_postres(
        texto
    )

    if historial_postres is not None:
        return historial_postres

    if texto.startswith("compra "):
        compra_pack = interpretar_compra_pack(
            texto,
            contexto=contexto,
        )

        if compra_pack is not None:
            return compra_pack

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
        "stock insumos",
        "ver stock insumos",
        "stock de insumos",
        "adicionales",
        "ver adicionales",
        "catalogo adicionales",
        "deudas",
        "deudas negocio",
        "deudas del negocio",
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
                "caja ",
                "recaudado ",
                "ventas ",
                "cuanto ",
                "cuanta ",
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

    if texto == "venta" or texto.startswith("venta "):
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

    cajas_seccion = {
        "caja bebidas postres": "bebidas_postres",
        "caja bebidas y postres": "bebidas_postres",
        "caja postres y bebidas": "bebidas_postres",
        "caja comidas": "comidas",
        "caja general comidas": "comidas",
    }

    if texto in cajas_seccion:
        resultado = ejecutar_accion({
            "accion": "consultar_caja_seccion",
            "datos": {
                "seccion": cajas_seccion[texto],
            },
        })

        if not resultado["ok"]:
            return error_comando(resultado)

        return {
            "ok": True,
            "codigo": "COMANDO_CAJA_SECCION",
            "respuesta": formatear_caja_seccion(
                resultado["datos"]
            ),
            **resultado["datos"],
        }

    coincidencia_recaudado = re.match(
        r"^(?:cuanto\s+|cuanta\s+plata\s+)?"
        r"(?:recaude|recaudado|recaudamos|ventas?)"
        r"(?:\s+en|\s+de)?\s+"
        r"(bebidas|postres|comidas)$",
        texto
    )

    if coincidencia_recaudado:
        categoria = coincidencia_recaudado.group(1)

        resultado = ejecutar_accion({
            "accion": "consultar_recaudado",
            "datos": {
                "categoria": categoria,
            },
        })

        if not resultado["ok"]:
            return error_comando(resultado)

        total = resultado["datos"]["total"]

        return {
            "ok": True,
            "codigo": "COMANDO_RECAUDADO_CATEGORIA",
            "categoria": categoria,
            "total": total,
            "respuesta": (
                f"*Recaudado en {categoria}*\n"
                f"{formatear_pesos(total)}"
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
