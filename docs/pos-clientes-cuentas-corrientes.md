# Clientes y Cuentas Corrientes en Abadion Entrenamiento

Implementación del [Issue #14](https://github.com/NicoNunezFM/contabilidad-bebidas-postres/issues/14) sobre el PR #13. Ventas y Administración pueden registrar y buscar clientes, confirmar fiados, ver saldos y abonar. Administración puede corregir un abono con motivo. Las ventas saldadas siguen aceptándose sin cliente y el estado del pedido conserva su circuito.

## Decisiones técnicas

- Cada alta genera un ID entero persistente. El nombre o apodo es obligatorio. Teléfono y referencia son opcionales. Pueden coexistir homónimos y se seleccionan por ID. La búsqueda admite los cuatro datos.
- Las tablas nuevas identifican al cliente, enlazan la venta y agrupan los eventos de una solicitud. Los importes efectivos se registran en el libro existente. El historial de la ficha se deriva de las ventas, sus eventos y movimientos. Cada importe de un abono se imputa a una venta por fecha ascendente y luego por ID. El reparto por sector conserva el prorrateo vigente e incluye devoluciones y pagos anteriores.
- La vista previa muestra las ventas y secciones que recibirían el importe. Al confirmar, SQLite vuelve a calcularlo bajo reserva de escritura. Rechaza una vista desactualizada, un monto superior al saldo o una referencia de pago duplicada. El UUID permite reintentar la operación y todos sus movimientos se confirman juntos. La referencia global se reserva en el primer movimiento y se muestra en la operación agrupada.
- El receptor real recibe el cobro en la caja o cuenta seleccionada. La atribución por sección sigue al saldo de cada venta. El diezmo se reconoce con la fecha del movimiento real de cobro en el libro existente. Los traslados siguen en el flujo de transferencias internas.
- La corrección registra contramovimientos al receptor original en la fecha corriente, conserva el abono y audita autor y motivo. Si ya hubo un reembolso vinculado a parte del abono, se rechaza la corrección global para evitar una doble reversión. Los cierres anteriores se conservan.
- Los fiados de texto aparecen como históricos sin vincular y conservan su saldo y abonos por venta. El alta de un homónimo jamás los incorpora a una ficha. Los reintentos de ventas previas conservan su formato. No hay límite automático de crédito.
- La operación es local a Entrenamiento. La pantalla de cocina, el stock, el menú, los precios, los roles y las dos cajas siguen usando sus rutas existentes.

## Actualización segura en Windows

1. Revisá el PR y sus pruebas. Ensayá primero en una copia ficticia descartable. Detené el servidor de Entrenamiento con Ctrl+C y cerrá sus pestañas.
2. Anotá el commit anterior del código con `git rev-parse HEAD` y verificá que el directorio del código esté limpio. Con el servidor detenido, copiá la carpeta de práctica completa `%LOCALAPPDATA%\Abadion\Entrenamiento` a un directorio local fechado. Confirmá que incluye `abadion-entrenamiento.db` y `catalogo-entrenamiento.json`. Si hay archivos auxiliares de SQLite, verificá primero que el proceso se haya detenido correctamente.
3. Descargá `feature/abadion-clientes-fifo` y seleccioná el commit aprobado con `git switch --detach <SHA-aprobado>`. Usá el entorno virtual de práctica para actualizar los requisitos.
4. Con el servidor detenido, ejecutá `python scripts/abadion_entrenamiento.py activar-clientes` desde ese entorno. El comando valida el marcador de Entrenamiento, reserva escritura, guarda una copia SQLite con prefijo `abadion-entrenamiento.pre-clientes-` y agrega el esquema en la misma transacción. Es idempotente. El comando `reiniciar` borra prácticas y queda fuera de la actualización.
5. Iniciá con `python scripts/abadion_entrenamiento.py servir` y abrí `http://127.0.0.1:8060/pos/`. Confirmá que se pueda buscar un cliente y que el historial anterior siga visible. Probá en la copia ficticia con dos homónimos, dos ventas para uno, un abono inferior al saldo total y un receptor de la otra sección. Contrastá la vista FIFO con las dos cajas y el informe de contabilidad. Probá una corrección desde Administración y revisá la trazabilidad.
6. Para volver, detené el servidor, conservá una copia de la carpeta actual, restaurá la carpeta completa del paso 2 y volvé al commit anotado. Las operaciones posteriores al respaldo quedan en la carpeta desplazada.

## Validación

El PR documenta la ejecución SQLite/API, Microsoft Edge y Node. Las nuevas pruebas verifican homónimos, búsqueda, un fiado que exige ID, prioridad por fecha e ID, sectores cruzados con receptor real, pagos previos, devoluciones, vista desactualizada, UUID concurrentes, rollback intermedio, permisos, corrección, diezmo y respaldo restaurable.

Queda por comprobar la comodidad de búsqueda y cobro en la tablet física. Si se decide reconciliar fiados históricos con clientes registrados, hace falta acordar cómo se identifica al titular y cómo se audita la vinculación. Una corrección con reembolsos previos requiere revisión manual.
