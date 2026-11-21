# Issue #15 · Diseño de pedidos y conciliación de envíos

Base inspeccionada: `0eabad9ddb88ac1ad8fc443d03a069d664b96aaa` (PR #16). Este borrador documenta el contrato y el bloqueo de la integración directa. La aplicación todavía no registra pedidos.

## Dependencias y bloqueo contable

| Componente | Comportamiento en la base |
| --- | --- |
| `pos_pedidos.py` | Valida el menú, las personalizaciones y los importes de productos. |
| `pos_simulacion.py` | Confirma venta, valida total, guarda productos y descuenta stock en una transacción. Si queda un saldo, exige modalidad fiada. En Entrenamiento el fiado nuevo requiere cliente. La validación actual también rechaza un cliente en una venta saldada. |
| `pos_clientes.py` | Los abonos FIFO se aplican a saldos de ventas del cliente. Un pedido pendiente anónimo necesita su propio estado operativo antes de la venta; no debe convertirse en deuda de un cliente ficticio. |
| `pos_cobros.py` | El saldo de cada venta suma todos sus movimientos sin distinguir propiedad o custodia. Solo admite los receptores actuales y asocia cada receptor a una de las dos secciones. |
| `pos_caja_diaria.py` | Un movimiento a un receptor de efectivo afecta el arqueo y requiere jornada abierta. |
| `pos_contabilidad.py` | Los cierres y la base del diezmo consumen los cobros atribuidos del libro. Los desgloses por receptor leen movimientos con medio de pago. |

Ejemplo de control: mercadería por $10.000 y envío para el repartidor por $1.000, ambos pagados por transferencia a una cuenta del negocio. Si se registra todo como un pago de venta, la API rechaza el exceso. Añadir el envío como un producto para que coincida el total convierte $1.000 ajenos en ingreso propio y aumenta la base del diezmo. Registrar solo $10.000 deja $1.000 del extracto sin contrapartida. El efectivo entregado al repartidor presenta otro problema: registrarlo en una caja física adelanta el arqueo, y volver a registrarlo al recibirlo duplica el cobro. La transferencia interna existente exige distribución entre secciones y no representa ninguna de esas dos operaciones.

## Contrato propuesto

- Pedido propio con ID, fecha local de visualización, origen, modalidad, versión, cliente opcional y referencia única a la venta. Guardar un resumen de líneas y personalizaciones con las reglas del POS. Para envío, dirección obligatoria y referencias opcionales. Importe manual en centavos con titular explícito.
- Retiro: pendiente → en preparación → listo → entregado. Envío: el mismo recorrido con en camino entre listo y entregado. Guardar transición, usuario, hora y motivo cuando corresponda en un historial sin sobreescritura. Ventas puede confirmar entrega. Administración autoriza cancelación con motivo; la cancelación operativa conserva saldos y stock y remite a los flujos contables existentes.
- Confirmar la venta de forma explícita, como máximo una vez por pedido. Reusar validaciones de catálogo, stock, devoluciones y clientes. Permitir cliente opcional en venta saldada y exigir cliente del PR #16 para convertir saldo en fiado. El cobro posterior anónimo requiere distinguir saldo operativo de deuda registrada en el FIFO. Entrega con saldo exige confirmación explícita, comprobada contra el saldo actual, sin registrar cobro. Una venta anulada no debe mostrarse como saldada.
- Registrar cobro propio, custodia física y obligación a terceros como conceptos con saldos independientes. Un cobro propio recibido fuera del local disminuye el saldo del cliente y acredita efectivo en tránsito. Su entrega al local mueve custodia a la caja física abierta, sin segundo cobro. Una transferencia por el envío del repartidor a la cuenta del negocio aumenta el saldo bancario y una obligación por el mismo importe. Liquidarla reduce ambos saldos. Si el repartidor cobra su parte directamente, registrar la constancia operativa sin movimiento del negocio. El envío propio se reconoce como concepto separado de Comidas, sin stock, con participación explícita en devoluciones, cierres y diezmo.
- Reservar escritura con `BEGIN IMMEDIATE`. Cada mutación debe validar versión y permisos, registrar su UUID por usuario y comparar la solicitud en reintentos. Un reintento idéntico devuelve el resultado anterior. Una transición concurrente o una rendición superior al pendiente falla sin mover saldos. Registrar reversión mediante contramovimientos vinculados y conservar los cierres anteriores.
- Agregar las tablas con migración transaccional e idempotente para la base de Entrenamiento. Antes de incrementar la versión, verificar marca SQLite, reservar escritura y crear un respaldo consistente por SQLite Backup API. Comparar conteos y totales de ventas, movimientos y clientes antes y después. Arranque y restauración deben comprobar `application_id`, versión, `integrity_check` y `foreign_key_check`. Evitar migrar automáticamente una base sin marca o con versión desconocida.

## Ensayo de actualización desde el PR #16

Aplicar estos pasos cuando exista una implementación validada. Este borrador de diseño no requiere actualizar la instalación.

1. Ensayar en un perfil de Windows descartable con datos ficticios. Detener solo el servidor de Entrenamiento y verificar que Edge ya no tenga operaciones pendientes. Registrar el commit actual y confirmar que coincide con el del PR #16.
2. Con el servidor detenido, respaldar la carpeta completa `%LOCALAPPDATA%\Abadion\Entrenamiento` y comprobar que contiene la base y el JSON del catálogo. Verificar el respaldo SQLite con `PRAGMA integrity_check` en modo de solo lectura. Si hay archivos auxiliares, comprobar que la copia se obtuvo con SQLite Backup API y es consistente.
3. Seleccionar el SHA aprobado en el checkout de práctica. Con el Python de su entorno virtual, ejecutar `python -m pip install -r requirements.txt` y `python -m pip check`. Comprobar la zona y el paquete con `python -c "from zoneinfo import ZoneInfo; import tzdata; print(tzdata.__version__, ZoneInfo('America/Argentina/Buenos_Aires'))"`. El PR #16 fija `tzdata==2025.3`.
4. Aplicar la futura migración a la copia. Repetir el comando y verificar que conserva saldos, catálogo, stock, historial, clientes, abonos FIFO y cierres. Iniciar con `python scripts/abadion_entrenamiento.py servir` en loopback. Ejecutar la matriz de pruebas en Edge y conciliar cada sección antes de autorizar la actualización.
5. Para recuperar, detener el servidor, conservar la carpeta del intento con otro nombre y restaurar la carpeta completa de respaldo. Volver al SHA del PR #16 y verificar saldos y apertura de la base restaurada. Si hubo operaciones después del respaldo, conservarlas en la carpeta desplazada para revisarlas.

## Matriz de pruebas

| Caso | Resultado | Evidencia o comprobación pendiente |
| --- | --- | --- |
| Receptor para efectivo en tránsito | Confirmado en la base | `PagoPos` rechaza el receptor propuesto. |
| Obligación por transferencia ajena | Confirmado en la base | `PagoPos` rechaza el receptor y el libro atribuye el importe a la venta si se imputa en banco. |
| Venta de $10.000 con $1.000 de terceros | Confirmado en SQLite ficticia | Imputación directa deja saldo del cliente de −$1.000. Las tres comprobaciones de diagnóstico pasan con `python -m pytest -q tests/test_issue15_base.py`. |
| Regresión API y contable del PR #16 | Bloqueada durante preparación | `TestClient` queda esperando en `socket._fallback_socketpair` al inicializar el bucle de Windows. No hay validación completa de la suite. |
| Microsoft Edge | 7 errores de preparación | La suite existente espera a Uvicorn y vence antes de abrir Edge. Reintentar en un entorno que pueda levantar el servidor en loopback. |
| JS del POS base | Correcto | `node --check` sobre el bloque de script de `pos-web/index.html`, Node v20.20.2. |
| Dependencias Windows | Correcto en este entorno | `pip check` y carga de `America/Argentina/Buenos_Aires` con `tzdata 2025.3`. |
| Retiro, envío y entrega con saldo | Pendiente | Verificar transiciones auditadas y ausencia de movimientos de caja al entregar. |
| Pago parcial, mixto y FIFO | Pendiente en pedidos | Comprobar que un pago nuevo aplica una sola vez y que FIFO conserva el orden. |
| Efectivo en tránsito y rendición | Pendiente | El arqueo solo cambia con la recepción física, incluso si ocurre después del cierre diario. |
| Envío propio y del repartidor | Pendiente | Verificar total para cliente, extracto bancario, obligación, liquidación, resultado y diezmo. |
| Cancelaciones, permisos y devoluciones | Pendiente en pedidos | Cancelación auditada por Administración, sin tocar stock o caja. Ejecutar la reversión por separado. |
| Concurrencia, reintentos y cierres | Pendiente en pedidos | Dos solicitudes válidas que compiten deben producir un solo efecto, sin alterar el cierre anterior. |
| Migración y recuperación | Pendiente | Ensayar dos aplicaciones consecutivas y restauración al PR #16 con bases ficticias. |

Los cambios de esta rama comprenden documentación y pruebas de diagnóstico. El diseño requiere implementar y validar primero la distinción entre cobro, custodia y obligación antes de habilitar el circuito de pedidos.

## Avance posterior del PR #17

La rama incorpora receptores de efectivo en tránsito por sección. El cobro reduce la deuda y queda fuera del diario físico. La rendición mueve custodia mediante dos movimientos sin medio de pago, enlaza el evento al cobro original y requiere caja abierta cuando está activo el arqueo. Un reembolso de ese cobro se distribuye entre la custodia pendiente y el efectivo rendido. La creación de tablas auxiliares es idempotente y ocurre dentro de la transacción de escritura ficticia.

El importe de envío propio queda en la venta como concepto separado, devenga en Comidas y se revierte al devolver la totalidad de la mercadería. Para importes del repartidor, la recepción digital, la liquidación y el reembolso se registran en el libro auxiliar de fondos por receptor. La obligación se mantiene fuera del saldo del cliente, el ingreso propio y el diezmo. El resumen de cajas incluye esa obligación para conciliar el saldo digital. Los movimientos del libro auxiliar requieren Administración.

| Prueba nueva | Resultado local |
| --- | --- |
| Validación de combinación receptor y medio | 2 casos aprobados |
| Transferencia de terceros y liquidación idempotente | Aprobada en SQLite ficticia |
| Efectivo en tránsito, rendición parcial, reintento, diario físico y devolución | Aprobada en SQLite ficticia |
| Envío propio, devengado separado y devolución total | Aprobada en SQLite ficticia |

Quedan pendientes pruebas integradas de API, abonos FIFO, pagos mixtos, devoluciones y liquidaciones concurrentes, arqueo al cierre y comprobación directa del diezmo. También quedan pendientes el flujo de pedidos, la conciliación de pagos al repartidor fuera de las cuentas del negocio y el ensayo completo de actualización y recuperación.

### Ensayo de la preparación contable

En la copia ficticia y con el servidor detenido, ejecutar `python scripts/abadion_entrenamiento.py activar-fondos-envio` antes de practicar los flujos nuevos. El comando bloquea Entrenamiento, reserva escritura, crea un respaldo SQLite y agrega las tablas auxiliares. Repetir el comando devuelve que los fondos ya están preparados. La comprobación local compara tablas históricas con el respaldo y verifica integridad y claves foráneas. La recuperación sigue el procedimiento de carpeta completa y retorno al SHA del PR #16.

GitHub Actions aprobó SQLite/API y Edge en el commit de separación de fondos (`e323975`). El primer ensayo integrado de pago mixto, concurrencia y diezmo pasó sus comprobaciones hasta la conciliación. La conciliación exigía dos secciones diferentes para todo evento de transferencia y marcaba incorrectamente una rendición de la misma sección y los eventos del libro auxiliar. La corrección valida cada estructura de acuerdo con su registro auxiliar y conserva la regla anterior para transferencias entre cajas. Se agregaron casos API para esa conciliación y para el abono FIFO en tránsito. Los pedidos y su interfaz siguen pendientes.

## Circuito de pedidos implementado en el POS

En el checkout de Entrenamiento, elegí Retiro en local o Envío a domicilio. Para envíos, cargá dirección y, si corresponde, importe y titular. El envío propio se suma al importe contable de la venta. El importe del repartidor se muestra por separado. La venta rápida sigue disponible. El menú, el stock y las personalizaciones siguen siendo los de la venta.

Pedidos muestra el trabajo activo y el historial finalizado. El seguimiento nace en la misma transacción que la venta, con su mismo identificador. La entrega con saldo requiere confirmación. Las transiciones tienen versión, UUID, autor y hora. Administración puede cancelar con motivo. La cancelación operativa preserva los efectos de la venta. Desde el historial de ventas, Administración puede rendir efectivo y registrar recepciones digitales, liquidaciones o reembolsos de fondos de reparto.

### Cobertura y pendientes

| Área | Evidencia |
| --- | --- |
| Contabilidad, pagos mixtos, FIFO, diezmo, concurrencia, reversión, arqueo y cierres | Aprobada en GitHub Actions, ejecución [44919829525](https://github.com/NicoNunezFM/contabilidad-bebidas-postres/actions/runs/44919829525). |
| Preparación con respaldo e idempotencia | Aprobada en SQLite ficticia y en la misma ejecución. |
| Preparación, entrega con saldo, reintento, permiso de cancelación e historial | Caso nuevo de API en la suite del PR. |
| Registro y avance de retiro de mostrador | Caso nuevo de Edge en la suite del PR. |
| Sintaxis JavaScript | Aprobada localmente con Node 20. |

El registro de un pedido todavía requiere confirmar una venta. El saldo pendiente sigue el flujo de fiados del PR #16 y exige cliente. El checkout permite asociar un cliente a la venta saldada. El historial permite confirmar un pago directo al repartidor, con constancia sin saldo bancario ni obligación. Quedan pendientes el alta de pedidos anónimos antes de confirmar la venta y el ensayo de restauración con pedidos ya registrados.

Los casos nuevos de seguimiento pasaron SQLite/API y Edge en la [ejecución 44920199208](https://github.com/NicoNunezFM/contabilidad-bebidas-postres/actions/runs/44920199208). Esa ejecución es anterior a la constancia de pago directo y a la asociación opcional en la interfaz.
