# Jornada contable ficticia de Lo de Clau

El ensayo crea un Entrenamiento descartable con tres productos, diez unidades de cada uno, un extra y un cliente. Usa los asistentes de las pruebas de QA integrada, caja diaria y clientes. Compras, inventario y merma usan las funciones de dominio existentes sobre ese mismo archivo. Las ventas, pedidos, cobros, saldos, cierres y reportes se ejercitan por API. WhatsApp es el origen declarado del pedido, ingresado desde el POS.

## Libro de control independiente

Importes en pesos. Los saldos son acumulados. La compra se contabiliza como costo legado y queda fuera del diario físico. El gasto se registra en el diario de rotisería.

| Operación | Importe | Efectivo rotisería | Efectivo postres/bebidas | Banco | Mercado Pago | Fiado |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Aperturas | 10 + 5 | 10 | 5 | 0 | 0 | 0 |
| Pedidos pendientes de mostrador y WhatsApp | 0 | 10 | 5 | 0 | 0 | 0 |
| Mostrador, comida $10 + extra $2 + bebida $3, con reintento | 15 | 22 | 5 | 3 | 0 | 0 |
| WhatsApp, dos postres | 10 | 22 | 5 | 3 | 10 | 0 |
| Fiado de una comida | 10 | 22 | 5 | 3 | 10 | 10 |
| Abono por transferencia al banco de postres/bebidas, con reintento | 4 | 22 | 5 | 7 | 10 | 6 |
| Bebida cobrada en efectivo | 3 | 22 | 8 | 7 | 10 | 6 |
| Compra de dos bebidas a $1, ajuste de inventario y merma | 2 | 22 | 8 | 7 | 10 | 6 |
| Gasto físico en rotisería | -1 | 21 | 8 | 7 | 10 | 6 |
| Traspaso de efectivo de rotisería a postres/bebidas, con reintento | 2 | 19 | 10 | 7 | 10 | 6 |
| Cambio de categoría y precio de bebida y postre | 0 | 19 | 10 | 7 | 10 | 6 |
| Devolución de un postre, con reintento | -5 | 19 | 10 | 7 | 5 | 6 |
| Anulación de la bebida cobrada en efectivo | -3 | 19 | 7 | 7 | 5 | 6 |

La rotisería devenga $22 y cobra $16 atribuibles a su sección. Postres/bebidas devenga y cobra $8. El banco de postres/bebidas recibe $7, de los cuales $4 corresponden al fiado de rotisería. El traspaso sólo redistribuye el efectivo. La diferencia entre los $30 devengados y los $24 cobrados es la deuda de $6. La base de diezmo es $24 − $2 − $1 = $21 y el diezmo es $2,10. La prueba también restaura el archivo respaldado y vuelve a consultar saldos, reporte y stock.

## Reproducir

Desde un checkout de esta rama, con las dependencias del proyecto instaladas, usá `python -m pytest -q tests/test_jornada_contable.py`. La suite crea la base en `tmp_path`; la restauración se abre desde otro directorio temporal. El flujo cubre el libro del POS ficticio. Sigue pendiente definir cómo se registrará el egreso físico de compras pagadas desde una caja en un despliegue real, de manera que el costo se compute una vez.
