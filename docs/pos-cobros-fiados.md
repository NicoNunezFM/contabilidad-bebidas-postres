# Cobros y fiados de Lo de Clau en Abadion POS

Esta etapa corre en SQLite ficticio con `POS_V1_SIMULACION=1` y una base marcada como POS 4. La rama parte de `98f7c09`, punta del [PR de auditoría #3](https://github.com/NicoNunezFM/contabilidad-bebidas-postres/pull/3), apilado sobre los PR #1 y #2. El libro del POS simulado es la única fuente de sus ventas, cobros, distribuciones y ajustes. Las ventas simuladas no se escriben en el libro legado de WhatsApp ni en los cierres generales.

## Flujo para probar

1. Prepará una base nueva con `python scripts/preparar_simulacion_pos.py RUTA_FICTICIA.db` y las dos claves de prueba. Configurá `NEGOCIO_DB_PATH` con la ruta exacta de esa base, `PYTHON_DOTENV_DISABLED=1` y `POS_V1_SIMULACION=1`. Para un ensayo local, ejecutá `python -m uvicorn api:app --app-dir src --host 127.0.0.1` y abrí `http://127.0.0.1:8000/pos/` desde Edge.
2. Iniciá sesión como **ventas**, armá un pedido mixto y validalo. Para un único medio podés elegir el receptor. La opción «Distribuir según la sección de cada producto» conserva el comportamiento anterior de los pedidos pagados con un único medio. En **Pago combinado**, agregá filas hasta cubrir el total. Escribí los importes en pesos con hasta dos decimales, por ejemplo `1500,50`.
3. Elegí **Pendiente / Fiado** y cargá un nombre o identificador ficticio. Podés dejar todos los pagos vacíos o registrar una parte. En **Historial simulado** abrí la venta para consultar el importe original, el cobrado, el saldo, las fechas y los pagos. **Registrar abono** permite completar el saldo con uno o más medios y receptores.
4. Con **admin**, revisá **Cajas simuladas**. Ahí aparecen el devengado, los cobros atribuidos, el fiado, los saldos por receptor y lo que cada sección tiene que recibir o enviar. Registrá una transferencia interna para liquidar parte o toda la distribución. En el historial podés devolver unidades de una línea o anular lo que queda de una venta.
5. Cerrá el período con un motivo. Probá una devolución o un abono posterior y verificá en el historial que aparezcan en el siguiente período. El resumen congelado se consulta como admin en `GET /pos-api/simulacion/cierres/{periodo}`.

### Copiar una simulación anterior

`python scripts/preparar_simulacion_pos.py COPIA_FICTICIA.db --desde-pos3 ORIGEN_FICTICIO.db`

El origen debe tener la marca del POS ficticio y el esquema 3. Se abre solo para lectura y se copia a un nombre nuevo. La copia conserva los IDs de venta, usuarios, fechas, anulaciones, cantidades y saldos. Los movimientos viejos pasan al período 1 con el receptor predeterminado según caja y medio. La migración reconstruye su historial contable sin volver a aplicar el stock. Para volver a la rama anterior, usá la base ficticia original.

## Regla aplicada en el ensayo

- **Devengado.** Cada línea, con sus extras, pertenece a la sección histórica del producto. Bebidas y postres usan las categorías de caja existentes. El resto se atribuye a Comidas, incluida Rotisería. Se conserva la sección de cada línea para que una reclasificación del catálogo no altere operaciones anteriores.
- **Recepción.** Cada pago tiene un medio (efectivo, transferencia o Mercado Pago), un receptor y un importe entero en centavos. Hay una caja de efectivo, una cuenta bancaria y una cuenta Mercado Pago ficticias por sección. Cualquier pago digital puede registrarse en cualquiera de las cuentas digitales y el efectivo puede entrar en cualquiera de las dos cajas. El nombre del medio indica cómo pagó el cliente. El receptor indica dónde quedó el dinero.
- **Imputación del cobro.** Para un pedido con devengado vigente total `T`, devengado de Comidas `C` y cobros netos acumulados `P`, se atribuyen `(P * C) // T` centavos a Comidas y los restantes `P - (P * C) // T` a Bebidas y Postres. Con `T = 0` ambas atribuciones son cero. Cada evento registra la diferencia entre la atribución nueva y la anterior. El saldo pendiente de una sección es su devengado vigente menos su cobro atribuido. El resultado final es independiente de cuántas veces pagó el cliente y de qué caja cobró.
- **Ejemplo.** Un pedido de $100,01 contiene $60,00 de Comidas y $40,01 de Bebidas y Postres. Si entran $50,00 en la cuenta bancaria de Bebidas y Postres, se atribuyen $29,99 a Comidas y $20,01 a Bebidas y Postres. Quedan por cobrar $30,01 y $20,00, respectivamente. Bebidas y Postres tiene $50,00 disponibles y $29,99 por enviar a Comidas. El saldo fiado de $50,01 no entra en ningún receptor.
- **Distribución.** `por_distribuir_centavos` es cobrado atribuido menos saldo disponible en los receptores de la sección. Positivo indica por recibir y negativo por enviar. Una transferencia interna usa un evento con dos movimientos opuestos, motivo, cuentas, operador y período. Se limita a lo que se debe distribuir y al saldo del origen. Los cobros y el devengado quedan iguales y la suma de saldos de ambas secciones se conserva.
- **Devoluciones y anulaciones.** Se restauran solo las unidades que efectivamente descontó el pedido y todavía no se devolvieron. Se reduce primero la deuda pendiente hasta el valor de la devolución. Si sobra un importe a reembolsar, se revierten cobros del más reciente al más antiguo, por los receptores y medios originales, vinculados a cada movimiento original. En un pedido mixto se recalcula la atribución acumulada sobre las líneas vigentes y se registra la diferencia en el período abierto. Si ya se había distribuido dinero, un reembolso ficticio puede dejar negativo el receptor original y abrir una distribución inversa.
- **Cierres.** Son cortes numerados que guardan los acumulados conciliados en ese momento. El cierre compara el número de período esperado antes de avanzar. Los ajustes, devoluciones y abonos posteriores usan el período abierto y conservan el vínculo con la operación original. Las fechas de movimientos se guardan en UTC.

## Permisos y consistencia

Las consultas y mutaciones del libro se habilitan solo en una base marcada para simulación. **Ventas** puede registrar pedidos, consultar los propios y abonar su saldo. **Admin** puede ver y abonar todos, además de operar devoluciones, anulaciones, transferencias y cierres. Las mutaciones requieren sesión POS y el origen del propio servidor. La interfaz envía el ID esperado del operador para detectar cambios de sesión.

Venta, abonos, stock, libro y respuestas idempotentes se confirman con `BEGIN IMMEDIATE`. El ajuste de stock y el conteo físico adquieren el mismo bloqueo antes de leer el stock. El UUID de venta es por operador. Las otras operaciones admiten reintentos con el UUID y el contenido original. Una referencia informada de pago se acepta una sola vez por receptor, incluso con otro UUID. Los montos iguales pueden representar cobros distintos. Para identificar el mismo depósito cargado manualmente con otro UUID hace falta repetir su referencia. Las anulaciones de los clientes anteriores sin UUID se bloquean después de aplicarse una vez.

## Decisiones pendientes antes del uso real

- Confirmar prorrateo, destinatario del centavo residual y asignación por producto y sus extras.
- Confirmar las cuentas y cajas reales, operadores habilitados para cobrar o registrar un fiado, referencias digitales obligatorias, autorizaciones de traslado y conciliación con extractos y comisiones.
- Confirmar cómo identificar deudores y quién puede acceder a su historial, y definir límites, vencimientos y tratamiento de incobrables.
- Confirmar que una devolución cancele deuda primero, que reembolse en orden inverso, que permita saldos negativos transitorios y cuándo corresponda devolver stock no apto para reventa.
- Definir frecuencia y zona horaria de los cierres reales, política de ajustes históricos, migración productiva y consolidación con reportes, caja general y WhatsApp. La integración con datos, pagos y servicios reales requiere una autorización posterior.

## Verificación

La línea base `98f7c09` pasó **226 pruebas**. La rama de cobros y fiados pasó **235 pruebas**. La verificación de Edge corre en loopback con perfiles temporales y cubre el pedido mixto, el precio desactualizado, los reintentos, el fiado, los cobros combinados y la reversión. Las pruebas de backend también comprueban la concurrencia, los permisos, los cierres y la copia de bases ficticias. Persisten dos avisos de deprecación de FastAPI por `on_event`.

El puente de WhatsApp se verificó con llamadas ficticias al backend y `node --check whatsapp-bot/index.js`. Queda pendiente una prueba con una sesión real de WhatsApp.

Para repetir la suite en Windows, instalá las dependencias del repositorio y `websocket-client` para el control de Edge. Ejecutá desde la raíz del repositorio con PowerShell.

```powershell
$env:NEGOCIO_DB_PATH = Join-Path ([IO.Path]::GetTempPath()) ('abadion-fiados-' + [guid]::NewGuid() + '.sqlite')
$env:PYTHON_DOTENV_DISABLED = '1'
$env:POS_TEST_BROWSER = 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'
python -m pytest -q
node --check whatsapp-bot/index.js
```
