# Costos históricos y margen del POS — Fase 2.2

Base: PR #39, `4c312768528207d774247be42d075f1be8727d33`.
Rama propuesta: `feature/abadion-costos-historicos-pos`, PR en borrador contra
`fix/abadion-compras-atomicas`. No habilita producción.

## Explicación didáctica

Vender una bebida por $100 con un costo calculado de $30 deja un margen bruto
estimado de $70. Si mañana la compra cuesta $50, esa venta sigue guardando $30:
el nuevo costo sirve para ventas futuras, no para reescribir el pasado.

El POS toma una fotografía del costo cuando confirma la venta. Guarda los importes,
la cantidad y cómo los obtuvo. La fotografía es inmutable. Si la información está
incompleta, guarda explícitamente el faltante: desconocido no significa gratis.
El costo de catálogo de un adicional puede ser conocido, mientras el producto base
se valora por una estimación. La suma conserva el grado de certeza más débil.

Si se devuelve una unidad, se revierte una parte del costo original. No se consulta
el precio actual. Los abonos de un fiado cambian el dinero cobrado, pero no vuelven
a vender el producto ni a generar su costo.

## Modelo y contratos

`src/pos_costos_historicos.py` contiene captura, esquema, lectura de movimientos y
agregación. `src/pos_simulacion.py:registrar_venta_simulada` llama a `capturar`
después de insertar la venta y antes de pagos/stock/confirmación. Incluye conversiones
de pedidos porque reutilizan el mismo confirmador. Cotizar no captura ni escribe.

`pos_costos_lineas` tiene clave primaria `(id_venta, linea)`, FK a la venta y:

| Campo | Significado |
| --- | --- |
| cantidad | Unidades de la línea confirmada, después de separar precios promocionales |
| estado | conocido, estimado, parcial o desconocido |
| costo_unitario | Decimal serializado como TEXT, NULL si falta alguna parte |
| costo_total_centavos | Total completo en centavos, NULL si falta alguna parte |
| costo_parcial_centavos | Componentes valorados, incluidos los estimados; nunca equivale por sí solo al costo completo |
| fuente / metodo | Origen de valoración y regla de composición/redondeo |
| version_receta | Versión de producción o receta consultada, cuando existe |
| version_modelo | 1; independiente de los marcadores de esquema POS existentes |
| detalle | JSON con componentes, estados, evidencia, receta/estimación y personalizaciones faltantes |

Los promedios conservan IDs, fechas, cantidades y precios de compras fuente; la última
producción conserva ID, fecha y versión. La alternativa por receta guarda el contenido
consultado y su desglose valorado. No hay vínculo nuevo de lote de inventario a venta.

Se conservan las fórmulas existentes, incluida su aritmética REAL de entrada. La nueva
captura serializa el resultado unitario con Decimal; compone componentes y redondea
el total de cada línea a centavos con HALF_UP. No es una migración monetaria ni un
cambio a FIFO/PMP de inventario. Valores no finitos, negativos o fuera del rango
admitido no se aceptan como costos conocidos. Un cero explícito válido se conserva.

Triggers rechazan UPDATE y DELETE de capturas; no hay UPSERT ni reemplazo. Las
reversiones son eventos nuevos de unidades, no modificaciones de la fotografía.
Se verifica que cada INSERT haya guardado una fila, incluyendo rechazo silencioso
por un trigger. Los controles no son una barrera contra un administrador que edite
el archivo SQLite o elimine sus restricciones.

## Matriz de fuentes y cobertura

| Categoría/componente | Fuente existente y método conservado | Certeza | Información necesaria si falta |
| --- | --- | --- | --- |
| Bebidas | Promedio ponderado de últimas 3 compras no anuladas, por cantidad | Estimado; se congela al vender | Al menos una compra válida del producto; trazabilidad de lotes para certificar costo real vendido |
| Postres con producción | Costo unitario de última producción registrada por nombre | Estimado: costo registrado, sin asignación de lote vendido | Producción compatible por nombre y vínculo a lote si se requiere certeza de consumo |
| Postres sin producción | Receta activa, cantidades/rendimiento + fijo por unidad; insumos por últimas 3 compras válidas | Estimado si completo, parcial/desconocido si faltan precios | Receta aplicable, cantidades, rendimiento y compras de cada insumo |
| Postres chicos/grandes del menú | Solo se usa una fuente que el motor existente pueda identificar | Desconocido si nombre/composición no coinciden | Correspondencia explícita de producto/presentación con receta y rendimiento; no se adivina por el nombre |
| Adicional de catálogo | `adicionales_catalogo.costo_unitario`, por unidad de producto | Componente conocido cuando está declarado, incluso cero | Costo declarado del ID de adicional; el recargo de venta no sirve como costo |
| Rotisería | No hay fuente de costo equivalente en el motor existente | Desconocido | Composición/rendimiento o costo confiable por producto y unidad |
| Cheddar/huevo por destino, papas dobles | Hay precios comerciales pero no composición de costos | Desconocido; invalida completitud de línea | Identificación, cantidad/unidad y costo de insumos de la preparación |
| Ingredientes quitados | Texto sin gramajes ni vínculo inequívoco a receta | Línea parcial/desconocida; no se infiere ahorro | Correspondencia ingrediente/receta y cantidad retirada |
| Observaciones libres | No se puede inferir impacto material del texto | Conservadoramente parcial/desconocido | Normalización explícita de modificaciones sin interpretar texto automáticamente |
| Promociones/descuentos | Se conserva precio efectivamente cobrado por línea | No cambian cantidad ni costo unitario | Sin nueva regla comercial |
| Envío | Fuera de la mercadería del informe | No se afirma margen de delivery | Costos de logística serían otro alcance |
| Venta anterior sin captura | No se reconstruye | Desconocido | No se completa con precios actuales ni mediante backfill automático |

Ninguna fuente actual certifica el lote base vendido: por eso las líneas completas
actualmente resultan estimadas, aunque incorporen componentes adicionales conocidos.
El estado conocido no se utiliza para promover una estimación a costo real.

## Una sola transacción

El dueño sigue siendo `transaccion_simulacion`: abre BEGIN IMMEDIATE y confirma
al salir correctamente. La captura y los resolutores reutilizan esa conexión;
no abren otra, ni hacen commit, rollback o close. La creación aditiva del esquema
también participa de la transacción. Si falla costo, pago, stock o COMMIT, el contexto
revierte venta, captura, pagos y stock. Esto no toca las escrituras de compras del #39.

La clave idempotente sigue siendo usuario/UUID de venta. Un reintento devuelve la
venta original, sin costearla otra vez; un payload distinto con esa clave se rechaza.
BEGIN IMMEDIATE serializa escritores antes de leer las fuentes. No hay garantía
contra edición manual de archivos, hardware defectuoso o ejecución de código viejo.
Fundamento: [transacciones SQLite](https://www.sqlite.org/lang_transaction.html)
y [restricciones diferidas al COMMIT](https://www.sqlite.org/foreignkeys.html#fk_deferred).

## Reversiones, períodos y fiados

Los eventos de anulación/devolución y `pos_unidades_devueltas` ya registran unidades
por línea en la transacción existente. El informe los aplica sobre la captura, por
fecha local del evento (UTC menos tres horas), conservando descuentos originales.
Una anulación después de una devolución solo revierte las unidades restantes.

Para centavos indivisibles se usa prorrateo acumulado del total capturado: la diferencia
entre lo asignado a las unidades devueltas acumuladas antes y después de cada evento.
Por ejemplo, $60,01 para dos unidades revierte $30,01 y luego $30,00. El total devuelto
coincide exactamente con el original, sin residuos ni consultas al costo vigente.

Efectivo, transferencia y fiado comparten la misma captura; pagar no es una segunda
venta. Ni captura ni informe insertan gastos, deudas o movimientos de caja. Las
reversiones financieras conservan las reglas existentes del POS.

Las ventas legadas carecen de eventos de reversión fechados comparables: se conservan
sus snapshots y la exclusión vigente de filas anuladas. Su histórico por período es
el libro vigente, no una reconstrucción del estado que existía antes de una anulación.
Esta limitación se incluye en `alcance`; no se promete inmutabilidad de ingresos ante
reversiones comerciales posteriores, sino de los costos capturados de ventas nuevas.

## Reportes y cobertura

`reportes.rentabilidad_historica_por_periodo` es una lectura consistente y sin DDL.
Combina dos libros disjuntos, con `origen=pos/legado`; no inserta ventas legadas a
partir del POS ni suma cabeceras de `ventas_operaciones` con sus líneas. Los adicionales
legados se suman una vez. Las ventas anteriores sin snapshot siguen desconocidas.
El POS conserva categoría y sección del pedido guardado, aunque cambie el catálogo.

`resumen_por_periodo` y `pos_contabilidad.calcular_periodo` incluyen el campo aditivo
`rentabilidad_historica`. `rentabilidad_producto` incorpora unidades/ingresos/costos
POS y expone `historico_consolidado` y `cobertura_pos`; `rentabilidad_categoria` expone
`historico_consolidado`. Las proyecciones antiguas a costo actual siguen identificadas
como estimadas y no sustituyen el nuevo resumen histórico. Rotisería está cubierta
por el nuevo informe por sección; no se inventa un motor de recetas para ella.

En el informe contable integrado se respeta también el ID de corte POS y se excluye
el libro de ventas legadas anterior al corte. La consulta histórica independiente
combina ambos libros por período completo. Los campos `id_evento_minimo` e
`incluye_legado` hacen explícita esa diferencia. No se vuelven a sumar ventas previas
al corte que casualmente compartan su misma fecha.

Cada sección muestra costos y margen completos solo cuando todas sus líneas tienen
costo completo. Incluye estados y porcentaje de cobertura por unidades absolutas
de movimientos (ventas y reversiones), evitando divisiones por cero en períodos netos
nulos o negativos. No es cobertura por importe ni certificación de lote. Sin movimientos
el porcentaje es NULL. El parcial valorado y el costo de líneas cubiertas tienen nombres
explícitos; si falta alguna parte, el margen total es NULL, nunca cero.

La pantalla existente de Contabilidad muestra cobertura por sección, margen desconocido
cuando falta información y aviso si incluye estimaciones. No agrega administración de recetas.

| Magnitud | Qué mide | Qué no se cambia |
| --- | --- | --- |
| Resultado devengado existente | Ventas devengadas menos compras/gastos del período, según reglas vigentes | Cierres, diezmo y reglas contables |
| Flujo/cobros | Dinero recibido/reembolsado; el fiado puede devengarse antes de cobrarse | Cajas, pagos, deuda, reparto |
| Margen bruto histórico nuevo | Ingreso de mercadería menos costo capturado de mercadería vendida/revertida | No resta compras otra vez ni pretende ser utilidad neta |

## Compatibilidad

| Base ficticia | Lectura | Venta nueva |
| --- | --- | --- |
| Legada sin POS | Usa snapshots disponibles; no crea tablas | Contrato legado sin cambio |
| POS 4 anterior, sin tabla de costos | Ventas anteriores desconocidas; no escribe al consultar | Crea tabla/triggers en la transacción y captura solo la nueva venta |
| POS 4 con capturas | Lee fotografía y reversiones | Añade captura por cada línea; no reemplaza anteriores |
| Esquema POS incompatible o candidata bloqueada | Se mantienen rechazos previos | No elimina marcadores, bloqueos ni migra instalaciones |

No cambia `user_version`, application_id, preparación, activación ni respaldo/recuperación.
Respaldos SQLite completos incluyen la tabla nueva; su recuperación sigue las validaciones
existentes. Volver a código anterior y continuar escribiendo no conserva estas garantías:
ese código no captura costos nuevos. No se certifica downgrade con continuidad de escritura.

## Validación y límites pendientes

El archivo nuevo `tests/test_pos_costos_historicos.py` cubre fuentes, faltantes, cero
explícito, receta parcial/completa, última producción, cambios posteriores, adicionales,
personalizaciones, promociones, efectivo/transferencia/fiado/abono, devoluciones/anulación,
períodos separados, concurrencia/idempotencia, lectores, rechazo de INSERT y COMMIT,
rollback de DDL, base anterior, informes disjuntos y cobertura visible en Edge.
No se modifican ni reducen los 570 casos de referencia del #39.

Los resultados definitivos de las suites completas, SHA validado, JUnit y omisiones
se registran en el cuerpo del PR. No se crea otro commit solo para repetir resultados
que volvería a cambiar el SHA probado. Las tandas focales se solapan con las completas.

Riesgos conservados: fuentes incompletas de menú y Rotisería, costos REAL de origen,
sin identificación de lote, sin reconstrucción de inconsistencias históricas, sin crédito
de compras de insumos. La consulta recorre movimientos para respetar reversiones acumuladas;
volúmenes comerciales altos necesitan medir rendimiento e indexar/consultar de forma incremental
sin alterar resultados. No se afirma una certificación contable o de hardware.

Solo se utilizan bases ficticias temporales. Ninguna instalación, base real, bot de
WhatsApp, main o configuración productiva se modifica; no se fusionan ramas.
