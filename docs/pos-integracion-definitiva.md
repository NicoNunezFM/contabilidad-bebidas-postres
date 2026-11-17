# Abadion POS · Etapa 7 · Contabilidad unificada ficticia

La rama parte del [PR de caja diaria #6](https://github.com/NicoNunezFM/contabilidad-bebidas-postres/pull/6) en `03343c5`. La etapa se habilita al crear una copia nueva de etapa 6 con `--contabilidad`. El informe de administración requiere la marca de la copia y las dos opciones de simulación. El servidor del ensayo se limita a `127.0.0.1` y usa credenciales de integración efímeras.

## Registros y períodos

| Operación | Registro y efecto |
| --- | --- |
| Venta POS | El pedido y la sección histórica de cada línea y sus adicionales se guardan al vender. El libro POS registra el devengado y el stock se descuenta una vez dentro de la misma transacción. La API y los comandos legados dirigen las ventas y devoluciones nuevas al POS durante este ensayo. |
| Cobros | Cada cobro guarda su medio, receptor e importe. Los pagos combinados, los abonos posteriores y los reembolsos comparten el libro POS. Los abonos acrecientan el cobrado y reducen la deuda. El devengado se mantiene hasta que haya una devolución. |
| Cajas | El diario físico se actualiza con la pata que corresponde al receptor real. Cada caja abre, arquea y cierra de forma independiente. El efectivo, los gastos pagados en esa caja, los aportes, los retiros y los traslados netos quedan en su diario. Las transferencias internas se compensan entre receptores. |
| Compras | El registro legado actualiza stock y, cuando corresponde, deuda con el proveedor. En la misma transacción se guarda un asiento contable identificado por compra y tipo de evento. Una compra a deuda deduce su importe al registrar la compra, según la definición legada del resultado. Los pagos de esa deuda quedan en el módulo de deudas. |
| Gastos | El gasto con receptor físico se registra una vez en Caja diaria y se lee de ese diario. Un gasto legado sin receptor se incorpora al resultado por su importe, con la sección declarada si existe, y queda fuera del arqueo físico. Los costos legados se redondean por asiento a centavos. |
| Diezmo | Se calcula el 10% del resultado positivo de **cobros netos de clientes menos compras menos gastos**. Cada abono de fiado participa por lo que se cobró en su fecha local, incluso si corresponde a una venta anterior. Para el ensayo cuentan efectivo, transferencia y Mercado Pago. El resultado devengado se informa por separado. |
| Devoluciones | Se reduce el devengado de la sección histórica. Primero se reduce la deuda. El efectivo o digital efectivamente reembolsado resta de lo cobrado en la fecha de devolución, con vínculo al pago original y en orden inverso. La devolución física requiere una caja receptora abierta para el día. |
| Cierres | Los cierres semanales y mensuales nuevos guardan el informe completo en la misma transacción que el cierre. Incluyen los arqueos cerrados que corresponden al período, por ID de jornada y de cierre diario. Se esperan fechas terminadas y jornadas cerradas. Los cierres de un mismo tipo no se superponen. El diezmo semanal es una estimación. La obligación mensual sigue el cierre mensual. Los cortes acumulados numerados del POS siguen disponibles para distribución y auditoría. |

El corte guarda la fecha local de Argentina y los últimos IDs del libro POS y del diario físico. Las consultas de períodos que cruzan el corte muestran flujos desde el corte e indican la fecha efectiva en `desde_contable`. Los cierres históricos quedan archivados con sus valores previos. Un saldo fiado de un POS ficticio anterior al corte aparece como pendiente y un abono posterior cuenta en el período del pago. El dinero y los gastos del día registrados antes de copiar la base quedan en el historial de origen. Una jornada preexistente puede conservar esos importes en su arqueo completo.

Las ventas devengadas y el cobro atribuido se agrupan por sección histórica. El prorrateo acumulado usa la proporción del devengado de cada sección y asigna el centavo residual a Bebidas y Postres. El receptor conserva el movimiento realmente recibido y puede pertenecer a la otra caja. Los reportes muestran la variación del fiado del rango y el saldo pendiente al final.

Una anulación de compra o gasto de etapa 7 agrega un ajuste de signo opuesto, con referencia al costo original y fecha de la anulación. Los costos anteriores al corte quedan archivados. El corte opera con fechas locales de Buenos Aires y los timestamps UTC del libro POS se convierten con el desplazamiento argentino de este ensayo. Las compras y gastos nuevos del legado se registran con fecha local del día. Los cierres anteriores conservan su foto frente a abonos, devoluciones y ajustes posteriores. Un resultado base negativo se informa en el período que lo generó, con diezmo cero.

El informe de administración vive en `GET /pos-api/simulacion/contabilidad` y en **Contabilidad** del POS. La consulta HTTP acepta `desde` y `hasta` en formato ISO. Los reportes legados de hoy, semana y mes y los comandos de resumen de WhatsApp leen la misma proyección. Las claves históricas de los reportes y cierres siguen disponibles, y `contabilidad_centavos` contiene el detalle integrado. `/caja` y sus secciones incluyen el diario físico en `caja_diaria_centavos`. En etapa 7, los comandos `caja` muestran el diario de la jornada. `conciliacion pos` también muestra la diferencia de alcance entre el origen legado y el período contable integrado.

Los UUID del POS y las referencias de cobro por receptor se validan en las transacciones existentes. El bot conserva `whatsapp-web.js`, `POST /comandos`, autorización Bearer, contexto e ID de mensaje. Se pueden seguir enviando consultas y registrar operaciones complementarias como compras y gastos sin receptor. Los ID del POS, los ID de cierres y las claves de origen de los costos permiten seguir cada importe hasta su registro.

## Decisiones de ensayo pendientes de aprobación

| Tema | Pendiente para producción |
| --- | --- |
| Gastos, compras y receptores | Definir cómo identificar cada comprobante entre canales. En el ensayo, un gasto pagado en caja se carga en Caja diaria, y un gasto sin receptor se carga por el flujo legado. Una carga manual independiente con datos iguales no identifica una operación duplicada. Confirmar medios y receptores de gastos y compras, pagos de deudas, depósitos, comisiones y conciliación bancaria. |
| Cálculo del diezmo | Ya está aprobado el reconocimiento del fiado cuando se paga, por el importe pagado. Confirmar el uso de todos los medios, el ingreso bruto o neto de comisiones, la imputación temporal de costos y el tratamiento de pérdidas y correcciones entre períodos. |
| Secciones | Aprobar el prorrateo, el residual de centavos, los gastos generales y los permisos para transferencias. |
| Fiados | En el ensayo se requiere identificar al cliente y se impiden abonos por encima del pendiente. Falta decidir acceso individual, límites y vencimientos, datos del cliente e incobrables. |
| Reembolsos | Aprobar el orden del reverso, caja o medio alternativo, faltantes de fondos y condición del stock devuelto. |
| Historial y activación | Acordar fecha y hora de corte, saldos iniciales conciliados, revisión de duplicados históricos, correcciones previas al corte y convivencia con la instalación real del bot. Ensayar copias y recuperación, incluyendo mensajes con confirmación incierta de WhatsApp. |

## Prueba manual local

1. Usá una copia ficticia de etapa 6. Creá otra copia para el ensayo y arrancala en la máquina local.

   ```powershell
   python scripts/puente_pos_ficticio.py copiar pos6-ficticio.db pos7-ficticio.db --contabilidad
   python scripts/puente_pos_ficticio.py servir pos7-ficticio.db
   ```

2. En [POS local](http://127.0.0.1:8000/pos/) abrí las dos cajas como ventas. Con el catálogo estándar de prueba, elegí un artículo de cada sección. De un pedido por $4.000, registrá $2.000 en efectivo recibido por Rotisería, $1.000 en una cuenta digital de Bebidas y Postres y $1.000 de fiado. Verificá una sola venta en Historial, el stock y que la caja física de Rotisería aumente $2.000.
3. Como administración, registrá un gasto físico de $200 en Rotisería y abrí **Contabilidad**. Con otros movimientos del día en cero, esperá $4.000 devengados, $3.000 cobrados, $1.000 pendientes, base $2.800 y diezmo $280. Si el catálogo o la base ficticia ya tiene otros movimientos del día, compará las diferencias.
4. En el mismo pedido registrá un abono de $400 por transferencia. El devengado se mantiene en $4.000, el cobrado sube a $3.400 y el pendiente baja a $600. En las mismas condiciones, el diezmo sube a $320. Refrescá el informe y verificá los receptores.
5. Transferí entre las dos cajas abiertas un importe admitido por la distribución pendiente. Debe cambiar el efectivo esperado por caja y mantenerse el cobrado global. Hacé una devolución parcial y controlá la cancelación de deuda antes de cualquier reembolso. Arqueá y cerrá las cajas por separado.
6. Comprobá que `python scripts/puente_pos_ficticio.py conciliar pos7-ficticio.db` devuelva `cuadrado: true`. Para ensayar cierres semanales y mensuales, reintentos o el bot sin conectar una sesión de WhatsApp, ejecutá `python -m pytest -q tests/test_pos_contabilidad.py`. Los casos de cierre esperan una fecha anterior y comparan los importes guardados antes y después de los ajustes.

Para toda la suite en Windows, usá un archivo de pruebas nuevo fuera de la base del negocio. Las pruebas web requieren Edge y `websocket-client`.

```powershell
$env:NEGOCIO_DB_PATH = Join-Path ([IO.Path]::GetTempPath()) ('abadion-etapa7-suite-' + [guid]::NewGuid() + '.sqlite')
$env:PYTHON_DOTENV_DISABLED = '1'
$env:POS_TEST_BROWSER = 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'
python -m pytest -q
node --check whatsapp-bot/index.js
git diff --check
```
