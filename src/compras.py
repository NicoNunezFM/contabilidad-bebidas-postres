from database import obtener_conexion
from productos import listar_productos, buscar_producto_por_id

def agregar_compra():
    listar_productos()

    id_texto = input("Ingrese ID del producto: ")

    if not id_texto.isdigit():
        print("El ID debe ser un numero.")
        return

    id_producto = int(id_texto)

    producto = buscar_producto_por_id(id_producto)

    if producto is None:
        print("Producto no encontrado")
        return

    print("Producto encontrado")

    fecha = input("Ingrese fecha: ")

    if fecha == "":
        print("La fecha no puede estar vacia.")
        return

    cantidad_texto = input("Ingrese cantidad: ")

    if not cantidad_texto.isdigit():
        print("La cantidad debe ser un numero entero.")
        return

    cantidad = int(cantidad_texto)

    if cantidad <= 0:
        print("La cantidad debe ser mayor que cero.")
        return    

    precio_texto = input("Ingrese el precio: ")

    try:
        precio_unitario= float(precio_texto)
    except ValueError:
        print("El precio debe ser un numero.")
        return

    if precio_unitario <= 0:
        print("El precio debe ser mayor que cero.")
        return

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute("""
        INSERT INTO compras (
            id_producto,
            fecha,
            cantidad,
            precio_unitario
        )
        VALUES (?, ?, ?, ?)
    """,(
        id_producto,
        fecha,
        cantidad,
        precio_unitario
    ))
    conexion.commit()
    conexion.close()

    print("Compra registrada con exito.")
    
def listar_compras():
    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute("""
    
    SELECT
        compras.id_compra,
        productos.nombre,
        compras.fecha,
        compras.cantidad,
        compras.precio_unitario
    from compras
    INNER JOIN productos
        on compras.id_producto = productos.id_producto
    ORDER BY compras.id_compra
    """)

    compras = cursor.fetchall()

    conexion.close()

    if not compras:
        print("No hay compras registradas.") 
        return

    for compra in compras:
        total = compra[3] * compra[4]
        print(f"Compra N°: {compra[0]}")
        print(f"Producto: {compra[1]}")
        print(f"Fecha: {compra[2]}")
        print(f"Cantidad: {compra[3]}")
        print(f"Precio unitario: {compra[4]:.2f}")
        print(f"Total: {total:.2f}")
        print("-----------------------\n")

        