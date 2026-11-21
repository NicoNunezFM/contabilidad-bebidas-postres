# Issue #15 · Pedidos y envíos en Abadion Entrenamiento

## Registro y confirmación de la venta

1. Armá el carrito táctil y validá los productos. Elegí **Guardar pedido sin venta** para registrar mostrador o WhatsApp, retiro o envío, dirección si corresponde, observaciones e importe de reparto.
2. En **Pedidos**, abrí su ficha para ver el estimado, las líneas y el historial. El equipo puede avanzar la preparación mientras el pedido esté sin venta. Administración puede cancelar con motivo. La entrega con importe pendiente exige reconocer el importe vigente.
3. Abrí **Confirmar venta del pedido**. El POS muestra la cotización actual y conserva el estimado original. La confirmación usa las líneas guardadas y vuelve a comprobar precios, personalizaciones y stock. Si el total cambia, volvé a abrir la confirmación y validá el nuevo importe.
4. La venta saldada puede ser anónima. Para dejar saldo, elegí un cliente registrado y usá el circuito de fiado del PR #16. Las ventas rápidas siguen disponibles desde el checkout.

Crear o avanzar un pedido guarda datos operativos y deja intactos el stock, las ventas, el libro de cobros, el fiado, el diezmo y las cajas. Confirmar una venta actualiza esos registros según los medios de pago elegidos. La entrega y la cancelación operativa tienen su propio historial. Si ya hay venta, la devolución o anulación contable se gestiona desde el historial de ventas.

## Identificadores, persistencia y reintentos

Cada pedido tiene un identificador propio y una referencia opcional y única a la venta. Los identificadores anteriores se preservan junto con su vínculo y el historial. Los pedidos previos a la venta guardan las líneas originales y un estimado para consulta. La confirmación registra la venta, el stock y el vínculo en la misma transacción SQLite con `BEGIN IMMEDIATE`. El UUID permite recuperar el resultado de una confirmación repetida. Una segunda solicitud concurrente con otro UUID recibe un conflicto. Los cambios operativos validan versión, UUID y permisos y dejan constancia de quién y cuándo los hizo.

## Contabilidad del envío

- El envío propio se contabiliza como un concepto separado de Comidas. Forma parte del total de la venta y se revierte cuando se devuelve toda la mercadería.
- Los fondos del repartidor se registran por cuenta receptora, con recepción, liquidación y reembolso. Un pago directo al repartidor queda como constancia. Estos importes se excluyen del ingreso propio y del diezmo.
- El efectivo confirmado fuera del local reduce el saldo de la venta y queda en tránsito. La rendición transfiere el importe a una jornada física abierta. El traspaso de custodia conserva el cobro original.
- La confirmación de entrega comprueba por separado el saldo propio y lo pendiente del envío al repartidor. Para un pedido sin venta usa el estimado guardado. Confirmar la entrega no genera un movimiento contable.

## Matriz de validación

| Caso | Evidencia |
| --- | --- |
| WhatsApp anónimo, preparación y conversión en una venta | API y Microsoft Edge |
| Alta sin venta, conciliación, stock y diezmo | SQLite y API |
| Cancelación con permiso, motivo y bloqueo de conversión | API |
| Confirmación saldada, fiado con cliente y rechazo de fiado anónimo | API |
| Stock insuficiente, cambio de precio, reintentos y confirmaciones concurrentes | API |
| Migración de identificadores, historial previo y UUID | SQLite |
| Copia restaurada y consulta del pedido convertido | SQLite y API |
| Regresión de ventas, caja física, envíos, FIFO, diezmo y cierres | SQLite/API y Edge |
| Sintaxis JavaScript del POS | `node --check` |

La ejecución del commit probado y los resultados se registran en el PR #17.

## Ensayo de actualización y recuperación sobre el PR #16

1. Ensayá en una instalación ficticia descartable en Windows. Detené el servidor de Entrenamiento y verificá que el checkout de práctica corresponde al PR #16. Guardá el SHA anterior y respaldá la carpeta completa `%LOCALAPPDATA%\Abadion\Entrenamiento` con la base y el JSON del catálogo.
2. Seleccioná en el checkout de práctica el SHA aprobado del PR #17. Con el Python del entorno virtual de práctica, ejecutá `python -m pip install -r requirements.txt` y `python -m pip check`. Verificá zona horaria y paquete con `python -c "from zoneinfo import ZoneInfo; import tzdata; print(tzdata.__version__, ZoneInfo('America/Argentina/Buenos_Aires'))"`.
3. Ejecutá `python scripts/abadion_entrenamiento.py activar-fondos-envio`. El comando reserva escritura, crea un respaldo con SQLite Backup API y prepara el seguimiento y los fondos auxiliares. En una base del PR #17 anterior también migra identificadores, estados, historial y respuestas de reintento. Una segunda ejecución conserva el mismo estado.
4. Verificá `PRAGMA integrity_check` y `PRAGMA foreign_key_check` en la copia. Iniciá con `python scripts/abadion_entrenamiento.py servir` y probá en Edge desde loopback. Compará saldos, stock, ventas e historial y ensayá el registro de un pedido sin venta, su preparación y conversión.
5. Para volver al PR #16, detené el servidor, preservá la carpeta posterior con otro nombre, restaurá la carpeta previa completa y volvé al SHA original. Para recuperar un respaldo posterior con pedidos, usá la versión del PR #17 que generó el respaldo. Verificá historial, ventas y saldos tras la restauración.
