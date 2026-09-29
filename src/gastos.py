from datetime import datetime
import sqlite3

from database import obtener_conexion


CATEGORIAS_GASTO = {
    "1": "Materia prima",
    "2": "Bebidas",
    "3": "Envases",
    "4": "Transporte",
    "5": "Publicidad",
    "6": "Servicios",
    "7": "Equipamiento",
    "8": "Otros"
}


# ============================================================
# REGISTRAR GASTO
# ============================================================

def registrar_gasto(
    categoria,
    descripcion_gasto,
    valor_final,
    fecha=None
):
    """
    Registra un gasto en la base de datos.

    No utiliza input(), por lo que puede ser llamada desde
    terminal, WhatsApp, Notion u otra interfaz.
    """

    if not isinstance(categoria, str) or not categoria.strip():
        return {
            "ok": False,
            "mensaje": "La categoría no puede estar vacía."
        }

    if categoria not in CATEGORIAS_GASTO.values():
        return {
            "ok": False,
            "mensaje": "La categoría seleccionada no es válida."
        }

    if (
        not isinstance(descripcion_gasto, str)
        or not descripcion_gasto.strip()
    ):
        return {
            "ok": False,
            "mensaje": "La descripción del gasto no puede estar vacía."
        }

    if not isinstance(valor_final, (int, float)):
        return {
            "ok": False,
            "mensaje": "El valor del gasto debe ser un número."
        }

    if valor_final <= 0:
        return {
            "ok": False,
            "mensaje": "El valor del gasto debe ser mayor que cero."
        }

    if fecha is None:
        fecha = datetime.now().strftime("%Y-%m-%d")

    conexion = obtener_conexion()

    try:
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
            categoria.strip(),
            descripcion_gasto.strip(),
            valor_final
        ))

        id_gasto = cursor.lastrowid

        conexion.commit()

        return {
            "ok": True,
            "mensaje": "Gasto registrado correctamente.",
            "id_gasto": id_gasto,
            "fecha": fecha,
            "categoria": categoria,
            "descripcion": descripcion_gasto.strip(),
            "valor": valor_final
        }

    except sqlite3.Error as error:
        conexion.rollback()

        return {
            "ok": False,
            "mensaje": f"Error al registrar el gasto: {error}"
        }

    finally:
        conexion.close()


# ============================================================
# REGISTRAR GASTO DESDE TERMINAL
# ============================================================

def agregar_gasto():
    """
    Interfaz de consola para registrar un gasto.
    """

    print("Seleccione la categoría del gasto:")

    for opcion, descripcion in CATEGORIAS_GASTO.items():
        print(f"{opcion} - {descripcion}")

    opcion_categoria = input("Ingrese su opción: ")

    if opcion_categoria not in CATEGORIAS_GASTO:
        print("Debe seleccionar una opción válida.")
        return

    categoria = CATEGORIAS_GASTO[opcion_categoria]

    descripcion_gasto = input(
        "Ingrese la descripción del gasto: "
    ).strip()

    if not descripcion_gasto:
        print("La descripción no puede estar vacía.")
        return

    valor_texto = input("Ingrese valor: ")

    try:
        valor_final = float(valor_texto)

    except ValueError:
        print("El valor debe ser un número.")
        return

    resultado = registrar_gasto(
        categoria=categoria,
        descripcion_gasto=descripcion_gasto,
        valor_final=valor_final
    )

    print(resultado["mensaje"])

    if resultado["ok"]:
        print(f"Categoría: {resultado['categoria']}")
        print(f"Descripción: {resultado['descripcion']}")
        print(f"Monto: ${resultado['valor']:.2f}")


# ============================================================
# OBTENER GASTOS
# ============================================================

def obtener_gastos():
    """
    Devuelve todos los gastos como una lista de diccionarios.
    """

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute("""
        SELECT
            id_gasto,
            fecha,
            categoria,
            descripcion_gasto,
            valor_final,
            anulado,
            fecha_anulacion,
            motivo_anulacion
        FROM gastos
        ORDER BY id_gasto
    """)

    gastos_db = cursor.fetchall()

    conexion.close()

    gastos = []

    for gasto in gastos_db:
        gasto_python = {
            "id_gasto": gasto[0],
            "fecha": gasto[1],
            "categoria": gasto[2],
            "descripcion": gasto[3],
            "valor": gasto[4],
            "anulado": bool(gasto[5]),
            "fecha_anulacion": gasto[6],
            "motivo_anulacion": gasto[7]

        }

        gastos.append(gasto_python)

    return gastos

def anular_gasto(id_gasto, motivo):

    if not isinstance(id_gasto, int):
        return {
            "ok": False,
            "mensaje": "El ID del gasto debe ser un número entero."
        }

    if not isinstance(motivo, str) or not motivo.strip():
        return {
            "ok": False,
            "mensaje": "El motivo de anulación no puede estar vacío."
        }

    conexion = obtener_conexion()

    try:
        cursor = conexion.cursor()

        cursor.execute("""
            SELECT anulado
            FROM gastos
            WHERE id_gasto = ?
        """, (id_gasto,))

        gasto = cursor.fetchone()

        if gasto is None:
            return {
                "ok": False,
                "mensaje": "Gasto no encontrado."
            }

        if gasto[0] == 1:
            return {
                "ok": False,
                "mensaje": "El gasto ya se encuentra anulado."
            }

        fecha_anulacion = datetime.now().strftime("%Y-%m-%d")

        cursor.execute("""
            UPDATE gastos
            SET
                anulado = 1,
                fecha_anulacion = ?,
                motivo_anulacion = ?
            WHERE id_gasto = ?
        """, (
            fecha_anulacion,
            motivo.strip(),
            id_gasto
        ))

        conexion.commit()

        return {
            "ok": True,
            "mensaje": "Gasto anulado correctamente.",
            "id_gasto": id_gasto,
            "fecha_anulacion": fecha_anulacion,
            "motivo": motivo.strip()
        }

    except sqlite3.Error as error:
        conexion.rollback()

        return {
            "ok": False,
            "mensaje": f"Error al anular el gasto: {error}"
        }

    finally:
        conexion.close()


# ============================================================
# LISTAR GASTOS EN TERMINAL
# ============================================================

def listar_gastos():
    """
    Muestra los gastos en la terminal.
    """

    gastos = obtener_gastos()

    if not gastos:
        print("No existen gastos registrados.")
        return

    for gasto in gastos:
        print(f"Gasto N°: {gasto['id_gasto']}")
        print(f"Fecha: {gasto['fecha']}")
        print(f"Categoría: {gasto['categoria']}")
        print(f"Descripción: {gasto['descripcion']}")
        print(f"Monto: ${gasto['valor']:.2f}")
        print("------------------------\n")