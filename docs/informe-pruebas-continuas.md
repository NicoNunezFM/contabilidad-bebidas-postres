# Informe técnico y matriz — Abadion Pruebas continuas

## Corrección de fiados en el mismo PR #36 — 24/11/2026

Código: `da354070765ddc5a7fa3fef228dc34867f889dea`, sobre la cabecera inicial `48caa79ff747ab5107adbd4e931c055d7c6d805d`. GitHub y fetch confirmaron #36 abierto, borrador, sin fusionar, con la misma rama `integration/abadion-v1-pruebas-continuas`; su CI inicial [45442035384](https://github.com/NicoNunezFM/contabilidad-bebidas-postres/actions/runs/45442035384) estaba aprobada. Se publicó por avance normal de esa rama, sin rama adicional, PR nuevo ni fusión.

Inspección previa: `pos-web/index.html`, `pos_clientes.py`, `pos_api.py`, contabilidad/cobros y las suites de clientes, entrenamiento, roles, UI, delivery y Pruebas. El problema estaba en la secuencia de búsqueda/alta del navegador. La API ya guarda UUID, contenido y resultado transaccionalmente; no se modificó el backend, esquema, cálculo de deuda ni auditoría. El alta y la venta conservan operaciones separadas y explícitas. [Guía del flujo y actualización manual](fiado-directo-pr36.md).

La validación final enfocada dio **5 aprobadas, 0 omitidas, 0 fallidas** (`abadion-fiado-validacion-final.xml`, fuera del repositorio): cuatro variantes nuevas y la regresión UI existente de promoción, fiado parcial, abono, devolución y cierre. No se suman las repeticiones como casos nuevos.

Regresión local completa SQLite/API: **413 aprobadas, 29 omitidas por requerir navegador y 1 fallo del ensayo nuevo**, en 527,28 s (`abadion-fiado-regresion-api.xml`). El fallo consultaba conciliación con rol ventas como si fuese admin; el producto correctamente devolvía 403. Se corrigió el ensayo para verificar ese 403 y conciliar con admin; ambos roles aprobaron después, dentro de las 5 pruebas finales anteriores. La ejecución completa había cargado la versión anterior del ensayo antes de esa corrección. Resultado por casos de API tras la repetición: **414 aprobados**, sin fallos pendientes; no se presenta la ejecución inicial como una corrida íntegramente verde. Las 29 pruebas de navegador se verifican por separado en Edge.

Regresión local Windows/Edge completa: **133 aprobadas y 2 fallos del ensayo nuevo**, 0 omitidas, en 428,24 s (`abadion-fiado-regresion-edge.xml`). Ambas comprobaciones intentaban medir el botón Crear después de ocultarlo al seleccionar. La versión final mide el botón mientras está visible y verifica su ocultación tras el alta; los dos casos completos aprobaron en la repetición final. Las suites se habían iniciado antes de ese ajuste y no se alteraron sus resultados originales.

**Resultado consolidado por identidad de caso: 443 casos únicos aprobados, 0 fallos pendientes y 0 omitidos**, tomando el último resultado ejecutado de cada caso y sin sumar repeticiones. No equivale a una sola corrida completa verde. [Resumen con hashes de los XML originales](evidencia-fiado/resultados.json) y [JUnit de las 5 pruebas finales](evidencia-fiado/validacion-final.xml). La sintaxis JavaScript extraída de `pos-web/index.html` aprobó `node --check`; `git diff --check` aprobó.

La [CI inicial del código da35407](https://github.com/NicoNunezFM/contabilidad-bebidas-postres/actions/runs/45450185105) detectó después una diferencia real en el archivo generado `pos-web/demo-tablet.html`: faltaban las dos reglas CSS de tamaño táctil agregadas al índice. La prueba local de coherencia se había ejecutado antes de ese último ajuste de estilos. Se regeneró la demo con `scripts/generar_demo_tablet.py`; el único cambio generado son esas dos reglas, sin código operativo ni acceso a datos. La repetición posterior dio **8 aprobadas, 0 omitidas, 0 fallidas** en 27,44 s: coherencia de generación, aislamiento HTTP, dos recorridos de demo en Edge y los cuatro casos de fiado. [JUnit de esa repetición](evidencia-fiado/demo-final.xml). Los resultados consolidados mantienen 443 identidades únicas. El commit final incluye esta sincronización y la evidencia actualizada. Revisar los [controles del PR #36](https://github.com/NicoNunezFM/contabilidad-bebidas-postres/pull/36/checks) para el SHA entregado antes de activar; el estado de CI no se infiere de los resultados locales.

| Evidencia | Resultado comprobado |
|---|---|
| API/SQLite, ventas y admin | Alta concurrente repetida devuelve el mismo cliente; UUID reutilizado con otro contenido devuelve 409. Venta y abono concurrentes crean una sola operación de cada tipo. |
| $9.000 fiados y $4.000 de abono | Saldo $5.000, caja +$4.000, una venta, stock −1, conciliación cuadrada. Otro Onchi identificado por referencia conserva saldo cero. |
| Permisos y sesión | Ventas no puede corregir abonos ni consultar conciliación administrativa (403); después de logout no puede dar altas (401). Administración concilia. |
| Edge real, 1280×900 / ventas y 600×1024 / admin | Nombre → Crear → selección automática → Confirmar; teléfono ausente; resumen total/pagado/deuda. Flujo completo de abono FIFO desde Clientes. |
| Respuesta de alta perdida después del commit del servidor | Doble clic genera una sola alta; reintento conserva UUID y carga útil. Identidad bloqueada y venta rechazada hasta resolver; luego foco en confirmar y errores anteriores limpios. |
| Coincidencias y respuestas de búsqueda | Dos Onchi no se autoseleccionan. Crear homónimo sin referencia/teléfono se rechaza en UI. Editar nombre invalida la ficha. Error de búsqueda bloquea crear; respuesta tardía no reemplaza el resultado actual. |
| Teclado y tacto | Foco inicial en nombre, Enter busca sin vender, Enter selecciona ficha enfocada, foco en confirmar tras alta; alta con eventos táctiles de Edge. Controles de al menos 44 px, diálogo sin desbordamiento horizontal. |
| Regresión existente de UI | Promoción mixta, fiado parcial $5.000 con entrega $2.000, deuda $3.000, abono, devolución por admin y cierre. |

Capturas revisadas visualmente: [Edge angosto](evidencia-fiado/edge-600.png) y [Edge escritorio](evidencia-fiado/edge-1280.png). Sólo contienen datos ficticios. Al revisar la primera captura se corrigió un mensaje de reintento que permanecía después del alta exitosa; las capturas entregadas corresponden al flujo final.

### Reproducir los ensayos

En un checkout de prueba con Python 3.12, requisitos instalados y Microsoft Edge, fuera de instalaciones existentes:

```powershell
$env:PYTHON_DOTENV_DISABLED = '1'
$env:PYTHONUTF8 = '1'
$env:NEGOCIO_DB_PATH = Join-Path $env:TEMP ('abadion-fiados-ficticia-' + [guid]::NewGuid() + '.db')
Remove-Item Env:POS_TEST_BROWSER -ErrorAction SilentlyContinue
python -m pytest -q -rs --junitxml=../abadion-fiado-regresion-api.xml
$env:POS_TEST_BROWSER = "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe"
$env:POS_UI_CAPTURAS = Join-Path $env:TEMP 'abadion-fiado-capturas'
python -m pytest -q tests/test_fiado_directo.py tests/test_pos_web.py::test_pos_web_entrenamiento_promocion_fiado_devolucion_y_cierre --junitxml=../abadion-fiado-validacion-final.xml
```

La lista Windows/Edge completa está en `.github/workflows/abadion-pos.yml` e incluye `tests/test_fiado_directo.py`. El ensayo usa servidor en puerto libre y perfil temporal; los ensayos existentes verifican que el launcher instalado de Pruebas sigue ligado a loopback 8079. Los primeros intentos restringidos se detuvieron por bloqueo de conexiones locales de asyncio; se repitieron con conexiones locales disponibles. No se cambió el producto para sortear esa restricción.

No se abrió ni modificó la instalación existente, negocio.db, Entrenamiento/Preproducción instalados, WhatsApp ni accesos directos. Sólo se escribió código y evidencia en el checkout y se prepararon bases ficticias en carpetas temporales. La actualización del usuario queda manual y conserva el mecanismo de backup/rollback de #36. Pendientes humanos: actualización por SHA y repetición ficticia de $9.000/$4.000, tacto físico, reinicio del equipo y escenarios de corte de energía ya descritos abajo.

---

Fecha: 24/11/2026. Base exacta: #35 `47bf78dccb1fd6e3c297cd58a070663499e550e4`. Rama independiente `integration/abadion-v1-pruebas-continuas`, apilada contra #35, sin fusión ni producción.

## Alcance

Reutiliza POS Premium, SQLite persistente, contabilidad y delivery del código acumulado #33–#35. Agrega un perfil Pruebas explícito a las primitivas verificadas de Preproducción, sin cambiar el formato de esa instalación. Incorpora launcher manual, instalador Windows con ACL privada, versiones por SHA, puntero de activación atómico, respaldo previo verificado, rollback de código con conservación de movimientos y restauración exclusivamente aislada. [Guía y comandos completos](abadion-pruebas-continuas.md).

Las instalaciones existentes, accesos directos, bot WhatsApp y negocio.db quedan fuera de los comandos y de todos los ensayos. La inspección se limitó al código de los launchers, metadatos Git/GitHub e historia; no abrió datos instalados.

## Matriz reproducible

| Requisito | Ensayo automatizado |
|---|---|
| Nueva base vacía, 38 productos, aprobación SHA/UUID, stock cero | `test_abadion_pruebas::test_nueva_vacia_catalogo_aprobacion_stock_y_disponibilidad`; rechaza bebida con stock cero y reimportación |
| Identidades/cookies/rutas separadas, servidor general cerrado, aislamiento de Preproducción | `test_aislamiento_entre_instalaciones_y_general` |
| Esquema, modo, UUID y hardlink incorrectos | `test_rechazo_identidad_esquema_y_enlaces` (4 variantes) |
| Backup antes de actualizar, historial/stock/ID intactos, rollback conservando stock posterior | `test_actualizacion_backup_rollback_sin_perder_historia` |
| Backup inválido, código alterado, esquema de origen inválido, dependencias fallidas | `test_fallo_actualizacion_no_cambia_version_ni_datos` (4 variantes) |
| Candidato con otro esquema, base sana sin cambios, puntero anterior intacto | `test_codigo_candidato_incompatible_no_activa` |
| Actualización y catálogo bloqueados con servidor en uso | `test_actualizacion_y_catalogo_rechazan_servidor_activo` |
| Backup manipulado o de otra instancia rechazado | `test_backup_alterado_y_otra_instancia_no_recuperan` |
| Base principal corrupta/ausente, recuperación aislada, sin sobrescribir original | `test_recuperacion_aislada_sin_abrir_base_danada` (2 variantes) |
| Catálogo rechazado si ya hay una jornada, aunque no haya productos | `test_catalogo_rechaza_base_con_jornada_aunque_sin_productos` |
| Perfil Edge dedicado y eliminación de entorno ajeno | `test_launcher_edge_perfil_diferenciado_y_entorno` |
| Jornada integrada, worker real, reinicio y restore en otra carpeta | `test_jornada_comercial_integrada_worker_reinicio_restore` |
| Edge real con banda de Pruebas, login propio y catálogo comercial | `test_edge_pruebas_perfil_y_catalogo` |
| Promoción mixta de sabores, bajas, precios, adicionales, devolución e idempotencia | `test_catalogo_comercial.py`, además de la jornada integrada |
| Delivery sencillo, $2.000 del repartidor, efectivo/transferencia, cancelación y devoluciones antes/después del reparto | `test_lo_de_clau_delivery.py`, `test_lo_de_clau_edge.py`, además de la jornada integrada |
| POS Premium táctil emulado, permisos, compras, fiados/abonos FIFO, cajas y conciliación | Regresión existente completa, sin reemplazar sus pruebas |
| Backup WAL, publicación sin sobrescritura, caída y restauración | `test_preproduccion*.py`, `test_backups.py` y worker integrado |

## Jornada comercial integrada

Parte de una SQLite nueva en una carpeta temporal Pruebas; aprueba el catálogo con su SHA/UUID sólo dentro del fixture. Verifica cero inicial antes de registrar cantidades. Abre ambas cajas con $20.000 ficticios cada una. Registra compra explícita de diez Manaos Cola 600 ml a costo de ensayo $100/unidad, pagada desde Comidas. Es un costo ficticio de prueba, no una propuesta de costo comercial.

Vende Clásica simple con cheddar y huevo, Manaos Cola 600 ml, Pepitos chico y Oreo chico. Productos: $15.300, incluida la promoción mixta de $1.000. Delivery: $2.000 adicionales, exclusivos del repartidor. Cobro: $9.000 efectivo y $8.300 transferencia. Repite el mismo UUID y la entrega sin duplicar movimientos. Entrega el envío desde efectivo y comprueba custodia cero.

Registra retiro fiado de un Pepitos chico por $3.000, abono de $1.000 y deuda residual de $2.000. Registra otra venta, comprueba que Ventas no pueda anular, anula como Admin y cancela el pedido. Devuelve la bebida de la primera venta conservando el servicio de delivery ya realizado. Arquea y cierra ambas cajas, verifica conciliación cuadrada y captura ventas, pedidos finalizados, cajas, diarios, deuda y contabilidad.

Detiene y reinicia un proceso real con la misma base, compara esos informes e idempotencia por el mismo usuario. Recupera un snapshot en otra carpeta temporal con control renovado y sesiones revocadas; arranca otro proceso y compara los mismos informes. La bebida queda en diez unidades: compra diez, venta una, devolución una. Comprueba integridad SQLite. No usa cantidades cargadas silenciosamente por el catálogo.

## Resultados y controles

Código final: `4d4e71880aca751fc2866c5ffd9b282fee25a843`. Instalador corregido en `f01264e4f5087c7d38f4d4d5979aae28bf9aed90`: Windows oculta AppData, por eso la inspección de ancestros usa `Get-Item -Force`.

| Ejecución local Windows / Edge real | Aprobadas | Omitidas | Fallidas en esa ejecución |
|---|---:|---:|---:|
| Regresión completa, XML `abadion-pruebas-regresion-final.xml` | 433 | 0 | 1: timeout al guardar PNG, después de aprobar las aserciones UI |
| Archivo final nuevo, XML `abadion-pruebas-controles-final.xml` | 20 | 0 | 0 |
| Repetición explícita con captura PNG, XML `abadion-pruebas-edge-repeticion.xml` | 1 | 0 | 0 |
| Control final de activación repetida y fallos, XML `abadion-pruebas-actualizacion-idempotente.xml` | 6 | 0 | 0 |
| Unión por archivo/clase/nombre | **439 casos únicos con aprobación** | **0 sin cubrir** | **0 pendientes tras repetición** |

La regresión se recogió antes de agregar los últimos cinco casos del archivo nuevo; los 20 controles finales cubren esa ampliación. Las suites se solapan, por lo que no se suman las repeticiones como casos nuevos. El timeout de la captura queda registrado, no se presenta la regresión como una ejecución enteramente verde. La captura repetida se guardó y se inspeccionó: banda ABADION PRUEBAS, usuario admin-pruebas y catálogo agrupado.

Además de pytest se ejecutó el **instalador PowerShell real** contra el commit `f01264e`, con LOCALAPPDATA redirigido a una carpeta temporal nueva y privada. Se instalaron dependencias y una versión desde `git archive`, se verificaron vista previa de 38 productos, aprobación SHA/ID exclusivamente ficticia, arranque sin ventana de navegador, estado autenticado, backup y detención. El wrapper PowerShell aceptó los argumentos de la guía.

Se ejecutó después una actualización real por esos comandos desde `f01264e` a `1644e0d`, y rollback a `f01264e`, con dos entornos Python realmente instalados. Se comparó SHA-256 de la SQLite antes, después de actualizar y después de rollback: **idéntica**. Se reinició y detuvo la versión recuperada. La jornada con historial y stock posterior al cambio se verifica adicionalmente en pytest. El ajuste final `4d4e718` conserva también el destino anterior cuando se repite exactamente el mismo SHA; seis casos finales aprobados lo verifican, incluidos fallos y esquema candidato incompatible.

CI remota comprobada: [ejecución 45440854188 del instalador corregido](https://github.com/NicoNunezFM/contabilidad-bebidas-postres/actions/runs/45440854188), **SQLite/API 412 aprobadas, 27 omitidas**, más sintaxis Node aprobada; Windows/Edge todavía en ejecución al redactar esta evidencia. [CI del código final 4d4e718](https://github.com/NicoNunezFM/contabilidad-bebidas-postres/actions/runs/45441672510) iniciada, sin declarar aprobación anticipada. El commit posterior de evidencia sólo cambia documentación y puede abrir otra ejecución. Revisar siempre la cabecera exacta del PR antes de instalar.

La CI de #33, #34 y de la cabecera más reciente de #35 está aprobada en ambos trabajos. La CI de esta rama conserva `sqlite-ficticio` (Ubuntu, toda la suite sin Edge) y `pos-edge` (Windows/Edge); agrega el archivo nuevo a este último. El trabajo sin navegador omite los casos que requieren `POS_TEST_BROWSER`; esas omisiones se declaran por separado. El chequeo de sintaxis Node del bot no conecta WhatsApp.

## Límites y recuperación

Los hashes acreditan contenido y las órdenes registran aprobación explícita, sin constituir firma digital de una persona. El mecanismo acepta un SHA elegido por el usuario; no consulta GitHub para decidir automáticamente si su CI aprobó. La guía requiere revisar el SHA exacto antes de activarlo.

Las pruebas de fallo de descarga/dependencias usan una falla inyectada; no simulan todos los cortes de red o energía posibles. La activación comprueba integridad, UUID y esquema con el Python candidato en sólo lectura. No hay migraciones de esquema automáticas. Un rollback incompatible se detiene. La restauración crea otra carpeta y conserva el original para no perder silenciosamente operaciones posteriores al backup.

Las versiones y snapshots no se eliminan automáticamente. No se hicieron pruebas táctiles físicas, reinicio del equipo, corte de energía, restauración externa en otra PC ni aceptación familiar. No se habilitó dinero real, WhatsApp ni producción.

Huella SHA-256 del JSON comercial revisado: `36bb753a5980a9fa445728ae13471e56b7325edea047e9e4b48a98eecff43486`. La aprobación de una instalación nueva exige generar su propia vista previa y confirmar su UUID; esta huella no autoriza bases existentes.
