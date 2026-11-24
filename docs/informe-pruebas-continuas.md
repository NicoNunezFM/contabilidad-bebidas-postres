# Informe técnico y matriz — Abadion Pruebas continuas

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
