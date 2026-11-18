from collections import Counter
from decimal import Decimal, ROUND_HALF_UP
from typing import Annotated, Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from database import RUTA_ENTRENAMIENTO
from pos_entrenamiento_db import DESCUENTO_POSTRE_CENTAVOS, consultar_catalogo_entrenamiento
from pos_menu_entrenamiento import personalizacion_menu


IdCatalogo = Annotated[int, Field(strict=True, gt=0, le=2**63 - 1)]
Ingrediente = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]


class AdicionalPreparacion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tipo: Literal["cheddar", "huevo"]
    destino: Literal["principal", "papas", "pure"]
    cantidad: int = Field(strict=True, ge=1, le=30)


class LineaPedidoPos(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id_producto: IdCatalogo
    cantidad: int = Field(strict=True, gt=0, le=10_000)
    ingredientes_quitados: list[Ingrediente] = Field(default_factory=list, max_length=30)
    ids_adicionales: list[IdCatalogo] = Field(default_factory=list, max_length=30)
    adicionales_preparacion: list[AdicionalPreparacion] = Field(
        default_factory=list, max_length=6, exclude_if=lambda valor: not valor,
    )
    papas_dobles: bool = Field(default=False, strict=True, exclude_if=lambda valor: not valor)
    observacion: Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)] = Field(
        default="", exclude_if=lambda valor: not valor,
    )


class PedidoPos(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[LineaPedidoPos] = Field(min_length=1, max_length=100)


def consultar_opciones_producto(conexion, id_producto):
    ingredientes = conexion.execute(
        """
        SELECT ingrediente FROM pos_ingredientes_producto
        WHERE id_producto = ? ORDER BY ingrediente COLLATE NOCASE
        """,
        (id_producto,),
    ).fetchall()
    adicionales = conexion.execute(
        """
        SELECT a.id_adicional_catalogo, a.nombre, a.precio_venta
        FROM pos_adicionales_producto AS pa
        JOIN adicionales_catalogo AS a USING (id_adicional_catalogo)
        WHERE pa.id_producto = ? AND a.activo = 1
        ORDER BY a.nombre COLLATE NOCASE
        """,
        (id_producto,),
    ).fetchall()
    return [fila[0] for fila in ingredientes], [
        {"id_adicional_catalogo": id_extra, "nombre": nombre, "precio_venta": precio}
        for id_extra, nombre, precio in adicionales
    ]


def _precio_centavos(precio, nombre, minimo):
    if not isinstance(precio, (int, float)):
        raise HTTPException(409, f"Precio inválido para {nombre}.")
    importe = Decimal(str(precio))
    if not importe.is_finite() or not 0 <= importe <= 100_000_000:
        raise HTTPException(409, f"Precio inválido para {nombre}.")
    centavos = int((importe * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    if centavos < minimo:
        raise HTTPException(409, f"Precio inválido para {nombre}.")
    return centavos


def _personalizar_preparacion(linea, menu):
    if menu is None:
        if linea.adicionales_preparacion or linea.papas_dobles or linea.observacion:
            raise HTTPException(422, "Estas opciones están disponibles en modo entrenamiento.")
        return 0, {}

    adicionales = []
    recargo = 0
    guarnicion = menu["guarnicion"]
    recargo_papas = menu["papas_dobles_centavos"]
    if linea.papas_dobles:
        if recargo_papas is None:
            raise HTTPException(422, "Las papas dobles se pueden pedir en los combos con papas.")
        guarnicion = "Papas fritas dobles"
        recargo += recargo_papas
    elif recargo_papas is not None:
        guarnicion = "Papas fritas normales"

    destinos = menu["destinos"]
    opciones = {extra["tipo"]: extra for extra in menu["adicionales"]}
    usados = set()
    for extra in linea.adicionales_preparacion:
        clave = (extra.tipo, extra.destino)
        if clave in usados or extra.destino not in destinos or extra.tipo not in opciones:
            raise HTTPException(422, "Adicionales por preparación no disponibles o repetidos.")
        usados.add(clave)
        opcion = opciones[extra.tipo]
        recargo += opcion["precio_centavos"] * extra.cantidad
        adicionales.append({
            "tipo": extra.tipo,
            "nombre": opcion["nombre"],
            "destino": extra.destino,
            "preparacion": destinos[extra.destino],
            "cantidad": extra.cantidad,
            "precio_unitario_centavos": opcion["precio_centavos"],
        })

    detalle = {}
    if guarnicion:
        detalle["guarnicion"] = guarnicion
    if linea.observacion:
        detalle["observacion"] = linea.observacion
    if adicionales:
        detalle["adicionales_preparacion"] = adicionales
    if linea.papas_dobles:
        detalle["recargo_papas_dobles_centavos"] = recargo_papas
    return recargo, detalle


def calcular_pedido_pos(conexion, pedido):
    """Calcula el pedido dentro de la transacción abierta por el llamador."""
    cantidades = Counter()
    for linea in pedido.items:
        cantidades[linea.id_producto] += linea.cantidad

    entrenamiento = RUTA_ENTRENAMIENTO.get() is not None
    opciones = consultar_catalogo_entrenamiento(conexion) if entrenamiento else {}
    unidades_promo = Counter()
    grupos_promo = {}
    catalogo = {}
    for id_producto, cantidad in cantidades.items():
        producto = conexion.execute(
            """
            SELECT nombre, categoria, precio_venta, stock, controla_stock
            FROM productos WHERE id_producto = ?
            """,
            (id_producto,),
        ).fetchone()
        if producto is None:
            raise HTTPException(404, f"Producto no encontrado (ID {id_producto}).")

        nombre, categoria, precio, stock, controla_stock = producto
        estado, grupo = opciones.get(id_producto, ("disponible", None))
        if estado == "sin_stock":
            raise HTTPException(409, f"Sin stock: {nombre}.")
        if estado == "fuera_menu":
            raise HTTPException(409, f"{nombre} está fuera del menú.")
        if entrenamiento and precio is None:
            raise HTTPException(409, f"Precio pendiente para {nombre}.")
        if controla_stock and cantidad > stock:
            raise HTTPException(409, {
                "codigo": "STOCK_INSUFICIENTE",
                "mensaje": f"Stock insuficiente para {nombre}.",
                "id_producto": id_producto,
                "stock_disponible": stock,
                "cantidad_solicitada": cantidad,
            })

        base = _precio_centavos(precio, nombre, 1)
        if grupo is not None and base > DESCUENTO_POSTRE_CENTAVOS:
            grupos_promo[id_producto] = grupo
            unidades_promo[grupo] += cantidad
        ingredientes, adicionales = consultar_opciones_producto(conexion, id_producto)
        menu = personalizacion_menu(nombre, categoria) if entrenamiento else None
        if menu:
            ingredientes.extend(menu["ingredientes"])
        catalogo[id_producto] = (
            nombre, categoria, base, bool(controla_stock),
            {ingrediente.casefold(): ingrediente for ingrediente in ingredientes},
            {extra["id_adicional_catalogo"]: extra for extra in adicionales},
            menu,
        )

    pendientes_promo = {grupo: cantidad - cantidad % 2 for grupo, cantidad in unidades_promo.items()}
    descuento_total = 0
    items = []
    for linea in pedido.items:
        nombre, categoria, base, controla_stock, ingredientes, extras, menu = catalogo[linea.id_producto]
        quitados = [ingrediente.casefold() for ingrediente in linea.ingredientes_quitados]
        if len(set(quitados)) != len(quitados) or not ingredientes.keys() >= set(quitados):
            raise HTTPException(422, f"Ingredientes no permitidos o repetidos para {nombre}.")

        ids = linea.ids_adicionales
        if len(set(ids)) != len(ids) or not extras.keys() >= set(ids):
            raise HTTPException(422, f"Adicionales no disponibles o repetidos para {nombre}.")

        adicionales = [
            {
                "id_adicional_catalogo": id_extra,
                "nombre": extras[id_extra]["nombre"],
                "precio_unitario_centavos": _precio_centavos(
                    extras[id_extra]["precio_venta"], extras[id_extra]["nombre"], 0
                ),
            }
            for id_extra in ids
        ]
        recargo, detalle = _personalizar_preparacion(linea, menu)
        unitario = base + recargo + sum(extra["precio_unitario_centavos"] for extra in adicionales)
        item = {
            "id_producto": linea.id_producto,
            "producto": nombre,
            "categoria": categoria,
            "cantidad": linea.cantidad,
            "controla_stock": controla_stock,
            "ingredientes_quitados": [ingredientes[clave] for clave in quitados],
            "adicionales": adicionales,
            "precio_base_centavos": base,
            "precio_unitario_centavos": unitario,
            "subtotal_centavos": unitario * linea.cantidad,
            **detalle,
        }
        grupo = grupos_promo.get(linea.id_producto)
        cantidad_con_descuento = min(linea.cantidad, pendientes_promo.get(grupo, 0))
        if cantidad_con_descuento:
            # Una línea por precio efectivo permite devolver unidades al importe realmente cobrado.
            pendientes_promo[grupo] -= cantidad_con_descuento
            precio_reducido = unitario - DESCUENTO_POSTRE_CENTAVOS
            descuento = DESCUENTO_POSTRE_CENTAVOS * cantidad_con_descuento
            items.append(dict(item, cantidad=cantidad_con_descuento,
                              precio_unitario_centavos=precio_reducido,
                              subtotal_centavos=precio_reducido * cantidad_con_descuento,
                              descuento_centavos=descuento))
            descuento_total += descuento
        cantidad_regular = linea.cantidad - cantidad_con_descuento
        if cantidad_regular:
            items.append(dict(item, cantidad=cantidad_regular, subtotal_centavos=unitario * cantidad_regular))

    resultado = {"items": items, "total_centavos": sum(item["subtotal_centavos"] for item in items)}
    if descuento_total:
        resultado["descuento_centavos"] = descuento_total
    return resultado
