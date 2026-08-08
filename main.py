nombre_del_producto = input("Ingrese nombre del producto: ")
precio_texto = input("Ingrese precio del producto: ")
cantidad_texto = input("Ingrese cantidad: ")

precio = float(precio_texto)
cantidad = int(cantidad_texto)

producto_final = precio * cantidad

print("Nombre del producto: ",nombre_del_producto)
print("Precio: ", precio)
print("Cantidad: ", cantidad)
print("Total: ", producto_final)