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
  Efectivo y cuentas digitales siguen diferenciados por receptor; los fondos del repartidor no son ingreso propio.
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

1. Contar por separado efectivo real de Rotisería y de Postres/Bebidas, con hora y responsable.
2. Conciliar todas las cuentas digitales vigentes con extractos a la misma hora. Identificar titular/cuenta,
   fondos pendientes, transferencias en tránsito y asignación por caja. Una cuenta compartida se cuenta una sola vez;
   la suma de sus asignaciones debe coincidir con el extracto. Confirmar ceros expresamente; desconocido no es cero.
3. Contar las nueve variantes controladas; registrar fecha y cada cantidad, diferencias y agotados.
   Revisar y aceptar el modelo de las otras 29 y decidir si requieren control adicional antes de vender.
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
- [ ] Efectivo de ambas cajas y totalidad de cuentas digitales conciliados y aprobados.
- [ ] Stock físico y modelo de control aceptados; deudas y créditos vigentes relevados expresamente.
- [ ] Bot contable excluido y pendientes asignados a un solo libro.
- [ ] Backup externo y restore aislado verificados; contraseñas privadas recuperables o renovables.
- [ ] Permisos, dispositivos, reinicio de Windows y recuperación tras corte de energía ensayados antes de operar.
- [ ] Etapa de activación implementada y revisada por separado; ninguna operación autorizada por esta preparación.
