from typing import Literal


from contextlib import closing
from datetime import date
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, Request, Response

from pydantic import BaseModel, Field

from pos_auth import (
    autenticar_usuario,
    crear_sesion_pos,
    obtener_usuario_sesion_pos,
    revocar_sesion_pos,
)

from database import RUTA_ENTRENAMIENTO, obtener_conexion
from pos_entrenamiento_db import clientes_activos, consultar_catalogo_entrenamiento
from pos_menu_entrenamiento import personalizacion_menu, variante_menu
from pos_pedidos import PedidoPos, calcular_pedido_pos, consultar_opciones_producto
from productos import obtener_productos
from pos_caja_diaria import (
    Caja, alertas_cierre, caja_diaria_activa, estado_cajas, exigir_caja_diaria,
    historial_caja, historial_eventos, registrar_operacion,
)
from pos_clientes import (
    AltaCliente, PagoCliente, abonar_cliente, alta_cliente, buscar_clientes, corregir_abono,
    ficha_cliente, prever_abono,
)
from pos_seguimiento import AltaPedido, TransicionPedido, alta_pedido, cambiar_estado_pedido, listar_seguimiento
from pos_envios import MovimientoReparto, registrar_fondo_reparto
from pos_cobros import (
    RendicionEntrada, registrar_rendicion,
    AbonoEntrada, PagoPos, Centavos, CierreEntrada, DevolucionEntrada, ReversionEntrada,
    SolicitudContable, TransferenciaEntrada,
)
from pos_contabilidad import calcular_periodo, corte_contable, etapa_contable_activa, fecha_local
from pos_compras_caja import CompraCajaEntrada, ReversoCompraCaja, listar_compras_caja, operar_compra
from pos_puente import consultar_puente_ficticio
from pos_saldo_unificado import (
    PagoDeuda, ValidarReposicion, pagar_deuda, resumen as resumen_unificado, validar_reposicion,
    ReversoDeuda, revertir_deuda, CierreUnificado, cerrar_unificado, conciliacion as conciliacion_unificada,
)
from pos_simulacion import (
    AnulacionSimuladaEntrada,
    VentaSimuladaEntrada,
    abonar_venta_simulada,
    cerrar_periodo_simulado,
    consultar_cierre_simulado,
    consultar_cajas_simuladas,
    consultar_historial_simulado,
    consultar_venta,
    ConversionPedidoEntrada, convertir_pedido_simulado, cotizar_conversion,
    consultar_movimientos_simulados,
    registrar_venta_simulada,
    revertir_venta_simulada,
    transferir_simulado,
    transaccion_simulacion,
)

router = APIRouter(prefix="/pos-api", tags=["POS - Sesiones"])

COOKIE_ADMIN = "abadion_pos_admin"
COOKIE_VENTAS = "abadion_pos_ventas"


def cookies_pos(request):
    return getattr(request.app.state, "cookies_pos", (COOKIE_ADMIN, COOKIE_VENTAS))


class LoginEntrada(BaseModel):
    usuario: str = Field(min_length=1, max_length=40)
    contrasena: str = Field(min_length=1, max_length=256)


class PrecioNuevoEntrada(BaseModel):
    precio_nuevo: float = Field(
        gt=0,
        le=100_000_000,
        allow_inf_nan=False
    )


class PrecioAdicionalEntrada(BaseModel):
    precio_nuevo: int = Field(
        ge=0,
        le=100_000_000,
        strict=True
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


def evitar_cache_pos(response: Response):
    response.headers["Cache-Control"] = "no-store"


def exigir_administrador_pos(request: Request) -> dict:
    cookie_admin, cookie_ventas = cookies_pos(request)
    token_admin = request.cookies.get(cookie_admin)

    if token_admin:
        usuario = obtener_usuario_sesion_pos(token_admin)

        if usuario is not None and usuario["rol"] == "admin":
            return usuario

    token_ventas = request.cookies.get(cookie_ventas)

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
    cookie_admin, cookie_ventas = cookies_pos(request)
    nombre_cookie = cookie_admin if es_admin else cookie_ventas
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


def exigir_usuario_pos(request: Request):
    for nombre_cookie, rol in zip(cookies_pos(request), ("admin", "ventas")):
        token = request.cookies.get(nombre_cookie)

        if not token:
            continue

        usuario = obtener_usuario_sesion_pos(token)

        if usuario is not None and usuario["rol"] == rol:
            return usuario

    raise HTTPException(
        status_code=401,
        detail="No hay una sesión válida."
    )


@router.get("/yo", dependencies=[Depends(evitar_cache_pos)])
def usuario_actual(usuario: dict = Depends(exigir_usuario_pos)):
    return {"ok": True, "usuario": usuario}


@router.post("/pedidos/validar", dependencies=[Depends(comprobar_origen), Depends(exigir_usuario_pos)])
def validar_pedido_pos(pedido: PedidoPos, advertir_faltantes: bool = False):
    if advertir_faltantes:
        with transaccion_simulacion() as db:
            return {"ok": True, **calcular_pedido_pos(db, pedido, advertir_faltantes=True)}
    conexion = obtener_conexion()
    try:
        conexion.execute("PRAGMA query_only = ON")
        conexion.execute("BEGIN")
        return {"ok": True, **calcular_pedido_pos(conexion, pedido)}
    finally:
        conexion.close()


@router.get("/simulacion/estado", dependencies=[Depends(evitar_cache_pos)])
def estado_simulacion_pos():
    with transaccion_simulacion() as db:
        estado = {"ok": True, "simulacion": True}
        from pos_saldo_unificado import existe
        if existe(db):
            estado["saldo_unificado"] = True
        if caja_diaria_activa(db):
            estado["caja_diaria"] = True
        if etapa_contable_activa(db):
            estado["contabilidad"] = True
        if RUTA_ENTRENAMIENTO.get() is not None and clientes_activos(db):
            estado["clientes"] = True
        return estado


def exigir_simulacion_activa():
    with transaccion_simulacion():
        pass


def comprobar_usuario_simulacion(id_esperado, usuario):
    if id_esperado is not None and id_esperado != usuario["id_usuario"]:
        raise HTTPException(409, {
            "codigo": "SESION_CAMBIADA",
            "mensaje": "La sesión cambió. Iniciá sesión con la cuenta que confirmó la operación.",
        })


class AperturaCajaEntrada(SolicitudContable):
    fecha: date
    inicial_centavos: int = Field(strict=True, ge=0, le=10**13)


class JornadaCajaEntrada(SolicitudContable):
    id_jornada: int = Field(strict=True, gt=0, le=2**63 - 1)


class ArqueoCajaEntrada(JornadaCajaEntrada):
    revision_efectivo: int = Field(strict=True, gt=0, le=2**63 - 1)
    contado_centavos: int = Field(strict=True, ge=0, le=10**13)
    motivo: str | None = Field(default=None, min_length=1, max_length=300)


class CierreCajaEntrada(JornadaCajaEntrada):
    id_arqueo: int = Field(strict=True, gt=0, le=2**63 - 1)


class MovimientoCajaEntrada(JornadaCajaEntrada, ReversionEntrada):
    tipo: Literal["gasto", "retiro", "aporte"]
    importe_centavos: Centavos


diario = APIRouter(prefix="/simulacion/caja-diaria", dependencies=[Depends(exigir_simulacion_activa)])


@diario.get("", dependencies=[Depends(evitar_cache_pos)])
def consultar_caja_diaria(usuario: dict = Depends(exigir_usuario_pos)):
    with transaccion_simulacion() as db:
        exigir_caja_diaria(db)
        return estado_cajas(db)


@diario.get("/{caja}/historial", dependencies=[Depends(evitar_cache_pos)])
def consultar_historial_caja_diaria(
    caja: Caja,
    antes_de: int = Query(default=2**63 - 1, gt=0, le=2**63 - 1),
    limite: int = Query(default=20, ge=1, le=50),
    usuario: dict = Depends(exigir_usuario_pos),
):
    with transaccion_simulacion() as db:
        exigir_caja_diaria(db)
        return historial_caja(db, caja, antes_de, limite)


@diario.get("/alertas", dependencies=[Depends(evitar_cache_pos)])
def consultar_alertas_diarias(
    antes_de: int = Query(default=2**63 - 1, gt=0, le=2**63 - 1),
    limite: int = Query(default=20, ge=1, le=50),
    usuario: dict = Depends(exigir_administrador_pos),
):
    with transaccion_simulacion() as db:
        exigir_caja_diaria(db)
        return alertas_cierre(db, antes_de, limite)


@diario.get("/{caja}/historial/{id_jornada}", dependencies=[Depends(evitar_cache_pos)])
def consultar_eventos_caja_diaria(
    caja: Caja,
    id_jornada: int = Path(gt=0, le=2**63 - 1),
    antes_de: int = Query(default=2**63 - 1, gt=0, le=2**63 - 1),
    limite: int = Query(default=20, ge=1, le=50),
    usuario: dict = Depends(exigir_usuario_pos),
):
    with transaccion_simulacion() as db:
        exigir_caja_diaria(db)
        return historial_eventos(db, caja, id_jornada, antes_de, limite)


def operar_caja_diaria(caja, tipo, datos, usuario, id_esperado):
    comprobar_usuario_simulacion(id_esperado, usuario)
    with transaccion_simulacion(escritura=True) as db:
        exigir_caja_diaria(db)
        return registrar_operacion(db, caja, tipo, datos, usuario)


@diario.post("/{caja}/apertura", dependencies=[Depends(comprobar_origen)])
def abrir_caja_diaria(
    caja: Caja, datos: AperturaCajaEntrada, usuario: dict = Depends(exigir_usuario_pos),
    x_pos_usuario: int | None = Header(default=None),
):
    return operar_caja_diaria(caja, "apertura", datos, usuario, x_pos_usuario)


@diario.post("/{caja}/arqueo", dependencies=[Depends(comprobar_origen)])
def arquear_caja_diaria(
    caja: Caja, datos: ArqueoCajaEntrada, usuario: dict = Depends(exigir_usuario_pos),
    x_pos_usuario: int | None = Header(default=None),
):
    return operar_caja_diaria(caja, "arqueo", datos, usuario, x_pos_usuario)


@diario.post("/{caja}/cierre", dependencies=[Depends(comprobar_origen)])
def cerrar_caja_diaria(
    caja: Caja, datos: CierreCajaEntrada, usuario: dict = Depends(exigir_usuario_pos),
    x_pos_usuario: int | None = Header(default=None),
):
    return operar_caja_diaria(caja, "cierre", datos, usuario, x_pos_usuario)


@diario.post("/{caja}/movimientos", dependencies=[Depends(comprobar_origen)])
def mover_caja_diaria(
    caja: Caja, datos: MovimientoCajaEntrada, usuario: dict = Depends(exigir_usuario_pos),
    x_pos_usuario: int | None = Header(default=None),
):
    if datos.tipo == "gasto" and usuario["rol"] != "admin":
        raise HTTPException(403, "Administración debe registrar los gastos.")
    return operar_caja_diaria(caja, datos.tipo, datos, usuario, x_pos_usuario)


router.include_router(diario)


compras_caja = APIRouter(prefix="/simulacion/compras", dependencies=[
    Depends(exigir_simulacion_activa),
])


@compras_caja.get("", dependencies=[Depends(evitar_cache_pos)])
def consultar_compras_caja(antes_de: int = Query(default=2**63 - 1, gt=0, le=2**63 - 1),
                         limite: int = Query(default=20, ge=1, le=50),
                         usuario=Depends(exigir_administrador_pos)):
    with transaccion_simulacion() as db:
        if not etapa_contable_activa(db):
            raise HTTPException(404, "Se requiere una base ficticia con contabilidad integrada.")
        return listar_compras_caja(db, antes_de, limite)


@compras_caja.post("", dependencies=[Depends(comprobar_origen)])
def crear_compra_caja(datos: CompraCajaEntrada, usuario=Depends(exigir_administrador_pos),
                      x_pos_usuario: int | None = Header(default=None)):
    comprobar_usuario_simulacion(x_pos_usuario, usuario)
    with transaccion_simulacion(escritura=True) as db:
        return operar_compra(db, "alta", datos, usuario)


@compras_caja.post("/{id_compra}/{evento}", dependencies=[Depends(comprobar_origen)])
def revertir_compra_caja(id_compra: int, evento: Literal["anulacion", "devolucion"],
                        datos: ReversoCompraCaja, usuario=Depends(exigir_administrador_pos),
                        x_pos_usuario: int | None = Header(default=None)):
    comprobar_usuario_simulacion(x_pos_usuario, usuario)
    with transaccion_simulacion(escritura=True) as db:
        return operar_compra(db, evento, datos, usuario, id_compra)


router.include_router(compras_caja)


clientes = APIRouter(prefix="/simulacion/clientes", dependencies=[Depends(exigir_simulacion_activa),
                                                                 Depends(evitar_cache_pos)])


@clientes.get("")
def listar_clientes(q: str = Query(default="", max_length=300), usuario=Depends(exigir_usuario_pos)):
    return {"clientes": buscar_clientes(q)}


@clientes.post("", dependencies=[Depends(comprobar_origen)])
def crear_cliente(datos: AltaCliente, usuario=Depends(exigir_usuario_pos),
                  x_pos_usuario: int | None = Header(default=None)):
    comprobar_usuario_simulacion(x_pos_usuario, usuario)
    return alta_cliente(datos, usuario)


@clientes.get("/{id_cliente}")
def ver_cliente(id_cliente: int = Path(gt=0, le=2**53 - 1), usuario=Depends(exigir_usuario_pos)):
    return ficha_cliente(id_cliente)


@clientes.post("/{id_cliente}/abonos/vista-previa", dependencies=[Depends(comprobar_origen)])
def vista_previa_abono(datos: PagoPos, id_cliente: int = Path(gt=0, le=2**53 - 1),
                      usuario=Depends(exigir_usuario_pos)):
    return prever_abono(id_cliente, datos)


@clientes.post("/{id_cliente}/abonos", dependencies=[Depends(comprobar_origen)])
def registrar_abono_cliente(datos: PagoCliente, id_cliente: int = Path(gt=0, le=2**53 - 1),
                            usuario=Depends(exigir_usuario_pos), x_pos_usuario: int | None = Header(default=None)):
    comprobar_usuario_simulacion(x_pos_usuario, usuario)
    return abonar_cliente(id_cliente, datos, usuario)


@clientes.post("/{id_cliente}/abonos/{uuid_abono}/correccion", dependencies=[Depends(comprobar_origen)])
def corregir_abono_cliente(uuid_abono: UUID, datos: ReversionEntrada, id_cliente: int = Path(gt=0, le=2**53 - 1),
                           usuario=Depends(exigir_administrador_pos), x_pos_usuario: int | None = Header(default=None)):
    comprobar_usuario_simulacion(x_pos_usuario, usuario)
    return corregir_abono(id_cliente, str(uuid_abono), datos, usuario)


router.include_router(clientes)


@router.post("/simulacion/ventas", dependencies=[Depends(comprobar_origen), Depends(exigir_simulacion_activa)])
def simular_venta_pos(
    venta: VentaSimuladaEntrada,
    usuario: dict = Depends(exigir_usuario_pos),
    x_pos_usuario: int | None = Header(default=None),
):
    comprobar_usuario_simulacion(x_pos_usuario, usuario)
    return {"ok": True, "simulacion": True, **registrar_venta_simulada(venta, usuario)}


@router.post("/simulacion/pedidos", dependencies=[Depends(comprobar_origen), Depends(exigir_simulacion_activa)])
def guardar_pedido_pos(
    pedido: AltaPedido, usuario: dict = Depends(exigir_usuario_pos),
    x_pos_usuario: int | None = Header(default=None),
):
    comprobar_usuario_simulacion(x_pos_usuario, usuario)
    with transaccion_simulacion(escritura=True) as db:
        return alta_pedido(db, pedido, usuario["id_usuario"])


@router.get("/simulacion/pedidos/{id_pedido}/cotizacion", dependencies=[
    Depends(exigir_simulacion_activa), Depends(evitar_cache_pos), Depends(exigir_usuario_pos),
])
def cotizar_pedido_pos(id_pedido: int = Path(gt=0, le=2**53 - 1)):
    with transaccion_simulacion() as db:
        return cotizar_conversion(db, id_pedido)


@router.post("/simulacion/pedidos/{id_pedido}/venta", dependencies=[
    Depends(comprobar_origen), Depends(exigir_simulacion_activa),
])
def convertir_pedido_pos(
    datos: ConversionPedidoEntrada, id_pedido: int = Path(gt=0, le=2**53 - 1),
    usuario: dict = Depends(exigir_usuario_pos), x_pos_usuario: int | None = Header(default=None),
):
    comprobar_usuario_simulacion(x_pos_usuario, usuario)
    return {"ok": True, "simulacion": True, **convertir_pedido_simulado(id_pedido, datos, usuario)}


@router.get("/simulacion/pedidos", dependencies=[
    Depends(exigir_simulacion_activa), Depends(evitar_cache_pos),
])
def listar_pedidos_pos(
    finalizados: bool = False,
    antes_de: int | None = Query(default=None, gt=0, le=2**63 - 1),
    limite: int = Query(default=25, ge=1, le=100),
    usuario: dict = Depends(exigir_usuario_pos),
):
    with transaccion_simulacion() as db:
        return listar_seguimiento(db, finalizados=finalizados, antes_de=antes_de, limite=limite)


@router.post("/simulacion/pedidos/{id_pedido}/estado", dependencies=[
    Depends(comprobar_origen), Depends(exigir_simulacion_activa),
])
def cambiar_pedido_pos(
    cambio: TransicionPedido,
    id_pedido: int = Path(gt=0, le=2**63 - 1),
    usuario: dict = Depends(exigir_usuario_pos),
    x_pos_usuario: int | None = Header(default=None),
):
    comprobar_usuario_simulacion(x_pos_usuario, usuario)
    with transaccion_simulacion(escritura=True) as db:
        return cambiar_estado_pedido(db, id_pedido, cambio, usuario)


@router.get("/simulacion/ventas", dependencies=[Depends(exigir_simulacion_activa), Depends(evitar_cache_pos)])
def consultar_historial_pos(
    antes_de: int | None = Query(default=None, gt=0, le=2**63 - 1),
    limite: int = Query(default=25, ge=1, le=100),
    usuario: dict = Depends(exigir_usuario_pos),
):
    return {"ok": True, "simulacion": True, **consultar_historial_simulado(usuario, antes_de, limite)}


@router.post("/simulacion/ventas/{id_venta}/anulacion", dependencies=[Depends(comprobar_origen), Depends(exigir_simulacion_activa)])
def anular_venta_pos(
    anulacion: AnulacionSimuladaEntrada,
    id_venta: int = Path(gt=0, le=2**63 - 1),
    usuario: dict = Depends(exigir_administrador_pos),
    x_pos_usuario: int | None = Header(default=None),
):
    comprobar_usuario_simulacion(x_pos_usuario, usuario)
    return {"ok": True, "simulacion": True, **revertir_venta_simulada(id_venta, anulacion, usuario, tipo="anulacion")}


@router.post("/simulacion/ventas/{id_venta}/abonos", dependencies=[Depends(comprobar_origen), Depends(exigir_simulacion_activa)])
def abonar_venta_pos(
    abono: AbonoEntrada,
    id_venta: int = Path(gt=0, le=2**63 - 1),
    usuario: dict = Depends(exigir_usuario_pos),
    x_pos_usuario: int | None = Header(default=None),
):
    comprobar_usuario_simulacion(x_pos_usuario, usuario)
    return {"ok": True, "simulacion": True, **abonar_venta_simulada(id_venta, abono, usuario)}


@router.post("/simulacion/ventas/{id_venta}/devoluciones", dependencies=[Depends(comprobar_origen), Depends(exigir_simulacion_activa)])
def devolver_venta_pos(
    devolucion: DevolucionEntrada,
    id_venta: int = Path(gt=0, le=2**63 - 1),
    usuario: dict = Depends(exigir_administrador_pos),
    x_pos_usuario: int | None = Header(default=None),
):
    comprobar_usuario_simulacion(x_pos_usuario, usuario)
    return {"ok": True, "simulacion": True, **revertir_venta_simulada(id_venta, devolucion, usuario, tipo="devolucion")}


@router.post(
    "/simulacion/ventas/{id_venta}/fondos-reparto/{tipo}",
    dependencies=[Depends(comprobar_origen), Depends(exigir_simulacion_activa)],
)
def operar_fondo_reparto_pos(
    movimiento: MovimientoReparto,
    tipo: Literal["recepcion", "liquidacion", "reembolso", "directo"],
    id_venta: int = Path(gt=0, le=2**63 - 1),
    usuario: dict = Depends(exigir_administrador_pos),
    x_pos_usuario: int | None = Header(default=None),
):
    comprobar_usuario_simulacion(x_pos_usuario, usuario)
    with transaccion_simulacion(escritura=True) as db:
        pedido, anulada = consultar_venta(db, id_venta, usuario)
        return {"ok": True, "simulacion": True, **registrar_fondo_reparto(
            db, id_venta, pedido, movimiento, usuario, tipo=tipo, anulada=anulada,
        )}


@router.post(
    "/simulacion/cobros/{id_cobro}/rendiciones",
    dependencies=[Depends(comprobar_origen), Depends(exigir_simulacion_activa)],
)
def rendir_efectivo_pos(
    rendicion: RendicionEntrada,
    id_cobro: int = Path(gt=0, le=2**63 - 1),
    usuario: dict = Depends(exigir_administrador_pos),
    x_pos_usuario: int | None = Header(default=None),
):
    comprobar_usuario_simulacion(x_pos_usuario, usuario)
    with transaccion_simulacion(escritura=True) as db:
        return {"ok": True, "simulacion": True, **registrar_rendicion(db, id_cobro, rendicion, usuario)}


@router.post("/simulacion/cajas/transferencias", dependencies=[Depends(comprobar_origen), Depends(exigir_simulacion_activa)])
def transferir_pos(
    transferencia: TransferenciaEntrada,
    usuario: dict = Depends(exigir_administrador_pos),
    x_pos_usuario: int | None = Header(default=None),
):
    comprobar_usuario_simulacion(x_pos_usuario, usuario)
    return {"ok": True, "simulacion": True, **transferir_simulado(transferencia, usuario)}


@router.post("/simulacion/cierres", dependencies=[Depends(comprobar_origen), Depends(exigir_simulacion_activa)])
def cerrar_periodo_pos(
    cierre: CierreEntrada,
    usuario: dict = Depends(exigir_administrador_pos),
    x_pos_usuario: int | None = Header(default=None),
):
    comprobar_usuario_simulacion(x_pos_usuario, usuario)
    return {"ok": True, "simulacion": True, **cerrar_periodo_simulado(cierre, usuario)}


@router.get("/simulacion/cierres/{periodo}", dependencies=[
    Depends(exigir_simulacion_activa), Depends(exigir_administrador_pos), Depends(evitar_cache_pos),
])
def consultar_cierre_pos(periodo: int = Path(gt=0, le=2**63 - 1)):
    return {"ok": True, "simulacion": True, **consultar_cierre_simulado(periodo)}


@router.get("/simulacion/cajas", dependencies=[Depends(exigir_simulacion_activa), Depends(exigir_administrador_pos), Depends(evitar_cache_pos)])
def consultar_cajas_pos():
    return {"ok": True, "simulacion": True, **consultar_cajas_simuladas()}


@router.get("/simulacion/contabilidad", dependencies=[
    Depends(exigir_administrador_pos), Depends(evitar_cache_pos),
])
def contabilidad_pos(desde: date | None = None, hasta: date | None = None):
    with transaccion_simulacion() as db:
        if not etapa_contable_activa(db):
            raise HTTPException(404, "Prepará una copia ficticia para la etapa 7.")
        hoy = fecha_local()
        inicio = desde.isoformat() if desde else hoy
        fin = hasta.isoformat() if hasta else hoy
        if inicio > fin or fin > hoy or fin < corte_contable(db)[0]:
            raise HTTPException(422, "Elegí un período válido que incluya fechas de la etapa 7.")
        return {"ok": True, **calcular_periodo(db, inicio, fin)}


@router.get("/simulacion/conciliacion", dependencies=[
    Depends(exigir_simulacion_activa), Depends(exigir_administrador_pos), Depends(evitar_cache_pos),
])
def conciliacion_pos():
    return consultar_puente_ficticio()


@router.get('/simulacion/conciliacion-financiera', dependencies=[
    Depends(exigir_simulacion_activa), Depends(exigir_administrador_pos), Depends(evitar_cache_pos),
])
def consultar_contrato_financiero():
    from pos_conciliacion_financiera import informe
    with transaccion_simulacion() as db:
        return {'ok': True, 'simulacion': True, **informe(db)}


@router.get("/simulacion/cajas/movimientos", dependencies=[Depends(exigir_simulacion_activa), Depends(exigir_administrador_pos), Depends(evitar_cache_pos)])
def consultar_movimientos_pos(
    caja: Literal["comidas", "bebidas_postres"],
    antes_de: int | None = Query(default=None, gt=0, le=2**63 - 1),
    limite: int = Query(default=25, ge=1, le=100),
):
    return {"ok": True, "simulacion": True, **consultar_movimientos_simulados(caja, antes_de, limite)}


@router.post("/logout")
def cerrar_sesion(request: Request, response: Response):
    comprobar_origen(request)

    for nombre_cookie in cookies_pos(request):
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


@router.get("/catalogo/productos", dependencies=[Depends(evitar_cache_pos)])
def consultar_productos_pos(request: Request):
    try:
        with transaccion_simulacion():
            pass
    except HTTPException as error:
        if error.status_code != 404:
            raise
        exigir_usuario_pos(request)
    productos = obtener_productos()
    if RUTA_ENTRENAMIENTO.get() is not None:
        with closing(obtener_conexion()) as db:
            opciones = consultar_catalogo_entrenamiento(db)
            from pos_saldo_unificado import existe
            if existe(db):
                bloqueadas = {p for p, in db.execute("SELECT p.id_producto FROM productos p LEFT JOIN pos_stock_progresivo s USING(id_producto) WHERE lower(trim(p.categoria))='bebidas' AND COALESCE(s.habilitado,0)=0")}
                for p in productos:
                    if p['id_producto'] in bloqueadas or (p['categoria'].strip().lower() in ('postres','bebidas') and p['stock'] <= 0):
                        anterior = opciones.get(p['id_producto'], ('disponible', None))
                        opciones[p['id_producto']] = ('sin_stock', anterior[1])
        productos = [
            dict(producto, estado_entrenamiento=estado, promo_postres_chicos=grupo is not None,
                 **({"familia_menu": familia, "variante_menu": variante} if familia else {}))
            for producto in productos
            for estado, grupo in [opciones.get(producto["id_producto"], ("disponible", None))]
            if estado != "fuera_menu"
            for familia, variante in [variante_menu(producto["nombre"], producto["categoria"])]
        ]
    return {"ok": True, "productos": productos}


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
            SELECT nombre, categoria
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

        ingredientes, adicionales = consultar_opciones_producto(conexion, id_producto)
        menu = {"menu": personalizacion_menu(*producto)} if RUTA_ENTRENAMIENTO.get() is not None else {}

        return {
            "ok": True,
            "id_producto": id_producto,
            "producto": producto[0],
            "ingredientes": ingredientes,
            "adicionales": adicionales,
            **menu,
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


@router.patch("/admin/adicionales/{id_adicional}/precio")
def actualizar_precio_adicional_pos(
    id_adicional: int,
    datos: PrecioAdicionalEntrada,
    request: Request,
    usuario: dict = Depends(exigir_administrador_pos)
):
    comprobar_origen(request)

    conexion = obtener_conexion()

    try:
        conexion.execute("BEGIN IMMEDIATE")

        adicional = conexion.execute(
            """
            SELECT nombre, precio_venta
            FROM adicionales_catalogo
            WHERE id_adicional_catalogo = ?
              AND activo = 1
            """,
            (id_adicional,)
        ).fetchone()

        if adicional is None:
            raise HTTPException(
                status_code=404,
                detail="Adicional no encontrado o inactivo."
            )

        nombre, precio_anterior = adicional
        precio_nuevo = datos.precio_nuevo

        if precio_anterior == precio_nuevo:
            conexion.rollback()

            return {
                "ok": True,
                "actualizado": False,
                "mensaje": "El precio no cambió."
            }

        conexion.execute(
            """
            UPDATE adicionales_catalogo
            SET precio_venta = ?,
                fecha_actualizacion = CURRENT_TIMESTAMP
            WHERE id_adicional_catalogo = ?
            """,
            (precio_nuevo, id_adicional)
        )

        conexion.execute(
            """
            INSERT INTO historial_precios_adicionales_pos (
                id_adicional_catalogo,
                id_usuario,
                precio_anterior,
                precio_nuevo
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                id_adicional,
                usuario["id_usuario"],
                precio_anterior,
                precio_nuevo
            )
        )

        conexion.commit()

        return {
            "ok": True,
            "actualizado": True,
            "adicional": nombre,
            "precio_anterior": precio_anterior,
            "precio_nuevo": precio_nuevo,
            "modificado_por": usuario["usuario"]
        }

    except Exception:
        conexion.rollback()
        raise

    finally:
        conexion.close()


@router.get("/simulacion/saldo-unificado", dependencies=[Depends(evitar_cache_pos)])
def consultar_saldo_unificado(usuario: dict = Depends(exigir_usuario_pos)):
    with transaccion_simulacion() as db:
        return resumen_unificado(db)


@router.post("/simulacion/saldo-unificado/deudas/{numero}/pago", dependencies=[Depends(comprobar_origen)])
def pagar_deuda_apertura(numero: int, datos: PagoDeuda, usuario: dict = Depends(exigir_administrador_pos),
                        x_pos_usuario: int | None = Header(default=None)):
    comprobar_usuario_simulacion(x_pos_usuario, usuario)
    with transaccion_simulacion(escritura=True) as db:
        return pagar_deuda(db, numero, datos, usuario)


@router.post("/simulacion/saldo-unificado/bebidas/{producto}/validar", dependencies=[Depends(comprobar_origen)])
def validar_stock_bebida(producto: int, datos: ValidarReposicion, usuario: dict = Depends(exigir_administrador_pos),
                       x_pos_usuario: int | None = Header(default=None)):
    comprobar_usuario_simulacion(x_pos_usuario, usuario)
    with transaccion_simulacion(escritura=True) as db:
        return validar_reposicion(db, producto, datos, usuario)


@router.post("/simulacion/saldo-unificado/pagos/{numero}/reverso", dependencies=[Depends(comprobar_origen)])
def reversar_pago_apertura(numero: int, datos: ReversoDeuda, usuario: dict = Depends(exigir_administrador_pos),
                          x_pos_usuario: int | None = Header(default=None)):
    comprobar_usuario_simulacion(x_pos_usuario, usuario)
    with transaccion_simulacion(escritura=True) as db:
        return revertir_deuda(db, numero, datos, usuario)


@router.get("/simulacion/saldo-unificado/conciliacion", dependencies=[Depends(evitar_cache_pos)])
def consultar_conciliacion_unificada(usuario: dict = Depends(exigir_administrador_pos)):
    with transaccion_simulacion() as db:
        return conciliacion_unificada(db)


@router.post("/simulacion/saldo-unificado/cierres", dependencies=[Depends(comprobar_origen)])
def cierre_saldo_unificado(datos: CierreUnificado, usuario: dict = Depends(exigir_administrador_pos),
                          x_pos_usuario: int | None = Header(default=None)):
    comprobar_usuario_simulacion(x_pos_usuario, usuario)
    with transaccion_simulacion(escritura=True) as db:
        return cerrar_unificado(db, datos, usuario)
