from datetime import datetime
import sqlite3

from database import obtener_conexion
from productos import listar_productos, buscar_producto_por_id


def _normalizar_contexto(contexto):
    if not isinstance(contexto, dict):
        contexto = {}

    usuario_id = contexto.get("usuario_id")
    usuario_numero = contexto.get("usuario_numero")

    usuario_origen = (
        str(usuario_id).strip()
        if usuario_id
        else (
            str(usuario_numero).strip()
            if usuario_numero
            else None
        )
    )

    return {
        "canal": (
            str(contexto.get("canal")).strip()
            if contexto.get("canal")
            else None
        ),
        "usuario_origen": usuario_origen,
        "numero_origen": (
            str(usuario_numero).strip()
            if usuario_numero
            else None
        ),
        "grupo_origen": (
            str(contexto.get("grupo_id")).strip()
            if contexto.get("grupo_id")
            else None
        ),
        "id_mensaje": (
            str(contexto.get("id_mensaje")).strip()
            if contexto.get("id_mensaje")
            else None
        ),
    }


# ============================================================
# REGISTRAR VENTA
# ============================================================

def registrar_venta(
    id_producto,
    cantidad,
    precio_unitario=None,
    fecha=None,
    contexto=None
):
    """
    Registra una venta en la base de datos y descuenta el stock.

    Esta función no utiliza input(), por lo que puede ser llamada
    desde la terminal, WhatsApp, Notion u otra interfaz.
    """

    # Validar ID
    if not isinstance(id_producto, int):
        return {
            "ok": False,
            "codigo": "DATOS_INVALIDOS",
            "mensaje": "El ID del producto debe ser un número entero."
        }

    # Buscar producto
    producto = buscar_producto_por_id(id_producto)

    if producto is None:
        return {
            "ok": False,
            "codigo": "PRODUCTO_NO_ENCONTRADO",
            "mensaje": "Producto no encontrado."
        }

    # Validar cantidad
    if not isinstance(cantidad, int):
        return {
            "ok": False,
            "codigo": "DATOS_INVALIDOS",
            "mensaje": "La cantidad debe ser un número entero."
        }

    if cantidad <= 0:
        return {
            "ok": False,
            "codigo": "DATOS_INVALIDOS",
            "mensaje": "La cantidad debe ser mayor que cero."
        }

    # Obtener datos comerciales del producto.
    stock_actual = producto[7]
    precio_configurado = producto[8]
    controla_stock = bool(producto[9])

    if controla_stock and cantidad > stock_actual:
        return {
            "ok": False,
            "codigo": "STOCK_INSUFICIENTE",
            "mensaje": (
                f"Stock insuficiente. "
                f"Stock disponible: {stock_actual}"
            )
        }

    # Si no se informa un precio, usar el precio configurado del producto.
    if precio_unitario is None:
        precio_unitario = precio_configurado

    if precio_unitario is None:
        return {
            "ok": False,
            "codigo": "PRECIO_NO_CONFIGURADO",
            "mensaje": "El producto no tiene un precio de venta configurado."
        }

    # Validar precio
    if isinstance(precio_unitario, bool) or not isinstance(precio_unitario, (int, float)):
        return {
            "ok": False,
            "codigo": "DATOS_INVALIDOS",
            "mensaje": "El precio unitario debe ser un número."
        }

    if precio_unitario <= 0:
        return {
            "ok": False,
            "codigo": "DATOS_INVALIDOS",
            "mensaje": "El precio unitario debe ser mayor que cero."
        }

    # Si no se recibe fecha, usar la fecha actual
    if fecha is None:
        fecha = datetime.now().strftime("%Y-%m-%d")

    contexto_origen = _normalizar_contexto(contexto)
    fecha_hora = datetime.now().isoformat(timespec="seconds")

    conexion = obtener_conexion()

    try:
        cursor = conexion.cursor()

        # Toda venta se considera cobrada por defecto.
        cursor.execute(
            """
            INSERT INTO ventas_operaciones (
                fecha,
                estado_pago,
                fecha_hora,
                canal_origen,
                usuario_origen,
                numero_origen,
                grupo_origen,
                id_mensaje_origen
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                fecha,
                "Cobrado",
                fecha_hora,
                contexto_origen["canal"],
                contexto_origen["usuario_origen"],
                contexto_origen["numero_origen"],
                contexto_origen["grupo_origen"],
                contexto_origen["id_mensaje"],
            )
        )

        id_operacion = cursor.lastrowid

        # Registrar venta.
        cursor.execute(
            """
            INSERT INTO ventas (
                id_producto,
                fecha,
                cantidad,
                precio_unitario,
                id_operacion
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                id_producto,
                fecha,
                cantidad,
                precio_unitario,
                id_operacion
            )
        )

        # Guardar ID de la nueva venta.
        id_venta = cursor.lastrowid

        # Descontar stock solo en productos inventariables.
        if controla_stock:
            cursor.execute(
                """
                UPDATE productos
                SET stock = stock - ?
                WHERE id_producto = ?
                """,
                (
                    cantidad,
                    id_producto
                )
            )

        conexion.commit()

        total = cantidad * precio_unitario

        return {
            "ok": True,
            "codigo": "VENTA_REGISTRADA",
            "mensaje": "Venta registrada correctamente.",
            "id_venta": id_venta,
            "id_operacion": id_operacion,
            "estado_pago": "Cobrado",
            "producto": producto[1],
            "cantidad": cantidad,
            "precio_unitario": precio_unitario,
            "total": total,
            "fecha": fecha,
            "stock_restante": (
                stock_actual - cantidad
                if controla_stock
                else None
            ),
            "controla_stock": controla_stock
        }

    except sqlite3.Error as error:
        conexion.rollback()

        return {
            "ok": False,
            "codigo": "ERROR_BASE_DATOS",
            "mensaje": f"Error al registrar la venta: {error}"
        }

    finally:
        conexion.close()


# ============================================================
# ANULAR VENTA
# ============================================================

def anular_venta(id_venta, motivo):
    """
    Anula una venta registrada y devuelve las unidades
    correspondientes al stock.
    """

    # Validar ID
    if not isinstance(id_venta, int):
        return {
            "ok": False,
            "codigo": "DATOS_INVALIDOS",
            "mensaje": "El ID de la venta debe ser un número entero."
        }

    # Validar motivo
    if not isinstance(motivo, str) or not motivo.strip():
        return {
            "ok": False,
            "codigo": "DATOS_INVALIDOS",
            "mensaje": "El motivo de anulación no puede estar vacío."
        }

    conexion = obtener_conexion()

    try:
        cursor = conexion.cursor()

        cursor.execute(
            """
            SELECT
                ventas.id_producto,
                ventas.cantidad,
                ventas.anulada,
                productos.controla_stock
            FROM ventas
            INNER JOIN productos
                ON ventas.id_producto = productos.id_producto
            WHERE id_venta = ?
            """,
            (id_venta,)
        )

        venta = cursor.fetchone()

        # Venta inexistente
        if venta is None:
            return {
                "ok": False,
                "codigo": "VENTA_NO_ENCONTRADA",
                "mensaje": "Venta no encontrada."
            }

        id_producto = venta[0]
        cantidad = venta[1]
        anulada = venta[2]
        controla_stock = bool(venta[3])

        # Venta ya anulada
        if anulada == 1:
            return {
                "ok": False,
                "codigo": "VENTA_YA_ANULADA",
                "mensaje": "La venta ya se encuentra anulada."
            }

        fecha_anulacion = datetime.now().strftime("%Y-%m-%d")

        # Devolver unidades al stock solo si el producto lo controla.
        if controla_stock:
            cursor.execute(
                """
                UPDATE productos
                SET stock = stock + ?
                WHERE id_producto = ?
                """,
                (
                    cantidad,
                    id_producto
                )
            )

        # Marcar la venta como anulada
        cursor.execute(
            """
            UPDATE ventas
            SET
                anulada = 1,
                fecha_anulacion = ?,
                motivo_anulacion = ?
            WHERE id_venta = ?
            """,
            (
                fecha_anulacion,
                motivo.strip(),
                id_venta
            )
        )

        conexion.commit()

        return {
            "ok": True,
            "codigo": "VENTA_ANULADA",
            "mensaje": "Venta anulada correctamente.",
            "id_venta": id_venta,
            "cantidad_devuelta_stock": cantidad,
            "fecha_anulacion": fecha_anulacion,
            "motivo": motivo.strip()
        }

    except sqlite3.Error as error:
        conexion.rollback()

        return {
            "ok": False,
            "codigo": "ERROR_BASE_DATOS",
            "mensaje": f"Error al anular la venta: {error}"
        }

    finally:
        conexion.close()


# ============================================================
# REGISTRAR VENTA DESDE TERMINAL
# ============================================================

def agregar_venta():
    """
    Interfaz de consola para registrar una venta.
    Solicita los datos al usuario y utiliza registrar_venta().
    """

    listar_productos()

    id_texto = input("Ingrese ID del producto: ")

    if not id_texto.isdigit():
        print("El ID debe ser un número.")
        return

    id_producto = int(id_texto)

    cantidad_texto = input("Ingrese cantidad: ")

    if not cantidad_texto.isdigit():
        print("La cantidad debe ser un número entero.")
        return

    cantidad = int(cantidad_texto)

    precio_texto = input("Ingrese el precio unitario: ")

    try:
        precio_unitario = float(precio_texto)

    except ValueError:
        print("El precio debe ser un número.")
        return

    resultado = registrar_venta(
        id_producto=id_producto,
        cantidad=cantidad,
        precio_unitario=precio_unitario
    )

    print(resultado["mensaje"])

    if resultado["ok"]:
        print(f"Producto: {resultado['producto']}")
        print(f"Cantidad: {resultado['cantidad']}")
        print(f"Total: ${resultado['total']:.2f}")
        print(f"Stock restante: {resultado['stock_restante']}")


# ============================================================
# OBTENER VENTAS
# ============================================================

def obtener_ventas():
    """
    Obtiene todas las ventas y las devuelve como una lista
    de diccionarios de Python.
    """

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute(
        """
        SELECT
            ventas.id_venta,
            productos.nombre,
            ventas.fecha,
            ventas.cantidad,
            ventas.precio_unitario,
            ventas.anulada,
            ventas.fecha_anulacion,
            ventas.motivo_anulacion
        FROM ventas
        INNER JOIN productos
            ON ventas.id_producto = productos.id_producto
        ORDER BY ventas.id_venta
        """
    )

    ventas_db = cursor.fetchall()

    conexion.close()

    ventas = []

    for venta in ventas_db:

        total = venta[3] * venta[4]

        venta_python = {
            "id_venta": venta[0],
            "producto": venta[1],
            "fecha": venta[2],
            "cantidad": venta[3],
            "precio_unitario": venta[4],
            "total": total,
            "anulada": bool(venta[5]),
            "fecha_anulacion": venta[6],
            "motivo_anulacion": venta[7]
        }

        ventas.append(venta_python)

    return ventas


# ============================================================
# LISTAR VENTAS EN TERMINAL
# ============================================================

def listar_ventas():
    """
    Muestra las ventas en la terminal.
    """

    ventas = obtener_ventas()

    if not ventas:
        print("No hay ventas registradas.")
        return

    for venta in ventas:
        print(f"Venta N°: {venta['id_venta']}")
        print(f"Producto: {venta['producto']}")
        print(f"Fecha: {venta['fecha']}")
        print(f"Cantidad: {venta['cantidad']}")
        print(
            f"Precio unitario: "
            f"${venta['precio_unitario']:.2f}"
        )
        print(f"Total: ${venta['total']:.2f}")
        print("-----------------------\n")


# ============================================================
# REGISTRAR VENTA MÚLTIPLE / OPERACIÓN AGRUPADA
# ============================================================

def registrar_venta_multiple(
    items,
    fecha=None,
    contexto=None
):
    """
    Registra varios productos como una sola operación de venta.

    La operación es atómica: si cualquier item es inválido,
    no se registra ninguna línea y no se modifica ningún stock.
    """

    if not isinstance(items, list) or not items:
        return {
            "ok": False,
            "codigo": "DATOS_INVALIDOS",
            "mensaje": "La venta debe contener al menos un producto."
        }

    if fecha is None:
        fecha = datetime.now().strftime("%Y-%m-%d")

    agrupados = {}

    for item in items:
        if not isinstance(item, dict):
            return {
                "ok": False,
                "codigo": "DATOS_INVALIDOS",
                "mensaje": "Cada item de la venta debe ser un objeto."
            }

        id_producto = item.get("id_producto")
        cantidad = item.get("cantidad")
        precio_informado = item.get("precio_unitario")

        if isinstance(id_producto, bool) or not isinstance(id_producto, int):
            return {
                "ok": False,
                "codigo": "DATOS_INVALIDOS",
                "mensaje": "El ID del producto debe ser un número entero."
            }

        if isinstance(cantidad, bool) or not isinstance(cantidad, int):
            return {
                "ok": False,
                "codigo": "DATOS_INVALIDOS",
                "mensaje": "La cantidad debe ser un número entero."
            }

        if cantidad <= 0:
            return {
                "ok": False,
                "codigo": "DATOS_INVALIDOS",
                "mensaje": "La cantidad debe ser mayor que cero."
            }

        if precio_informado is not None:
            if isinstance(precio_informado, bool) or not isinstance(
                precio_informado,
                (int, float)
            ):
                return {
                    "ok": False,
                    "codigo": "DATOS_INVALIDOS",
                    "mensaje": "El precio unitario debe ser un número."
                }

            if precio_informado <= 0:
                return {
                    "ok": False,
                    "codigo": "DATOS_INVALIDOS",
                    "mensaje": "El precio unitario debe ser mayor que cero."
                }

        if id_producto not in agrupados:
            agrupados[id_producto] = {
                "cantidad": cantidad,
                "precio_unitario": precio_informado,
            }

        else:
            precio_anterior = agrupados[id_producto]["precio_unitario"]

            if (
                precio_anterior is not None
                and precio_informado is not None
                and precio_anterior != precio_informado
            ):
                return {
                    "ok": False,
                    "codigo": "DATOS_INVALIDOS",
                    "mensaje": (
                        "El mismo producto no puede tener dos precios "
                        "diferentes dentro de la misma venta."
                    )
                }

            agrupados[id_producto]["cantidad"] += cantidad

            if precio_anterior is None and precio_informado is not None:
                agrupados[id_producto]["precio_unitario"] = precio_informado

    conexion = obtener_conexion()

    try:
        conexion.execute("BEGIN IMMEDIATE")
        cursor = conexion.cursor()

        items_validados = []

        for id_producto, item in agrupados.items():
            cursor.execute(
                """
                SELECT
                    id_producto,
                    nombre,
                    stock,
                    precio_venta,
                    controla_stock
                FROM productos
                WHERE id_producto = ?
                """,
                (id_producto,)
            )

            producto = cursor.fetchone()

            if producto is None:
                conexion.rollback()

                return {
                    "ok": False,
                    "codigo": "PRODUCTO_NO_ENCONTRADO",
                    "mensaje": (
                        f"Producto no encontrado. ID: {id_producto}"
                    )
                }

            nombre = producto[1]
            stock_actual = producto[2]
            precio_configurado = producto[3]
            controla_stock = bool(producto[4])

            precio_unitario = item["precio_unitario"]

            if precio_unitario is None:
                precio_unitario = precio_configurado

            if precio_unitario is None:
                conexion.rollback()

                return {
                    "ok": False,
                    "codigo": "PRECIO_NO_CONFIGURADO",
                    "mensaje": (
                        f"{nombre} no tiene un precio de venta configurado."
                    )
                }

            cantidad = item["cantidad"]

            if controla_stock and cantidad > stock_actual:
                conexion.rollback()

                return {
                    "ok": False,
                    "codigo": "STOCK_INSUFICIENTE",
                    "mensaje": (
                        f"Stock insuficiente para {nombre}. "
                        f"Disponible: {stock_actual}. "
                        f"Solicitado: {cantidad}."
                    ),
                    "id_producto": id_producto,
                    "producto": nombre,
                    "stock_disponible": stock_actual,
                    "cantidad_solicitada": cantidad,
                }

            items_validados.append({
                "id_producto": id_producto,
                "producto": nombre,
                "cantidad": cantidad,
                "precio_unitario": precio_unitario,
                "stock_anterior": stock_actual,
                "controla_stock": controla_stock,
            })

        contexto_origen = _normalizar_contexto(contexto)
        fecha_hora = datetime.now().isoformat(timespec="seconds")

        cursor.execute(
            """
            INSERT INTO ventas_operaciones (
                fecha,
                estado_pago,
                fecha_hora,
                canal_origen,
                usuario_origen,
                numero_origen,
                grupo_origen,
                id_mensaje_origen
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                fecha,
                "Cobrado",
                fecha_hora,
                contexto_origen["canal"],
                contexto_origen["usuario_origen"],
                contexto_origen["numero_origen"],
                contexto_origen["grupo_origen"],
                contexto_origen["id_mensaje"],
            )
        )

        id_operacion = cursor.lastrowid
        total_operacion = 0
        lineas = []

        for item in items_validados:
            cursor.execute(
                """
                INSERT INTO ventas (
                    id_producto,
                    fecha,
                    cantidad,
                    precio_unitario,
                    id_operacion
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    item["id_producto"],
                    fecha,
                    item["cantidad"],
                    item["precio_unitario"],
                    id_operacion,
                )
            )

            id_venta = cursor.lastrowid

            if item["controla_stock"]:
                cursor.execute(
                    """
                    UPDATE productos
                    SET stock = stock - ?
                    WHERE id_producto = ?
                    """,
                    (
                        item["cantidad"],
                        item["id_producto"],
                    )
                )

                stock_restante = (
                    item["stock_anterior"]
                    - item["cantidad"]
                )

            else:
                stock_restante = None

            subtotal = (
                item["cantidad"]
                * item["precio_unitario"]
            )

            total_operacion += subtotal

            lineas.append({
                "id_venta": id_venta,
                "id_producto": item["id_producto"],
                "producto": item["producto"],
                "cantidad": item["cantidad"],
                "precio_unitario": item["precio_unitario"],
                "subtotal": subtotal,
                "controla_stock": item["controla_stock"],
                "stock_restante": stock_restante,
            })

        conexion.commit()

        return {
            "ok": True,
            "codigo": "VENTA_MULTIPLE_REGISTRADA",
            "mensaje": "Venta múltiple registrada correctamente.",
            "id_operacion": id_operacion,
            "estado_pago": "Cobrado",
            "fecha": fecha,
            "cantidad_items": len(lineas),
            "items": lineas,
            "total": total_operacion,
        }

    except sqlite3.Error as error:
        conexion.rollback()

        return {
            "ok": False,
            "codigo": "ERROR_BASE_DATOS",
            "mensaje": (
                f"Error al registrar la venta múltiple: {error}"
            )
        }

    finally:
        conexion.close()



# ============================================================
# ANULAR OPERACIÓN DE VENTA
# ============================================================

def _asegurar_campos_operacion_venta(conexion):
    cursor = conexion.cursor()

    cursor.execute("PRAGMA table_info(ventas_operaciones)")
    columnas = cursor.fetchall()

    nombres = [columna[1] for columna in columnas]

    if "anulada" not in nombres:
        cursor.execute(
            """
            ALTER TABLE ventas_operaciones
            ADD COLUMN anulada INTEGER NOT NULL DEFAULT 0
            """
        )

    if "fecha_anulacion" not in nombres:
        cursor.execute(
            """
            ALTER TABLE ventas_operaciones
            ADD COLUMN fecha_anulacion TEXT
            """
        )

    if "motivo_anulacion" not in nombres:
        cursor.execute(
            """
            ALTER TABLE ventas_operaciones
            ADD COLUMN motivo_anulacion TEXT
            """
        )

    conexion.commit()


def anular_operacion_venta(
    id_operacion,
    motivo,
    contexto=None
):
    if isinstance(id_operacion, bool) or not isinstance(
        id_operacion,
        int
    ):
        return {
            "ok": False,
            "codigo": "DATOS_INVALIDOS",
            "mensaje": "El ID de operación debe ser un número entero."
        }

    if id_operacion <= 0:
        return {
            "ok": False,
            "codigo": "DATOS_INVALIDOS",
            "mensaje": "El ID de operación debe ser mayor que cero."
        }

    if not isinstance(motivo, str) or not motivo.strip():
        return {
            "ok": False,
            "codigo": "DATOS_INVALIDOS",
            "mensaje": "El motivo de anulación no puede estar vacío."
        }

    conexion = obtener_conexion()

    try:
        _asegurar_campos_operacion_venta(conexion)

        conexion.execute("BEGIN IMMEDIATE")
        cursor = conexion.cursor()

        cursor.execute(
            """
            SELECT
                id_operacion,
                fecha,
                estado_pago,
                anulada
            FROM ventas_operaciones
            WHERE id_operacion = ?
            """,
            (id_operacion,)
        )

        operacion = cursor.fetchone()

        if operacion is None:
            conexion.rollback()

            return {
                "ok": False,
                "codigo": "OPERACION_VENTA_NO_ENCONTRADA",
                "mensaje": "Operación de venta no encontrada."
            }

        if operacion[3] == 1:
            conexion.rollback()

            return {
                "ok": False,
                "codigo": "OPERACION_VENTA_YA_ANULADA",
                "mensaje": "La operación de venta ya está anulada."
            }

        cursor.execute(
            """
            SELECT
                ventas.id_venta,
                ventas.id_producto,
                productos.nombre,
                ventas.cantidad,
                ventas.precio_unitario,
                ventas.anulada,
                productos.controla_stock
            FROM ventas
            INNER JOIN productos
                ON ventas.id_producto = productos.id_producto
            WHERE ventas.id_operacion = ?
            ORDER BY ventas.id_venta
            """,
            (id_operacion,)
        )

        filas = cursor.fetchall()

        if not filas:
            conexion.rollback()

            return {
                "ok": False,
                "codigo": "OPERACION_VENTA_SIN_ITEMS",
                "mensaje": "La operación no contiene ventas asociadas."
            }

        if any(fila[5] == 1 for fila in filas):
            conexion.rollback()

            return {
                "ok": False,
                "codigo": "OPERACION_VENTA_PARCIALMENTE_ANULADA",
                "mensaje": (
                    "La operación tiene líneas anuladas previamente "
                    "y no puede anularse completa automáticamente."
                )
            }

        fecha_anulacion = datetime.now().strftime("%Y-%m-%d")
        motivo_limpio = motivo.strip()
        contexto_anulacion = _normalizar_contexto(contexto)

        items = []
        total_anulado = 0

        for fila in filas:
            id_venta = fila[0]
            id_producto = fila[1]
            nombre = fila[2]
            cantidad = fila[3]
            precio_unitario = fila[4]
            controla_stock = bool(fila[6])

            subtotal = cantidad * precio_unitario
            total_anulado += subtotal

            if controla_stock:
                cursor.execute(
                    """
                    UPDATE productos
                    SET stock = stock + ?
                    WHERE id_producto = ?
                    """,
                    (
                        cantidad,
                        id_producto,
                    )
                )

            cursor.execute(
                """
                UPDATE ventas
                SET
                    anulada = 1,
                    fecha_anulacion = ?,
                    motivo_anulacion = ?
                WHERE id_venta = ?
                """,
                (
                    fecha_anulacion,
                    motivo_limpio,
                    id_venta,
                )
            )

            items.append({
                "id_venta": id_venta,
                "id_producto": id_producto,
                "producto": nombre,
                "cantidad": cantidad,
                "precio_unitario": precio_unitario,
                "subtotal": subtotal,
                "controla_stock": controla_stock,
            })

        cursor.execute(
            """
            UPDATE ventas_operaciones
            SET
                anulada = 1,
                fecha_anulacion = ?,
                motivo_anulacion = ?,
                usuario_anulacion = ?,
                id_mensaje_anulacion = ?
            WHERE id_operacion = ?
            """,
            (
                fecha_anulacion,
                motivo_limpio,
                contexto_anulacion["usuario_origen"],
                contexto_anulacion["id_mensaje"],
                id_operacion,
            )
        )

        conexion.commit()

        return {
            "ok": True,
            "codigo": "OPERACION_VENTA_ANULADA",
            "mensaje": "Operación de venta anulada correctamente.",
            "id_operacion": id_operacion,
            "fecha_anulacion": fecha_anulacion,
            "motivo": motivo_limpio,
            "items": items,
            "total_anulado": total_anulado,
        }

    except sqlite3.Error as error:
        conexion.rollback()

        return {
            "ok": False,
            "codigo": "ERROR_BASE_DATOS",
            "mensaje": (
                f"Error al anular la operación de venta: {error}"
            )
        }

    finally:
        conexion.close()


def anular_ultima_operacion_venta(
    motivo="Corrección de última venta",
    contexto=None
):
    contexto_origen = _normalizar_contexto(contexto)
    usuario_origen = contexto_origen["usuario_origen"]

    conexion = obtener_conexion()

    try:
        _asegurar_campos_operacion_venta(conexion)

        cursor = conexion.cursor()

        if usuario_origen:
            cursor.execute(
                """
                SELECT id_operacion
                FROM ventas_operaciones
                WHERE anulada = 0
                  AND usuario_origen = ?
                  AND EXISTS (
                      SELECT 1
                      FROM ventas
                      WHERE ventas.id_operacion =
                            ventas_operaciones.id_operacion
                        AND ventas.anulada = 0
                  )
                ORDER BY id_operacion DESC
                LIMIT 1
                """,
                (usuario_origen,)
            )
        else:
            cursor.execute(
                """
                SELECT id_operacion
                FROM ventas_operaciones
                WHERE anulada = 0
                  AND EXISTS (
                      SELECT 1
                      FROM ventas
                      WHERE ventas.id_operacion =
                            ventas_operaciones.id_operacion
                        AND ventas.anulada = 0
                  )
                ORDER BY id_operacion DESC
                LIMIT 1
                """
            )

        fila = cursor.fetchone()

    finally:
        conexion.close()

    if fila is None:
        return {
            "ok": False,
            "codigo": "OPERACION_VENTA_NO_ENCONTRADA",
            "mensaje": (
                "No hay ventas activas tuyas para anular."
                if usuario_origen
                else "No hay ventas activas para anular."
            )
        }

    return anular_operacion_venta(
        id_operacion=fila[0],
        motivo=motivo,
        contexto=contexto,
    )
