# Inspección previa y contrato financiero — Fase 2.3

Base inspeccionada: PR #40, `91f293b8b5c303170626b202cdd72cc6c33ba718`.
La cabeza remota conserva ese SHA. Rama lateral inspeccionada sin integrarla:
`feature/comandos-whatsapp-v1`, `f6ce5534ed5506044155627b028b628f173ffd5b`.
Este documento se escribió antes de modificar código de aplicación.

## Fuentes autorizadas y matriz de efectos

| Concepto / operación | Fuente autorizada en la base | Efecto y prohibición de duplicar |
| --- | --- | --- |
| Venta devengada, devolución, anulación | Pedido guardado + unidades revertidas; deltas de `pos_eventos_simulados` | Ingreso de mercadería por sección económica. No sumar cobro como segunda venta |
| Venta cobrada / abono / reintegro | `pos_movimientos_simulados` ligados a venta; deltas de cobrado atribuido | El abono disminuye cuenta por cobrar, no vuelve a devengar ni costear |
| Cuentas por cobrar | `pos_cobros.estado_cuenta`, con imputación existente por sección | Devengado menos cobrado; ficha de cliente es vista, no otro libro de ingresos |
| Efectivo físico | Apertura y eventos de `pos_diario_caja`, por jornada y caja | Movimientos POS vinculados por `id_movimiento_pos` ya están dentro; nunca sumarlos otra vez |
| Disponibilidades digitales POS | Movimientos del receptor menos pagos netos de compras asociados | Flujo registrado, no saldo bancario certificado: no existe extracto/saldo inicial digital identificado |
| Efectivo de productos en tránsito | Receptor `_efectivo_en_transito`, rendiciones y reembolsos | Custodia de cobros de productos; rendir mueve tránsito a caja, sin nuevo cobro ni devengado |
| Delivery sencillo: recepción, entrega, devolución | `pos_delivery_movimientos`; espejo financiero identificado por `id_movimiento` | El espejo ya está en movimientos/diario. Custodia de envío no es venta ni gasto |
| Reparto anterior, recepción/liquidación/reembolso/directo | `pos_fondos_reparto` | Libro separado que no integra movimientos POS; no importar ni sumarlo como venta. Retención directa no es saldo propio |
| Compra de producto, contado o financiada | `compras` + `pos_costos_contables`; `pos_compras_caja` para pagador/pago; deuda para financiado | Stock/costo, pago y deuda son dimensiones distintas. Diario de compra es espejo del pago, no aporte/retiro económico adicional |
| Compra de insumo | Compra + gasto + recibo atómico #39 | No agregar otro gasto ni inferir pagador físico/digital que no está registrado |
| Gasto legado | `gastos`, trigger de costo contable | Tiene sección pero no necesariamente receptor de pago. No inventar salida de una caja específica |
| Gasto físico POS | Evento `gasto` del diario | Una salida y un gasto; no insertar otro gasto legado automáticamente |
| Aporte / retiro | Diario POS con motivo; en legado `movimientos_caja` separado | Cambia disponibilidad patrimonial, no ventas. Espejos de compras se excluyen de aportes/retiros del informe |
| Transferencia entre receptores | Dos movimientos opuestos de un evento POS, medio NULL | Conserva dinero y sección económica; no genera venta/cobro/gasto |
| Distribución entre secciones vigente | Transferencia limitada a distribución pendiente de cobros atribuidos | Regulariza quién conserva un cobro ajeno; no autoriza préstamos ni gastos cruzados nuevos |
| Apertura / diferencia / arqueo / cierre | Diario y resultado guardado, revisión de efectivo, observación y alerta | Apertura no es ingreso; arqueo y diferencia son controles, no ajustes automáticos |
| Saldo unificado optativo | `pos_saldos_iniciales` + movimientos + manuales no espejados - compras/deudas - custodia | Modelo agregado, no permite identificar físico/digital. No sumarlo al diario ni activarlo en instalaciones |
| Deudas de negocio | `cuentas_deuda_negocio`, movimientos y reservas; apertura unificada en libro específico | Obligación, reserva y pago no equivalen a gasto nuevo ni ingreso |
| Margen bruto | Capturas inmutables #40 menos reversiones originales | No es dinero en caja; costo desconocido sigue NULL; no duplica compras/gastos |
| Resultado financiero vigente | `pos_contabilidad.calcular_periodo`, con corte por ID y fecha | Preservar fórmulas de devengado/cobrado, compras/gastos y diezmo; no sustituirlas por margen bruto |
| Caja legada calculada | `caja.py`, movimientos, diezmo y reservas de deuda | Resultado calculado según su modelo; no certifica efectivo ni debe sumarse al POS |

Evidencia: funciones de `src/pos_caja_diaria.py`, `pos_saldo_unificado.py`,
`pos_cobros.py`, `pos_delivery.py`, `pos_envios.py`, `pos_compras_caja.py`,
`pos_clientes.py`, `pos_contabilidad.py`, `pos_costos_historicos.py`, `pos_puente.py`,
`caja.py`, `gastos.py`, `compras.py`, `movimientos_caja.py`, `deudas_negocio.py`,
`cierres.py`, en el SHA de base indicado.

## Hallazgos y correcciones delimitadas

1. `pos_delivery.disponible_receptor` resta todos los pagos digitales de compras,
   incluidos reintegros positivos, sin cambiar signo. Debe usar egreso neto.
2. `pos_simulacion.transferir_simulado` toma saldo del libro de cobros, que no descuenta
   pagos de compras ni gastos del diario. Debe cotejar disponibilidad autorizada sin
   contar custodia de terceros. La API solo permite distribución entre secciones;
   se ampliará a receptores distintos de la misma sección con dos patas netas cero.
3. El diario concilia del movimiento al espejo pero no detecta todos los espejos
   huérfanos/incompatibles ni estados de apertura/cierre. Agregar lectura de diagnóstico,
   sin cambiar importes ni cerrar jornadas automáticamente.
4. Los modelos de custodia y los pagos sin receptor requieren cobertura explícita:
   mostrar diferencias/advertencias en lugar de declarar un saldo global certificado.

Se mantienen apertura propuesta entre 10:00 inclusive y 12:00 exclusive, ingreso
manual fuera de la franja, diferencias de apertura guardadas, cierre con observación
y alerta persistente, y motivos obligatorios para aportes/retiros. No se sustituye
ningún modelo ni se decide una política nueva de descubierto, compensación entre
secciones o imputación de gastos sin pagador.

## Rama WhatsApp: integración bloqueada

La rama lateral agrega `saldos_iniciales_caja` con monto REAL, fecha local sin zona
y cuatro máximos de ID (ventas, compras, gastos, movimientos). Usa `rotiseria` donde
el POS usa `comidas`; agrega sección opcional a movimientos legados. El último saldo
por sección actúa como reemplazo de corte, no como apertura diaria de efectivo.
No guarda receptor/medio, UUID/usuario POS, jornada, arqueo, custodia ni vínculo de
equivalencia a un movimiento POS. Los cuatro máximos no representan el corte POS.

No hay correspondencia inequívoca para importar. Procedimiento de ensayo: conservar
origen/ID y SHA; detectar registros sin sección y múltiples cortes; comparar importes,
fechas, moneda, comprobantes y medio con un inventario ficticio; proponer equivalencias
individuales documentadas y revisión humana. Ninguna similitud de fecha/monto autoriza
una importación. Esta fase solo produce diagnóstico de compatibilidad, nunca escrituras
ni selección automática del último saldo como apertura actual.
