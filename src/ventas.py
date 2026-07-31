from database import obtener_conexion
from productos import listar_productos, buscar_producto_por_id
from datetime import datetime

def agregar_venta():
    listar_productos()

    id_texto = input("Ingrese id del producto: ")

    if not id_texto.isdigit():
        print("El ID debe ser un numero")
        return

    id_producto = int(id_texto)

    producto = buscar_producto_por_id(id_producto)

    if producto is None:
        print("Producto no encontrado")
        return

    print("Producto encontrado")

    fecha = datetime.now().strftime("%d/%m/%Y")

    cantidad_texto = input("Ingrese cantidad: ")

    if not cantidad_texto.isdigit():
        print("La cantidad debe ser un numero entero.")
        return

    cantidad = int(cantidad_texto)

    if cantidad <= 0:
        print("La cantidad debe ser un numero positivo y mayor a 0.")
        return

    stock_actual = producto[7]

    if cantidad > stock_actual:
        print("Stock Insuficiente.")
        return

    precio_texto = input("Ingrese el precio unitario: ")

    try:
        precio_unitario = float(precio_texto)
    except ValueError:
        print("El precio debe ser un numero.")
        return

    if precio_unitario <= 0:
        print("El precio debe ser mayor que cero.")
        return

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute("""
        INSERT INTO VENTAS (
            id_producto,
            fecha,
            cantidad,
            precio_unitario
        )
        VALUES (?, ?, ?, ?)
    """, (
        id_producto,
        fecha,
        cantidad,
        precio_unitario
    ))

    cursor.execute("""
        UPDATE productos
        SET stock = stock - ?
        WHERE id_producto = ? 
    """, (
        cantidad,
        id_producto
    ))
    conexion.commit ()
    conexion.close()
    print("Venta registrada correctamente.")
