# Compras pagadas desde las cajas de Abadion

La compra legada registra cantidad, precio y medio Caja o Deuda. El disparador del libro integrado toma el costo y congela la sección según categoría. El diario físico registra por separado sus egresos y el reporte trata los gastos de caja como un costo adicional. Registrar el pago de una compra como gasto duplicaría el costo.

Las nuevas operaciones de administración del POS ficticio reutilizan el alta y la reversión de compras dentro de una única transacción SQLite. Un registro vinculado conserva receptor del costo, cuenta pagadora, medio, pago inicial, deuda inicial, autor y clave de reintento. El movimiento físico se vincula al diario como retiro de compra o reintegro. El reporte lo presenta aparte de los retiros y aportes operativos. Una transferencia o pago de Mercado Pago se registra como egreso digital declarado. El saldo bancario se concilia contra el extracto fuera de este flujo. Los costos y el diezmo conservan la regla actual, que resta el costo devengado completo una sola vez.

La deuda inicial reutiliza la cuenta del proveedor por el saldo impago. La devolución total y la anulación revierten el costo y el stock usando el alta original. Se registra el reintegro por el mismo medio y cuenta de origen con confirmación explícita. Una compra cuyo proveedor ya tuvo pagos o ajustes posteriores requiere conciliación antes de revertirla. Quedan por definir las devoluciones parciales, reintegros por otra cuenta y liquidaciones posteriores de proveedor por compra individual.

El alta nueva usa la fecha local y exige jornada abierta y fondos suficientes para un egreso en efectivo. La reversión en efectivo usa la jornada actual para conservar cierres previos. No se imputan pagos a compras legadas de manera retroactiva. El esquema adicional se crea dentro de la primera alta exitosa en una base ficticia habilitada. Los cierres guardados y las rutas legadas siguen disponibles.

## Matriz de comprobación

Importes en pesos. Los fondos físicos empiezan en $10 por caja. Banco y Mercado Pago representan egresos declarados durante el ensayo.

| Operación | Sección del costo | Costo | Pagador y medio | Delta físico | Saldo rotisería | Saldo postres/bebidas | Deuda nueva |
| --- | --- | ---: | --- | ---: | ---: | ---: | ---: |
| Compra propia | Rotisería | 1,00 | Rotisería, efectivo | -1,00 | 9,00 | 10,00 | 0 |
| Compra propia | Postres/bebidas | 2,00 | Postres/bebidas, efectivo | -2,00 | 9,00 | 8,00 | 0 |
| Compra cruzada | Rotisería | 3,00 | Postres/bebidas, efectivo | -3,00 | 9,00 | 5,00 | 0 |
| Compra cruzada | Postres/bebidas | 4,00 | Rotisería, efectivo | -4,00 | 5,00 | 5,00 | 0 |
| Compra digital | Rotisería | 5,00 | Rotisería, transferencia | 0 | 5,00 | 5,00 | 0 |
| Compra digital | Postres/bebidas | 6,00 | Postres/bebidas, Mercado Pago | 0 | 5,00 | 5,00 | 0 |
| Compra parcial | Rotisería | 7,00 | Rotisería, efectivo $2,50 | -2,50 | 2,50 | 5,00 | 4,50 |
| Anulación de primera compra | Rotisería | -1,00 | Reintegro a rotisería, efectivo | +1,00 | 3,50 | 5,00 | 0 |
| Devolución de segunda compra | Postres/bebidas | -2,00 | Reintegro a postres/bebidas, efectivo | +2,00 | 3,50 | 7,00 | 0 |

El costo neto esperado es $25, con $15 de rotisería y $10 de postres/bebidas. Se pagaron $20,50 netos ($9,50 de efectivo y $11 digitales) y quedaron $4,50 pendientes. La jornada extendida termina con $19 y $7 en efectivo, costo $2 atribuido a postres/bebidas, gasto independiente de $1 y diezmo de $2,10.

## Reproducir y operar en el ambiente ficticio

Ejecutá `python -m pytest -q tests/test_pos_compras_caja.py tests/test_jornada_contable.py`. La jornada abre una restauración en otro directorio temporal y vuelve a comprobar sus resultados.

El alta usa `POST /pos-api/simulacion/compras` con sesión de Administrador, origen válido, UUID `id_solicitud`, `id_producto`, `cantidad`, `precio_unitario_centavos` y `pagado_centavos`. Si hay pago, indicá `pagador` y `medio_pago`. Si queda pendiente, indicá `cuenta_deuda`. El reporte expone `pagos_compras_por_receptor`.

Las rutas `/pos-api/simulacion/compras/{id_compra}/anulacion` y `/devolucion` reciben UUID, motivo y `reintegro_confirmado` cuando hubo pago. Registran reversos totales. La integración visual queda fuera de este alcance.

