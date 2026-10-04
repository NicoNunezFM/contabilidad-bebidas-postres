from database import inicializar_base_de_datos
from catalogo import sincronizar_catalogo


def main():
    inicializar_base_de_datos()

    resultado = sincronizar_catalogo()

    print("Catálogo sincronizado.")
    print(f"Productos creados: {resultado['creados']}")
    print(f"Productos actualizados: {resultado['actualizados']}")
    print(f"Total catálogo: {resultado['total_catalogo']}")


if __name__ == "__main__":
    main()
