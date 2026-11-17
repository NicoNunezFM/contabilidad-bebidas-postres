# Abadion POS · Etapa 6 · Caja diaria ficticia

La [etapa 7](pos-integracion-definitiva.md) integra esta caja diaria con reportes, cierres y diezmo sobre una copia ficticia nueva.

En Lo de Clau se cuenta el efectivo de Rotisería / Comidas y de Bebidas y Postres por separado. El POS será el canal principal para ventas y WhatsApp seguirá como complemento. La base de esta etapa es el PR #5 en `9e50636`, con el [puente de conciliación ficticio](pos-integracion-contable.md).

## Operación por caja

1. Entrá a **Caja diaria** en el POS y abrí cada caja que vaya a recibir o entregar efectivo. Registrá el fondo inicial físicamente contado, incluso si es cero. Cada caja admite una jornada por fecha local de Argentina.
2. Registrá los cobros con el receptor que tomó el dinero. Un pedido mixto puede cobrarse en cualquier caja física abierta o cuenta digital. La sección devengada sale de las líneas del pedido. Los fiados y las cuentas digitales se consultan en los informes del POS.
3. Desde administración, registrá un gasto efectivamente pagado desde una caja, un retiro o un aporte, cada uno con motivo. La distribución entre cajas usa la transferencia del libro POS, requiere ambas cajas abiertas y conserva los límites del saldo POS y la distribución pendiente. Las cuentas digitales se transfieren desde **Cajas simuladas**.
4. Compará el efectivo esperado con el conteo físico y guardá el arqueo, con motivo si hay diferencia. Cada movimiento nuevo requiere un nuevo conteo, incluso cuando su efecto neto sea cero. Se pueden consultar intentos de conteo anteriores en la auditoría.
5. Cerrá la caja correspondiente. El rol de ventas puede cerrar si el último arqueo vigente da cero. Cuando hay un faltante o sobrante, administración ve el conteo y su motivo y autoriza al confirmar el cierre con su propia sesión. El historial conserva los responsables del conteo y del cierre.

**Efectivo esperado** es la suma de apertura, cobros y abonos físicos, reembolsos físicos con signo negativo, gastos pagados en efectivo, retiros, aportes y transferencias físicas netas. **Diferencia** es contado menos esperado. Una diferencia se conserva con signo y motivo en el cierre. El cierre diario guarda una foto del efectivo y el arqueo en su propio registro. El corte acumulado del POS, las ventas, la distribución pendiente, los cierres semanales y mensuales y el diezmo siguen sus flujos contables específicos.

## Permisos, transacciones y auditoría

| Rol | Operaciones diarias |
| --- | --- |
| Ventas | Abrir, arquear, cerrar sin diferencia y consultar el estado, historial y auditoría de las dos cajas. |
| Administración | Las mismas operaciones, más cierre con diferencia, gasto, aporte, retiro y distribución entre cajas. |

Las escrituras del POS que mueven efectivo y las de caja diaria se serializan con `BEGIN IMMEDIATE` en el mismo archivo SQLite. Si falta abrir un receptor físico o si su jornada ya cerró, se rechaza toda la operación, incluidos stock, cobros y movimientos de la otra caja. Las dos patas de una transferencia física quedan juntas o se revierten juntas. Si una venta gana la carrera contra el cierre, invalida el arqueo. Si gana el cierre, se rechaza el cobro físico. Cada confirmación de caja diaria admite reintentos con el mismo UUID, usuario y datos. Se guarda fecha, hora con desplazamiento argentino, usuario, rol, motivo cuando corresponde e ID de movimiento POS para cada entrada física proveniente del libro.

El puente agrega `caja_diaria_centavos` al informe y verifica que los movimientos POS físicos posteriores a la activación estén vinculados por receptor e importe, y que el saldo guardado del cierre concuerde con el diario. `cuadrado` mide la integridad entre registros. Un faltante o sobrante contado y autorizado aparece en el arqueo aunque los registros concilien. Las operaciones anteriores a la activación quedan disponibles en el POS legado o contable, según su origen. El fondo inicial se cuenta al empezar a usar caja diaria.

## Defaults de simulación pendientes de aprobar para producción

| Tema | Default probado |
| --- | --- |
| Fecha y turnos | Fecha de Buenos Aires. Si quedó una jornada abierta al cambiar el día, se puede arquear y cerrar esa jornada con la hora real. Antes de volver a mover efectivo hay que abrir la jornada de hoy. Un cierre es definitivo. No se arrastra el saldo ni se habilitan reaperturas o cierres parciales. |
| Autorización | Toda diferencia requiere motivo y confirmación de administración. Administración puede contar y cerrar la misma caja. Falta definir doble firma, tolerancias y permisos por caja o turno. |
| Gastos, aportes y retiros | Se registran en el diario físico con receptor explícito. Los gastos, compras o movimientos legados quedan fuera del arqueo porque sus datos carecen de medio o de caja física verificable. Falta definir identificación compartida, contabilización, reversión y captura complementaria desde WhatsApp. |
| Distribución y depósito | En esta copia se admiten distribuciones entre dos cajas físicas o entre dos cuentas digitales. Para producción falta definir traslados de cambio ajenos a la distribución, depósitos a banco, reembolsos con caja cerrada y ajustes posteriores al cierre. |
| Históricos y habilitación | Empezar desde una fecha acordada con fondos verificados. Aprobar el circuito operativo y el traslado desde simulación antes de habilitar ventas reales. |

## Prueba manual en localhost

1. Prepará una copia nueva desde un POS 4 o un puente ficticio de etapa 5. Elegí nombres ficticios.

   ```powershell
   python scripts/puente_pos_ficticio.py copiar pos5-ficticio.db pos6-ficticio.db --caja-diaria
   python scripts/puente_pos_ficticio.py servir pos6-ficticio.db
   ```

2. Abrí `http://127.0.0.1:8000/pos/`. Iniciá sesión de ventas y abrí Rotisería con $300 y Bebidas y Postres con $100. En un pedido mixto, cobrá efectivo en Rotisería y un pago digital en Bebidas y Postres, y dejá una parte fiada. Revisá que solo el cobro físico modifique el esperado de Rotisería.
3. Como administración, probá un gasto efectivo, un retiro, un aporte y una distribución física inferior al pendiente. Abrí **Totales de efectivo** y verificá los signos en cada caja.
4. Como ventas, guardá un arqueo exacto en Bebidas y Postres y cerralo. Confirmá que Rotisería siga abierta. Probá cobrar allí y verificá que un cobro a la caja cerrada se rechaza.
5. En Rotisería, guardá un conteo con diferencia y motivo. Verificá que ventas vea el pedido de autorización. Iniciá sesión como administración, cerrá la caja y revisá importe, diferencia, motivo y responsables en **Ver historial** y **Ver auditoría**.
6. Revisá `/pos-api/simulacion/conciliacion` como administración o ejecutá `python scripts/puente_pos_ficticio.py conciliar pos6-ficticio.db`. Identificá por separado el saldo diario físico, el devengado, los receptores digitales, los importes a distribuir y los cierres del legado.

GitHub Actions ejecuta las pruebas SQLite/API en Linux y las del POS en Edge en Windows. Para el ensayo local, usá `NEGOCIO_DB_PATH` con un archivo temporal ficticio, `PYTHON_DOTENV_DISABLED=1` y `POS_TEST_BROWSER` con la ruta de Edge. Las pruebas de Edge también requieren `websocket-client`.
