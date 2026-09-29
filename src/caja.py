from database import obtener_conexion
from movimientos_caja import total_aportes, total_retiros
from diezmo import estado_general_diezmo

def ventas_caja():
    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute("""
    
    SELECT
        SUM(cantidad * precio_unitario)
    FROM ventas
    WHERE anulada = 0
    """)

    resultado = cursor.fetchone()

    ventas = resultado[0]

    if ventas is None:
        ventas = 0

    print(f"Su total es: ${ventas}")

    conexion.close()
    return ventas

def compras_caja():
    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute("""
    
    SELECT
        SUM(cantidad * precio_unitario)
        FROM compras
        WHERE anulada = 0
    """)

    resultado = cursor.fetchone()

    compras = resultado[0]

    if compras is None:
        compras = 0

    conexion.close()
    return compras

def gastos_caja():
    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute("""
    SELECT SUM(valor_final)
    FROM gastos
    WHERE anulado = 0
    """)

    resultado = cursor.fetchone()
    gastos = resultado[0]

    if gastos is None:
        gastos = 0

    conexion.close()
    return gastos

def mostrar_caja():

    compras = compras_caja()
    ventas = ventas_caja()
    gastos = gastos_caja()

    aportes = total_aportes()
    retiros = total_retiros()

    resultado_negocio = ventas - compras - gastos

    saldo_caja = resultado_negocio + aportes - retiros

    saldo_fisico = (
        saldo_caja
        - diezmo_entregado
    )

    saldo_disponible = (
        saldo_fisico
        - diezmo_reservado
    )

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

    print("\n" + "-" * 40)
    print(
        f"{'RESULTADO NEGOCIO:':<25} "
        f"${resultado_negocio:>12.2f}"
    )

    print(
        f"{'SALDO DE CAJA:':<25} "
        f"${saldo_caja:>12.2f}"
    )

    print("=" * 40)

    estado_diezmo = estado_general_diezmo()

    diezmo_reservado = estado_diezmo["reservado_en_caja"]
    diezmo_entregado = estado_diezmo["entregado_total"]
    print(f"Saldo base de caja: ${saldo_caja:.2f}")
    print(f"Saldo físico: ${saldo_fisico:.2f}")
    print(f"Saldo disponible: ${saldo_disponible:.2f}")


