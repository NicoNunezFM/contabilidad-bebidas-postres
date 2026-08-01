from database import obtener_conexion

def ventas_caja():
    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute("""
    
    SELECT
        SUM(cantidad * precio_unitario)
    FROM ventas
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
    SELECT
        SUM(valor_final)
    FROM gastos
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

    total = ventas - compras - gastos

    print("=" * 40)
    print(f"{'CONTROL DEL NEGOCIO':^40}")
    print("=" * 40)
    print("\nINGRESOS")
    print(f"{'Ventas:':<25} ${ventas:>12.2f}")
    print("\nEGRESOS")
    print(f"{'Compras:':<25} ${compras:>12.2f}")
    print(f"{'Gastos:':<25} ${gastos:>12.2f}")
    print("\n")
    print("-" * 40)
    print(f"{'SALDO DE CAJA:':<25} ${total:>12.2f}")
    print("=" * 40)


