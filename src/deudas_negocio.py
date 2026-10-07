from datetime import datetime

from database import obtener_conexion


def _nombre_limpio(nombre):
    return " ".join(
        str(nombre or "").strip().split()
    )


def _buscar_cuenta(cursor, nombre):
    nombre_limpio = _nombre_limpio(
        nombre
    )

    return cursor.execute(
        """
        SELECT
            id_cuenta,
            nombre,
            tipo,
            moneda,
            proximo_vencimiento,
            activa
        FROM cuentas_deuda_negocio
        WHERE LOWER(nombre) = LOWER(?)
        """,
        (nombre_limpio,)
    ).fetchone()


def _saldo_cuenta(cursor, id_cuenta):
    fila = cursor.execute(
        """
        SELECT COALESCE(SUM(importe), 0)
        FROM movimientos_deuda_negocio
        WHERE id_cuenta = ?
        """,
        (id_cuenta,)
    ).fetchone()

    return float(
        fila[0] or 0
    )


def _crear_cuenta(
    cursor,
    nombre,
    tipo="Tarjeta",
    moneda="ARS",
):
    nombre_limpio = _nombre_limpio(
        nombre
    )

    if not nombre_limpio:
        raise ValueError(
            "La cuenta de deuda debe tener un nombre."
        )

    fecha_creacion = datetime.now().isoformat(
        timespec="seconds"
    )

    cursor.execute(
        """
        INSERT INTO cuentas_deuda_negocio (
            nombre,
            tipo,
            moneda,
            activa,
            fecha_creacion
        )
        VALUES (?, ?, ?, 1, ?)
        """,
        (
            nombre_limpio,
            tipo,
            moneda,
            fecha_creacion,
        )
    )

    return cursor.lastrowid


def _obtener_o_crear_cuenta(
    cursor,
    nombre,
):
    cuenta = _buscar_cuenta(
        cursor,
        nombre,
    )

    if cuenta is not None:
        return cuenta[0]

    return _crear_cuenta(
        cursor,
        nombre,
    )


def _validar_monto_positivo(monto):
    return (
        not isinstance(monto, bool)
        and isinstance(monto, (int, float))
        and monto > 0
    )


def registrar_saldo_inicial(
    nombre,
    monto,
):
    if (
        isinstance(monto, bool)
        or not isinstance(monto, (int, float))
        or monto < 0
    ):
        return {
            "ok": False,
            "codigo": "MONTO_DEUDA_INVALIDO",
            "mensaje": (
                "El saldo inicial debe ser un número "
                "mayor o igual a cero."
            ),
        }

    conexion = obtener_conexion()

    try:
        conexion.execute(
            "BEGIN IMMEDIATE"
        )
        cursor = conexion.cursor()

        id_cuenta = _obtener_o_crear_cuenta(
            cursor,
            nombre,
        )

        cantidad_movimientos = cursor.execute(
            """
            SELECT COUNT(*)
            FROM movimientos_deuda_negocio
            WHERE id_cuenta = ?
            """,
            (id_cuenta,)
        ).fetchone()[0]

        if cantidad_movimientos > 0:
            conexion.rollback()

            return {
                "ok": False,
                "codigo": "SALDO_INICIAL_YA_REGISTRADO",
                "mensaje": (
                    "La cuenta ya tiene movimientos. "
                    "Usá un ajuste si necesitás corregir su saldo."
                ),
            }

        fecha_hora = datetime.now().isoformat(
            timespec="seconds"
        )

        if monto > 0:
            cursor.execute(
                """
                INSERT INTO movimientos_deuda_negocio (
                    id_cuenta,
                    fecha_hora,
                    tipo,
                    importe,
                    descripcion
                )
                VALUES (?, ?, 'Saldo inicial', ?, ?)
                """,
                (
                    id_cuenta,
                    fecha_hora,
                    float(monto),
                    "Carga inicial del saldo pendiente",
                )
            )

        cuenta = _buscar_cuenta(
            cursor,
            nombre,
        )

        conexion.commit()

        return {
            "ok": True,
            "codigo": "SALDO_INICIAL_DEUDA_REGISTRADO",
            "id_cuenta": id_cuenta,
            "cuenta": cuenta[1],
            "saldo": float(monto),
            "moneda": cuenta[3],
        }

    except Exception as error:
        conexion.rollback()
        return {
            "ok": False,
            "codigo": "ERROR_BASE_DATOS",
            "mensaje": (
                "Error al registrar saldo inicial de deuda: "
                f"{error}"
            ),
        }

    finally:
        conexion.close()


def registrar_compra_deuda_en_cursor(
    cursor,
    nombre,
    monto,
    descripcion=None,
    fecha_hora=None,
):
    if not _validar_monto_positivo(
        monto
    ):
        raise ValueError(
            "El monto de la compra financiada debe ser mayor que cero."
        )

    id_cuenta = _obtener_o_crear_cuenta(
        cursor,
        nombre,
    )

    if fecha_hora is None:
        fecha_hora = datetime.now().isoformat(
            timespec="seconds"
        )

    cursor.execute(
        """
        INSERT INTO movimientos_deuda_negocio (
            id_cuenta,
            fecha_hora,
            tipo,
            importe,
            descripcion
        )
        VALUES (?, ?, 'Compra', ?, ?)
        """,
        (
            id_cuenta,
            fecha_hora,
            float(monto),
            (
                str(descripcion).strip()
                if descripcion
                else "Compra financiada del negocio"
            ),
        )
    )

    id_movimiento = cursor.lastrowid
    cuenta = _buscar_cuenta(
        cursor,
        nombre,
    )
    saldo = _saldo_cuenta(
        cursor,
        id_cuenta,
    )

    return {
        "id_movimiento_deuda": id_movimiento,
        "id_cuenta": id_cuenta,
        "cuenta": cuenta[1],
        "monto": float(monto),
        "saldo": saldo,
        "moneda": cuenta[3],
    }


def registrar_compra_deuda(
    nombre,
    monto,
    descripcion=None,
):
    if not _validar_monto_positivo(
        monto
    ):
        return {
            "ok": False,
            "codigo": "MONTO_DEUDA_INVALIDO",
            "mensaje": (
                "El monto de la compra financiada "
                "debe ser mayor que cero."
            ),
        }

    conexion = obtener_conexion()

    try:
        conexion.execute(
            "BEGIN IMMEDIATE"
        )
        cursor = conexion.cursor()

        datos = registrar_compra_deuda_en_cursor(
            cursor=cursor,
            nombre=nombre,
            monto=monto,
            descripcion=descripcion,
        )

        conexion.commit()

        return {
            "ok": True,
            "codigo": "COMPRA_DEUDA_REGISTRADA",
            **datos,
        }

    except Exception as error:
        conexion.rollback()
        return {
            "ok": False,
            "codigo": "ERROR_BASE_DATOS",
            "mensaje": (
                "Error al registrar compra financiada: "
                f"{error}"
            ),
        }

    finally:
        conexion.close()


def registrar_pago_deuda(
    nombre,
    monto,
    descripcion=None,
    afecta_caja=True,
):
    if not _validar_monto_positivo(
        monto
    ):
        return {
            "ok": False,
            "codigo": "MONTO_DEUDA_INVALIDO",
            "mensaje": (
                "El pago debe ser un número mayor que cero."
            ),
        }

    conexion = obtener_conexion()

    try:
        conexion.execute(
            "BEGIN IMMEDIATE"
        )
        cursor = conexion.cursor()

        cuenta = _buscar_cuenta(
            cursor,
            nombre,
        )

        if cuenta is None:
            conexion.rollback()

            return {
                "ok": False,
                "codigo": "CUENTA_DEUDA_NO_ENCONTRADA",
                "mensaje": (
                    f"No existe una deuda registrada como "
                    f"'{_nombre_limpio(nombre)}'."
                ),
            }

        id_cuenta = cuenta[0]
        saldo_anterior = _saldo_cuenta(
            cursor,
            id_cuenta,
        )

        if float(monto) > saldo_anterior + 1e-9:
            conexion.rollback()

            return {
                "ok": False,
                "codigo": "PAGO_DEUDA_EXCESIVO",
                "mensaje": (
                    f"El pago supera el saldo pendiente. "
                    f"Saldo actual: {saldo_anterior:.2f}."
                ),
                "saldo": saldo_anterior,
            }

        fecha_hora = datetime.now().isoformat(
            timespec="seconds"
        )
        fecha = datetime.now().strftime(
            "%Y-%m-%d"
        )
        id_movimiento_caja = None

        if afecta_caja:
            cursor.execute(
                """
                INSERT INTO movimientos_caja (
                    fecha,
                    tipo,
                    descripcion,
                    monto,
                    anulado
                )
                VALUES (?, 'Retiro', ?, ?, 0)
                """,
                (
                    fecha,
                    (
                        "Pago deuda negocio - "
                        f"{cuenta[1]}"
                    ),
                    float(monto),
                )
            )
            id_movimiento_caja = cursor.lastrowid

        cursor.execute(
            """
            INSERT INTO movimientos_deuda_negocio (
                id_cuenta,
                fecha_hora,
                tipo,
                importe,
                descripcion,
                id_movimiento_caja
            )
            VALUES (?, ?, 'Pago', ?, ?, ?)
            """,
            (
                id_cuenta,
                fecha_hora,
                -float(monto),
                (
                    str(descripcion).strip()
                    if descripcion
                    else "Pago de deuda del negocio"
                ),
                id_movimiento_caja,
            )
        )

        id_movimiento = cursor.lastrowid
        saldo_nuevo = (
            saldo_anterior
            - float(monto)
        )

        conexion.commit()

        return {
            "ok": True,
            "codigo": "PAGO_DEUDA_REGISTRADO",
            "id_movimiento_deuda": id_movimiento,
            "id_movimiento_caja": id_movimiento_caja,
            "id_cuenta": id_cuenta,
            "cuenta": cuenta[1],
            "monto": float(monto),
            "saldo_anterior": saldo_anterior,
            "saldo": saldo_nuevo,
            "afecta_caja": bool(
                afecta_caja
            ),
            "moneda": cuenta[3],
        }

    except Exception as error:
        conexion.rollback()
        return {
            "ok": False,
            "codigo": "ERROR_BASE_DATOS",
            "mensaje": (
                "Error al registrar pago de deuda: "
                f"{error}"
            ),
        }

    finally:
        conexion.close()


def ajustar_deuda(
    nombre,
    nuevo_saldo,
    descripcion=None,
):
    if (
        isinstance(nuevo_saldo, bool)
        or not isinstance(
            nuevo_saldo,
            (int, float)
        )
        or nuevo_saldo < 0
    ):
        return {
            "ok": False,
            "codigo": "MONTO_DEUDA_INVALIDO",
            "mensaje": (
                "El nuevo saldo debe ser un número "
                "mayor o igual a cero."
            ),
        }

    conexion = obtener_conexion()

    try:
        conexion.execute(
            "BEGIN IMMEDIATE"
        )
        cursor = conexion.cursor()

        cuenta = _buscar_cuenta(
            cursor,
            nombre,
        )

        if cuenta is None:
            conexion.rollback()

            return {
                "ok": False,
                "codigo": "CUENTA_DEUDA_NO_ENCONTRADA",
                "mensaje": (
                    f"No existe una deuda registrada como "
                    f"'{_nombre_limpio(nombre)}'."
                ),
            }

        saldo_anterior = _saldo_cuenta(
            cursor,
            cuenta[0],
        )
        diferencia = (
            float(nuevo_saldo)
            - saldo_anterior
        )

        if abs(diferencia) > 1e-9:
            cursor.execute(
                """
                INSERT INTO movimientos_deuda_negocio (
                    id_cuenta,
                    fecha_hora,
                    tipo,
                    importe,
                    descripcion
                )
                VALUES (?, ?, 'Ajuste', ?, ?)
                """,
                (
                    cuenta[0],
                    datetime.now().isoformat(
                        timespec="seconds"
                    ),
                    diferencia,
                    (
                        str(descripcion).strip()
                        if descripcion
                        else "Ajuste manual de saldo"
                    ),
                )
            )

        conexion.commit()

        return {
            "ok": True,
            "codigo": "DEUDA_AJUSTADA",
            "id_cuenta": cuenta[0],
            "cuenta": cuenta[1],
            "saldo_anterior": saldo_anterior,
            "saldo": float(
                nuevo_saldo
            ),
            "diferencia": diferencia,
            "moneda": cuenta[3],
        }

    except Exception as error:
        conexion.rollback()
        return {
            "ok": False,
            "codigo": "ERROR_BASE_DATOS",
            "mensaje": (
                "Error al ajustar deuda: "
                f"{error}"
            ),
        }

    finally:
        conexion.close()


def configurar_vencimiento(
    nombre,
    fecha_vencimiento,
):
    try:
        datetime.strptime(
            fecha_vencimiento,
            "%Y-%m-%d",
        )
    except (TypeError, ValueError):
        return {
            "ok": False,
            "codigo": "FECHA_VENCIMIENTO_INVALIDA",
            "mensaje": (
                "La fecha debe usar formato AAAA-MM-DD."
            ),
        }

    conexion = obtener_conexion()

    try:
        conexion.execute(
            "BEGIN IMMEDIATE"
        )
        cursor = conexion.cursor()
        id_cuenta = _obtener_o_crear_cuenta(
            cursor,
            nombre,
        )

        cursor.execute(
            """
            UPDATE cuentas_deuda_negocio
            SET proximo_vencimiento = ?
            WHERE id_cuenta = ?
            """,
            (
                fecha_vencimiento,
                id_cuenta,
            )
        )

        cuenta = _buscar_cuenta(
            cursor,
            nombre,
        )
        saldo = _saldo_cuenta(
            cursor,
            id_cuenta,
        )

        conexion.commit()

        return {
            "ok": True,
            "codigo": "VENCIMIENTO_DEUDA_CONFIGURADO",
            "id_cuenta": id_cuenta,
            "cuenta": cuenta[1],
            "proximo_vencimiento": (
                fecha_vencimiento
            ),
            "saldo": saldo,
            "moneda": cuenta[3],
        }

    except Exception as error:
        conexion.rollback()
        return {
            "ok": False,
            "codigo": "ERROR_BASE_DATOS",
            "mensaje": (
                "Error al configurar vencimiento: "
                f"{error}"
            ),
        }

    finally:
        conexion.close()


def resumen_deudas():
    conexion = obtener_conexion()

    try:
        filas = conexion.execute(
            """
            SELECT
                c.id_cuenta,
                c.nombre,
                c.tipo,
                c.moneda,
                c.proximo_vencimiento,
                COALESCE(
                    SUM(m.importe),
                    0
                ) AS saldo
            FROM cuentas_deuda_negocio c
            LEFT JOIN movimientos_deuda_negocio m
                ON m.id_cuenta = c.id_cuenta
            WHERE c.activa = 1
            GROUP BY
                c.id_cuenta,
                c.nombre,
                c.tipo,
                c.moneda,
                c.proximo_vencimiento
            ORDER BY
                CASE
                    WHEN c.proximo_vencimiento IS NULL
                    THEN 1
                    ELSE 0
                END,
                c.proximo_vencimiento,
                c.nombre
            """
        ).fetchall()

        cuentas = [
            {
                "id_cuenta": fila[0],
                "nombre": fila[1],
                "tipo": fila[2],
                "moneda": fila[3],
                "proximo_vencimiento": fila[4],
                "saldo": float(
                    fila[5] or 0
                ),
            }
            for fila in filas
        ]

        total_ars = sum(
            cuenta["saldo"]
            for cuenta in cuentas
            if cuenta["moneda"] == "ARS"
        )

        return {
            "ok": True,
            "codigo": "RESUMEN_DEUDAS_NEGOCIO",
            "cuentas": cuentas,
            "total_ars": total_ars,
        }

    finally:
        conexion.close()


def detalle_deuda(nombre):
    conexion = obtener_conexion()

    try:
        cursor = conexion.cursor()
        cuenta = _buscar_cuenta(
            cursor,
            nombre,
        )

        if cuenta is None:
            return {
                "ok": False,
                "codigo": "CUENTA_DEUDA_NO_ENCONTRADA",
                "mensaje": (
                    f"No existe una deuda registrada como "
                    f"'{_nombre_limpio(nombre)}'."
                ),
            }

        saldo = _saldo_cuenta(
            cursor,
            cuenta[0],
        )

        return {
            "ok": True,
            "codigo": "DETALLE_DEUDA_NEGOCIO",
            "id_cuenta": cuenta[0],
            "cuenta": cuenta[1],
            "tipo": cuenta[2],
            "moneda": cuenta[3],
            "proximo_vencimiento": cuenta[4],
            "saldo": saldo,
        }

    finally:
        conexion.close()


def historial_deuda(
    nombre,
    limite=20,
):
    if (
        isinstance(limite, bool)
        or not isinstance(limite, int)
        or limite <= 0
    ):
        limite = 20

    conexion = obtener_conexion()

    try:
        cursor = conexion.cursor()
        cuenta = _buscar_cuenta(
            cursor,
            nombre,
        )

        if cuenta is None:
            return {
                "ok": False,
                "codigo": "CUENTA_DEUDA_NO_ENCONTRADA",
                "mensaje": (
                    f"No existe una deuda registrada como "
                    f"'{_nombre_limpio(nombre)}'."
                ),
            }

        filas = cursor.execute(
            """
            SELECT
                id_movimiento_deuda,
                fecha_hora,
                tipo,
                importe,
                descripcion,
                id_movimiento_caja
            FROM movimientos_deuda_negocio
            WHERE id_cuenta = ?
            ORDER BY
                id_movimiento_deuda DESC
            LIMIT ?
            """,
            (
                cuenta[0],
                limite,
            )
        ).fetchall()

        return {
            "ok": True,
            "codigo": "HISTORIAL_DEUDA_NEGOCIO",
            "cuenta": cuenta[1],
            "moneda": cuenta[3],
            "saldo": _saldo_cuenta(
                cursor,
                cuenta[0],
            ),
            "movimientos": [
                {
                    "id_movimiento_deuda": fila[0],
                    "fecha_hora": fila[1],
                    "tipo": fila[2],
                    "importe": float(fila[3]),
                    "descripcion": fila[4],
                    "id_movimiento_caja": fila[5],
                }
                for fila in filas
            ],
        }

    finally:
        conexion.close()


def deuda_vence_primero():
    resumen = resumen_deudas()

    cuentas = [
        cuenta
        for cuenta in resumen["cuentas"]
        if (
            cuenta["saldo"] > 0
            and cuenta["proximo_vencimiento"]
        )
    ]

    if not cuentas:
        return {
            "ok": True,
            "codigo": "SIN_VENCIMIENTOS_DEUDA",
            "cuenta": None,
        }

    cuenta = min(
        cuentas,
        key=lambda item: (
            item["proximo_vencimiento"],
            item["nombre"],
        )
    )

    return {
        "ok": True,
        "codigo": "DEUDA_VENCE_PRIMERO",
        "cuenta": cuenta,
    }
