from database import inicializar_base_de_datos

from caja import mostrar_caja

from compras import (
    agregar_compra,
    listar_compras,
)

from gastos import (
    agregar_gasto,
    listar_gastos,
)

from productos import (
    agregar_producto,
    buscar_producto_por_id,
    eliminar_producto,
    listar_productos,
    modificar_producto,
)

from validaciones import (
    pedir_entero,
    pedir_float,
    pedir_texto,
)

from ventas import (
    agregar_venta,
    listar_ventas,
)


# ============================================================
# MENÚ PRINCIPAL
# ============================================================

def mostrar_menu():

    print("\n===== CONTROL DEL NEGOCIO =====")
    print("0 - Salir")
    print("1 - Agregar producto")
    print("2 - Listar productos")
    print("3 - Buscar producto por ID")
    print("4 - Modificar producto")
    print("5 - Eliminar producto")
    print("6 - Registrar compra")
    print("7 - Listar compras")
    print("8 - Registrar venta")
    print("9 - Listar ventas")
    print("10 - Registrar gasto")
    print("11 - Listar gastos")
    print("12 - Dashboard")


# ============================================================
# SOLICITAR DATOS DE PRODUCTO
# ============================================================

def solicitar_datos_producto():

    print("\n--- NUEVO PRODUCTO ---")

    nombre = pedir_texto("Nombre: ")
    categoria = pedir_texto("Categoría: ")
    presentacion = pedir_texto("Presentación: ")
    contenido = pedir_float("Contenido: ")
    unidad_medida = pedir_texto("Unidad de medida: ")
    unidades_por_pack = pedir_entero("Unidades por pack: ")

    return (
        nombre,
        categoria,
        presentacion,
        contenido,
        unidad_medida,
        unidades_por_pack
    )


# ============================================================
# DATOS OPCIONALES PARA MODIFICAR PRODUCTOS
# ============================================================

def pedir_texto_opcional(mensaje, valor_actual):

    while True:

        texto = input(mensaje).strip()

        if texto == "":
            return valor_actual

        return texto


def pedir_float_opcional(mensaje, valor_actual):

    while True:

        texto = input(mensaje).strip()

        if texto == "":
            return valor_actual

        try:
            numero = float(texto)

            if numero <= 0:
                print("El número debe ser mayor que cero.")
                continue

            return numero

        except ValueError:
            print("El dato ingresado debe ser un número.")


def pedir_entero_opcional(mensaje, valor_actual):

    while True:

        texto = input(mensaje).strip()

        if texto == "":
            return valor_actual

        try:
            numero = int(texto)

            if numero <= 0:
                print("El número debe ser mayor que cero.")
                continue

            return numero

        except ValueError:
            print("El dato ingresado debe ser un número entero.")


# ============================================================
# MOSTRAR PRODUCTOS
# ============================================================

def mostrar_productos():

    productos = listar_productos()

    if not productos:
        print("No hay productos registrados.")
        return

    print("\n========== PRODUCTOS ==========")

    print(
        f"{'ID':<4} | "
        f"{'Nombre':<25} | "
        f"{'Categoría':<15} | "
        f"{'Presentación':<15} | "
        f"{'Contenido':<12} | "
        f"{'Unidad':<10} | "
        f"{'Pack':<6} | "
        f"{'Stock':<8}"
    )

    print("-" * 125)

    for producto in productos:

        print(
            f"{producto[0]:<4} | "
            f"{producto[1]:<25} | "
            f"{producto[2]:<15} | "
            f"{producto[3]:<15} | "
            f"{producto[4]:<12} | "
            f"{producto[5]:<10} | "
            f"{producto[6]:<6} | "
            f"{producto[7]:<8}"
        )


# ============================================================
# MOSTRAR UN PRODUCTO
# ============================================================

def mostrar_producto(producto):

    print("\n========== PRODUCTO ==========")

    print(
        f"{'ID':<4} | "
        f"{'Nombre':<25} | "
        f"{'Categoría':<15} | "
        f"{'Presentación':<15} | "
        f"{'Contenido':<12} | "
        f"{'Unidad':<10} | "
        f"{'Pack':<6} | "
        f"{'Stock':<8}"
    )

    print("-" * 125)

    print(
        f"{producto[0]:<4} | "
        f"{producto[1]:<25} | "
        f"{producto[2]:<15} | "
        f"{producto[3]:<15} | "
        f"{producto[4]:<12} | "
        f"{producto[5]:<10} | "
        f"{producto[6]:<6} | "
        f"{producto[7]:<8}"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    inicializar_base_de_datos()

    while True:

        mostrar_menu()

        opcion = input("Seleccione una opción: ").strip()

        # ----------------------------------------------------
        # SALIR
        # ----------------------------------------------------

        if opcion == "0":

            print("Programa finalizado.")
            break

        # ----------------------------------------------------
        # AGREGAR PRODUCTO
        # ----------------------------------------------------

        elif opcion == "1":

            datos_producto = solicitar_datos_producto()

            resultado = agregar_producto(*datos_producto)

            print(resultado["mensaje"])

            if resultado["ok"]:
                print(
                    f"ID del nuevo producto: "
                    f"{resultado['id_producto']}"
                )

        # ----------------------------------------------------
        # LISTAR PRODUCTOS
        # ----------------------------------------------------

        elif opcion == "2":

            mostrar_productos()

        # ----------------------------------------------------
        # BUSCAR PRODUCTO
        # ----------------------------------------------------

        elif opcion == "3":

            id_producto = pedir_entero(
                "Ingrese el ID del producto: "
            )

            producto = buscar_producto_por_id(id_producto)

            if producto is None:
                print("Producto no encontrado.")

            else:
                mostrar_producto(producto)

        # ----------------------------------------------------
        # MODIFICAR PRODUCTO
        # ----------------------------------------------------

        elif opcion == "4":

            id_producto = pedir_entero(
                "Ingrese el ID del producto: "
            )

            producto = buscar_producto_por_id(id_producto)

            if producto is None:

                print("Producto no encontrado.")

            else:

                print("\n--- MODIFICAR PRODUCTO ---")
                print(
                    "Presione Enter para mantener "
                    "el valor actual."
                )

                nuevo_nombre = pedir_texto_opcional(
                    f"Nombre [{producto[1]}]: ",
                    producto[1]
                )

                nueva_categoria = pedir_texto_opcional(
                    f"Categoría [{producto[2]}]: ",
                    producto[2]
                )

                nueva_presentacion = pedir_texto_opcional(
                    f"Presentación [{producto[3]}]: ",
                    producto[3]
                )

                nuevo_contenido = pedir_float_opcional(
                    f"Contenido [{producto[4]}]: ",
                    producto[4]
                )

                nueva_unidad = pedir_texto_opcional(
                    f"Unidad [{producto[5]}]: ",
                    producto[5]
                )

                nuevo_pack = pedir_entero_opcional(
                    f"Pack [{producto[6]}]: ",
                    producto[6]
                )

                resultado = modificar_producto(
                    id_producto,
                    nuevo_nombre,
                    nueva_categoria,
                    nueva_presentacion,
                    nuevo_contenido,
                    nueva_unidad,
                    nuevo_pack
                )

                print(resultado["mensaje"])

        # ----------------------------------------------------
        # ELIMINAR PRODUCTO
        # ----------------------------------------------------

        elif opcion == "5":

            id_producto = pedir_entero(
                "Ingrese el ID del producto: "
            )

            producto = buscar_producto_por_id(id_producto)

            if producto is None:

                print("Producto no encontrado.")

            else:

                print("\n--- PRODUCTO A ELIMINAR ---")
                print(f"ID: {producto[0]}")
                print(f"Nombre: {producto[1]}")
                print(f"Categoría: {producto[2]}")

                confirmacion = input(
                    "¿Seguro desea eliminarlo? (s/n): "
                ).strip().lower()

                if confirmacion == "s":

                    resultado = eliminar_producto(id_producto)

                    print(resultado["mensaje"])

                else:

                    print("Eliminación cancelada.")

        # ----------------------------------------------------
        # COMPRAS
        # ----------------------------------------------------

        elif opcion == "6":

            agregar_compra()

        elif opcion == "7":

            listar_compras()

        # ----------------------------------------------------
        # VENTAS
        # ----------------------------------------------------

        elif opcion == "8":

            agregar_venta()

        elif opcion == "9":

            listar_ventas()

        # ----------------------------------------------------
        # GASTOS
        # ----------------------------------------------------

        elif opcion == "10":

            agregar_gasto()

        elif opcion == "11":

            listar_gastos()

        # ----------------------------------------------------
        # DASHBOARD
        # ----------------------------------------------------

        elif opcion == "12":

            mostrar_caja()

        # ----------------------------------------------------
        # OPCIÓN INVÁLIDA
        # ----------------------------------------------------

        else:

            print("Opción inválida. Intente nuevamente.")


if __name__ == "__main__":
    main()