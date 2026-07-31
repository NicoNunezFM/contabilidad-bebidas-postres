from database import obtener_conexion
from datetime import datetime

def agregar_gasto():

    fecha = datetime.now().strftime("%d/%m/%Y")

    categorias = {
        "1": "Materia prima",
        "2": "Bebidas",
        "3": "Envases",
        "4": "Transporte",
        "5": "Publicidad",
        "6": "Servicios",
        "7": "Equipamiento",
        "8": "Otros"
    }
    print("Seleccione la opcion que desea registrar. ")

    for opcion_categoria, descripcion in categorias.items():
        print(f"{opcion_categoria} - {descripcion}")

    opcion_categoria = input("Ingrese su opcion: ")

    if opcion_categoria not in categorias:
        print("Debe seleccionar una opcion de la lista")
        return

    categoria = categorias[opcion_categoria]

    descripcion_gasto = input("Ingrese la descripcion del gasto: ")

    if descripcion_gasto == "":
        print("La descripcion no puede estar sin datos.")
        return

    valor_texto = input("Ingrese valor: ")

    if not valor_texto.isdigit():
        print("El valor debe ser un numero.")
        return

    valor_final = float(valor_texto)

    if valor_final <= 0:
        print("El valor final debe ser superior a cero.")


    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute("""
        INSERT INTO gastos (
            fecha,
            categoria,
            descripcion_gasto,
            valor_final
        )
        VALUES (?, ?, ?, ?)
    """, (
        fecha,
        categoria,
        descripcion_gasto,
        valor_final
    ))


    conexion.commit ()
    conexion.close()

    print("Gasto registrado correctamente.")

def listar_gastos():
    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute("""
    
    SELECT 
        gastos.id_gasto,
        gastos.fecha,
        gastos.categoria,
        gastos.descripcion_gasto,
        gastos.valor_final
    from gastos
    ORDER BY gastos.id_gasto
    """)

    gastos = cursor.fetchall()

    conexion.close()

    if not gastos:
        print("No existen gastos registrados.")
        return

    for gasto in gastos:
        print(f"Gasto N°: {gasto[0]}")
        print(f"Fecha: {gasto[1]}")
        print(f"Categoria: {gasto[2]}")
        print(f"Descripcion: {gasto[3]}")
        print(f"Monto: {gasto[4]:.2f}")
        print("------------------------\n")
        

