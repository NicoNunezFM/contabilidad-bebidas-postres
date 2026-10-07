from database import obtener_conexion
from deudas_negocio import total_reservado_deudas
from movimientos_caja import (
    total_aportes,
    total_movimientos_seccion,
    total_retiros,
)
from saldos_caja import (
    normalizar_seccion_caja,
    obtener_saldo_inicial_caja,
)
from diezmo import estado_general_diezmo


# ============================================================
# TOTAL DE VENTAS
# ============================================================

def ventas_caja():
    """
    Devuelve el total de ventas activas.
    Las ventas anuladas no participan del cálculo.
    """

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute(
        """
        SELECT SUM(
            cantidad * precio_unitario
            + COALESCE(
                (
                    SELECT SUM(precio_total)
                    FROM venta_adicionales
                    WHERE venta_adicionales.id_venta = ventas.id_venta
                ),
                0
            )
        )
        FROM ventas
        WHERE anulada = 0
        """
    )

    resultado = cursor.fetchone()

    ventas = resultado[0]

    if ventas is None:
        ventas = 0

    conexion.close()

    return ventas


# ============================================================
# TOTAL DE COMPRAS
# ============================================================

def compras_caja():
    """
    Devuelve el total de compras activas.
    Las compras anuladas no participan del cálculo.
    """

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute(
        """
        SELECT SUM(cantidad * precio_unitario)
        FROM compras
        WHERE anulada = 0
          AND COALESCE(medio_pago, 'Caja') = 'Caja'
        """
    )

    resultado = cursor.fetchone()

    compras = resultado[0]

    if compras is None:
        compras = 0

    conexion.close()

    return compras


# ============================================================
# TOTAL DE GASTOS
# ============================================================

def gastos_caja():
    """
    Devuelve el total de gastos activos.
    Los gastos anulados no participan del cálculo.
    """

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute(
        """
        SELECT SUM(valor_final)
        FROM gastos
        WHERE anulado = 0
        """
    )

    resultado = cursor.fetchone()

    gastos = resultado[0]

    if gastos is None:
        gastos = 0

    conexion.close()

    return gastos


# ============================================================
# CAJAS VIRTUALES POR SECCIÓN
# ============================================================

CATEGORIAS_CAJA_BEBIDAS_POSTRES = {
    "bebidas",
    "postres",
}


def _ventas_por_categorias(
    categorias=None,
    excluir_categorias=None,
    id_venta_corte=0,
):
    categorias = categorias or set()
    excluir_categorias = excluir_categorias or set()

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    condiciones = [
        "ventas.anulada = 0",
    ]
    parametros = []

    if id_venta_corte:
        condiciones.append(
            "ventas.id_venta > ?"
        )
        parametros.append(
            int(id_venta_corte)
        )

    if categorias:
        placeholders = ",".join(
            "?"
            for _ in categorias
        )
        condiciones.append(
            f"LOWER(productos.categoria) IN ({placeholders})"
        )
        parametros.extend(
            sorted(categorias)
        )

    if excluir_categorias:
        placeholders = ",".join(
            "?"
            for _ in excluir_categorias
        )
        condiciones.append(
            f"LOWER(productos.categoria) NOT IN ({placeholders})"
        )
        parametros.extend(
            sorted(excluir_categorias)
        )

    cursor.execute(
        f"""
        SELECT SUM(
            ventas.cantidad * ventas.precio_unitario
            + COALESCE(
                (
                    SELECT SUM(precio_total)
                    FROM venta_adicionales
                    WHERE venta_adicionales.id_venta = ventas.id_venta
                ),
                0
            )
        )
        FROM ventas
        INNER JOIN productos
            ON ventas.id_producto = productos.id_producto
        WHERE {" AND ".join(condiciones)}
        """,
        parametros
    )

    total = cursor.fetchone()[0]
    conexion.close()

    return total or 0


def _compras_por_categorias(
    categorias=None,
    excluir_categorias=None,
    id_compra_corte=0,
):
    categorias = categorias or set()
    excluir_categorias = excluir_categorias or set()

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    condiciones = [
        "compras.anulada = 0",
        "COALESCE(compras.medio_pago, 'Caja') = 'Caja'",
    ]
    parametros = []

    if id_compra_corte:
        condiciones.append(
            "compras.id_compra > ?"
        )
        parametros.append(
            int(id_compra_corte)
        )

    if categorias:
        placeholders = ",".join(
            "?"
            for _ in categorias
        )
        condiciones.append(
            f"LOWER(productos.categoria) IN ({placeholders})"
        )
        parametros.extend(
            sorted(categorias)
        )

    if excluir_categorias:
        placeholders = ",".join(
            "?"
            for _ in excluir_categorias
        )
        condiciones.append(
            f"LOWER(productos.categoria) NOT IN ({placeholders})"
        )
        parametros.extend(
            sorted(excluir_categorias)
        )

    cursor.execute(
        f"""
        SELECT SUM(
            compras.cantidad * compras.precio_unitario
        )
        FROM compras
        INNER JOIN productos
            ON compras.id_producto = productos.id_producto
        WHERE {" AND ".join(condiciones)}
        """,
        parametros
    )

    total = cursor.fetchone()[0]
    conexion.close()

    return total or 0


def _gastos_por_seccion(
    secciones,
    id_gasto_corte=0,
):
    if isinstance(secciones, str):
        secciones = {secciones}

    secciones = set(
        secciones or set()
    )

    if not secciones:
        return 0

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    placeholders = ",".join(
        "?"
        for _ in secciones
    )

    condiciones = [
        "anulado = 0",
        f"seccion IN ({placeholders})",
    ]
    parametros = sorted(
        secciones
    )

    if id_gasto_corte:
        condiciones.append(
            "id_gasto > ?"
        )
        parametros.append(
            int(id_gasto_corte)
        )

    cursor.execute(
        f"""
        SELECT SUM(valor_final)
        FROM gastos
        WHERE {" AND ".join(condiciones)}
        """,
        parametros
    )

    total = cursor.fetchone()[0]
    conexion.close()

    return total or 0


def recaudado_por_categoria(categoria):
    categoria_normalizada = str(
        categoria or ""
    ).strip().lower()

    if categoria_normalizada == "bebidas":
        return _ventas_por_categorias(
            categorias={"bebidas"}
        )

    if categoria_normalizada == "postres":
        return _ventas_por_categorias(
            categorias={"postres"}
        )

    if categoria_normalizada == "comidas":
        return _ventas_por_categorias(
            excluir_categorias=CATEGORIAS_CAJA_BEBIDAS_POSTRES
        )

    raise ValueError(
        "La categoría debe ser bebidas, postres o comidas."
    )


def obtener_caja_seccion(seccion):
    seccion_normalizada = normalizar_seccion_caja(
        seccion
    )

    if seccion_normalizada is None:
        raise ValueError(
            "La sección debe ser bebidas_postres o rotiseria."
        )

    apertura = obtener_saldo_inicial_caja(
        seccion_normalizada
    )

    id_venta_corte = (
        apertura["id_venta_corte"]
        if apertura
        else 0
    )
    id_compra_corte = (
        apertura["id_compra_corte"]
        if apertura
        else 0
    )
    id_gasto_corte = (
        apertura["id_gasto_corte"]
        if apertura
        else 0
    )
    id_movimiento_corte = (
        apertura["id_movimiento_caja_corte"]
        if apertura
        else 0
    )

    if seccion_normalizada == "bebidas_postres":
        ventas_bebidas = _ventas_por_categorias(
            categorias={"bebidas"},
            id_venta_corte=id_venta_corte,
        )
        ventas_postres = _ventas_por_categorias(
            categorias={"postres"},
            id_venta_corte=id_venta_corte,
        )
        ventas = (
            ventas_bebidas
            + ventas_postres
        )

        compras = _compras_por_categorias(
            categorias=CATEGORIAS_CAJA_BEBIDAS_POSTRES,
            id_compra_corte=id_compra_corte,
        )
        gastos_seccion = _gastos_por_seccion(
            {"bebidas_postres"},
            id_gasto_corte=id_gasto_corte,
        )
        nombre = "Bebidas + Postres"
        detalle_recaudado = {
            "recaudado_bebidas": ventas_bebidas,
            "recaudado_postres": ventas_postres,
        }

    else:
        ventas = _ventas_por_categorias(
            excluir_categorias=CATEGORIAS_CAJA_BEBIDAS_POSTRES,
            id_venta_corte=id_venta_corte,
        )
        compras = _compras_por_categorias(
            excluir_categorias=CATEGORIAS_CAJA_BEBIDAS_POSTRES,
            id_compra_corte=id_compra_corte,
        )
        gastos_seccion = _gastos_por_seccion(
            {"rotiseria", "comidas"},
            id_gasto_corte=id_gasto_corte,
        )
        nombre = "Rotisería"
        detalle_recaudado = {
            "recaudado_comidas": ventas,
        }

    aportes = total_movimientos_seccion(
        seccion_normalizada,
        "Aporte",
        id_movimiento_corte,
    )
    retiros = total_movimientos_seccion(
        seccion_normalizada,
        "Retiro",
        id_movimiento_corte,
    )

    saldo_operativo = (
        ventas
        - compras
        - gastos_seccion
        + aportes
        - retiros
    )

    saldo_inicial = (
        apertura["monto"]
        if apertura
        else 0
    )

    saldo_actual = (
        saldo_inicial
        + saldo_operativo
        if apertura
        else saldo_operativo
    )

    return {
        "seccion": seccion_normalizada,
        "nombre": nombre,
        "saldo_inicial_configurado": bool(
            apertura
        ),
        "saldo_inicial": saldo_inicial,
        "fecha_inicio": (
            apertura["fecha_hora"]
            if apertura
            else None
        ),
        "ventas": ventas,
        **detalle_recaudado,
        "compras_directas": compras,
        "gastos_seccion": gastos_seccion,
        "aportes": aportes,
        "retiros": retiros,
        "saldo_operativo": saldo_operativo,
        "saldo_actual": saldo_actual,
        "incluye_gastos_generales": False,
    }


# ============================================================
# OBTENER ESTADO DE CAJA
# ============================================================

def obtener_estado_caja():
    """
    Devuelve el estado general de caja como un diccionario.

    Este formato puede ser utilizado por:
    - Terminal
    - FastAPI
    - WhatsApp
    - Notion
    - IA
    """

    compras = compras_caja()
    ventas = ventas_caja()
    gastos = gastos_caja()

    aportes = total_aportes()
    retiros = total_retiros()

    # Resultado propio del negocio.
    resultado_negocio = (
        ventas
        - compras
        - gastos
    )

    # Caja base teniendo en cuenta aportes y retiros.
    saldo_caja = (
        resultado_negocio
        + aportes
        - retiros
    )

    # Consultar estado global del diezmo.
    estado_diezmo = estado_general_diezmo()

    diezmo_reservado = estado_diezmo["reservado_en_caja"]
    diezmo_entregado = estado_diezmo["entregado_total"]

    # El dinero entregado como diezmo ya no está físicamente
    # dentro de la caja.
    saldo_fisico = (
        saldo_caja
        - diezmo_entregado
    )

    # El diezmo reservado sigue físicamente en caja,
    # pero no debería considerarse disponible.
    deuda_reservada = total_reservado_deudas()

    saldo_disponible = (
        saldo_fisico
        - diezmo_reservado
        - deuda_reservada
    )

    caja_bebidas_postres = obtener_caja_seccion(
        "bebidas_postres"
    )
    caja_rotiseria = obtener_caja_seccion(
        "rotiseria"
    )

    cajas_iniciadas = (
        caja_bebidas_postres["saldo_inicial_configurado"]
        and caja_rotiseria["saldo_inicial_configurado"]
    )

    total_cajas_actuales = (
        caja_bebidas_postres["saldo_actual"]
        + caja_rotiseria["saldo_actual"]
    )

    return {
        "ventas": ventas,
        "compras": compras,
        "gastos": gastos,
        "resultado_negocio": resultado_negocio,
        "aportes": aportes,
        "retiros": retiros,
        "saldo_caja": saldo_caja,
        "diezmo_entregado": diezmo_entregado,
        "diezmo_reservado": diezmo_reservado,
        "deuda_reservada": deuda_reservada,
        "saldo_fisico": saldo_fisico,
        "saldo_disponible": saldo_disponible,
        "cajas_separadas_activas": cajas_iniciadas,
        "caja_bebidas_postres": caja_bebidas_postres,
        "caja_rotiseria": caja_rotiseria,
        "total_cajas_actuales": total_cajas_actuales,
    }


# ============================================================
# MOSTRAR CAJA EN TERMINAL
# ============================================================

def mostrar_caja():
    """
    Muestra en terminal el estado general de caja.

    Los cálculos se realizan en obtener_estado_caja()
    para evitar duplicar lógica.
    """

    estado = obtener_estado_caja()

    ventas = estado["ventas"]
    compras = estado["compras"]
    gastos = estado["gastos"]
    resultado_negocio = estado["resultado_negocio"]

    aportes = estado["aportes"]
    retiros = estado["retiros"]

    saldo_caja = estado["saldo_caja"]

    diezmo_entregado = estado["diezmo_entregado"]
    diezmo_reservado = estado["diezmo_reservado"]

    saldo_fisico = estado["saldo_fisico"]
    saldo_disponible = estado["saldo_disponible"]

    print("=" * 40)
    print(f"{'CONTROL DEL NEGOCIO':^40}")
    print("=" * 40)

    print("\nINGRESOS")
    print(f"{'Ventas:':<25} ${ventas:>12.2f}")
    print(f"{'Aportes:':<25} ${aportes:>12.2f}")

    print("\nEGRESOS")
    print(f"{'Compras:':<25} ${compras:>12.2f}")
    print(f"{'Gastos:':<25} ${gastos:>12.2f}")
    print(f"{'Retiros:':<25} ${retiros:>12.2f}")

    print("\nDIEZMO")
    print(
        f"{'Reservado:':<25} "
        f"${diezmo_reservado:>12.2f}"
    )
    print(
        f"{'Entregado:':<25} "
        f"${diezmo_entregado:>12.2f}"
    )

    print("\n" + "-" * 40)

    print(
        f"{'RESULTADO NEGOCIO:':<25} "
        f"${resultado_negocio:>12.2f}"
    )

    print(
        f"{'SALDO DE CAJA:':<25} "
        f"${saldo_caja:>12.2f}"
    )

    print(
        f"{'SALDO FÍSICO:':<25} "
        f"${saldo_fisico:>12.2f}"
    )

    print(
        f"{'SALDO DISPONIBLE:':<25} "
        f"${saldo_disponible:>12.2f}"
    )

    print("=" * 40)

