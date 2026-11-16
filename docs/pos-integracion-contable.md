# Abadion POS · Etapa 5 de integración contable ficticia

## Base revisada

La rama de trabajo parte de `39e7d2f`, punta del PR #4. La cadena abierta y en borrador es #1 (`e8bb64d`), #2 (`a5efe43`), #3 (`98f7c09`) y #4 (`39e7d2f`). Se revisaron sus cambios y las guías [de auditoría](auditoria-integracion-pos.md) y [de cobros y fiados](pos-cobros-fiados.md). La prueba manual del POS 4 fue confirmada por el usuario.

`main` (`3bead61`) es el ancestro común. Se revisaron las referencias de catálogo, autenticación y edición de carrito de las que deriva la cadena. Las referencias `feature/comandos-whatsapp-v1` y `feature(pos-tablet-v1` apuntan a `f6ce553`, una línea paralela que registra aperturas de caja por sección y gastos operativos en Rotisería. La instalación efectiva del bot se debe confirmar antes de unificar criterios de caja. El checkout de Etapa 5 sigue la lógica que está en la cadena de PR.

## Contabilidad observada en código

| Área | Regla en la base del PR #4 |
| --- | --- |
| Ventas y caja | `ventas.py` registra ventas legadas en pesos y extras por separado. Los reportes y caja suman las ventas activas. La caja general descuenta compras con medio Caja y gastos activos, aplica aportes y retiros, y considera diezmo entregado y reservas al calcular el disponible. El medio y receptor de los cobros históricos carecen de trazabilidad uniforme. |
| Secciones | `caja.py` clasifica Bebidas y Postres por categoría actual del catálogo. Las demás categorías entran en Comidas. Las cajas de sección usan compras directas y gastos de sección, mientras que la general toma también los gastos generales. El POS atribuye cada línea y sus extras según la sección guardada al vender. |
| Stock, compras y producción | Ambos orígenes usan `productos.stock`. Las ventas, compras, anulaciones, conteos físicos y producción que alteran ese stock se serializan con SQLite. La venta POS y su reversión usan el control de stock guardado con el pedido. Las compras a deuda conservan su registro de deuda y la producción mantiene su costo e inventario de insumos. |
| Diezmo y cierres | `reportes.py` calcula el resultado periódico como ventas menos compras y gastos. `cierres.py` aplica el 10 % al resultado positivo y guarda los importes semanales y mensuales. Los cierres POS son cortes acumulados numerados en UTC y los eventos posteriores pasan al período abierto. No hay correspondencia aprobada entre esos cortes y los calendarios del legado. |
| WhatsApp | `whatsapp-web.js` envía mensajes a `POST /comandos` con Bearer, ID de mensaje y contexto. La reserva de un mensaje y la confirmación de la operación legada son transacciones distintas. Un fallo entre ambas puede dejar un mensaje incierto. La autorización individual en grupos y la recuperación de esos mensajes siguen pendientes. |

## Arquitectura del ensayo

El POS sigue escribiendo venta, snapshot, stock, cobros, devoluciones e idempotencia en una sola transacción. El stock de ambos canales comparte el bloqueo de SQLite. El libro legado sigue recibiendo las operaciones de su propio canal. El puente de lectura toma ambas fuentes en la misma transacción SQLite y reutiliza el cálculo legado de caja general y de las dos secciones, con compras, gastos y diezmo incluidos según sus reglas existentes. La salida conserva los pesos del legado y los centavos enteros del POS.

En la copia ficticia marcada, administración puede consultar `GET /pos-api/simulacion/conciliacion`. El comando `conciliacion pos` usa el mismo cálculo mediante el contrato existente de `/comandos` y devuelve un resumen sin deudores ni referencias. El comando es una lectura y un reintento vuelve a consultar el estado actual, sin reservar mensajes ni escribir asientos. Los comandos existentes siguen su recorrido. El cruce de importes de los dos orígenes queda disponible para revisión, en vez de incorporar deudas o cobros digitales del POS al saldo que el legado trata como caja.

La conciliación compara el neto de cada venta con el snapshot original, las devoluciones y los movimientos por receptor. Comprueba que cada evento conserve el valor de los cobros, que las transferencias internas tengan dos movimientos opuestos, que los reembolsos apunten al cobro de origen y que los cierres coincidan con los eventos hasta su período. Una diferencia se informa con el ID o período afectado. La auditoría no puede identificar por importe a un mismo pedido cargado por ambos canales ni conciliar depósitos con un extracto sin una referencia común aprobada. El stock actual también incorpora compras, producción y ajustes, por lo que no se reconstruye como si solo hubiera ventas POS.

Para la futura contabilización definitiva, el diseño requiere un identificador de operación compartido o una regla explícita de qué canal es dueño de cada venta. El esquema final debería registrar la venta una sola vez con sección y costo históricos, cobros independientes vinculados al pedido, asientos compensatorios en el período abierto y una clave idempotente ligada a la solicitud. Los reportes, cierre y bot leerían esa misma fuente. La selección del esquema y el corte de migración dependen de las decisiones siguientes.

## Decisiones para aprobar antes de contabilizar en el legado

| Tema | Decisión |
| --- | --- |
| Doble registro de una misma venta | Definir cuándo WhatsApp registra una venta y cuándo consulta una venta POS, qué identificador compartirán y cómo tratar duplicados e históricos sin vínculo. Confirmar qué revisión de caja usa el bot de Lo de Clau. |
| Sección y centavo residual | Aprobar o corregir la sección histórica por línea y extras, el prorrateo acumulado y el residual de Bebidas y Postres que ya usa el POS ficticio. |
| Fiado | Definir identificador de deudor, acceso por rol y sección, límites, vencimientos e incobrables. |
| Medios, receptores y conciliación | Confirmar titularidad de cajas y cuentas, referencia obligatoria y su unicidad, liquidaciones brutas o netas, comisiones e impuestos, y procedimiento contra extractos. Definir permisos y cuentas admisibles para transferencias internas. |
| Devolución | Aprobar el orden entre cancelar deuda y reembolsar, el medio y receptor de devolución, el tratamiento de saldos negativos y si vuelve al stock una unidad no apta. |
| Caja, diezmo y cierres | Definir aperturas por caja, gastos generales, base de diezmo para ventas fiadas, fecha y zona horaria de corte, y ajustes posteriores al cierre. Acordar migración e informes con históricos sin medio ni receptor. |

## Prueba manual en localhost

1. Si todavía no tenés un POS 4 ficticio, generá uno con `python scripts/preparar_simulacion_pos.py pos4-ficticio.db` y elegí claves de prueba para administración y ventas.
2. Ejecutá `python scripts/puente_pos_ficticio.py copiar pos4-ficticio.db pos5-ficticio.db`. El script abre la fuente en solo lectura, crea un archivo independiente, añade la marca del puente y verifica el saldo. Si hay un problema, elimina la copia incompleta. El original sirve para volver al PR #4.
3. Ejecutá `python scripts/puente_pos_ficticio.py servir pos5-ficticio.db` y abrí `http://127.0.0.1:8000/pos/`. El servidor de prueba genera credenciales efímeras y no lee archivos `.env`. Funciona en loopback.
4. Registrá un pedido mixto con parte en efectivo, parte en transferencia a otra sección y parte fiada. Como administración, liquidá parte de la distribución, cerrá el período y luego registrá un abono o devolución. Compará el corte guardado con el saldo vigente. En la misma sesión de administración, abrí `http://127.0.0.1:8000/pos-api/simulacion/conciliacion` y verificá `cuadrado: true`, el devengado y fiado por sección y los movimientos por receptor.
5. Con el servidor detenido o en una segunda terminal, corré `python scripts/puente_pos_ficticio.py conciliar pos5-ficticio.db`. Emite JSON y devuelve código 1 si detecta diferencias. Para ensayar el mensaje del bot y un comando legado sin sesión de WhatsApp, ejecutá `python -m pytest -q tests/test_pos_puente.py -k reconcilia_pagos` con el entorno de prueba indicado abajo.

## Archivos y verificación

- `src/pos_puente.py`, `src/pos_cobros.py` y `src/pos_simulacion.py` implementan la conciliación, las lecturas por período y la comparación de cierres.
- `src/api.py` y `src/pos_api.py` activan el puente para el comando del bot y la consulta de administración. `src/caja.py`, `src/database.py`, `src/movimientos_caja.py`, `src/diezmo.py` y `src/deudas_negocio.py` permiten leer el cálculo existente de caja con el mismo corte SQLite.
- `scripts/puente_pos_ficticio.py` prepara la copia, verifica sus importes y sirve el ensayo local. `tests/test_pos_puente.py` verifica la copia con historial, permisos, errores de conciliación, flujos combinados y concurrencia entre canales. `.github/workflows/abadion-pos.yml` ejecuta las pruebas de backend y comprueba la sintaxis de Node en GitHub Actions.

```powershell
$env:NEGOCIO_DB_PATH = Join-Path ([IO.Path]::GetTempPath()) ('abadion-pos5-' + [guid]::NewGuid() + '.sqlite')
$env:PYTHON_DOTENV_DISABLED = '1'
$env:POS_TEST_BROWSER = 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'
python -m pytest -q
node --check whatsapp-bot/index.js
git diff --check
```

Se aprobaron **241 pruebas en Windows**, incluidas las dos de Edge. Persisten dos avisos de deprecación de FastAPI por `on_event`. Pasaron también la copia y conciliación desde la CLI, la comprobación de sintaxis de Node y `git diff --check`. Se ensayó el arranque en `127.0.0.1`, donde la consulta rechazó el acceso sin sesión y devolvió el informe tras iniciar sesión como administración.

El visor de Edge requiere `websocket-client`. En el CI de backend se omiten los casos de navegador. Este ensayo utiliza datos ficticios y el contrato HTTP del bot simulado. El paso a una instalación real requiere aprobación expresa.
