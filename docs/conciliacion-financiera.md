# Conciliación y contrato financiero — Fase 2.3

Base: PR #40, `91f293b8b5c303170626b202cdd72cc6c33ba718`.
Rama independiente: `fix/abadion-conciliacion-financiera`. Propuesta en borrador;
sin fusiones, instalaciones ni producción. Solo bases ficticias.

## Qué significa cada importe

Una venta de $100, cobrada $40 y fiada por $60, devenga $100 y cobra $40.
El abono posterior de $60 cancela la cuenta por cobrar: no genera otra venta.
Si el costo capturado era $30, su margen bruto es $70; no equivale al efectivo
disponible ni al resultado financiero del período.

Si se cobran además $20 para un repartidor, se reciben físicamente $60 pero solo
$40 corresponden al negocio. Los otros $20 son custodia. Entregarlos no es un gasto
ni una segunda venta. Si el repartidor los retiene directamente, nunca entran en caja.

Depositar $10 de caja en banco cambia su ubicación: efectivo -$10, banco +$10,
ingresos $0. La apertura de una jornada tampoco es venta. Un arqueo con $1 de faltante
registra el faltante y una observación, sin fabricar un gasto o compensar el saldo.

## Mapa y fuentes autorizadas

La [matriz previa de inspección y operaciones](conciliacion-financiera-inspeccion.md)
identifica todos los libros, sus efectos, sus consumidores y las restricciones de
la rama WhatsApp. Las fuentes no son sumables entre sí.

| Magnitud | Fuente del contrato | Cobertura / límite |
| --- | --- | --- |
| Efectivo esperado | Diario de la última jornada por caja; apertura y eventos ya vinculados | Último contado se muestra separado. No confundir esperado con efectivo recién contado |
| Dinero digital registrado | Movimientos del receptor menos pagos netos de compras POS | Es flujo del libro: no hay un saldo bancario inicial ni extracto certificado |
| Custodia de productos en tránsito | Movimientos `_efectivo_en_transito` y sus rendiciones/reembolsos | No disponible para gastar desde caja antes de rendir |
| Custodia de envío sencillo | Libro delivery y su espejo financiero único | Separada del saldo propio; solo delivery puede usarla para su circuito existente |
| Fondos de reparto anterior | `pos_fondos_reparto` | Libro externo al de movimientos POS. Se muestra separado, nunca como venta |
| Ventas y cuentas por cobrar | Pedido/unidades vigentes, eventos y cobros; ficha de cliente como vista | Imputación económica existente por sección; cobro recibido y cobro atribuido pueden diferir |
| Deuda de proveedor | Cuentas y movimientos de deuda, con moneda y reserva por cuenta | No se suma entre monedas ni se atribuye a una sección sin evidencia |
| Deudas de apertura unificada | Libro optativo de apertura y sus pagos/reversiones | Se presenta aparte de deudas legadas; no se presume equivalencia |
| Compras y gastos | Costos contables y sus fuentes, pagador cuando esté identificado | Si falta pagador, se advierte; no se inventa una salida física o digital |
| Aportes/retiros | Diario manual; se excluyen espejos de pagos de compras | Motivo obligatorio, sin efecto en ventas |
| Margen bruto | Capturas históricas #40 y reversiones originales | Costo faltante sigue desconocido; no duplica gastos o pagos |
| Resultado financiero | Fórmulas existentes de `pos_contabilidad` y cortes por ID/fecha | Se conservan devengado, cobrado, compras/gastos y diezmo |
| Saldo unificado optativo | Aperturas y libros definidos por ese modelo | No permite descomponer efectivo/digital; no se activa ni se transforma una instalación |

La falta de saldo bancario inicial no se convierte en afirmación de saldo real cero.
Los importes digitales son explícitamente movimientos registrados desde el origen
del libro. `saldo_global_certificado` es false; `cuadrado` del puente significa
conciliación de enlaces/asientos, no certificación de dinero real ni cobertura total.

## Cambios implementados

`src/pos_conciliacion_financiera.py` centraliza lectura de fuentes, pagos netos de
compras, disponibilidad operativa, diagnóstico y compatibilidad legada. No ejecuta
DDL, importaciones, ajustes ni commits. El llamador aporta la transacción de lectura.

1. **Reintegros digitales:** un pago de compra de $3 y su devolución de $3 tienen
   egreso neto $0. Antes `pos_delivery.disponible_receptor` restaba ambos importes
   positivos, reduciendo disponibilidad en $6. Ahora descuenta el pago neto.
2. **Transferencias:** la API existente admite dos receptores distintos de la misma
   sección, incluidas caja/cuenta. Dos patas opuestas, medio NULL, un único evento y
   ninguna venta/cobro adicional. El origen se verifica contra su fuente autorizada,
   excluyendo custodia de envío. La UI explica ambas modalidades.
3. **Distribución entre secciones:** conserva el límite existente de cobro atribuido
   pendiente y saldo registrado; además coteja la disponibilidad efectiva de su
   fuente. No transforma una distribución de cobros en préstamo o gasto cruzado.
   Se mantienen las restricciones existentes entre físico y digital en esa modalidad.
4. **Custodia:** retiros, gastos físicos, compras físicas/digitales y transferencias
   no consumen fondos de envío identificados como custodia. No se introduce una
   política general nueva de descubierto donde antes no existía: los límites
   desconocidos y movimientos sin pagador siguen explícitos y pendientes.
5. **Espejos:** detecta diario sin correspondencia, vínculo de delivery inválido,
   dos modelos de custodia en una misma venta y estados de jornada incompatibles.
   Una transferencia ordinaria debe coincidir con origen, destino e importe de su
   solicitud; no basta con que sume cero.
6. **Recibos completos:** comprueba filas guardadas al iniciar/completar eventos,
   insertar movimientos, diario, rendición, compra/pago y custodia. Rechazos silenciosos
   mediante `RAISE(IGNORE)` provocan rollback, sin éxito parcial. La venta también
   verifica su INSERT antes de capturar costos.
7. **Revisión unificada:** la huella incluye eventos y libros opcionales de custodia
   y rendiciones. Un movimiento directo sin cambio de saldo propio no queda fuera
   del control de revisión. Sin corte validado se muestra incompatibilidad y no un
   saldo inventado.
8. **Visibilidad:** `/pos-api/simulacion/conciliacion-financiera` requiere administración,
   marca de simulación y respuesta sin caché; la pantalla de Contabilidad muestra
   fuentes, custodia, diferencias, jornadas pendientes y alertas persistentes.
   El puente conserva sus claves y añade `contrato_financiero` y diferencias nuevas.

## Reglas que se conservan

- Dos secciones independientes: `comidas` (Rotisería) y `bebidas_postres`.
- Propuesta de apertura desde 10:00 inclusive hasta 12:00 exclusive, usando el último
  contado de cierre. Fuera de esa franja se ingresa manualmente. La diferencia contra
  el contado anterior se guarda; nunca se agrega otra apertura al saldo acumulado.
- Una jornada abierta por caja; una jornada por fecha; fechas de apertura verificadas.
  Una jornada anterior abierta se muestra pendiente, no se cierra automáticamente.
- Arqueo vigente por revisión de efectivo; cierre con diferencia permitido con
  observación obligatoria. Alerta administrativa persistente; no se borra ni se
  considera resuelta por un conteo posterior. También se exponen diferencias de cierres
  unificados como controles separados.
- Motivos obligatorios en aportes/retiros y transferencias; UUID/actor/payload para
  reintentos, restricciones de usuario y validación dentro de la transacción.
- El dinero bajo custodia de otro negocio/sección no se adjudica automáticamente.
  Cuando un envío fue recibido y pagado desde secciones distintas se advierte la
  atribución pendiente, sin compensación automática.

## Atomicidad y conservación de #39/#40

Se mantiene el dueño `transaccion_simulacion`, BEGIN IMMEDIATE, una sola conexión,
commit al completar y rollback ante errores. Las verificaciones nuevas no confirman
ni cierran conexiones prestadas. Las compras de insumos de #39 no se modifican.
Las capturas de costos y el motor de costos de #40 tampoco se modifican; los fallos
finales de la venta revierten también su captura y stock.

Una caída después de la primera pata de una transferencia se ensaya con `os._exit`
en un proceso hijo y SQLite ficticio: al recuperar no quedan evento, movimiento
ni cambio de caja parcial. Los reintegros/anulaciones siguen creando reversiones,
sin borrar el registro original.

Fundamento: [transacciones SQLite](https://www.sqlite.org/lang_transaction.html),
[commit y recuperación](https://www.sqlite.org/atomiccommit.html).
Los tests no certifican hardware, energía ni edición manual del archivo por terceros.

## Jornada ficticia completa y evidencia

El caso `test_jornada_completa_conciliada_con_evidencia` utiliza:

| Operación | Importe en centavos |
| --- | ---: |
| Apertura de cada caja | 1000 |
| Venta de dos unidades, solo Postres/Bebidas | 20026 |
| Primer cobro físico / digital | 10000 / 5000 |
| Fiado inicial y abono posterior digital | 5026 |
| Aporte / retiro / gasto | 200 / 100 / 50 |
| Compra pagada desde efectivo | 300 |
| Devolución de una unidad | 10013 |
| Efectivo esperado final de Postres/Bebidas | 10750 |
| Contado final, diferencia con observación | 10740 / -10 |
| Flujo digital neto final | 13 |
| Ventas devengadas/cobradas netas | 10013 / 10013 |
| Costo histórico neto de mercadería | 3000 |
| Efectivo esperado de Rotisería | 1000 |

La devolución revierte los cobros según la regla vigente, sin alterar costos originales.
Ambas jornadas se cierran. El puente queda conciliado y la diferencia de arqueo sigue
visible como alerta, no como gasto ni ajuste. El JSON con entradas verificadas e informes
se genera en `.audit-artifacts/jornada-financiera.json` y se publica como artefacto de
ambos trabajos de CI. Las capturas de Edge documentan la presentación de fuentes.

## Compatibilidad y registros WhatsApp

No se agregan columnas/tablas ni se cambian versiones de esquema o marcadores.
Las bases POS ficticias anteriores se leen con sus tablas opcionales disponibles;
sin diario se conserva el flujo del libro POS y se declara su fuente, sin inventar
arqueos o aperturas. Los diagnósticos no crean esquemas ni completan históricos.
No se elimina ningún modelo ni registro existente.

La rama WhatsApp `f6ce5534ed5506044155627b028b628f173ffd5b` se inspeccionó mediante
objetos Git. Sus aperturas globales/cortes por máximos de IDs y sección opcional no
son equivalentes a jornadas/medios POS. El diagnóstico detecta presencia y faltantes,
pero `integracion_habilitada` permanece false incluso si los importes parecen coincidir.

Procedimiento autorizado en esta fase: crear datos ficticios de ambos esquemas,
conservar origen/ID/SHA, consultar el diagnóstico, revisar diferencias y demostrar
que las lecturas no escriben. Cualquier propuesta de importación futura necesita
receptor, medio, moneda, responsable, instante/corte con zona y comprobante inequívoco,
además de aprobación individual. No hay importador operativo en esta propuesta.

## Decisiones pendientes de autorización

No se decide ni ejecuta: reparto de gastos/compras sin pagador, política nueva de
descubiertos, compensación económica por pagos de delivery desde otra sección,
conversión entre saldo agregado y físico/digital, equivalencia entre deuda de apertura
y deuda legada, conversión de monedas, regularización de faltantes/sobrantes o uso
del último saldo WhatsApp como apertura POS.

Alternativas futuras: identificar cada origen con comprobante y mapearlo individualmente;
mantener libros separados con cobertura parcial; o diseñar un corte nuevo aprobado
en una copia ficticia. Elegir un saldo o compensar diferencias por semejanza de monto
no es una alternativa automática válida. Los pendientes permanecen visibles.

## Pruebas y límites

Se conservan los 604 casos de referencia sin modificar ni reducir. Los casos nuevos
cubren fuentes, compras y reintegros, custodia física/digital, rendición, saldo unificado,
aperturas por franja y días consecutivos, arqueos/alertas, fiados/abonos, devoluciones,
fallos de escritura, caída de proceso, concurrencia, idempotencia, compatibilidad y Edge.

Resultados finales, SHA probado, comparación de JUnit, omisiones y artefactos se
registran en el cuerpo del PR para no cambiar el SHA solo por agregar resultados.
Las tandas focales se solapan y no se suman como casos únicos.

Se vigila expresamente el timeout intermitente de apertura de acceso en Edge registrado
en #40. No se modifican sus pruebas, esperas ni aserciones; cualquier nueva incidencia
se informa incluso si su repetición aprueba. Continúan las advertencias heredadas
de FastAPI y las limitaciones de rendimiento/validación productiva de etapas anteriores.

No se abren bases reales, no se modifican instalaciones ni bot, no se importan movimientos
reales, no se reconstruyen saldos, no se fusiona main y no se habilita producción.
