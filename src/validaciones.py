def pedir_float(mensaje):

    

    while True:

        dato_texto = input(mensaje)

        try:
            numero = float(dato_texto)

            if numero <= 0:
                print("El numero debe ser mayor a cero.")

            else:
                return numero

        except ValueError:
            print("El dato ingresado debe ser un numero")

def pedir_entero(mensaje):

    while True:

        dato_texto = input(mensaje)

        try:

            numero = int(dato_texto)

            if numero <= 0:
                print("El numero debe ser mayor que cero.")
                continue

            return numero

        except ValueError:
            print("El dato ingresado debe ser un numero.")

def pedir_texto(mensaje):

    while True:

        texto = input(mensaje).strip()

        if texto == "":
            print("El texto no puede estar vacio.")
            continue

        return texto
       



  