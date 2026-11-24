# Pedidos y delivery de Lo de Clau — diseño previo

Base: PR #33, commit 6e8a297c1348620fe36d48a18ef157c4495fa967. Rama independiente; sólo instalaciones ficticias nuevas. No migrar ni abrir instalaciones existentes.

## Decisiones antes de modificar estados o fondos

- `entrega.circuito=sencillo` habilita Recibido (`pendiente`) → Entregado directamente. El circuito avanzado continúa siendo el predeterminado de la API y de Entrenamiento. La interfaz de preproducción ofrece el sencillo. Se conservan versiones, UUID, autor e historial.
- Cobro y entrega son independientes. Entregar con deuda requiere confirmar el saldo vigente y un motivo; no perdona deuda ni crea cobros. Un pedido sin venta debe confirmarse antes de su entrega sencilla.
- Retiro no tiene envío. Delivery propio sencillo cobra $2.000 (200.000 centavos) por defecto. Siempre pertenece al repartidor, sin identificación. Bonificar significa cargo cero con motivo obligatorio conservado en el pedido y la solicitud auditada. No hay gasto por ese envío bonificado; si se quisiera compensar a quien reparte pese a la bonificación, requerirá otra decisión comercial.
- El total del cliente incluye envío. El devengado y el cobro atribuido a Rotisería/Postres sólo incluyen productos. El pago conjunto se divide de forma determinista: primero cubre productos; el resto cubre envío. Los abonos posteriores siguen el mismo orden. La deuda de envío se muestra aparte y también en el total del cliente; jamás se imputa a Rotisería.
- Un libro de delivery separado registra recepción, entrega al repartidor y reembolso. Sus movimientos afectan el receptor físico/digital real, con importe y signo explícitos, sin ingresos ni gastos de productos. Se vinculan a eventos de transferencia interna y al diario físico cuando corresponde. No se reutiliza el circuito manual avanzado de fondos para estas ventas.
- La confirmación Entregado incluye la entrega inmediata del importe del envío al repartidor en la misma transacción. Se elige el receptor real que paga. Si el cliente todavía no pagó el envío, es un adelanto con deuda del cliente; se exige saldo disponible y motivo. Una transferencia del cliente no autoriza una salida ficticia de efectivo: se elige explícitamente caja o cuenta. No se permiten saldos negativos para pagar al repartidor.
- Cuando el repartidor retiene el envío cobrado en efectivo, se registra recepción y salida por el mismo receptor en la confirmación de cobro/entrega, sin doble ingreso comercial. El efectivo disponible final contiene sólo productos. No hay liquidaciones acumuladas.
- Cancelación operativa sencilla con venta vigente se bloquea: Administración debe anular la venta primero. Anulación antes del reparto revierte productos, stock y envío cobrado. Después del reparto, la anulación/devolución devuelve productos y conserva el servicio ya prestado; no vuelve a pagar ni reembolsar el envío. No se borra historial. Devolución total previa al reparto reembolsa también el envío.
- UUID, versión y transacción BEGIN IMMEDIATE protegen cobro, entrega y reembolsos del doble clic y de concurrencia. Reintentar una solicitud devuelve su resultado original. Cambiar datos con el mismo UUID debe fallar.
- Las tablas aditivas sólo se crean al operar una nueva venta sencilla en SQLite ficticia. Se mantienen marcadores de aislamiento, permisos, backup, restore, Premium, stock y catálogo sin cambios comerciales.

## Verificación prevista

API/SQLite: retiro, delivery mixto, efectivo, transferencia, pago combinado, cobro parcial, fiado con adelanto, bonificación y motivo, rechazo de titular negocio, cancelación segura, devolución parcial/total, anulación antes/después de reparto, UUID y concurrencia, caja cerrada/sin fondos, conciliación y detección de manipulación. Proceso real: reinicio, respaldo y restore aislado. Edge: alta, cobro conjunto, estado sencillo, historial, doble clic y funciones Premium existentes. La matriz final distinguirá ejecutado, omitido y pendiente.

## Aclaraciones contables verificadas

- Pago conjunto: el importe esperado de la solicitud es productos + envío. El snapshot `total_centavos` y los devengados por sector conservan sólo productos; `total_cliente_centavos`, `saldo_cliente_centavos` y `estado_cliente` informan al operador el conjunto. Las cuentas corrientes incorporan la deuda de envío separada de las dos secciones; abonos FIFO y correcciones mantienen esa separación.
- `pagos[].envio_directo=true` identifica exclusivamente el cargo completo del envío retenido en efectivo. Registra recepción y constancia de entrega sin movimiento físico del envío. Los productos pueden entrar en la caja elegida o quedar en tránsito hasta su rendición. La interfaz de pago en efectivo ofrece esta opción; no identifica a la persona que reparte. Con el envío ya retenido se prohíbe una segunda salida de caja al entregar.
- El libro de delivery conserva evento, venta, signo, receptor real, referencia y evento de cobro. Cada evento tiene autor, fecha, motivo, UUID y resultado. El historial de ventas muestra sus movimientos. Las bonificaciones guardan motivo en el snapshot inmutable y en la solicitud de alta.
- La custodia es dinero del envío todavía no entregado. El adelanto fiado se muestra como saldo a recuperar, no como una obligación pendiente con quien repartió. Los receptores exponen saldo propio y saldo total real; si se cobra por banco y se paga por caja, el efectivo baja y el banco queda a favor del negocio. La conciliación compara cada movimiento contra su constancia y su auditoría.
- Se permite a Ventas completar el reparto y su salida acotada al cargo de ese pedido, igual que las operaciones físicas diarias ya habilitadas. Los fondos avanzados, anulaciones, devoluciones y correcciones administrativas conservan sus permisos anteriores.
- Las nuevas opciones están omitidas del JSON cuando usan sus valores anteriores. Esto conserva la forma de las solicitudes idempotentes avanzadas guardadas por #33.

## Matriz de pruebas automatizadas

| Área | Casos | Archivo |
|---|---|---|
| Cobro conjunto | Efectivo, banco, Mercado Pago; Rotisería + Postres; productos $12.500, envío $2.000 | `tests/test_lo_de_clau_delivery.py` |
| Entrega | Recibido → Entregado, historial de dos estados, UUID repetido concurrente, versión obsoleta, receptor obligatorio | mismo |
| Efectivo retenido | Con productos ingresados o en tránsito, rendición sólo de productos, rechazo de segunda salida | mismo |
| Transferencia y caja | Ninguna salida de efectivo implícita; pago desde otra caja explícita; caja cerrada y cuenta sin fondos rechazan sin modificar pedido | mismo |
| Fiado | Entrega con deuda total confirmada y motivo; adelanto inmediato; abono sin deuda residual | mismo |
| Cuenta corriente | Abono global FIFO, parte de envío separada, corrección idempotente y doble corrección rechazada | mismo + `tests/test_pos_clientes.py` |
| Reversos | Anulación/devolución total antes y después del reparto; devolución parcial; stock y conciliación | mismo |
| Bonificación y cancelación | Cero con motivo, titular siempre repartidor, retiro sin cargo, cancelar sólo tras anular, permisos | mismo |
| Auditoría | Manipulación del importe detectada sin reparación automática | mismo |
| Persistencia | Worker real, parada/reinicio, backup verificado y restore en otra carpeta, deuda/stock/cajas/pedidos/historial iguales | mismo |
| Edge | Selector Premium de comida y postre, $2.000 predeterminado, pago conjunto, entrega sencilla, retención directa, doble clic en venta y entrega | `tests/test_lo_de_clau_edge.py` |
| Regresión | POS Premium, caja, stock, fiados, permisos, aislamiento, HTTPS, respaldo/restore y flujo avanzado | suites existentes y workflow `abadion-pos.yml` |

## Ensayo seguro en Windows

Usar una copia nueva en la carpeta temporal del sistema, fuera de OneDrive. Estos comandos ejecutan exclusivamente los ensayos con datos sintéticos. No arrancan el acceso directo ni apuntan a instalaciones existentes. Los puertos del ensayo de delivery son efímeros.

```powershell
$ensayo = Join-Path ([IO.Path]::GetTempPath()) ('abadion-delivery-' + [guid]::NewGuid())
git clone --single-branch --branch feature/lo-de-clau-pedidos-delivery https://github.com/NicoNunezFM/contabilidad-bebidas-postres.git $ensayo
if ($LASTEXITCODE -ne 0) { throw 'Falló la descarga' }
Set-Location -LiteralPath $ensayo
py -3.12 -m venv .venv
if ($LASTEXITCODE -ne 0) { throw 'Falló la creación del entorno de ensayo' }
$pythonEnsayo = Join-Path $ensayo '.venv\Scripts\python.exe'
& $pythonEnsayo -m pip install -r requirements-tablet-test.txt
if ($LASTEXITCODE -ne 0) { throw 'Falló la preparación de dependencias' }
$env:PYTHON_DOTENV_DISABLED = '1'
$env:PYTHONUTF8 = '1'
$env:NEGOCIO_DB_PATH = Join-Path $ensayo 'pos-qa-ficticio.db'
$env:POS_TEST_BROWSER = "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe"
$env:POS_UI_CAPTURAS = Join-Path $ensayo 'capturas'
if (!(Test-Path -LiteralPath $env:POS_TEST_BROWSER)) { throw 'Falta Edge; ajustar la ruta' }
& $pythonEnsayo -m pytest -q tests/test_lo_de_clau_delivery.py tests/test_lo_de_clau_edge.py --junitxml=delivery-qa.xml
if ($LASTEXITCODE -ne 0) { throw 'Revisar el ensayo fallido; no usar con datos reales' }
```

Para la regresión completa: `& $pythonEnsayo -m pytest -q --junitxml=regresion-qa.xml`. Las pruebas heredadas que requieren el puerto fijo 8078 lo omiten si está ocupado; el ensayo nuevo no lo usa. No restaurar estas bases sobre la instalación actual. No fusionar este PR ni habilitar producción. El catálogo comercial, las compras con tarjeta y WhatsApp quedan fuera de este cambio.

La validación automatizada comprueba eventos y movimientos registrados; el operador sigue siendo responsable de confirmar que efectivamente entregó el dinero. No se conecta a bancos ni realiza transferencias reales. Quedan pendientes la aceptación familiar y el ensayo físico con pantalla táctil y reinicio del equipo.

## Resultados locales — 24/11/2026

- Regresión completa: **380 aprobadas, 25 omitidas, 0 fallidas** (403 s). La conversión anónima agregada durante esa ejecución se verificó aparte y también pasó. Las omisiones corresponden a pruebas que requieren navegador u opciones de entorno; no se presentan como ejecutadas.
- Circuito final de Lo de Clau: **20 aprobadas, 0 omitidas**: 18 de API/SQLite/proceso y 2 de Edge (87 s). Incluye el bloqueo de entrega de una venta totalmente devuelta.
- Regresión de cuentas corrientes, junto con delivery: **20 aprobadas, 0 omitidas** (56 s), antes de agregar el último caso de conversión. Conserva la prueba de rollback intermedio de FIFO.
- Bloque amplio Windows/Edge: **79 aprobadas y 1 timeout al capturar una pantalla** en la primera ejecución (231 s). La prueba de captura se repitió completa y pasó; también pasó la conversión nueva en esa reverificación (**2 aprobadas**, 11 s). Las suites se solapan: no sumar sus cantidades.
- Sintaxis Python/JavaScript y `git diff --check`: correctos.
- [Controles automáticos actuales del PR #34](https://github.com/NicoNunezFM/contabilidad-bebidas-postres/pull/34/checks). El PR mantiene la condición de borrador contra #33. Sus controles ejecutan las suites de SQLite y Windows/Edge, incluyendo todos los casos nuevos.

Todos los respaldos/restauraciones del ensayo usan identidades y carpetas temporales nuevas. Ninguna prueba valida todavía el reinicio físico de la PC, la pantalla táctil real ni la aceptación del negocio.
