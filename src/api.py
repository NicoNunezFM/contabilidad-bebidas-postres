from fastapi import FastAPI

from productos import obtener_productos

from pydantic import BaseModel, Field

from ventas import registrar_venta

from compras import registrar_compra

from datetime import datetime

from gastos import registrar_gasto
from reportes import (
    resumen_por_periodo,
    resumen_semana_actual,
    resumen_mes_actual
)

from ajustes_stock import registrar_inventario_fisico

from caja import obtener_estado_caja

from movimientos_caja import (
    registrar_aporte,
    registrar_retiro
)

from diezmo import (
    estado_diezmo_mes,
    registrar_reserva_diezmo,
    registrar_entrega_diezmo
)

from ventas import anular_venta
from compras import anular_compra
from gastos import anular_gasto

from movimientos_caja import anular_movimiento_caja

from cierres import (
    registrar_cierre_semanal,
    registrar_cierre_mensual,
    obtener_cierres_semanales,
    obtener_cierres_mensuales
)


app = FastAPI(
    title="Lo de Clau API",
    version="1.0.0"
)

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

@app.get("/")
def inicio():

    return {
        "mensaje": "API de Lo de Clau funcionando."
    }


@app.get("/productos")
def listar_productos_api():

    productos = obtener_productos()

    return {
        "ok": True,
        "cantidad": len(productos),
        "productos": productos
    }

@app.post("/ventas")
def registrar_venta_api(venta: VentaEntrada):

    resultado = registrar_venta(
        id_producto=venta.id_producto,
        cantidad=venta.cantidad,
        precio_unitario=venta.precio_unitario
    )

    return resultado

@app.post("/compras")
def registrar_compra_api(compra: CompraEntrada):

    resultado = registrar_compra(
        id_producto=compra.id_producto,
        cantidad=compra.cantidad,
        precio_unitario=compra.precio_unitario
    )

    return resultado

@app.post("/gastos")
def registrar_gasto_api(gasto: GastoEntrada):

    resultado = registrar_gasto(
        categoria=gasto.categoria,
        descripcion_gasto=gasto.descripcion,
        valor_final=gasto.valor
    )

    return resultado

@app.get("/reportes/hoy")
def reporte_hoy_api():

    fecha_hoy = datetime.now().strftime("%Y-%m-%d")

    resultado = resumen_por_periodo(
        fecha_hoy,
        fecha_hoy
    )

    return resultado

@app.get("/reportes/semana")
def reporte_semana_api():

    return resumen_semana_actual()

@app.get("/reportes/mes")
def reporte_mes_api():

    return resumen_mes_actual()

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

@app.post("/inventario")
def registrar_inventario_api(inventario: InventarioEntrada):

    resultado = registrar_inventario_fisico(
        id_producto=inventario.id_producto,
        cantidad_real=inventario.cantidad_real
    )

    return resultado

@app.get("/caja")
def consultar_caja_api():

    return obtener_estado_caja()

@app.post("/caja/aportes")
def registrar_aporte_api(movimiento: MovimientoCajaEntrada):

    return registrar_aporte(
        descripcion=movimiento.descripcion,
        monto=movimiento.monto
    )


@app.post("/caja/retiros")
def registrar_retiro_api(movimiento: MovimientoCajaEntrada):

    return registrar_retiro(
        descripcion=movimiento.descripcion,
        monto=movimiento.monto
    )

@app.get("/diezmo/{anio}/{mes}")
def consultar_diezmo_api(anio: int, mes: int):

    return estado_diezmo_mes(
        anio=anio,
        mes=mes
    )

@app.post("/diezmo/reservas")
def registrar_reserva_diezmo_api(
    movimiento: DiezmoMovimientoEntrada
):

    if movimiento.descripcion:

        return registrar_reserva_diezmo(
            anio=movimiento.anio,
            mes=movimiento.mes,
            monto=movimiento.monto,
            descripcion=movimiento.descripcion
        )

    return registrar_reserva_diezmo(
        anio=movimiento.anio,
        mes=movimiento.mes,
        monto=movimiento.monto
    )

@app.post("/diezmo/entregas")
def registrar_entrega_diezmo_api(
    movimiento: DiezmoMovimientoEntrada
):

    if movimiento.descripcion:

        return registrar_entrega_diezmo(
            anio=movimiento.anio,
            mes=movimiento.mes,
            monto=movimiento.monto,
            descripcion=movimiento.descripcion
        )

    return registrar_entrega_diezmo(
        anio=movimiento.anio,
        mes=movimiento.mes,
        monto=movimiento.monto
    )

@app.patch("/ventas/{id_venta}/anular")
def anular_venta_api(
    id_venta: int,
    anulacion: AnulacionEntrada
):

    return anular_venta(
        id_venta=id_venta,
        motivo=anulacion.motivo
    )

@app.patch("/compras/{id_compra}/anular")
def anular_compra_api(
    id_compra: int,
    anulacion: AnulacionEntrada
):

    return anular_compra(
        id_compra=id_compra,
        motivo=anulacion.motivo
    )

@app.patch("/gastos/{id_gasto}/anular")
def anular_gasto_api(
    id_gasto: int,
    anulacion: AnulacionEntrada
):

    return anular_gasto(
        id_gasto=id_gasto,
        motivo=anulacion.motivo
    )

@app.patch("/caja/movimientos/{id_movimiento}/anular")
def anular_movimiento_caja_api(
    id_movimiento: int,
    anulacion: AnulacionEntrada
):

    return anular_movimiento_caja(
        id_movimiento=id_movimiento,
        motivo=anulacion.motivo
    )

@app.post("/cierres/semanales")
def registrar_cierre_semanal_api(
    cierre: CierreSemanalEntrada
):

    return registrar_cierre_semanal(
        fecha_desde=cierre.fecha_desde,
        fecha_hasta=cierre.fecha_hasta
    )

@app.get("/cierres/semanales")
def obtener_cierres_semanales_api():

    return {
        "ok": True,
        "cierres": obtener_cierres_semanales()
    }

@app.post("/cierres/mensuales")
def registrar_cierre_mensual_api(
    cierre: CierreMensualEntrada
):

    return registrar_cierre_mensual(
        anio=cierre.anio,
        mes=cierre.mes
    )

@app.get("/cierres/mensuales")
def obtener_cierres_mensuales_api():

    return {
        "ok": True,
        "cierres": obtener_cierres_mensuales()
    }