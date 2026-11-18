"""Presentación y personalizaciones del menú de Lo de Clau en entrenamiento."""

HAMBURGUESAS = "Hamburguesas"
SANDWICHES = "Sándwiches"
MILANESAS = "Milanesas al plato"

INGREDIENTES_CLASICA = (
    "Medallón", "Lechuga", "Tomate", "Cheddar", "Mayonesa", "Kétchup", "Mostaza",
)
INGREDIENTES_SANDWICH = ("Pan", "Milanesa", "Lechuga", "Tomate")
INGREDIENTES_NAPOLITANA = ("Milanesa", "Mozzarella", "Salsa de tomate", "Orégano", "Rodaja de tomate")

NOMBRES_ADICIONALES = {"cheddar": "Cheddar extra", "huevo": "Huevo extra"}
PRECIO_ADICIONAL_CENTAVOS = 100_000
PRECIO_PAPAS_DOBLES_CENTAVOS = 200_000


def variante_menu(nombre, categoria):
    if categoria == HAMBURGUESAS:
        for estilo in ("Clásica", "Cheddar y huevo", "Pollo con papas", "Big Mac"):
            for tamano in ("Simple", "Doble"):
                if nombre == f"{estilo} {tamano.lower()}":
                    return HAMBURGUESAS, {"Variedad": estilo, "Medallones": tamano}
    elif categoria == SANDWICHES:
        for tamano, presentacion in (("Chico", "+ papas"), ("Grande", "individual"), ("Grande", "+ papas")):
            for carne in ("Pollo", "Carne"):
                if nombre == f"{tamano} de {carne.lower()} {presentacion}":
                    return SANDWICHES, {
                        "Tamaño": tamano, "Milanesa": carne,
                        "Presentación": "Con papas" if presentacion == "+ papas" else "Solo sándwich",
                    }
    elif categoria == "Al plato":
        for prefijo, estilo in (("Milanesa", "Clásica"), ("Napo", "Napolitana")):
            for carne in ("Pollo", "Carne"):
                for sufijo, guarnicion in (("fritas", "Papas fritas"), ("puré", "Puré")):
                    if nombre == f"{prefijo} de {carne.lower()} con {sufijo}":
                        return MILANESAS, {"Milanesa": carne, "Preparación": estilo, "Guarnición": guarnicion}
    return None, {}


def personalizacion_menu(nombre, categoria):
    familia, variante = variante_menu(nombre, categoria)
    combo = False
    guarnicion = None
    ingredientes = ()
    if familia == HAMBURGUESAS:
        estilo = variante["Variedad"]
        combo = estilo in ("Clásica", "Cheddar y huevo", "Pollo con papas")
        if estilo == "Clásica":
            ingredientes = INGREDIENTES_CLASICA
    elif familia == SANDWICHES:
        combo = variante["Presentación"] == "Con papas"
        ingredientes = INGREDIENTES_SANDWICH
    elif familia == MILANESAS:
        guarnicion = variante["Guarnición"]
        ingredientes = INGREDIENTES_NAPOLITANA if variante["Preparación"] == "Napolitana" else ("Milanesa",)

    if combo:
        guarnicion = "Papas fritas"
    destinos = {}
    if categoria in (HAMBURGUESAS, SANDWICHES, "Al plato", "Conos", "Pizzas"):
        destinos["principal"] = "Papas" if categoria == "Conos" else "Plato principal"
    if guarnicion:
        destinos["papas" if guarnicion == "Papas fritas" else "pure"] = guarnicion
    return {
        "ingredientes": ingredientes,
        "destinos": destinos,
        "guarnicion": guarnicion,
        "papas_dobles_centavos": PRECIO_PAPAS_DOBLES_CENTAVOS if combo else None,
        "adicionales": [
            {"tipo": tipo, "nombre": etiqueta, "precio_centavos": PRECIO_ADICIONAL_CENTAVOS}
            for tipo, etiqueta in NOMBRES_ADICIONALES.items()
        ] if destinos else [],
    }
