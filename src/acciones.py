from datetime import datetime
import re
import unicodedata

from adicionales import (
    configurar_adicional,
    listar_adicionales,
)
from ajustes_stock import (
    registrar_consumo_interno,
    registrar_inventario_fisico,
    registrar_merma,
)
from caja import (
    obtener_estado_caja,
    obtener_caja_seccion,
    recaudado_por_categoria,
)
from compras import registrar_compra
from costos_postres import (
    estimar_costo_receta,
    historial_gastos_postres,
    historial_producciones_postres,
    necesidades_produccion,
    obtener_receta,
    obtener_stock_insumos,
    registrar_compra_insumo,
    registrar_compra_insumo_paquetes,
    registrar_inventario_insumo,
    registrar_produccion_postre,
)
from deudas_negocio import (
    ajustar_deuda,
    configurar_vencimiento,
    detalle_deuda,
    deuda_vence_primero,
    historial_deuda,
    registrar_compra_deuda,
    registrar_pago_deuda,
    registrar_saldo_inicial,
    resumen_deudas,
)
from gastos import registrar_gasto
from productos import obtener_productos
from rentabilidad import (
    rentabilidad_categoria,
    rentabilidad_producto,
)
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
    # Regla de bebidas:
    # si una Manaos se menciona por sabor sin tamaño,
    # se interpreta como botella grande de 2.25 l.
    # La chica debe indicarse explícitamente como 600/chica.
    "manaos cola": "manaos cola 2.25 l",
    "manaos pomelo": "manaos pomelo 2.25 l",
    "manaos naranja": "manaos naranja 2.25 l",
    "manaos manzana": "manaos manzana 2.25 l",
    "manaos lima": "manaos lima 2.25 l",
    "manaos lima limon": "manaos lima 2.25 l",

    "manaos cola chica": "manaos cola 600 ml",
    "manaos pomelo chica": "manaos pomelo 600 ml",
    "manaos cola 600": "manaos cola 600 ml",
    "manaos pomelo 600": "manaos pomelo 600 ml",

    "manaos cola grande": "manaos cola 2.25 l",
    "manaos naranja grande": "manaos naranja 2.25 l",
    "manaos manzana grande": "manaos manzana 2.25 l",
    "manaos pomelo grande": "manaos pomelo 2.25 l",
    "manaos lima grande": "manaos lima 2.25 l",
    "manaos lima limon grande": "manaos lima 2.25 l",

    # Pepsi y 7up actualmente solo se manejan en lata.
    "pepsi": "pepsi lata",
    "7up": "7 up lata",
    "7 up": "7 up lata",
    "postre oreo": "oreo",
    "postre chocotorta": "chocotorta",
    "bigmac simple": "big mac simple",
    "bigmac doble": "big mac doble",

    # Hamburguesa genérica = clásica.
    "hamburguesa simple": "clasica simple",
    "hamburguesas simples": "clasica simple",
    "hamburguesa doble": "clasica doble",
    "hamburguesas dobles": "clasica doble",

    # Napo genérica = pollo con fritas.
    "napo": "napo de pollo con fritas",
    "napo pollo": "napo de pollo con fritas",
    "napo de pollo": "napo de pollo con fritas",
    "napo con fritas": "napo de pollo con fritas",
    "napo con pure": "napo de pollo con pure",
    "napo carne": "napo de carne con fritas",
    "napo de carne": "napo de carne con fritas",
    "napo carne con pure": "napo de carne con pure",
    "napo de carne con pure": "napo de carne con pure",

    # Mila sola define guarnición fritas, pero no inventa la carne.
    "mila": "milanesa con fritas",
    "mila con fritas": "milanesa con fritas",
    "mila con pure": "milanesa con pure",
    "mila pollo": "milanesa de pollo con fritas",
    "mila de pollo": "milanesa de pollo con fritas",
    "mila carne": "milanesa de carne con fritas",
    "mila de carne": "milanesa de carne con fritas",

    # Abreviaturas habituales de postres.
    "choco": "chocotorta",
    "chocolina": "chocotorta",
    "postre choco": "chocotorta",
    "postre de chocolina": "chocotorta",

    # Regla de sanguches:
    # "chico" y "grande" sin aclarar carne/pollo
    # se interpretan como pollo con papas.
    "sanguche chico": "chico de pollo papas",
    "sandwich chico": "chico de pollo papas",
    "sanguche chico con papas": "chico de pollo papas",
    "sandwich chico con papas": "chico de pollo papas",
    "sanguches chicos": "chico de pollo papas",
    "sandwiches chicos": "chico de pollo papas",

    "sanguche grande": "grande de pollo papas",
    "sandwich grande": "grande de pollo papas",
    "sanguche grande con papas": "grande de pollo papas",
    "sandwich grande con papas": "grande de pollo papas",
    "sanguches grandes": "grande de pollo papas",
    "sandwiches grandes": "grande de pollo papas",

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


def accion_consultar_caja_seccion(datos):
    seccion = normalizar_texto(
        datos.get("seccion")
    )

    try:
        estado = obtener_caja_seccion(
            seccion
        )
    except ValueError as error:
        return {
            "ok": False,
            "codigo": "SECCION_CAJA_INVALIDA",
            "mensaje": str(error),
        }

    return {
        "ok": True,
        "codigo": "ACCION_CAJA_SECCION",
        "datos": estado,
    }


def accion_consultar_recaudado(datos):
    categoria = normalizar_texto(
        datos.get("categoria")
    )

    try:
        total = recaudado_por_categoria(
            categoria
        )
    except ValueError as error:
        return {
            "ok": False,
            "codigo": "CATEGORIA_RECAUDACION_INVALIDA",
            "mensaje": str(error),
        }

    return {
        "ok": True,
        "codigo": "ACCION_RECAUDADO_CATEGORIA",
        "datos": {
            "categoria": categoria,
            "total": total,
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


def accion_registrar_compra_pack(datos):
    producto_texto = datos.get("producto")
    cantidad_packs = datos.get("cantidad_packs")
    costo_total = datos.get("costo_total")
    precio_pack = datos.get("precio_pack")

    if (
        not isinstance(producto_texto, str)
        or not producto_texto.strip()
    ):
        return {
            "ok": False,
            "codigo": "DATOS_ACCION_INVALIDOS",
            "mensaje": "La compra debe indicar un producto.",
        }

    if (
        isinstance(cantidad_packs, bool)
        or not isinstance(cantidad_packs, int)
        or cantidad_packs <= 0
    ):
        return {
            "ok": False,
            "codigo": "DATOS_ACCION_INVALIDOS",
            "mensaje": (
                "La cantidad de packs debe ser un entero "
                "mayor que cero."
            ),
        }

    if costo_total is None and precio_pack is None:
        return {
            "ok": False,
            "codigo": "COSTO_COMPRA_REQUERIDO",
            "mensaje": (
                "Indicá el costo de la compra. "
                "Ejemplos: 'compra 2 packs manaos cola por 17000' "
                "o 'compra 2 packs manaos cola a 8500 cada pack'."
            ),
        }

    if costo_total is not None and precio_pack is not None:
        return {
            "ok": False,
            "codigo": "DATOS_ACCION_INVALIDOS",
            "mensaje": (
                "Indicá costo total o precio por pack, no ambos."
            ),
        }

    resolucion = resolver_producto(
        producto_texto
    )

    if not resolucion["ok"]:
        return resolucion

    producto = resolucion["producto"]
    unidades_por_pack = producto.get(
        "unidades_por_pack"
    )

    if (
        isinstance(unidades_por_pack, bool)
        or not isinstance(unidades_por_pack, int)
        or unidades_por_pack <= 1
    ):
        return {
            "ok": False,
            "codigo": "PACK_NO_CONFIGURADO",
            "mensaje": (
                f"{producto['nombre']} no tiene una cantidad "
                "por pack configurada."
            ),
        }

    valor_informado = (
        costo_total
        if costo_total is not None
        else precio_pack
    )

    if (
        isinstance(valor_informado, bool)
        or not isinstance(
            valor_informado,
            (int, float)
        )
        or valor_informado <= 0
    ):
        return {
            "ok": False,
            "codigo": "DATOS_ACCION_INVALIDOS",
            "mensaje": (
                "El costo de compra debe ser un número "
                "mayor que cero."
            ),
        }

    cantidad_unidades = (
        cantidad_packs
        * unidades_por_pack
    )

    if costo_total is not None:
        total_compra = float(costo_total)
    else:
        total_compra = (
            cantidad_packs
            * float(precio_pack)
        )

    precio_unitario = (
        total_compra
        / cantidad_unidades
    )

    resultado = registrar_compra(
        id_producto=producto["id_producto"],
        cantidad=cantidad_unidades,
        precio_unitario=precio_unitario,
        cuenta_deuda=datos.get("cuenta_deuda"),
    )

    if not resultado["ok"]:
        return resultado

    return {
        "ok": True,
        "codigo": "ACCION_COMPRA_PACK_REGISTRADA",
        "datos": {
            "id_compra": resultado["id_compra"],
            "id_producto": producto["id_producto"],
            "producto": resultado["producto"],
            "cantidad_packs": cantidad_packs,
            "unidades_por_pack": unidades_por_pack,
            "cantidad_unidades": cantidad_unidades,
            "precio_unitario_compra": precio_unitario,
            "precio_pack": (
                float(precio_pack)
                if precio_pack is not None
                else (
                    total_compra
                    / cantidad_packs
                )
            ),
            "total": total_compra,
            "stock_actual": resultado["stock_actual"],
            "medio_pago": resultado.get("medio_pago"),
            "cuenta_deuda": resultado.get("cuenta_deuda"),
            "saldo_deuda": resultado.get("saldo_deuda"),
            "id_movimiento_deuda": resultado.get(
                "id_movimiento_deuda"
            ),
        },
    }


def accion_resumen_deudas_negocio():
    return {
        "ok": True,
        "codigo": "ACCION_RESUMEN_DEUDAS_NEGOCIO",
        "datos": resumen_deudas(),
    }


def accion_detalle_deuda_negocio(datos):
    resultado = detalle_deuda(
        datos.get("cuenta")
    )

    if not resultado["ok"]:
        return resultado

    return {
        "ok": True,
        "codigo": "ACCION_DETALLE_DEUDA_NEGOCIO",
        "datos": resultado,
    }


def accion_historial_deuda_negocio(datos):
    resultado = historial_deuda(
        datos.get("cuenta"),
        limite=datos.get("limite", 20),
    )

    if not resultado["ok"]:
        return resultado

    return {
        "ok": True,
        "codigo": "ACCION_HISTORIAL_DEUDA_NEGOCIO",
        "datos": resultado,
    }


def accion_registrar_saldo_inicial_deuda(datos):
    resultado = registrar_saldo_inicial(
        nombre=datos.get("cuenta"),
        monto=datos.get("monto"),
    )

    if not resultado["ok"]:
        return resultado

    return {
        "ok": True,
        "codigo": "ACCION_SALDO_INICIAL_DEUDA_REGISTRADO",
        "datos": resultado,
    }


def accion_registrar_compra_deuda(datos):
    resultado = registrar_compra_deuda(
        nombre=datos.get("cuenta"),
        monto=datos.get("monto"),
        descripcion=datos.get("descripcion"),
    )

    if not resultado["ok"]:
        return resultado

    return {
        "ok": True,
        "codigo": "ACCION_COMPRA_DEUDA_REGISTRADA",
        "datos": resultado,
    }


def accion_registrar_pago_deuda(datos):
    resultado = registrar_pago_deuda(
        nombre=datos.get("cuenta"),
        monto=datos.get("monto"),
        descripcion=datos.get("descripcion"),
        afecta_caja=datos.get(
            "afecta_caja",
            True,
        ),
    )

    if not resultado["ok"]:
        return resultado

    return {
        "ok": True,
        "codigo": "ACCION_PAGO_DEUDA_REGISTRADO",
        "datos": resultado,
    }


def accion_ajustar_deuda(datos):
    resultado = ajustar_deuda(
        nombre=datos.get("cuenta"),
        nuevo_saldo=datos.get("saldo"),
        descripcion=datos.get("descripcion"),
    )

    if not resultado["ok"]:
        return resultado

    return {
        "ok": True,
        "codigo": "ACCION_DEUDA_AJUSTADA",
        "datos": resultado,
    }


def accion_configurar_vencimiento_deuda(datos):
    resultado = configurar_vencimiento(
        nombre=datos.get("cuenta"),
        fecha_vencimiento=datos.get(
            "fecha_vencimiento"
        ),
    )

    if not resultado["ok"]:
        return resultado

    return {
        "ok": True,
        "codigo": "ACCION_VENCIMIENTO_DEUDA_CONFIGURADO",
        "datos": resultado,
    }


def accion_deuda_vence_primero():
    return {
        "ok": True,
        "codigo": "ACCION_DEUDA_VENCE_PRIMERO",
        "datos": deuda_vence_primero(),
    }


def accion_configurar_adicional(datos):
    resultado = configurar_adicional(
        nombre=datos.get("nombre"),
        precio_venta=datos.get("precio_venta"),
        costo_unitario=datos.get("costo_unitario"),
    )

    if not resultado["ok"]:
        return resultado

    return {
        "ok": True,
        "codigo": "ACCION_ADICIONAL_CONFIGURADO",
        "datos": resultado,
    }


def accion_consultar_adicionales():
    return {
        "ok": True,
        "codigo": "ACCION_ADICIONALES",
        "datos": {
            "adicionales": listar_adicionales(),
        },
    }


def accion_consultar_rentabilidad_producto(datos):
    resolucion = resolver_producto(
        datos.get("producto")
    )

    if not resolucion["ok"]:
        return resolucion

    resultado = rentabilidad_producto(
        resolucion["producto"]["id_producto"]
    )

    if not resultado["ok"]:
        return resultado

    return {
        "ok": True,
        "codigo": "ACCION_RENTABILIDAD_PRODUCTO",
        "datos": resultado,
    }


def accion_consultar_rentabilidad_categoria(datos):
    resultado = rentabilidad_categoria(
        datos.get("categoria")
    )

    if not resultado["ok"]:
        return resultado

    return {
        "ok": True,
        "codigo": "ACCION_RENTABILIDAD_CATEGORIA",
        "datos": resultado,
    }


def accion_consultar_stock_insumos():
    return {
        "ok": True,
        "codigo": "ACCION_STOCK_INSUMOS",
        "datos": {
            "insumos": obtener_stock_insumos(),
        },
    }


def accion_registrar_inventario_insumo(datos):
    resultado = registrar_inventario_insumo(
        nombre_insumo=datos.get("insumo"),
        cantidad_real=datos.get("cantidad"),
        unidad=datos.get("unidad"),
        contexto=datos.get("contexto"),
    )

    if not resultado["ok"]:
        return resultado

    return {
        "ok": True,
        "codigo": "ACCION_INVENTARIO_INSUMO_REGISTRADO",
        "datos": resultado,
    }


def accion_consultar_necesidades_produccion(datos):
    resultado = necesidades_produccion(
        producto=datos.get("producto"),
        cantidad=datos.get("cantidad"),
    )

    if not resultado["ok"]:
        return resultado

    return {
        "ok": True,
        "codigo": "ACCION_NECESIDADES_PRODUCCION",
        "datos": resultado,
    }


def accion_registrar_produccion_postre(datos):
    resultado = registrar_produccion_postre(
        producto=datos.get("producto"),
        cantidad=datos.get("cantidad"),
        contexto=datos.get("contexto"),
    )

    if not resultado["ok"]:
        return resultado

    return {
        "ok": True,
        "codigo": "ACCION_PRODUCCION_POSTRE_REGISTRADA",
        "datos": resultado,
    }


def accion_historial_producciones_postres(datos):
    limite = datos.get("limite", 10)

    return {
        "ok": True,
        "codigo": "ACCION_HISTORIAL_PRODUCCIONES_POSTRES",
        "datos": {
            "producciones": historial_producciones_postres(
                limite=limite
            ),
        },
    }


def accion_registrar_compra_insumo_paquetes(datos):
    resultado = registrar_compra_insumo_paquetes(
        nombre_insumo=datos.get("insumo"),
        cantidad_paquetes=datos.get("cantidad_paquetes"),
        presentacion=datos.get("presentacion"),
        costo_total=datos.get("costo_total"),
        comercio=datos.get("comercio"),
    )

    if not resultado["ok"]:
        return resultado

    return {
        "ok": True,
        "codigo": "ACCION_COMPRA_INSUMO_PAQUETES_REGISTRADA",
        "datos": resultado,
    }


def accion_registrar_compra_insumo(datos):
    resultado = registrar_compra_insumo(
        nombre_insumo=datos.get("insumo"),
        cantidad=datos.get("cantidad"),
        unidad=datos.get("unidad"),
        costo_total=datos.get("costo_total"),
        comercio=datos.get("comercio"),
        observaciones=datos.get("observaciones"),
    )

    if not resultado["ok"]:
        return resultado

    return {
        "ok": True,
        "codigo": "ACCION_COMPRA_INSUMO_REGISTRADA",
        "datos": resultado,
    }


def accion_consultar_receta(datos):
    resultado = obtener_receta(
        datos.get("producto")
    )

    if not resultado["ok"]:
        return resultado

    return {
        "ok": True,
        "codigo": "ACCION_RECETA",
        "datos": resultado["receta"],
    }


def accion_estimar_costo_receta(datos):
    resultado = estimar_costo_receta(
        producto=datos.get("producto"),
        cantidad_objetivo=datos.get("cantidad"),
    )

    if not resultado["ok"]:
        return resultado

    return {
        "ok": True,
        "codigo": resultado["codigo"],
        "datos": resultado,
    }


def accion_historial_gastos_postres(datos):
    limite = datos.get("limite", 10)

    if (
        isinstance(limite, bool)
        or not isinstance(limite, int)
        or limite <= 0
    ):
        limite = 10

    return {
        "ok": True,
        "codigo": "ACCION_HISTORIAL_GASTOS_POSTRES",
        "datos": {
            "gastos": historial_gastos_postres(
                limite=limite
            ),
        },
    }


def accion_registrar_gasto(datos):
    descripcion = datos.get("descripcion")
    monto = datos.get("monto")
    categoria = datos.get("categoria") or "Otros"

    if not isinstance(descripcion, str) or not descripcion.strip():
        return {
            "ok": False,
            "codigo": "DATOS_ACCION_INVALIDOS",
            "mensaje": "El gasto debe indicar una descripción.",
        }

    if isinstance(monto, bool) or not isinstance(monto, (int, float)):
        return {
            "ok": False,
            "codigo": "DATOS_ACCION_INVALIDOS",
            "mensaje": "El monto del gasto debe ser numérico.",
        }

    resultado = registrar_gasto(
        categoria=categoria,
        descripcion_gasto=descripcion.strip(),
        valor_final=monto,
        seccion=datos.get("seccion"),
        subseccion=datos.get("subseccion"),
    )

    if not resultado["ok"]:
        return resultado

    return {
        "ok": True,
        "codigo": "ACCION_GASTO_REGISTRADO",
        "datos": {
            "id_gasto": resultado["id_gasto"],
            "categoria": resultado["categoria"],
            "descripcion": resultado["descripcion"],
            "monto": resultado["valor"],
            "fecha": resultado["fecha"],
            "seccion": resultado.get("seccion"),
            "subseccion": resultado.get("subseccion"),
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
        adicionales=datos.get("adicionales"),
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
            "subtotal_producto": resultado["subtotal_producto"],
            "adicionales": resultado["adicionales"],
            "total_adicionales": resultado["total_adicionales"],
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

        if "adicionales" in item:
            item_resuelto["adicionales"] = item["adicionales"]

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

    if accion == "consultar caja seccion":
        return accion_consultar_caja_seccion(datos)

    if accion == "consultar recaudado":
        return accion_consultar_recaudado(datos)

    if accion == "consultar resumen":
        return accion_consultar_resumen(datos)

    if accion == "consultar total":
        return accion_consultar_total(datos)

    if accion == "registrar gasto":
        return accion_registrar_gasto(datos)

    if accion == "registrar compra insumo":
        return accion_registrar_compra_insumo(datos)

    if accion == "registrar compra insumo paquetes":
        return accion_registrar_compra_insumo_paquetes(datos)

    if accion == "registrar produccion postre":
        return accion_registrar_produccion_postre(datos)

    if accion == "consultar stock insumos":
        return accion_consultar_stock_insumos()

    if accion == "consultar rentabilidad producto":
        return accion_consultar_rentabilidad_producto(datos)

    if accion == "configurar adicional":
        return accion_configurar_adicional(datos)

    if accion == "consultar deudas negocio":
        return accion_resumen_deudas_negocio()

    if accion == "consultar deuda negocio":
        return accion_detalle_deuda_negocio(datos)

    if accion == "historial deuda negocio":
        return accion_historial_deuda_negocio(datos)

    if accion == "registrar saldo inicial deuda":
        return accion_registrar_saldo_inicial_deuda(datos)

    if accion == "registrar compra deuda":
        return accion_registrar_compra_deuda(datos)

    if accion == "registrar pago deuda":
        return accion_registrar_pago_deuda(datos)

    if accion == "ajustar deuda negocio":
        return accion_ajustar_deuda(datos)

    if accion == "configurar vencimiento deuda":
        return accion_configurar_vencimiento_deuda(datos)

    if accion == "consultar deuda vence primero":
        return accion_deuda_vence_primero()

    if accion == "consultar adicionales":
        return accion_consultar_adicionales()

    if accion == "consultar rentabilidad categoria":
        return accion_consultar_rentabilidad_categoria(datos)

    if accion == "registrar inventario insumo":
        return accion_registrar_inventario_insumo(datos)

    if accion == "consultar necesidades produccion":
        return accion_consultar_necesidades_produccion(datos)

    if accion == "historial producciones postres":
        return accion_historial_producciones_postres(datos)

    if accion == "consultar receta":
        return accion_consultar_receta(datos)

    if accion == "estimar costo receta":
        return accion_estimar_costo_receta(datos)

    if accion == "historial gastos postres":
        return accion_historial_gastos_postres(datos)

    if accion == "registrar compra pack":
        return accion_registrar_compra_pack(datos)

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
