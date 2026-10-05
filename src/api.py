from datetime import datetime

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from acciones import ejecutar_accion
from ajustes_stock import registrar_inventario_fisico
from backups import crear_backup_diario

from caja import (
    obtener_estado_caja,
    obtener_caja_seccion,
    recaudado_por_categoria,
)
from catalogo import asegurar_productos_catalogo

from comandos import procesar_comando
from database import inicializar_base_de_datos

from cierres import (
    registrar_cierre_semanal,
    registrar_cierre_mensual,
    obtener_cierres_semanales,
    obtener_cierres_mensuales
)

from compras import (
    registrar_compra,
    anular_compra
)

from diezmo import (
    estado_diezmo_mes,
    registrar_reserva_diezmo,
    registrar_entrega_diezmo
)

from gastos import (
    registrar_gasto,
    anular_gasto
)

from idempotencia import (
    finalizar_procesamiento,
    iniciar_procesamiento,
)

from movimientos_caja import (
    registrar_aporte,
    registrar_retiro,
    anular_movimiento_caja
)

from productos import obtener_productos

from reportes import (
    resumen_por_periodo,
    resumen_semana_actual,
    resumen_mes_actual
)

from ventas import (
    registrar_venta,
    anular_venta
)


# ============================================================
# APLICACIÓN FASTAPI
# ============================================================

app = FastAPI(
    title="Lo de Clau API",
    version="1.0.0"
)


# ============================================================
# CÓDIGOS DE ERROR DEL BACKEND -> HTTP
# ============================================================

CODIGOS_HTTP = {

    # 404 - Recurso inexistente
    "PRODUCTO_NO_ENCONTRADO": 404,
    "VENTA_NO_ENCONTRADA": 404,
    "COMPRA_NO_ENCONTRADA": 404,
    "GASTO_NO_ENCONTRADO": 404,
    "MOVIMIENTO_CAJA_NO_ENCONTRADO": 404,
    "OPERACION_VENTA_NO_ENCONTRADA": 404,

    # 409 - Conflictos con el estado actual
    "STOCK_INSUFICIENTE": 409,
    "VENTA_YA_ANULADA": 409,
    "COMPRA_YA_ANULADA": 409,
    "STOCK_INSUFICIENTE_PARA_ANULAR_COMPRA": 409,
    "GASTO_YA_ANULADO": 409,
    "MOVIMIENTO_CAJA_YA_ANULADO": 409,
    "OPERACION_VENTA_YA_ANULADA": 409,
    "OPERACION_VENTA_PARCIALMENTE_ANULADA": 409,
    "MENSAJE_EN_PROCESO": 409,
    "MENSAJE_REQUIERE_REVISION": 409,

    "CIERRE_SEMANAL_EXISTENTE": 409,
    "CIERRE_MENSUAL_EXISTENTE": 409,
    "MES_NO_TERMINADO": 409,

    # 400 - Datos rechazados por el backend
    "DATOS_INVALIDOS": 400,
    "FECHAS_INVALIDAS": 400,
    "ANIO_INVALIDO": 400,
    "MES_INVALIDO": 400,

    # 500 - Error interno de base de datos
    "ERROR_BASE_DATOS": 500,

    # Diezmo
    "ANIO_INVALIDO": 400,
    "MES_INVALIDO": 400,
    "TIPO_MOVIMIENTO_INVALIDO": 400,
    "MONTO_INVALIDO": 400,
    "DESCRIPCION_INVALIDA": 400,
    "FECHA_INVALIDA": 400,

    "MES_FUTURO": 409,
    "MES_NO_CERRADO": 409,
    "RESERVA_EXCEDE_PENDIENTE": 409,
    "ENTREGA_EXCEDE_PENDIENTE": 409,
}


# ============================================================
# RESPUESTA HTTP ESTANDARIZADA
# ============================================================

def responder_resultado(
    resultado,
    codigo_exito=200
):
    """
    Convierte los resultados del backend en respuestas HTTP.

    Ejemplos:
    - operación exitosa -> 200 o 201
    - recurso inexistente -> 404
    - conflicto -> 409
    - datos inválidos -> 400
    - error de base de datos -> 500
    """

    if resultado.get("ok") is True:

        return JSONResponse(
            status_code=codigo_exito,
            content=resultado
        )

    codigo = resultado.get("codigo")

    status_code = CODIGOS_HTTP.get(
        codigo,
        400
    )

    return JSONResponse(
        status_code=status_code,
        content=resultado
    )


# ============================================================
# MODELOS DE ENTRADA
# ============================================================

class VentaEntrada(BaseModel):
    id_producto: int = Field(gt=0)
    cantidad: int = Field(gt=0)
    precio_unitario: float = Field(gt=0)


class CompraEntrada(BaseModel):
    id_producto: int = Field(gt=0)
    cantidad: int = Field(gt=0)
    precio_unitario: float = Field(gt=0)


class GastoEntrada(BaseModel):
    categoria: str = Field(min_length=1)
    descripcion: str = Field(min_length=1)
    valor: float = Field(gt=0)


class InventarioEntrada(BaseModel):
    id_producto: int = Field(gt=0)
    cantidad_real: int = Field(ge=0)


class MovimientoCajaEntrada(BaseModel):
    descripcion: str = Field(min_length=1)
    monto: float = Field(gt=0)


class DiezmoMovimientoEntrada(BaseModel):
    anio: int = Field(gt=0)
    mes: int = Field(ge=1, le=12)
    monto: float = Field(gt=0)
    descripcion: str | None = None


class AnulacionEntrada(BaseModel):
    motivo: str = Field(min_length=1)


class CierreSemanalEntrada(BaseModel):
    fecha_desde: str
    fecha_hasta: str


class CierreMensualEntrada(BaseModel):
    anio: int = Field(gt=0)
    mes: int = Field(ge=1, le=12)


class ComandoEntrada(BaseModel):
    mensaje: str = Field(min_length=1)
    id_mensaje: str | None = Field(
        default=None,
        min_length=1
    )
    canal: str = Field(
        default="api",
        min_length=1
    )
    usuario_id: str | None = None
    usuario_numero: str | None = None
    grupo_id: str | None = None


class AccionEntrada(BaseModel):
    accion: str = Field(min_length=1)
    datos: dict = Field(default_factory=dict)


# ============================================================
# INICIALIZACIÓN / MIGRACIONES
# ============================================================

@app.on_event("startup")
def preparar_base_de_datos():
    inicializar_base_de_datos()
    resultado_catalogo = asegurar_productos_catalogo()

    if resultado_catalogo.get("creados"):
        print(
            "Productos nuevos agregados al catálogo:",
            resultado_catalogo["creados"]
        )

    resultado_backup = crear_backup_diario()

    if resultado_backup.get("ok"):
        if resultado_backup.get("creado"):
            print(
                "Backup diario creado:",
                resultado_backup["ruta"]
            )
    else:
        print(
            "ADVERTENCIA: no se pudo crear el backup diario:",
            resultado_backup.get(
                "mensaje",
                resultado_backup.get("codigo")
            )
        )


# ============================================================
# INICIO
# ============================================================

@app.get("/")
def inicio():

    return {
        "mensaje": "API de Lo de Clau funcionando."
    }


# ============================================================
# PRODUCTOS
# ============================================================

@app.get("/productos")
def listar_productos_api():

    productos = obtener_productos()

    return {
        "ok": True,
        "cantidad": len(productos),
        "productos": productos
    }


# ============================================================
# STOCK
# ============================================================

@app.get("/stock")
def consultar_stock_api():

    productos = obtener_productos()

    stock = []

    for producto in productos:

        stock.append({
            "id_producto": producto["id_producto"],
            "producto": producto["nombre"],
            "stock": producto["stock"]
        })

    return {
        "ok": True,
        "cantidad_productos": len(stock),
        "stock": stock
    }


# ============================================================
# VENTAS
# ============================================================

@app.post("/ventas")
def registrar_venta_api(
    venta: VentaEntrada
):

    resultado = registrar_venta(
        id_producto=venta.id_producto,
        cantidad=venta.cantidad,
        precio_unitario=venta.precio_unitario
    )

    return responder_resultado(
        resultado,
        codigo_exito=201
    )


@app.patch("/ventas/{id_venta}/anular")
def anular_venta_api(
    id_venta: int,
    anulacion: AnulacionEntrada
):

    resultado = anular_venta(
        id_venta=id_venta,
        motivo=anulacion.motivo
    )

    return responder_resultado(resultado)


# ============================================================
# COMPRAS
# ============================================================

@app.post("/compras")
def registrar_compra_api(
    compra: CompraEntrada
):

    resultado = registrar_compra(
        id_producto=compra.id_producto,
        cantidad=compra.cantidad,
        precio_unitario=compra.precio_unitario
    )

    return responder_resultado(
        resultado,
        codigo_exito=201
    )


@app.patch("/compras/{id_compra}/anular")
def anular_compra_api(
    id_compra: int,
    anulacion: AnulacionEntrada
):

    resultado = anular_compra(
        id_compra=id_compra,
        motivo=anulacion.motivo
    )

    return responder_resultado(resultado)


# ============================================================
# GASTOS
# ============================================================

@app.post("/gastos")
def registrar_gasto_api(
    gasto: GastoEntrada
):

    resultado = registrar_gasto(
        categoria=gasto.categoria,
        descripcion_gasto=gasto.descripcion,
        valor_final=gasto.valor
    )

    return responder_resultado(
        resultado,
        codigo_exito=201
    )


@app.patch("/gastos/{id_gasto}/anular")
def anular_gasto_api(
    id_gasto: int,
    anulacion: AnulacionEntrada
):

    resultado = anular_gasto(
        id_gasto=id_gasto,
        motivo=anulacion.motivo
    )

    return responder_resultado(resultado)


# ============================================================
# INVENTARIO
# ============================================================

@app.post("/inventario")
def registrar_inventario_api(
    inventario: InventarioEntrada
):

    resultado = registrar_inventario_fisico(
        id_producto=inventario.id_producto,
        cantidad_real=inventario.cantidad_real
    )

    return responder_resultado(resultado)


# ============================================================
# REPORTES
# ============================================================

@app.get("/reportes/hoy")
def reporte_hoy_api():

    fecha_hoy = datetime.now().strftime("%Y-%m-%d")

    return resumen_por_periodo(
        fecha_hoy,
        fecha_hoy
    )


@app.get("/reportes/semana")
def reporte_semana_api():

    return resumen_semana_actual()


@app.get("/reportes/mes")
def reporte_mes_api():

    return resumen_mes_actual()


# ============================================================
# CAJA
# ============================================================

@app.get("/caja")
def consultar_caja_api():

    return obtener_estado_caja()


@app.get("/caja/secciones/{seccion}")
def consultar_caja_seccion_api(
    seccion: str
):
    try:
        return {
            "ok": True,
            "codigo": "CAJA_SECCION",
            "datos": obtener_caja_seccion(
                seccion
            ),
        }
    except ValueError as error:
        return responder_resultado({
            "ok": False,
            "codigo": "SECCION_CAJA_INVALIDA",
            "mensaje": str(error),
        })


@app.get("/recaudado/{categoria}")
def consultar_recaudado_categoria_api(
    categoria: str
):
    try:
        total = recaudado_por_categoria(
            categoria
        )
    except ValueError as error:
        return responder_resultado({
            "ok": False,
            "codigo": "CATEGORIA_RECAUDACION_INVALIDA",
            "mensaje": str(error),
        })

    return {
        "ok": True,
        "codigo": "RECAUDADO_CATEGORIA",
        "categoria": categoria,
        "total": total,
    }


@app.post("/caja/aportes")
def registrar_aporte_api(
    movimiento: MovimientoCajaEntrada
):

    resultado = registrar_aporte(
        descripcion=movimiento.descripcion,
        monto=movimiento.monto
    )

    return responder_resultado(
        resultado,
        codigo_exito=201
    )


@app.post("/caja/retiros")
def registrar_retiro_api(
    movimiento: MovimientoCajaEntrada
):

    resultado = registrar_retiro(
        descripcion=movimiento.descripcion,
        monto=movimiento.monto
    )

    return responder_resultado(
        resultado,
        codigo_exito=201
    )


@app.patch("/caja/movimientos/{id_movimiento}/anular")
def anular_movimiento_caja_api(
    id_movimiento: int,
    anulacion: AnulacionEntrada
):

    resultado = anular_movimiento_caja(
        id_movimiento=id_movimiento,
        motivo=anulacion.motivo
    )

    return responder_resultado(resultado)


# ============================================================
# DIEZMO
# ============================================================

@app.get("/diezmo/{anio}/{mes}")
def consultar_diezmo_api(
    anio: int,
    mes: int
):

    return estado_diezmo_mes(
        anio=anio,
        mes=mes
    )


@app.post("/diezmo/reservas")
def registrar_reserva_diezmo_api(
    movimiento: DiezmoMovimientoEntrada
):

    if movimiento.descripcion:

        resultado = registrar_reserva_diezmo(
            anio=movimiento.anio,
            mes=movimiento.mes,
            monto=movimiento.monto,
            descripcion=movimiento.descripcion
        )

    else:

        resultado = registrar_reserva_diezmo(
            anio=movimiento.anio,
            mes=movimiento.mes,
            monto=movimiento.monto
        )

    return responder_resultado(
        resultado,
        codigo_exito=201
    )


@app.post("/diezmo/entregas")
def registrar_entrega_diezmo_api(
    movimiento: DiezmoMovimientoEntrada
):

    if movimiento.descripcion:

        resultado = registrar_entrega_diezmo(
            anio=movimiento.anio,
            mes=movimiento.mes,
            monto=movimiento.monto,
            descripcion=movimiento.descripcion
        )

    else:

        resultado = registrar_entrega_diezmo(
            anio=movimiento.anio,
            mes=movimiento.mes,
            monto=movimiento.monto
        )

    return responder_resultado(
        resultado,
        codigo_exito=201
    )


# ============================================================
# CIERRES SEMANALES
# ============================================================

@app.post("/cierres/semanales")
def registrar_cierre_semanal_api(
    cierre: CierreSemanalEntrada
):

    resultado = registrar_cierre_semanal(
        fecha_desde=cierre.fecha_desde,
        fecha_hasta=cierre.fecha_hasta
    )

    return responder_resultado(
        resultado,
        codigo_exito=201
    )


@app.get("/cierres/semanales")
def obtener_cierres_semanales_api():

    return {
        "ok": True,
        "cierres": obtener_cierres_semanales()
    }


# ============================================================
# CIERRES MENSUALES
# ============================================================

@app.post("/cierres/mensuales")
def registrar_cierre_mensual_api(
    cierre: CierreMensualEntrada
):

    resultado = registrar_cierre_mensual(
        anio=cierre.anio,
        mes=cierre.mes
    )

    return responder_resultado(
        resultado,
        codigo_exito=201
    )


@app.get("/cierres/mensuales")
def obtener_cierres_mensuales_api():

    return {
        "ok": True,
        "cierres": obtener_cierres_mensuales()
    }

# ============================================================
# COMANDOS PARA WHATSAPP / OTRAS INTERFACES
# ============================================================

@app.post("/comandos")
def procesar_comando_api(
    comando: ComandoEntrada
):

    if comando.id_mensaje:
        reserva = iniciar_procesamiento(
            canal=comando.canal,
            id_externo=comando.id_mensaje,
            mensaje=comando.mensaje,
        )

        if not reserva["ok"]:
            return responder_resultado(reserva)

        if reserva.get("nuevo") is False:
            return responder_resultado(
                reserva["resultado"]
            )

    contexto = {
        "canal": comando.canal,
        "id_mensaje": comando.id_mensaje,
        "usuario_id": comando.usuario_id,
        "usuario_numero": comando.usuario_numero,
        "grupo_id": comando.grupo_id,
    }

    resultado = procesar_comando(
        comando.mensaje,
        contexto=contexto,
    )

    if comando.id_mensaje:
        finalizar_procesamiento(
            canal=comando.canal,
            id_externo=comando.id_mensaje,
            resultado=resultado,
        )

    return responder_resultado(resultado)


# ============================================================
# ACCIONES ESTRUCTURADAS PARA IA / VOZ / INTEGRACIONES
# ============================================================

@app.post("/acciones")
def ejecutar_accion_api(
    solicitud: AccionEntrada
):

    resultado = ejecutar_accion({
        "accion": solicitud.accion,
        "datos": solicitud.datos,
    })

    return responder_resultado(resultado)
