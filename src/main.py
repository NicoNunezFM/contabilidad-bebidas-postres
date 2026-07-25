from database import inicializar_base_de_datos
from productos import (
    agregar_producto,
    listar_productos,
    buscar_producto_por_id,
    modificar_producto,
    eliminar_producto
)   

def mostrar_menu():
    print("\n===== CONTROL DEL NEGOCIO =====")
    print("5 - Eliminar producto")
    print("4 - Modificar producto")
    print("3 - Buscar producto por ID")
    print("2 - Listar productos")
    print("1 - Agregar producto")
    print("0 - Salir")



def solicitar_datos_producto():
    print("\n--- NUEVO PRODUCTO ---")

    nombre = input("Nombre: ")
    categoria = input("Categoria: ")
    presentacion = input("Presentación: ")
    contenido = float(input("Contenido: "))
    unidad_medida = input("Unidad de medida: ")
    unidades_por_pack = int(input("Unidades por pack: "))

    return (
        nombre,
        categoria,
        presentacion,
        contenido,
        unidad_medida,
        unidades_por_pack
    )

def main():
    inicializar_base_de_datos()

    while True:
        mostrar_menu()

        opcion = input("Seleccione una opcion: ")

        if opcion == "0":
            print("Programa finalizado.")
            break

        elif opcion == "1":
            datos_producto = solicitar_datos_producto()
            
            agregar_producto(*datos_producto)
            
            print("Producto agregado correctamente")

        elif opcion == "2":
            productos = listar_productos()
            print("\n========== PRODUCTOS ==========")
            print(f"{'ID':<4} | {'Nombre':<25} | {'Categoría':<15} | {'Presentación':<15} | {'Contenido':<12} | {'Unidad':<10} | {'Pack':<6}")
            print("-" * 110)

            for producto in productos:
                print(f"{producto[0]:<4} | {producto[1]:<25} | {producto[2]:<15} | {producto[3]:<15} | {producto[4]:<12} | {producto[5]:<10} | {producto[6]:<6}")

        elif opcion == "3":
            id_producto = int(input("Ingrese el Id del producto: "))

            producto = buscar_producto_por_id(id_producto)
            if producto is None:
                print("Producto no encontrado")        
            else:
                print("\n========== PRODUCTO ==========")
                print(f"{'ID':<4} | {'Nombre':<25} | {'Categoría':<15} | {'Presentación':<15} | {'Contenido':<12} | {'Unidad':<10} | {'Pack':<6}")
                print("-" * 110)

        elif opcion == "4":
            id_producto = int(input("Ingrese el ID del producto: "))

            producto = buscar_producto_por_id(id_producto)

            if producto is None:
                print("Producto no encontrado.")

            else: 

                print("\n--- MODIFICAR PRODUCTO ---")
                print("Presione enter para mantener el valor actual.")

                nuevo_nombre = input(f"Nombre [{producto[1]}]: ")

                if nuevo_nombre == "":
                    nuevo_nombre = producto[1]

                nueva_categoria = input(f"Categoria [{producto[2]}]: ")

                if nueva_categoria == "":
                    nueva_categoria = producto[2]

                nueva_presentacion = input(f"Presentacion [{producto[3]}]: ")

                if nueva_presentacion == "":
                    nueva_presentacion = producto[3]

                nuevo_contenido = input(f"Contenido [{producto[4]}]: ")

                if nuevo_contenido == "":
                    nuevo_contenido = producto[4]
                else: 
                    nuevo_contenido = float(nuevo_contenido)

                nueva_unidad = input(f"Unidad [{producto[5]}]: ")

                if nueva_unidad == "":
                    nueva_unidad = producto[5]

                nuevo_pack = input(f"Pack [{producto[6]}]: ")

                if nuevo_pack == "":
                    nuevo_pack = producto[6]

                else: 
                    nuevo_pack = int(nuevo_pack)

                modificar_producto(
                    id_producto,
                    nuevo_nombre,
                    nueva_categoria,
                    nueva_presentacion,
                    nuevo_contenido,
                    nueva_unidad,
                    nuevo_pack
                )

                print("Producto modificado correctamente")

        elif opcion == "5":
            id_producto = int(input("Ingrese el ID del producto: "))

            producto = buscar_producto_por_id(id_producto)

            if producto is None:
                print("Producto no encontrado.")

            else:
                print("\n --- PRODUCTO A ELIMINAR ---")
                print(f"ID: {producto[0]}")
                print(f"Nombre: {producto[1]}")
                print(f"Categoria: {producto[2]}")

                confirmacion = input(
                    "¿Seguro desea eliminarlo? (s/n)"
                ).lower()

                if confirmacion == "s":
                    eliminar_producto(id_producto)
                    print("Producto eliminado correctamente.")
                else:
                    print("Eliminacion cancelada.")

            
                    
                    

        else:
            print("Opción inválida. Intente nuevamente")


main()

