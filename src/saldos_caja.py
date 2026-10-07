from datetime import datetime

from database import obtener_conexion


SECCIONES_CAJA = {
    "bebidas_postres": "Bebidas + Postres",
    "rotiseria": "Rotisería",
}


def normalizar_seccion_caja(seccion):
    texto = str(seccion or "").strip().lower()

    equivalencias = {
        "bebidas_postres": "bebidas_postres",
        "bebidas postres": "bebidas_postres",
        "bebidas y postres": "bebidas_postres",
        "postres y bebidas": "bebidas_postres",
        "postres bebidas": "bebidas_postres",
        "rotiseria": "rotiseria",
        "rotisería": "rotiseria",
        "comidas": "rotiseria",
        "comida": "rotiseria",
    }

    return equivalencias.get(texto)


def registrar_saldo_inicial_caja(
    seccion,
    monto,
):
    seccion_normalizada = normalizar_seccion_caja(
        seccion
    )

    if seccion_normalizada is None:
        return {
            "ok": False,
            "codigo": "SECCION_CAJA_INVALIDA",
            "mensaje": (
                "La caja debe ser 'bebidas postres' "
                "o 'rotiseria'."
            ),
        }

    if (
        isinstance(monto, bool)
        or not isinstance(monto, (int, float))
        or monto < 0
    ):
        return {
            "ok": False,
            "codigo": "SALDO_INICIAL_CAJA_INVALIDO",
            "mensaje": (
                "El saldo inicial debe ser un número "
                "mayor o igual a cero."
            ),
        }

    conexion = obtener_conexion()

    try:
        cursor = conexion.cursor()
        cursor.execute("BEGIN IMMEDIATE")

        def maximo(tabla, columna):
            return cursor.execute(
                f"SELECT COALESCE(MAX({columna}), 0) FROM {tabla}"
            ).fetchone()[0]

        corte_ventas = maximo(
            "ventas",
            "id_venta",
        )
        corte_compras = maximo(
            "compras",
            "id_compra",
        )
        corte_gastos = maximo(
            "gastos",
            "id_gasto",
        )
        corte_movimientos = maximo(
            "movimientos_caja",
            "id_movimiento",
        )

        fecha_hora = datetime.now().isoformat(
            timespec="seconds"
        )

        cursor.execute(
            """
            INSERT INTO saldos_iniciales_caja (
                seccion,
                monto,
                fecha_hora,
                id_venta_corte,
                id_compra_corte,
                id_gasto_corte,
                id_movimiento_caja_corte
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                seccion_normalizada,
                float(monto),
                fecha_hora,
                corte_ventas,
                corte_compras,
                corte_gastos,
                corte_movimientos,
            )
        )

        id_saldo_inicial = cursor.lastrowid
        conexion.commit()

        return {
            "ok": True,
            "codigo": "SALDO_INICIAL_CAJA_REGISTRADO",
            "id_saldo_inicial": id_saldo_inicial,
            "seccion": seccion_normalizada,
            "nombre": SECCIONES_CAJA[
                seccion_normalizada
            ],
            "monto": float(monto),
            "fecha_hora": fecha_hora,
            "id_venta_corte": corte_ventas,
            "id_compra_corte": corte_compras,
            "id_gasto_corte": corte_gastos,
            "id_movimiento_caja_corte": corte_movimientos,
        }

    except Exception:
        conexion.rollback()
        raise

    finally:
        conexion.close()


def obtener_saldo_inicial_caja(seccion):
    seccion_normalizada = normalizar_seccion_caja(
        seccion
    )

    if seccion_normalizada is None:
        return None

    conexion = obtener_conexion()

    try:
        fila = conexion.execute(
            """
            SELECT
                id_saldo_inicial,
                seccion,
                monto,
                fecha_hora,
                id_venta_corte,
                id_compra_corte,
                id_gasto_corte,
                id_movimiento_caja_corte
            FROM saldos_iniciales_caja
            WHERE seccion = ?
            ORDER BY id_saldo_inicial DESC
            LIMIT 1
            """,
            (seccion_normalizada,)
        ).fetchone()

        if fila is None:
            return None

        return {
            "id_saldo_inicial": fila[0],
            "seccion": fila[1],
            "nombre": SECCIONES_CAJA[
                fila[1]
            ],
            "monto": float(fila[2]),
            "fecha_hora": fila[3],
            "id_venta_corte": int(fila[4] or 0),
            "id_compra_corte": int(fila[5] or 0),
            "id_gasto_corte": int(fila[6] or 0),
            "id_movimiento_caja_corte": int(
                fila[7] or 0
            ),
        }

    finally:
        conexion.close()
