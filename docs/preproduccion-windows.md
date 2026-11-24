# Abadion V1: preproducción persistente Windows / Edge

> Ampliación candidata, sin instalar: [comparación #29/#30 y catálogo offline seguro](consolidacion-preproduccion-windows-v1.md).
> Las instrucciones y evidencias originales siguientes corresponden a #29; no ejecutarlas
> para actualizar la instalación existente sin autorización explícita.

Base funcional y contable: PR #27, `integration/abadion-premium-edge`, commit
`5d44eba6d18363789253d63df7cc58f448e849e1`. Rama independiente:
`feature/abadion-v1-preproduccion-persistente`. No habilita producción ni migra datos.

## Inspección y decisiones

Se inspeccionaron `database.py`, `backups.py`, los inicializadores de Entrenamiento,
`servir_pos_windows_ficticio.py`, autenticación, router POS, bot y launcher Windows local.
El acceso directo validado invoca `Iniciar Abadion/abadion_launcher.py`: puerto 8076,
checkout en Temp y SQLite temporal eliminado al detener. Ese directorio y acceso directo
se mantienen intactos. Entrenamiento persistente usa su carpeta, marcador y puerto 8060.
El backup existente copia con SQLite, pero no valida integridad ni restaura automáticamente.
Por eso el nuevo ambiente implementa su propio ciclo de respaldo verificado.

| Ambiente | Base / ubicación | Acceso |
| --- | --- | --- |
| Práctica Edge validada | temporal creada por su launcher | 127.0.0.1:8076 |
| Entrenamiento persistente | LocalAppData/Abadion/Entrenamiento/abadion-entrenamiento.db | 127.0.0.1:8060 |
| PREPRODUCCIÓN ficticia | LocalAppData/Abadion/Preproduccion/abadion-preproduccion.db | 127.0.0.1:8078 |
| Instalación anterior / negocio.db | sin acceso desde este launcher | sin cambios |
| Producción futura | sin crear, sin configurar | deshabilitada |

La nueva API monta solamente el router POS; `/comandos`, `/ventas` y `/compras`
del legado no existen en ella. Las compras del POS conservan el contrato de PR #27.
Se reutiliza su esquema ficticio y su capacidad interna de Entrenamiento para mantener
fiados, promociones y caja diaria. El archivo tiene un marcador **exclusivo** de
preproducción y UUID ligado a `instalacion.json`; no tiene marcador de Entrenamiento.
El abridor de Entrenamiento lo rechaza, y `obtener_conexion()` normal rechaza también
copias renombradas con ese marcador. Cada solicitud fija su propio contexto de base:
`NEGOCIO_DB_PATH` no puede redirigirla a un archivo real. El worker descarta variables
heredadas de bases, tokens y simulación; no carga `.env`.

Cookies, cuentas y claves aleatorias son exclusivas. Edge usa un perfil independiente
en `Preproduccion/Edge`, evitando sesiones y almacenamiento local del acceso validado.
El aviso permanente indica PREPRODUCCIÓN / DATOS FICTICIOS / SIN VALIDEZ CONTABLE.
No se cambia `pos-web/index.html` ni se incorporan los tres ajustes visuales paralelos.

La protección previene cruces accidentales a través de esta versión de la aplicación.
No pretende impedir que el mismo usuario de Windows abra SQLite manualmente, ni
modifica versiones antiguas del bot o de otros checkouts. No les configure esta ruta.
El instalador restringe la carpeta al usuario actual y SYSTEM mediante ACL de Windows.
Nunca copie sus credenciales a Entrenamiento ni a WhatsApp.

## Instalar una vez

Requiere Windows, Python 3.12, Edge y acceso para instalar dependencias. Ejecute desde
la nueva rama; no desde Entrenamiento ni desde el acceso directo existente:

```powershell
$ErrorActionPreference = 'Stop'
git clone --branch feature/abadion-v1-preproduccion-persistente --single-branch https://github.com/NicoNunezFM/contabilidad-bebidas-postres.git abadion-preproduccion
if ($LASTEXITCODE -ne 0) { throw 'Falló la descarga' }
Set-Location -LiteralPath .\abadion-preproduccion
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\Instalar-Preproduccion.ps1
if ($LASTEXITCODE -ne 0) { throw 'Falló la instalación; revise el mensaje antes de continuar' }
```

El instalador crea una copia de código y un entorno Python propios en
`$env:LOCALAPPDATA\Abadion\Preproduccion\app`. Copia sólo código, scripts, POS,
documentación y requisitos; no bases, `.env`, bot ni credenciales Git. El código y la
base sobreviven a limpieza de Temp y reinicios. Si ya existe el destino, se detiene.
Una instalación interrumpida no se borra ni se reinicializa automáticamente: conserve
la carpeta y revise el paso fallido antes de reparar. No copie otro archivo sobre la base.

Se crea un catálogo **vacío**, stock y cajas sin abrir, sin movimientos. Los usuarios
son `admin-preprod` y `ventas-preprod`, con contraseñas distintas y aleatorias en
`credenciales.json` dentro de la carpeta privada. No publicar ese archivo ni
`instalacion.json` (contiene la clave del control local).

## Operación PowerShell

```powershell
$PreAbadion = Join-Path $env:LOCALAPPDATA 'Abadion\Preproduccion'
& (Join-Path $PreAbadion 'iniciar-preproduccion.cmd')
& (Join-Path $PreAbadion 'estado-preproduccion.cmd')
& (Join-Path $PreAbadion 'backup-preproduccion.cmd')
& (Join-Path $PreAbadion 'detener-preproduccion.cmd')
```

Abrir los `.cmd` con doble clic también funciona. No se crea ni reemplaza el acceso
directo existente. Detener cierra únicamente este servidor mediante control autenticado,
espera la salida normal y conserva la base. Un segundo inicio reutiliza la misma instancia.
El bloqueo de Windows permanece mientras vive el worker y se libera si falla el proceso.
Un puerto ocupado por un servidor ajeno produce un error: no lo abre ni lo detiene.
Una restauración con el servidor activo se rechaza. Si arranque o detención exceden
el plazo, revise `servidor.log` y `estado` antes de reintentar; no se fuerza la terminación.

El servidor no se inicia con Windows automáticamente. Tras reiniciar, abra el nuevo
`iniciar-preproduccion.cmd`; el archivo SQLite permanece en su ruta. Evite mover o
renombrar la carpeta, cuyo nombre y ubicación forman parte de la identidad instalada.

## Backups y restauración

Se crean al preparar, iniciar, cada hora mientras está abierto, detener y a pedido.
Se usa `Connection.backup()`, no una copia del archivo abierto. Cada snapshot exige
`integrity_check=ok`, `foreign_key_check` vacío, identidad y versión correctas; un JSON
asociado registra modo, UUID y SHA-256. No hay eliminación automática de backups en
esta primera versión: revise espacio libre. Un fallo automático se registra como
`backup-fallido` en `auditoria.jsonl`; un fallo al iniciar impide el arranque.

Los backups locales no cubren pérdida del disco. Una política externa cifrada y su
restauración en otro equipo quedan pendientes antes de cualquier producción.
No se afirma que el JSON/SHA sea una firma contra manipulación deliberada.

Para restaurar **sólo un backup de esta misma instalación**, detenga primero:

```powershell
$PreAbadion = Join-Path $env:LOCALAPPDATA 'Abadion\Preproduccion'
$PythonPreAbadion = Join-Path $PreAbadion 'app\.venv\Scripts\python.exe'
$ScriptPreAbadion = Join-Path $PreAbadion 'app\scripts\abadion_preproduccion.py'
& $PythonPreAbadion $ScriptPreAbadion --carpeta $PreAbadion detener
if ($LASTEXITCODE -ne 0) { throw 'No se pudo detener' }
Get-ChildItem -LiteralPath (Join-Path $PreAbadion 'backups') -Filter '*.db'
# Reemplace el nombre siguiente por uno listado arriba, sin directorios.
& $PythonPreAbadion $ScriptPreAbadion --carpeta $PreAbadion restaurar --archivo 'NOMBRE-DEL-BACKUP.db'
if ($LASTEXITCODE -ne 0) { throw 'Restauración rechazada; conserve la base actual y revise el error' }
& $PythonPreAbadion $ScriptPreAbadion --carpeta $PreAbadion iniciar
```

Se valida el hash y la identidad, se verifica el SQLite en staging, se crea un backup
`pre-restore`, y recién entonces se reemplaza atómicamente la base. Se invalidan las
sesiones y hay que autenticarse otra vez. Se rechazan backups ajenos, alterados, rutas
externas, enlaces y archivos auxiliares de SQLite pendientes. Tras un corte abrupto,
inicie y detenga normalmente para permitir recuperación del journal antes de restaurar.
Si queda `restore-pendiente.db` tras un corte, consérvelo para revisión; no se sobrescribe.

Si la base está dañada y no permite crear el respaldo previo, el restore normal se
rechaza. Con el servidor detenido, conserve la base dañada y todos sus auxiliares en
una carpeta de cuarentena para diagnóstico; nunca los borre. Una vez comprobado que
el destino está ausente y que `instalacion.json` sigue siendo el de esta instalación,
puede usar el mismo comando de restauración con `--base-ausente`. Esta opción sólo
admite un destino inexistente y un backup verificado de ese UUID; no sobrescribe archivos
ni crea otra instalación. Una instalación sin su configuración privada requiere una
recuperación administrada, no ejecutar `preparar` ni inventar un UUID.

`auditoria.jsonl` registra instalación, arranques, detenciones, backups y restores.
El libro de eventos contable de PR #27 conserva la auditoría de operaciones. No se
registran contraseñas ni tokens en los logs. Ante disco lleno, no borre bases ni snapshots
automáticamente; revise el error y libere espacio con control del operador.

## Catálogo y saldos iniciales: plan de importación validada

No se importan movimientos ficticios, cuentas, sesiones, precios ni importes antiguos.
El catálogo de Entrenamiento tampoco se publica como catálogo real automáticamente.
Esta entrega instala el ambiente vacío; el importador comercial queda como etapa separada.

1. Exportar a un archivo de revisión nombres, categorías, variantes, ingredientes,
   adicionales, unidades, relaciones y control de stock desde una fuente autorizada.
   Abrir el origen sólo para lectura. Excluir ventas, compras, fiados y cierres históricos.
2. Normalizar identificadores; validar nombres duplicados, referencias, categorías,
   unidades, precios en centavos, impuestos y disponibilidad. Revisar los precios uno
   por uno con el responsable; nunca asumir que un importe anterior es real.
3. Producir una vista previa y un informe de rechazos sin escribir. Aprobar el archivo
   exacto y su hash; registrar quién lo revisó, fecha y totales esperados.
4. Aplicar primero a una copia ficticia aislada, con backup previo, transacción única,
   reintento idempotente y conciliación de cantidades y relaciones. No copiar SQLite completo.
5. Registrar stock por conteo físico nuevo y efectivo inicial de cada caja por arqueo
   firmado en fecha de corte. Deudas iniciales requieren confirmación documental individual;
   no convertir saldos de prácticas en cuentas reales.
6. Repetir jornada y restauración. La creación futura de producción, sus usuarios y
   autorización de operaciones reales requieren otra entrega y aprobación explícita.

## WhatsApp: coexistencia revisada

`whatsapp-bot/index.js` usa `API_URL` (por defecto `http://127.0.0.1:8000/comandos`)
y `ABADION_BOT_TOKEN`; no abre SQLite directamente. Esta entrega no modifica ni inicia
el bot, no lee sus secretos y no configura `API_URL` ni su base. El nuevo 8078 no publica
`/comandos` ni acepta su token. No se conecta WhatsApp hasta validar explícitamente
el ambiente, autenticación, permisos, idempotencia y conciliación con datos ficticios.

## Pruebas reproducibles

```powershell
python -X utf8 -u -m pytest tests/test_preproduccion.py -q
python -X utf8 -u -m pytest tests -q
```

La prueba propia usa sólo carpetas temporales privadas llamadas `Preproduccion` y una
base ficticia. Comprueba usuarios y cookies ajenos, cruces por rutas y copias renombradas,
ausencia del API del bot, dos cajas, stock, compra cruzada, venta repetida idempotente,
fiado y abono, arqueos/cierres, conciliación, restore con sesiones revocadas, hash alterado,
lock, reinicio de servidor, duplicado, puerto ocupado e interrupción de transacción SQLite.
El ensayo de servidor requiere 8078 libre; si está ocupado se omite sin interferir.
UTF-8 evita que PowerShell/Windows intente enviar símbolos del POS a Node como CP1252.

Prueba manual pendiente para aprobación visual: abrir el nuevo `.cmd`, verificar en
Edge título/aviso, catálogo aprobado ficticio y perfil independiente; cerrar, reiniciar
Windows y volver a abrir. Comparar stock, saldos e historial contra la jornada anotada.
No confundir reinicios de procesos automatizados con un reinicio real de Windows.

## Evidencia local del 24 de noviembre de 2026

- Preproducción: **8 aprobadas**, incluida Edge, recuperación de destino ausente y
  captura UTF-8 de procesos con advertencias de hilos tratadas como errores.
- POS existente en Edge: **15 aprobadas** en la ejecución conjunta. El chequeo del
  aviso de Entrenamiento tuvo una intermitencia inicial; pasó aislado en el commit
  original y en esta rama. Se estabilizó esperando su posición visible después del clic,
  sin modificar la interfaz ni la expectativa del test.
- Regresión existente: **324 aprobadas, 19 omitidas**, y un fallo CP1252 al enviar
  JavaScript a Node. Se repitió su archivo con `python -X utf8`: **3 aprobadas**.
  No se presenta esa primera ejecución como una corrida completa sin fallos.
- Instalación real nueva en LocalAppData: entorno Python propio, permisos sólo para
  usuario/SYSTEM, arranque, duplicado, reinicio del servidor, backup, restore, ingreso
  y reporte vacío aprobados. SQLite íntegra, sin productos ni ventas. Quedó detenida.
- `pos-web` y `whatsapp-bot` no tienen cambios; el launcher y acceso directo existentes
  no se modificaron. No se abrió ni migró una base real.

Pendientes de aceptación: reinicio físico de Windows, operación manual con catálogo
ficticio aprobado y estrategia de respaldo externo. No se habilita producción.
