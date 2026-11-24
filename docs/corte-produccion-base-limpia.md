# Candidata de producción con contabilidad nueva

Estado: **bloqueada, offline, sin fecha efectiva de corte ni operaciones habilitadas**.
La preparación no implica aprobación comercial, aceptación de saldos ni autorización de despliegue.
No existe comando de inicio o activación. No eliminar los bloqueos SQL ni cambiar el application_id para utilizarla.

## Base técnica revisada

Se parte de #36, `integration/abadion-v1-pruebas-continuas`, en
`416cda54d5cb4d6254cb5683c0779999d4b7be7b`. Al consultar, estaba abierto, en borrador,
sin fusionar. Su workflow `45451036700` terminó con éxito en esa cabecera.
La cadena #29 → #32 → #33 → #34 → #35 → #36 permanece separada de esta propuesta.
#30 es una propuesta paralela de preproducción: no se mezclan sus instaladores ni identidades.
La rama de esta candidata se apila sobre #36 para mostrar únicamente el cambio nuevo.

El instalador de Pruebas usa SQLite ficticia, puerto 8079 y aprobación de catálogo sobre su propia identidad.
No se reutiliza ese instalador ni su base como producción. Tampoco se copia ningún respaldo histórico.
El inicializador de esquema actual se ejecuta únicamente contra un archivo nuevo privado.
Las tablas internas heredadas con nombre `simulados` se conservan vacías por compatibilidad de esquema;
su nombre no significa que se hayan importado prácticas. Se eliminan las identidades ficticias y el corte contable de ensayo.

## Qué prepara

- Archivo exclusivo `abadion-produccion-candidata.db`, application_id propio, UUID nuevo y esquema actual.
- Catálogo de 38 variantes de #35, hash `36bb753a5980a9fa445728ae13471e56b7325edea047e9e4b48a98eecff43486`.
  La comprobación verifica los precios, categorías, complementos, disponibilidad y grupos de promoción contra el JSON exacto.
  Dos adicionales de $1.000 y promoción combinable de postres chicos según el catálogo y motor vigente.
- Nueve variantes con stock por unidad y 29 sin ese control; todas con stock técnico cero.
  Ese cero **no acredita un conteo físico**. El modelo sin control por unidad requiere aceptación expresa;
  no se inventan recetas ni existencias por ingrediente.
- Roles Administración y Ventas con contraseñas aleatorias y hash PBKDF2; ambas cuentas deshabilitadas.
  Las credenciales quedan exclusivamente en la carpeta privada. No se imprimen, suben ni incluyen en snapshots.
- Esquema para cajas `comidas` (Rotisería) y `bebidas_postres` (Postres/Bebidas), sin jornadas abiertas.
  Un saldo unificado por sector, sin abrir efectivo/cuentas en la interfaz. Los medios históricos se
  conservan en los registros existentes; un cobro nuevo unificado usa receptor propio sin atribuirle un
  medio físico o digital que nadie declaró. Los fondos del repartidor no son ingreso propio.
- Marca de preparación UTC y `corte_efectivo=NULL`. Seis validaciones pendientes sin importes precargados.
- Bloqueos INSERT/UPDATE/DELETE para todas las tablas, incluidas configuración y aceptación.
  La conexión general también rechaza el identificador o marcador de candidata, incluso renombrada.

No hay ventas, compras, gastos, clientes, deudas, sesiones, importaciones, movimientos, cierres ni stock migrados.
La comprobación recorre todas las tablas y exige cero filas fuera de la lista de configuración permitida.
Un error deja una carpeta para diagnóstico; preparar jamás reintenta encima ni sobrescribe.

## Preparación Windows reproducible

Usar checkout limpio de esta rama con dependencias disponibles y el SHA completo revisado.
`Preparar-Candidata.ps1` crea por defecto una carpeta nueva en `%LOCALAPPDATA%\Abadion\CandidataOffline`.
Admite `-DestinoAbadion` para un ensayo en una carpeta temporal nueva; nunca pasar una instalación existente.

```powershell
$CommitAbadion = (git rev-parse HEAD).Trim()
.\scripts\Preparar-Candidata.ps1 -Commit $CommitAbadion
```

Valida la cabecera y limpieza del checkout, ruta absoluta, inexistencia del destino y ausencia de reparse points.
Restringe acceso al usuario actual y SYSTEM antes de crear dependencias o credenciales.
Exporta código versionado por SHA con lista permitida, genera manifiesto de archivos y entornos Python aislados.
No distribuye el bot, archivos .env, bases locales ni sesiones. No crea accesos directos, servicios, puertos ni tareas.
La herramienta de distribución compartida prepara una release pero **no invoca su función de activación**.
Un fallo de permisos o dependencias detiene la preparación; conservar la carpeta fallida para diagnóstico.

Para comprobar, respaldar o restaurar, usar el Python y el script de la release exportada:

```powershell
python .\scripts\abadion_candidata.py comprobar --carpeta <carpeta-nueva-ProduccionCandidata>
python .\scripts\abadion_candidata.py backup --carpeta <carpeta-nueva-ProduccionCandidata>
python .\scripts\abadion_candidata.py restaurar --respaldo <carpeta-backup> --carpeta <otra-carpeta-nueva-ProduccionCandidata>
```

Las rutas entre ángulos son parámetros a reemplazar, no comandos para copiar literalmente.
No ejecutar `preparar` sobre Pruebas ni pasar una SQLite como origen: el creador no admite bases fuente.

## Backup, recuperación y reinicio

Cada backup usa SQLite backup API, integridad y foreign_key_check, más hash SHA-256 e identidad en manifiesto.
La creación incluye un snapshot inicial. Mantener el par DB/manifiesto en almacenamiento privado separado;
el hash detecta alteraciones accidentales, no es una firma contra alguien con acceso de escritura a ambos.
No incluir credenciales en repositorios ni enviar respaldos por chat.

Restore exige snapshot sin WAL/SHM/journal, hash e identidad correctos, esquema y bloqueos vigentes y todas
las validaciones pendientes. Escribe exclusivamente en otra carpeta inexistente, con ACL privada.
Funciona sin la base original y no reemplaza el original. No importa respaldos legados o de Pruebas.
La recuperación conserva la identidad del snapshot y continúa offline; no se deben activar simultáneamente
original y copia. No restaura contraseñas en texto: cualquier futura habilitación deberá renovarlas.
SQLite puede cambiar contadores internos de cabecera al copiar; se compara contenido lógico, no igualdad binaria.

El test de reinicio consiste en cerrar conexiones y comprobar desde dos procesos Python nuevos,
sin pérdida de catálogo ni apertura del bloqueo. No es un ensayo de reinicio de Windows ni de un servidor productivo:
no existe servidor habilitado en esta etapa. Esas comprobaciones quedan en la aceptación de despliegue.

## Corte y validación real: condición previa de habilitación futura

Los siguientes datos se confirman **localmente por el responsable**, fuera de Git/PR y sin publicarlos.
Una implementación posterior deberá registrar responsable, evidencia privada, instante efectivo en Buenos Aires,
UUID, versión, hash de catálogo y aprobación de cada rubro en una transacción. Este cambio no implementa
esa habilitación ni permite sustituirla por una casilla o variable de entorno.

1. Confirmar **un saldo total de Rotisería y un saldo total de Postres y Bebidas**, a la misma hora,
   con responsable y evidencia privada. No exigir desglose efectivo/virtual en la pantalla de apertura.
2. Conciliar privadamente el origen de esos totales y excluir fondos de terceros o en tránsito. Una cuenta
   compartida se cuenta una sola vez; sus asignaciones deben sumar su saldo conciliado. No sumar al total
   de apertura los componentes que ya incluye. Confirmar ceros expresamente; desconocido no es cero.
3. Contar los seis SKU de postres por separado; registrar fecha, cantidad, diferencias y agotados.
   Mantener bebidas bloqueadas hasta reposición registrada, conteo positivo por SKU y validación de
   Administración con referencia. Stock técnico cero y control pendiente no significan existencia.
   Rotisería mantiene su modelo sin inventario por ingrediente, sujeto a aceptación expresa.
4. Relevar obligaciones pendientes y créditos a cobrar, contrapartes, concepto, sección, moneda y saldo al corte.
   Si no existen, confirmar una lista vacía expresamente. Conservar comprobantes en privado.
   Es una foto de apertura nueva, **no importar ventas/compras/gastos antiguos** ni recalcular ingresos históricos.
   Registrar saldos iniciales separados de ventas, compras, ingresos, costos y diezmo para evitar duplicación.
5. Verificar que no quede ninguna operación en tránsito al corte: pedidos, anticipos, cobros, repartidores y devoluciones.
   Asignar una sola contabilidad responsable de cada pendiente y un identificador de conciliación.
6. Aceptar catálogo/precios/promos, permisos y dispositivos; confirmar respaldo externo y recuperación en otro destino.

Sólo después de esas confirmaciones se podrá preparar y revisar la etapa de activación. También deberá verificar
CI del SHA exacto, asignar cuentas individuales, renovar contraseñas, ensayar permisos con ambos roles y validar
apertura de ambas cajas desde sus saldos aprobados. Ninguna de estas tareas debe adelantarse con números inventados.

## WhatsApp y una sola contabilidad

El historial anterior queda exclusivamente en el libro legado y su respaldo. No se consulta ni modifica durante esta preparación.
No tocar, iniciar, detener ni reconfigurar el bot para hacer estos ensayos.

Antes del corte, el responsable deberá confirmar que el bot legado no registra operaciones. Después del corte,
el POS será el único libro de nuevas operaciones. Un mensaje o pedido de WhatsApp se carga una sola vez en el POS
con referencia estable; recibir un mensaje no acredita una venta ni un cobro.
**No volver a encender el bot contable original durante la operación productiva.**
No hay bloqueo remoto sobre ese programa en esta propuesta: la exclusión del bot es una condición operativa verificable.
Un futuro canal WhatsApp requiere un adaptador al mismo POS con idempotencia y permisos, sin escribir en el libro viejo.

Si se detecta un encendido accidental, suspender nuevas registraciones por el procedimiento operativo acordado,
anotar la hora del incidente y conservar ambos libros. Conciliar pedido/importe/medio/hora entre ambos sin importación masiva.
Resolver duplicados con anulaciones justificadas en el libro responsable, sin borrar historia ni tocar datos por script.
No continuar hasta dejar documentado qué libro conserva cada operación. Esta guía no ejecuta ninguna de esas acciones.

## Checklist de aceptación

- [ ] Rama y SHA revisados; PR sigue borrador, sin fusión ni despliegue.
- [ ] Carpeta exclusiva local y ACL comprobadas; ninguna instalación existente reutilizada.
- [ ] Identidad propia, 38 variantes y hash correctos; cero transacciones; usuarios inactivos.
- [ ] Fecha de corte efectiva sigue pendiente hasta la confirmación real.
- [ ] Dos saldos unificados conciliados y aprobados, sin repetir componentes ni incluir custodia de terceros.
- [ ] Stock físico y modelo de control aceptados; deudas y créditos vigentes relevados expresamente.
- [ ] Bot contable excluido y pendientes asignados a un solo libro.
- [ ] Backup externo y restore aislado verificados; contraseñas privadas recuperables o renovables.
- [ ] Permisos, dispositivos, reinicio de Windows y recuperación tras corte de energía ensayados antes de operar.
- [ ] Etapa de activación implementada y revisada por separado; ninguna operación autorizada por esta preparación.

## Evidencia de preparación técnica

- 30 controles de candidata aprobados en Windows sobre el código `760791f`:
  esquema, catálogo/precios/promos, stock cero pendiente, roles inactivos, permisos privados reales,
  errores de permisos sin DB ni credenciales, no reutilización, bloqueo SQL, apertura genérica incluso
  renombrada, entorno con fuente ficticia ignorada, reinicio de procesos, restore aislado, snapshots
  alterados/ajenos/con auxiliares/sin bloqueos rechazados. Repetidos tras el ajuste final de persistencia de backup.
- Regresión sobre `2de5f47`: 47 aprobadas y 2 omitidas de navegador. Incluye database, catálogo comercial,
  Abadion Pruebas, contabilidad POS, separación de cajas y usuarios. El cambio posterior sólo agrega
  persistencia explícita de snapshot/manifiesto y cobertura Windows en CI; sus 30 controles fueron repetidos.
  Total: **77 casos distintos aprobados**, sin sumar las repeticiones.
- Instalador PowerShell real ensayado con código exportado por SHA `2de5f474fe8c89b3e7e92b37c1d1da38db0a2be2`
  en un destino temporal nuevo: entornos y dependencias independientes, catálogo exacto, backup inicial,
  permisos privados y candidata bloqueada. Ningún servidor iniciado.
- Sintaxis Python/PowerShell y limpieza del diff comprobadas. Las suites de CI del PR deben revisarse
  en su cabecera exacta; esta evidencia local no declara aprobada una ejecución remota pendiente.
- No se ejecutaron reinicio físico de Windows, corte de energía, aceptación de saldos reales ni activación.
  No se abrió ningún libro histórico ni instalación existente.
- La primera CI Linux detectó conversión automática de finales de línea del catálogo. Se fijó su
  representación CRLF en `.gitattributes` para conservar el SHA-256 aprobado en Windows, Linux y archivos
  exportados, sin cambiar productos ni precios. Se añadió un control de `git archive` con autocrlf deshabilitado.
  El ensayo persistente Windows del código `760791f` también aprobó preparación, dos procesos nuevos,
  restore aislado y rechazo de reutilización; la SQLite original conservó su hash.


## Continuación de Work: dos saldos y control progresivo (24/11/2026)

Se mantiene el mismo PR borrador #37, basado en #36: la UX y la contabilidad completan la candidata
bloqueada que ese PR prepara. No se fusiona ninguna rama. La candidata V2 se crea en un destino nuevo;
no hay migración ni actualización automática de candidatas V1 o instalaciones de Pruebas.

La revisión inicial de la CI `45475795367` encontró Linux aprobado, Edge aprobado y candidata Windows
fallida. La causa fue el directorio temporal abreviado 8.3 (`RUNNER~1`), distinto de su ruta resuelta.
El creador ahora rechaza enlaces/junctions **antes** de resolver el nombre abreviado; sigue rechazando
rutas sincronizadas y destinos existentes. No se debilita la ACL privada para acomodar al entorno.

La V2 prepara dos filas de saldos **NULL**, sin corte ni responsable; cero deudas de apertura y cero pagos.
Todos los bloqueos SQL se conservan, también sobre las tablas nuevas. Las API operativas continúan
aceptando exclusivamente identidades ficticias existentes; la conexión general rechaza la candidata.
No hay ruta para cargar saldos reales, fijar el corte ni habilitarla. Los escenarios con apertura y deuda
se construyen únicamente en fixtures temporales de ensayo.

El resumen presenta dos saldos propios y la custodia del repartidor por separado. Incluye cobros,
reversos, compras/reintegros y movimientos manuales una sola vez. La apertura no integra ingresos,
compras, gastos, resultado ni base del diezmo. El pago único de una deuda de apertura exige el saldo
completo, fondos en el sector responsable, sesión de Administración, motivo y UUID idempotente.
Guarda autor, fecha y solicitud; reduce disponible y pendiente sin repetir el gasto original.
No se implementó corrección/anulación de ese pago: queda pendiente definir un reverso auditable antes
de aceptar un circuito productivo de pagos de deuda. Nunca corregirlo borrando filas.

Compatibilidad interna: los receptores nuevos terminan en `_saldo_unificado`. El medio del movimiento
SQLite queda NULL (no identificado), mientras la solicitud y el pedido conservan `saldo_unificado`.
Los informes y la conciliación reconocen estos cobros por receptor y venta vinculada. NULL en una
transferencia o entrega de delivery sigue teniendo su significado anterior. No se recodifica ningún
movimiento histórico como unificado, efectivo o transferencia.

Postres se descuentan por SKU en la transacción de venta; una anulación devuelve sólo lo descontado.
La política nueva impide confirmar faltantes por API. Una bebida sin reposición validada se rechaza
aunque una pantalla antigua la envíe. Registrar una compra repone stock y paga desde una de las dos
cajas; no habilita automáticamente bebidas. La acción de Administración compara el conteo positivo
con la existencia registrada y deja referencia, autor y fecha antes de habilitar ese SKU.

Los datos financieros y de stock informados en la conversación son **referencias privadas pendientes**.
No se incorporan al catálogo, fixtures, base candidata ni código del repositorio. En el corte se deberán
reconfirmar ambos saldos, ausencia de fiados, deuda sólo de Rotisería con pago único y vencimiento,
los seis conteos de postres y la ausencia inicial de bebidas. Ninguna venta anterior al instante efectivo
se importa o se registra de nuevo; las obligaciones anteriores se representan sólo por su saldo de apertura.

### Condiciones pendientes para el 25/11/2026

El 25/11 es una fecha potencial, **no una habilitación viable sin completar estas condiciones**:

- [ ] Revisión humana y CI verde del SHA exacto, incluyendo Windows/Edge.
- [ ] Reconformar datos a la hora real del corte en Buenos Aires, identidad y responsable.
- [ ] Implementar/revisar por separado el registro atómico de apertura y el mecanismo de activación.
- [ ] Resolver aceptación del reverso auditable de pagos de deuda y el cierre operativo de saldo unificado.
- [ ] Ensayar fiados, delivery, permisos individuales, recuperación, dispositivos y reinicio físico de Windows.
- [ ] Confirmar exclusión del bot y asignar cada pendiente a un único libro. No tocar el bot para comprobarlo.
- [ ] Aprobación explícita de corte, importes, conteos, respaldos y posterior habilitación.

La jornada física anterior sigue disponible sólo para compatibilidad de instalaciones ficticias existentes;
la pantalla unificada no ofrece arqueo separado por medio. El cierre operativo definitivo del saldo total
requiere una revisión propia: no presentar un arqueo de efectivo como cierre del saldo unificado.


### Evidencia local de esta continuación

- Ensayo completo SQLite/API: 449 aprobadas, 30 omitidas y dos diferencias de contrato en el estado
  público de instalaciones anteriores. Ambas tenían la misma causa: agregar `saldo_unificado:false`.
  Se corrigió omitiendo el campo cuando el modelo no existe; ambos casos pasaron al repetirse.
- Verificación focal final: **49 aprobadas** sobre candidata, saldos, deuda, stock, corte con zona horaria,
  concurrencia, sesión cambiada, adelanto de delivery fiado cobrado en otra caja y Edge. Los dos casos anteriores pasaron por separado.
  No sumar estas cifras como casos únicos ni atribuir a la ejecución inicial las pruebas agregadas después.
- Edge con perfil temporal: dos saldos sin desglose por medio, venta de postre confirmada con doble clic
  una sola vez, saldo actualizado y captura `abadion-paso-saldo-unificado.png` con datos ficticios.
- Candidata: 38 controles específicos, incluidos cinco nuevos bloqueos SQL, filas de apertura NULL,
  bebidas no habilitadas, permisos privados Windows y alias de ruta 8.3. Backup/restore siguen bloqueados.
- Sintaxis Python y diff verificados; demo estática generada comparada con su fuente, sin diferencias.
- CI remota debe verificar de nuevo el commit publicado; ningún resultado local habilita Producción.

- La revisión final agregó el escenario de adelanto de delivery fiado con cobro posterior en otra caja.
  Se reutiliza la definición de custodia del motor de delivery: una entrega ya realizada no es custodia
  negativa y su salida sí reduce el saldo propio del sector pagador. Los cobros posteriores restituyen
  fondos al receptor elegido sin alterar la deuda del cliente dos veces.

- CI Linux del código `afca240`: 460 aprobadas, 31 omitidas, un fallo en el ensayo previo de cierre/reinicio
  de Preproducción. El puerto se liberaba antes que `uso.lock`. El comando de cierre ahora espera ambos
  dentro del plazo original, sin finalizar procesos a la fuerza; los errores de ruta no se reintentan.
  Los tres controles deterministas de esa carrera y el ensayo real de inicio/reinicio/cierre en Windows
  pasaron (4 casos). Se incorporan a CI y se requiere una ejecución nueva del commit corregido.
