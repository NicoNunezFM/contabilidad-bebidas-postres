# Candidata de producción con contabilidad nueva

Estado: **bloqueada, offline, sin fecha efectiva de corte ni operaciones habilitadas**.
La preparación actual es V3 y sólo crea destinos nuevos. Las secciones de evidencia V1/V2
son históricas; la continuación V3 al final describe el alcance vigente.
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

- En `e2dd09b`, Linux aprobó 464 casos (31 omitidos) y Windows/Edge aprobó sus 149 casos de flujo.
  La etapa de candidata rechazó la representación textual de ACL del runner. La comprobación ahora
  lee el descriptor nativo de Windows y compara los SIDs numéricos, máscara de control completo,
  tipo de ACE y flags de herencia, con DACL protegida y exactamente usuario actual más SYSTEM.
  No acepta alias textuales como prueba de acceso ni agrega excepciones para administradores.
  Los 38 controles de candidata pasaron localmente con ese lector, y dos ataques de permisos
  (acceso extra de terceros y herencia reactivada) fueron rechazados. CI comprueba ahora la candidata
  antes de iniciar los ensayos Edge para detectar pronto errores de permisos.

- La nueva CI siguió rechazando la ACL aun leyendo SIDs nativos. Se mantuvo el rechazo y se cambió
  la creación de carpetas nuevas para reemplazar la DACL completa por exactamente dos permisos,
  en vez de conservar posibles reglas explícitas predeterminadas al retirar sólo la herencia.
  El instalador aplica lo mismo a su raíz nueva. La comprobación nunca repara una carpeta existente.
  Pasaron 40 controles de candidata y un control adicional con una regla explícita de terceros sobre
  carpeta ficticia recién creada: al crear la ACL exacta quedaron sólo usuario y SYSTEM. Los rechazos
  de terceros y herencia siguen vigentes. Requiere confirmar esta creación en la nueva CI Windows.

## Continuación V3: protocolo de ensayo, reversos y conciliación

Esta continuación completa la preparación del mismo PR #37, que permanece en borrador.
**No hay activación productiva, servidor de candidata ni valores reales cargados.**
La identidad ahora es `PRODUCCION-CANDIDATA-BLOQUEADA-V3`; se crea exclusivamente en un destino
nuevo. No se migran ni actualizan candidatas V1/V2 o instalaciones existentes.

### Apertura atómica ensayable

`src/pos_apertura_ensayo.py` implementa un protocolo interno sin endpoint ni comando de instalación.
Sólo admite una identidad de Preproducción **ficticia**, sin operaciones, stock previo ni pendientes.
Rechaza el marcador de candidata independientemente de su application_id. No retira ningún bloqueo,
cambia identidades, habilita usuarios ni constituye consentimiento para operar en producción.

El modelo exige UUID, instancia, responsable, evidencia identificada por SHA-256, versión declarada,
huella del catálogo consultado, instante no futuro con zona Buenos Aires, exactamente dos saldos,
conteo completo de cada SKU de postres incluidos ceros, bebidas inicialmente sin existencias y bloqueadas,
deuda tarjeta de Rotisería de pago único (o ausencia explícita), fiados previos cero y confirmaciones
de conciliación sin duplicados, ausencia de tránsito y aceptación del modelo de Rotisería.
Los importes de los ensayos son sintéticos y no reproducen las referencias privadas del usuario.

El ensayo posee su transacción `BEGIN IMMEDIATE`: saldos, stock, deuda, corte contable y registro
inmutable se confirman juntos. Un error al insertar el registro final revierte todos los cambios.
Repetir el mismo UUID, contenido y autor devuelve el resultado original; un contenido o autor diferente
es rechazado. No genera ventas, ingresos, gastos ni diezmo de apertura.

La versión de código y la evidencia son declaraciones del ensayo: **no son firmas, aprobación humana,
verificación del SHA ejecutado ni aceptación operativa**. La futura apertura real deberá vincular la
identidad y manifiesto de la release, CI del SHA exacto, evidencia privada reconfirmada al corte y
consentimiento humano explícito. El protocolo de ensayo no se puede usar para activar una candidata.
Si hay fiados anteriores o circunstancias fuera del modelo acordado, se requiere revisión separada.

### Reverso de pagos de deuda

En la API ficticia, Administración puede registrar `/saldo-unificado/pagos/{id_pago}/reverso` con
UUID y motivo obligatorio. Debe representar un pago no realizado o fondos efectivamente devueltos;
no sirve para sumar disponibilidad sin conciliación. El pago original se conserva, el reverso queda
vinculado a él y restituye saldo y obligación exactamente una vez, sin nuevo gasto o diezmo.
Pago y reverso conservan autor, fecha, solicitud y resultado; SQL impide modificarlos o borrarlos.

Puede registrarse después un nuevo pago completo con otro UUID, con fondos suficientes y en la caja
responsable. Sólo puede existir un pago vigente por deuda. Un reintento del pago original después de
su reverso devuelve su respuesta histórica, sin volver a descontar dinero; el resumen refleja el estado
actual y muestra los pagos revertidos. Concurrencia y roles se verifican dentro de la transacción.

### Cierre y conciliación del saldo total

Administración consulta `/saldo-unificado/conciliacion` y confirma `/saldo-unificado/cierres`.
La pantalla permite contar un saldo total por sector y, por separado, custodia del repartidor.
Exige referencia, motivo, revisión vigente y secuencia siguiente. La revisión incorpora el libro de
movimientos y cierres: movimientos compensados tampoco permiten confirmar una consulta desactualizada.
Dos confirmaciones del mismo UUID producen un único cierre; otra solicitud con la revisión antigua se rechaza.

El cierre es una constancia inmutable de conciliación con autor, fecha, saldo del libro, conteos y ambas
diferencias. **No ajusta saldos, genera movimientos ni traslada diferencias al siguiente período.**
Permite nuevas operaciones posteriores al instante registrado, como siguiente tramo de conciliación.
Los reversos posteriores se ven en el tramo nuevo y no reescriben el cierre anterior. Las diferencias
quedan pendientes de resolución documentada; no se corrigen borrando filas o con apertura nueva.
No reemplaza ni presenta como equivalente el arqueo físico heredado por medio ni cierra automáticamente
sus jornadas. El procedimiento operativo de entrega de turno y aceptación física sigue pendiente.

### Condiciones de producción que continúan bloqueadas

- [ ] Revisar código y CI del SHA exacto de V3; conservar PR borrador sin fusionar.
- [ ] Diseñar y revisar la activación real separada; no reutilizar el consentimiento del ensayo.
- [ ] Reconfirmar privadamente instante de corte, dos saldos, deuda/vencimiento, fiados y cada conteo físico.
- [ ] Confirmar catálogo, asignaciones sin duplicación, ausencia de operaciones en tránsito y exclusión del bot.
- [ ] Aceptar el procedimiento de cierre y resolución de diferencias, con responsables individuales.
- [ ] Ensayar dispositivos reales, reinicio físico de Windows y recuperación tras corte de energía.
- [ ] Verificar respaldo externo y recuperación en un destino nuevo, cuentas y permisos individuales.
- [ ] Obtener consentimiento humano explícito para apertura y posterior habilitación.

No se promete una fecha de inicio. Hasta completar esas condiciones, la candidata permanece bloqueada,
con corte y saldos NULL, usuarios deshabilitados, stock cero pendiente y ninguna operación registrada.

### Validación de V3

- Windows, última revisión local del protocolo y bloqueos: **69 pruebas aprobadas** en
  `test_preparacion_unificada.py` y `test_produccion_candidata.py`. Incluye rollback en el último
  INSERT, concurrencia, revisión obsoleta aun con movimientos compensados, custodia separada,
  roles, historial inmutable, reinicio de conexiones, procesos nuevos y restauración ficticia.
- Edge: circuito de venta, pago de deuda, reverso y cierre con doble clic aprobado en un perfil
  temporal; sin duplicados ni ajuste de saldo por el cierre. Sintaxis JavaScript del POS aprobada.
- Una ejecución anterior de los tres módulos focales aprobó 70 casos y omitió uno de navegador,
  ejecutado por separado. Las cifras se solapan y no representan casos únicos sumables.
- Las primeras pruebas API dentro del entorno restringido no pudieron crear el socket interno de
  asyncio en Windows. Se interrumpieron y se repitieron con conexiones locales disponibles;
  ese bloqueo del entorno no se contó como aprobación ni se cambió el código para eludirlo.
- La regresión completa y CI del nuevo SHA deben comprobarse antes de aceptar esta revisión.
  Los resultados anteriores del SHA `2670023` no validan automáticamente V3.
- Reinicio físico, pérdida de energía, checklist de dispositivos, valores reales, consentimiento
  y activación productiva continúan pendientes. Ninguna base anterior ni bot se abrió o modificó.
