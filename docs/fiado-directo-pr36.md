# Fiados más simples — actualización manual del PR #36

24/11/2026. Rama existente `integration/abadion-v1-pruebas-continuas`, sobre `48caa79ff747ab5107adbd4e931c055d7c6d805d`. Sin rama adicional, PR nuevo, fusión ni habilitación de producción.

## Cambio visible

En Pendiente / Fiado, escribir un nombre o apodo busca automáticamente. Para una persona nueva, pulsar **Crear cliente: Onchi** y luego **Confirmar fiado · $9.000,00**. El teléfono es opcional; el alta selecciona al cliente y lleva el foco a confirmar. Los campos de alta desaparecen después de seleccionar para dejar visible la identidad y el resumen. No hace falta abrir Alta rápida ni repetir el nombre.

Si existe, pulsar su ficha identificada por nombre, ID, teléfono y referencia. Nunca se selecciona automáticamente por coincidencia de nombre. Para crear otra persona con el mismo nombre, se requiere teléfono o referencia. Antes de elegir una ficha verificar que corresponde a la persona: el programa no puede distinguir homónimos sin información humana.

El resumen muestra **Total / Pagado / Queda debiendo**, incluido el envío según el circuito vigente. **Agregar pago** conserva el fiado parcial. Cambiar el nombre invalida la selección anterior. Enter en el campo vuelve a buscar; Tab recorre los controles y Enter activa la ficha o confirmación enfocada. Botones de al menos 44 px; el diálogo permite desplazamiento vertical.

## Protección de operaciones y datos

Se mantienen las rutas API, validaciones, permisos, sesiones, esquema SQLite y auditoría existentes. No hay migraciones ni cambios en cálculos contables. El alta bloquea doble clic y conserva UUID y contenido durante un resultado incierto: **Reintentar la misma alta** consulta/repite esa operación. Mientras tanto bloquea cambios de identidad y confirmación de venta. Una búsqueda fallida no habilita crear a ciegas y una respuesta antigua no reemplaza la búsqueda actual. Seleccionar limpia mensajes de error anteriores.

Ventas y abonos siguen utilizando su idempotencia original. Crear al cliente y confirmar la venta son dos operaciones explícitas: cancelar después de crear conserva una ficha sin deuda. La protección por UUID cubre reintentos en el mismo diálogo; no es una prohibición global de homónimos ni una deduplicación entre dispositivos. Si se cierra el diálogo con un alta incierta, buscar la ficha antes de volver a crear.

## Actualizar exclusivamente Abadion Pruebas

Estos pasos son para que el usuario los ejecute manualmente. No se ejecutaron contra la instalación existente. No reinstalar, no preparar una base nueva y no volver a aprobar el catálogo. No usar el servidor general ni modificar accesos directos, WhatsApp, negocio.db, Entrenamiento o Preproducción.

En PowerShell, desde el checkout de código del PR #36 (ajustar sólo `$CodigoAbadion` si el usuario lo guarda en otro sitio):

```powershell
$CodigoAbadion = 'C:\Users\sergi\OneDrive\Documentos\ChatGPT\Abadion\abadion-pruebas'
$DatosAbadion = Join-Path $env:LOCALAPPDATA 'Abadion\Pruebas'
$AtajoAbadion = Join-Path $DatosAbadion 'Abadion-Pruebas.ps1'
& $AtajoAbadion estado
& $AtajoAbadion backup
& $AtajoAbadion detener
```

Cerrar únicamente la ventana del perfil Edge de Pruebas. El backup manual permite conservar un punto previo explícito; el actualizador además realiza y verifica su propio backup obligatorio.

```powershell
Set-Location -LiteralPath $CodigoAbadion
if ((git branch --show-current).Trim() -ne 'integration/abadion-v1-pruebas-continuas') {
    throw 'Esta carpeta no está en la rama del PR #36.'
}
if (git status --porcelain) { throw 'Hay cambios locales: conservarlos y revisar antes de actualizar.' }
git fetch origin integration/abadion-v1-pruebas-continuas
if ($LASTEXITCODE -ne 0) { throw 'Falló la descarga de la rama.' }
git pull --ff-only origin integration/abadion-v1-pruebas-continuas
if ($LASTEXITCODE -ne 0) { throw 'No se pudo avanzar sin combinar cambios.' }
$NuevaVersionAbadion = (git rev-parse HEAD).Trim()
$NuevaVersionAbadion
```

Verificar que ese SHA corresponde al commit entregado en #36 y que sus controles SQLite/API y Windows/Edge estén aprobados. Si hay commits posteriores, revisar sus resultados antes de seguir.

```powershell
& $AtajoAbadion actualizar --origen $CodigoAbadion --commit $NuevaVersionAbadion
if ($LASTEXITCODE -ne 0) { throw 'Actualización rechazada: conservar mensajes y no copiar archivos manualmente.' }
& $AtajoAbadion comprobar
if ($LASTEXITCODE -ne 0) { throw 'No iniciar hasta revisar la comprobación.' }
& $AtajoAbadion iniciar
& $AtajoAbadion estado
```

El mecanismo de #36 valida backup, UUID, integridad, hashes y esquema con el candidato en sólo lectura; activa la versión por SHA de forma atómica. Conserva stock, catálogo, clientes, sesiones y movimientos de la misma base. La URL sigue siendo `http://127.0.0.1:8079/pos/`, con banda **ABADION PRUEBAS — DATOS FICTICIOS**. Guardar el SHA y nombre de backup informados. Si la carpeta instalada no es la indicada, usar el launcher manual de esa instalación de Pruebas; no inventar ni crear otra instalación para actualizar.

Para volver al código anterior, conservando también las operaciones registradas después de actualizar:

```powershell
& $AtajoAbadion detener
& $AtajoAbadion rollback
if ($LASTEXITCODE -ne 0) { throw 'Rollback rechazado: revisar el mensaje antes de iniciar.' }
& $AtajoAbadion comprobar
& $AtajoAbadion iniciar
```

Rollback verifica otro backup y cambia sólo la versión de código. No reemplazar la base con un backup antiguo. La recuperación de datos se hace exclusivamente en otra carpeta según [la guía de #36](abadion-pruebas-continuas.md#6-recuperar-un-backup-en-otra-carpeta-incluso-con-base-dañada-o-ausente).

## Repetir la aceptación con dinero ficticio

1. Abrir Pruebas en 8079, ingresar con el rol habitual y comprobar la banda ficticia. Mantener los fondos existentes. Si la caja está cerrada, abrirla con el monto ficticio que realmente se desea ensayar.
2. Agregar **Clásica doble $9.000**, retiro en el local, **Pendiente / Fiado**. Escribir **Onchi**. Si ya existe por un intento anterior, seleccionar su ficha después de verificar ID/referencia; si no existe, **Crear cliente: Onchi**, sin teléfono.
3. Verificar cliente seleccionado, **Total $9.000 / Pagado $0 / Queda debiendo $9.000**, y pulsar **Confirmar fiado · $9.000** una vez. La deuda crece $9.000; el efectivo no cambia. Si se creó un pedido, marcarlo Entregado con el saldo pendiente visible.
4. Entrar en **Clientes**, buscar y abrir la misma ficha de Onchi. Anotar el saldo previo, especialmente si ya tenía historial. Pulsar **Registrar abono**, ingresar **$4.000**, seleccionar el medio y receptor reales de esta prueba (por ejemplo efectivo / caja Rotisería), revisar distribución FIFO y confirmar.
5. En una cuenta que antes estaba en cero, queda **$5.000** de deuda y el receptor aumenta **$4.000**, sin otra venta. Si había deuda previa, comparar incrementos: +$9.000 y luego −$4.000. FIFO puede imputar el abono a ventas anteriores; no borrar historial para forzar el ejemplo.
6. Comprobar una sola venta y un solo abono, saldo por sección, stock y conciliación con Administración. Registrar SHA, rol, pasos y resultado, sin compartir claves ni datos personales.

## Evidencia automatizada

Los resultados finales y comandos reproducibles se registran en [el informe de pruebas](informe-pruebas-continuas.md). Todos los ensayos usan carpetas temporales, SQLite ficticias y perfiles Edge separados; el servidor del navegador usa un puerto libre temporal y el launcher de Pruebas conserva su contrato 8079. No se lanzó ni se actualizó la instalación del usuario.

Pendientes de aceptación humana: tacto físico en el equipo del usuario y repetición manual posterior a la actualización. El toque emulado en Edge no sustituye el tacto físico.
