from database import obtener_conexion
from movimientos_caja import total_aportes, total_retiros
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
        SELECT SUM(cantidad * precio_unitario)
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
    saldo_disponible = (
        saldo_fisico
        - diezmo_reservado
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
        "saldo_fisico": saldo_fisico,
        "saldo_disponible": saldo_disponible
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

