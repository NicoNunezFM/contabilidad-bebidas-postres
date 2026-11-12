

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from pydantic import BaseModel, Field

from pos_auth import (
    autenticar_usuario,
    crear_sesion_pos,
    obtener_usuario_sesion_pos,
    revocar_sesion_pos,
)

from database import obtener_conexion

router = APIRouter(prefix="/pos-api", tags=["POS - Sesiones"])

COOKIE_ADMIN = "abadion_pos_admin"
COOKIE_VENTAS = "abadion_pos_ventas"


class LoginEntrada(BaseModel):
    usuario: str = Field(min_length=1, max_length=40)
    contrasena: str = Field(min_length=1, max_length=256)


class PrecioNuevoEntrada(BaseModel):
    precio_nuevo: float = Field(
        gt=0,
        le=100_000_000,
        allow_inf_nan=False
    )


class PersonalizacionesEntrada(BaseModel):
    ingredientes: list[str] = Field(max_length=30)
    ids_adicionales: list[int] = Field(max_length=30)



def comprobar_origen(request: Request):
    origen = request.headers.get("origin")
    esperado = f"{request.url.scheme}://{request.url.netloc}"

    if origen != esperado:
        raise HTTPException(
            status_code=403,
            detail="Origen no permitido."
        )


def exigir_administrador_pos(request: Request) -> dict:
    token_admin = request.cookies.get(COOKIE_ADMIN)

    if token_admin:
        usuario = obtener_usuario_sesion_pos(token_admin)

        if usuario is not None and usuario["rol"] == "admin":
            return usuario

    token_ventas = request.cookies.get(COOKIE_VENTAS)

    if token_ventas:
        usuario = obtener_usuario_sesion_pos(token_ventas)

        if usuario is not None and usuario["rol"] == "ventas":
            raise HTTPException(
                status_code=403,
                detail="No tenés permisos de administrador."
            )

    raise HTTPException(
        status_code=401,
        detail="Debés iniciar sesión como administrador."
    )


@router.post("/login")
def iniciar_sesion(
    datos: LoginEntrada,
    request: Request,
    response: Response,
):
    comprobar_origen(request)

    usuario = autenticar_usuario(
        datos.usuario,
        datos.contrasena
    )

    if usuario is None:
        raise HTTPException(
            status_code=401,
            detail="Usuario o contraseña incorrectos."
        )

    token = crear_sesion_pos(usuario["id_usuario"])

    es_admin = usuario["rol"] == "admin"
    nombre_cookie = COOKIE_ADMIN if es_admin else COOKIE_VENTAS
    duracion = 8 * 3600 if es_admin else 30 * 24 * 3600

    response.set_cookie(
        key=nombre_cookie,
        value=token,
        max_age=duracion,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="strict",
        path="/pos-api",
    )

    return {
        "ok": True,
        "usuario": usuario["usuario"],
        "rol": usuario["rol"]
    }


@router.get("/yo")
def usuario_actual(request: Request):
    for nombre_cookie, rol in (
        (COOKIE_ADMIN, "admin"),
        (COOKIE_VENTAS, "ventas"),
    ):
        token = request.cookies.get(nombre_cookie)

        if not token:
            continue

        usuario = obtener_usuario_sesion_pos(token)

        if usuario is not None and usuario["rol"] == rol:
            return {"ok": True, "usuario": usuario}

    raise HTTPException(
        status_code=401,
        detail="No hay una sesión válida."
    )


@router.post("/logout")
def cerrar_sesion(request: Request, response: Response):
    comprobar_origen(request)

    for nombre_cookie in (COOKIE_ADMIN, COOKIE_VENTAS):
        token = request.cookies.get(nombre_cookie)

        if token:
            revocar_sesion_pos(token)
            response.delete_cookie(
                key=nombre_cookie,
                path="/pos-api",
                samesite="strict",
            )

            return {"ok": True, "mensaje": "Sesión cerrada."}

    return {"ok": True, "mensaje": "No había una sesión abierta."}


@router.get("/admin/verificar")
def verificar_acceso_administrador(
    usuario: dict = Depends(exigir_administrador_pos)
):
    return {
        "ok": True,
        "mensaje": "Acceso administrativo autorizado.",
        "usuario": usuario["usuario"],
        "rol": usuario["rol"]
    }


@router.patch("/admin/productos/{id_producto}/precio")
def actualizar_precio_producto_pos(
    id_producto: int,
    datos: PrecioNuevoEntrada,
    request: Request,
    usuario: dict = Depends(exigir_administrador_pos)
):
    comprobar_origen(request)

    conexion = obtener_conexion()

    try:
        conexion.execute("BEGIN IMMEDIATE")

        producto = conexion.execute(
            """
            SELECT nombre, precio_venta
            FROM productos
            WHERE id_producto = ?
            """,
            (id_producto,)
        ).fetchone()

        if producto is None:
            raise HTTPException(
                status_code=404,
                detail="Producto no encontrado."
            )

        nombre, precio_anterior = producto
        precio_nuevo = datos.precio_nuevo

        if precio_anterior == precio_nuevo:
            conexion.rollback()
            return {
                "ok": True,
                "actualizado": False,
                "mensaje": "El precio ya tenía ese valor."
            }

        conexion.execute(
            """
            UPDATE productos
            SET precio_venta = ?
            WHERE id_producto = ?
            """,
            (precio_nuevo, id_producto)
        )

        conexion.execute(
            """
            INSERT INTO historial_precios_pos (
                id_producto,
                id_usuario,
                precio_anterior,
                precio_nuevo
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                id_producto,
                usuario["id_usuario"],
                precio_anterior,
                precio_nuevo
            )
        )

        conexion.commit()

        return {
            "ok": True,
            "actualizado": True,
            "producto": nombre,
            "precio_anterior": precio_anterior,
            "precio_nuevo": precio_nuevo,
            "modificado_por": usuario["usuario"]
        }

    except Exception:
        conexion.rollback()
        raise

    finally:
        conexion.close()


@router.get("/catalogo/adicionales")
def consultar_adicionales_pos():
    conexion = obtener_conexion()

    try:
        filas = conexion.execute("""
            SELECT
                id_adicional_catalogo,
                nombre,
                precio_venta
            FROM adicionales_catalogo
            WHERE activo = 1
            ORDER BY nombre COLLATE NOCASE
        """).fetchall()

        adicionales = []

        for fila in filas:
            adicionales.append({
                "id_adicional_catalogo": fila[0],
                "nombre": fila[1],
                "precio_venta": fila[2]
            })

        return {
            "ok": True,
            "cantidad": len(adicionales),
            "adicionales": adicionales
        }

    finally:
        conexion.close()


@router.get("/catalogo/productos/{id_producto}/personalizaciones")
def consultar_personalizaciones_pos(id_producto: int):
    conexion = obtener_conexion()

    try:
        # Comprobar que el producto existe.
        producto = conexion.execute(
            """
            SELECT nombre
            FROM productos
            WHERE id_producto = ?
            """,
            (id_producto,)
        ).fetchone()

        if producto is None:
            raise HTTPException(
                status_code=404,
                detail="Producto no encontrado."
            )

        # Ingredientes que se pueden quitar.
        filas_ingredientes = conexion.execute(
            """
            SELECT ingrediente
            FROM pos_ingredientes_producto
            WHERE id_producto = ?
            ORDER BY ingrediente COLLATE NOCASE
            """,
            (id_producto,)
        ).fetchall()

        ingredientes = [
            fila[0] for fila in filas_ingredientes
        ]

        # Extras permitidos y activos.
        filas_adicionales = conexion.execute(
            """
            SELECT
                a.id_adicional_catalogo,
                a.nombre,
                a.precio_venta
            FROM pos_adicionales_producto AS pa
            JOIN adicionales_catalogo AS a
              ON a.id_adicional_catalogo =
                 pa.id_adicional_catalogo
            WHERE pa.id_producto = ?
              AND a.activo = 1
            ORDER BY a.nombre COLLATE NOCASE
            """,
            (id_producto,)
        ).fetchall()

        adicionales = [
            {
                "id_adicional_catalogo": fila[0],
                "nombre": fila[1],
                "precio_venta": fila[2]
            }
            for fila in filas_adicionales
        ]

        return {
            "ok": True,
            "id_producto": id_producto,
            "producto": producto[0],
            "ingredientes": ingredientes,
            "adicionales": adicionales
        }

    finally:
        conexion.close()


@router.put("/admin/productos/{id_producto}/personalizaciones")
def configurar_personalizaciones_pos(
    id_producto: int,
    datos: PersonalizacionesEntrada,
    request: Request,
    usuario: dict = Depends(exigir_administrador_pos)
):
    comprobar_origen(request)

    ingredientes = [
        nombre.strip()
        for nombre in datos.ingredientes
    ]

    # Validar ingredientes vacíos, largos o repetidos.
    if any(
        not nombre or len(nombre) > 60
        for nombre in ingredientes
    ):
        raise HTTPException(
            status_code=422,
            detail="Hay ingredientes inválidos."
        )

    if len({n.casefold() for n in ingredientes}) != len(ingredientes):
        raise HTTPException(
            status_code=422,
            detail="Hay ingredientes repetidos."
        )

    ids = datos.ids_adicionales

    if (
        any(type(i) is not int or i <= 0 for i in ids)
        or len(set(ids)) != len(ids)
    ):
        raise HTTPException(
            status_code=422,
            detail="Hay adicionales inválidos o repetidos."
        )

    conexion = obtener_conexion()

    try:
        conexion.execute("BEGIN IMMEDIATE")

        producto = conexion.execute(
            """
            SELECT nombre
            FROM productos
            WHERE id_producto = ?
            """,
            (id_producto,)
        ).fetchone()

        if producto is None:
            raise HTTPException(
                status_code=404,
                detail="Producto no encontrado."
            )

        # Solo aceptar extras existentes y activos.
        for id_adicional in ids:
            adicional = conexion.execute(
                """
                SELECT id_adicional_catalogo
                FROM adicionales_catalogo
                WHERE id_adicional_catalogo = ?
                  AND activo = 1
                """,
                (id_adicional,)
            ).fetchone()

            if adicional is None:
                raise HTTPException(
                    status_code=422,
                    detail="Uno de los adicionales no está disponible."
                )

        # Reemplazar la configuración anterior del producto.
        conexion.execute(
            """
            DELETE FROM pos_ingredientes_producto
            WHERE id_producto = ?
            """,
            (id_producto,)
        )

        conexion.execute(
            """
            DELETE FROM pos_adicionales_producto
            WHERE id_producto = ?
            """,
            (id_producto,)
        )

        conexion.executemany(
            """
            INSERT INTO pos_ingredientes_producto
                (id_producto, ingrediente)
            VALUES (?, ?)
            """,
            [
                (id_producto, ingrediente)
                for ingrediente in ingredientes
            ]
        )

        conexion.executemany(
            """
            INSERT INTO pos_adicionales_producto
                (id_producto, id_adicional_catalogo)
            VALUES (?, ?)
            """,
            [
                (id_producto, id_adicional)
                for id_adicional in ids
            ]
        )

        conexion.commit()

        return {
            "ok": True,
            "producto": producto[0],
            "ingredientes": ingredientes,
            "ids_adicionales": ids,
            "modificado_por": usuario["usuario"]
        }

    except Exception:
        conexion.rollback()
        raise

    finally:
        conexion.close()
