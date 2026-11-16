from collections import Counter
from decimal import Decimal, ROUND_HALF_UP
from typing import Annotated

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, StringConstraints


IdCatalogo = Annotated[int, Field(strict=True, gt=0, le=2**63 - 1)]
Ingrediente = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]


class LineaPedidoPos(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id_producto: IdCatalogo
    cantidad: int = Field(strict=True, gt=0, le=10_000)
    ingredientes_quitados: list[Ingrediente] = Field(default_factory=list, max_length=30)
    ids_adicionales: list[IdCatalogo] = Field(default_factory=list, max_length=30)


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


def calcular_pedido_pos(conexion, pedido):
    """Calcula el pedido dentro de la transacción abierta por el llamador."""
    cantidades = Counter()
    for linea in pedido.items:
        cantidades[linea.id_producto] += linea.cantidad

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
        if controla_stock and cantidad > stock:
            raise HTTPException(409, {
                "codigo": "STOCK_INSUFICIENTE",
                "mensaje": f"Stock insuficiente para {nombre}.",
                "id_producto": id_producto,
                "stock_disponible": stock,
                "cantidad_solicitada": cantidad,
            })

        ingredientes, adicionales = consultar_opciones_producto(conexion, id_producto)
        catalogo[id_producto] = (
            nombre, categoria, _precio_centavos(precio, nombre, 1), bool(controla_stock),
            {nombre.casefold(): nombre for nombre in ingredientes},
            {extra["id_adicional_catalogo"]: extra for extra in adicionales},
        )

    items = []
    for linea in pedido.items:
        nombre, categoria, base, controla_stock, ingredientes, extras = catalogo[linea.id_producto]
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
        unitario = base + sum(extra["precio_unitario_centavos"] for extra in adicionales)
        items.append({
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
        })

    return {"items": items, "total_centavos": sum(item["subtotal_centavos"] for item in items)}
