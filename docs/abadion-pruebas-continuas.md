# Abadion V1.0 — Pruebas continuas en Windows y Edge

**Sólo dinero y datos ficticios. Producción no habilitada.** No reemplaza Entrenamiento ni Preproducción. No crea ni cambia accesos directos y no inicia WhatsApp.

## Estado verificado el 24 de noviembre de 2026

| PR | Rama / commit de cabecera | Revisiones y CI más reciente |
|---|---|---|
| #33 | `integration/abadion-v1-pos-persistente` · `6e8a297c1348620fe36d48a18ef157c4495fa967` | Abierto, borrador, sin revisiones/comentarios. [CI 45408708044](https://github.com/NicoNunezFM/contabilidad-bebidas-postres/actions/runs/45408708044): SQLite y Edge aprobados |
| #34 | `feature/lo-de-clau-pedidos-delivery` · `c6b9f79b8eb945214dd4815e8af72b31c1bc969c` | Abierto, borrador, sin revisiones/comentarios. [CI 45427701070](https://github.com/NicoNunezFM/contabilidad-bebidas-postres/actions/runs/45427701070): SQLite y Edge aprobados |
| #35 | `feature/abadion-catalogo-comercial` · `47bf78dccb1fd6e3c297cd58a070663499e550e4` | Abierto, borrador, sin revisiones/comentarios. [CI 45434926012](https://github.com/NicoNunezFM/contabilidad-bebidas-postres/actions/runs/45434926012): SQLite y Edge aprobados |

GitHub y `git fetch` confirmaron que no había avances posteriores en esas ramas ni otro PR de Pruebas. #35 acumula #34 y #33: esta rama parte de su SHA exacto; no reaplica sus commits. El PR se apila contra #35 para revisar sólo esta integración. No se fusiona ninguna rama.

El launcher antiguo `Iniciar Abadion/abadion_launcher.py` apunta a un checkout temporal, usa 8076 y una SQLite descartable; abre Edge sin perfil separado. El de Entrenamiento conserva su base y configuración propias. Preproducción usa 8078, UUID, schema v4, cookies propias, bloqueo del sistema operativo, snapshots SQLite verificados y catálogo offline. Se reutilizan esas primitivas con perfil explícito; el launcher de Preproducción continúa rechazando carpetas Pruebas. No se abrió ninguna base instalada para esta inspección.

## Qué se instala

En `%LOCALAPPDATA%\Abadion\Pruebas`, fuera de OneDrive:

- `abadion-pruebas.db`: única base persistente de este entorno.
- `instalacion.json`: ruta, modo `ABADION-PRUEBAS-FICTICIAS-V1`, UUID y token de control local.
- `credenciales.json`: claves aleatorias de `admin-pruebas` y `ventas-pruebas`. No compartir este archivo ni subirlo a GitHub.
- `releases\<SHA>\`: código de cada versión y su Python independiente. Exporta sólo `src`, `scripts`, `pos-web`, `docs` y requisitos desde un commit; excluye bot, bases, archivos locales y `.env`.
- `activa.json`: versión activa, versión anterior e ID de instancia. Cambio atómico al completar la validación.
- `backups\`: SQLite autocontenidas más manifiestos de identidad y SHA-256; `auditoria.jsonl` registra eventos.
- `Edge-Pruebas`: perfil propio de Edge, con cookies `abadion_pruebas_*`.

Escucha exclusivamente en `http://127.0.0.1:8079/pos/`. No usar el servidor general `src/api.py`, ni apuntar `NEGOCIO_DB_PATH` a esta base. Ese abridor rechaza el archivo reservado y las copias renombradas con su marcador. No hay ruta de fallback a `negocio.db`.

Se comprueban ruta local directa, archivos sin enlaces ni hardlinks, modo, UUID, `application_id`, `user_version=4`, marcador específico de Pruebas, integridad y claves foráneas. Un cambio de esquema se rechaza: esta versión **no ejecuta migraciones sobre los datos persistentes**. Una futura migración necesita otro diseño y ensayo independiente.

## 1. Obtener el código e instalar una vez

Requisitos: Windows, Git, Python 3.12 y Edge instalados, Internet para descargar dependencias. No requiere permisos de administrador. En PowerShell:

```powershell
$CodigoAbadion = Join-Path $env:USERPROFILE 'AbadionCodigoPruebas'
git clone --branch integration/abadion-v1-pruebas-continuas --single-branch https://github.com/NicoNunezFM/contabilidad-bebidas-postres.git $CodigoAbadion
Set-Location -LiteralPath $CodigoAbadion
$VersionAbadion = (git rev-parse HEAD).Trim()
$VersionAbadion
```

Revisar en el PR que la CI de **ese SHA** esté aprobada. Ejecutar entonces:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Instalar-Pruebas.ps1 -Commit $VersionAbadion
$DatosAbadion = Join-Path $env:LOCALAPPDATA 'Abadion\Pruebas'
$AtajoAbadion = Join-Path $DatosAbadion 'Abadion-Pruebas.ps1'
```

El instalador exige checkout limpio y SHA coincidente. Se detiene si Pruebas ya existe. Restringe la carpeta al usuario actual y SYSTEM. Un fallo no borra ni reinicia datos: conservar carpeta y logs para diagnóstico. Las versiones incompletas quedan en `.stage-*` sin activarse y no bloquean un nuevo intento de actualización del mismo SHA. No ejecutar nuevamente `preparar` sobre una instalación existente.

## 2. Revisar y aprobar el catálogo sólo en la base nueva

La instalación empieza sin productos ni historial. No copia datos de ningún otro entorno.

```powershell
$CatalogoAbadion = Join-Path $CodigoAbadion 'scripts\catalogo-comercial.json'
$PlanAbadion = (& $AtajoAbadion validar-catalogo --catalogo $CatalogoAbadion) | ConvertFrom-Json
$PlanAbadion | ConvertTo-Json -Depth 15 | Set-Content -Encoding utf8 (Join-Path $env:TEMP 'abadion-pruebas-vista-previa.json')
$PlanAbadion.productos | Select-Object nombre,id,stock_conservado,@{n='PrecioCentavos';e={$_.propuesto.precio_centavos}} | Format-Table -AutoSize
$PlanAbadion | Select-Object instancia,sha256,combinar_sabores_promo
```

Revisar los 38 nombres, precios y adicionales contra [la tabla comercial](catalogo-comercial-lo-de-clau.md). El archivo de vista previa queda en la carpeta temporal. La siguiente orden constituye la aprobación explícita del JSON y de la instancia mostrados; ejecutarla sólo después de revisarlos:

```powershell
& $AtajoAbadion aprobar-catalogo --catalogo $CatalogoAbadion --sha256 $PlanAbadion.sha256 --aprobar-instancia $PlanAbadion.instancia
```

Un hash distinto o un ID ajeno se rechazan antes de escribir. Se crea y verifica un respaldo previo; catálogo y registro de aprobación se guardan en una sola transacción. Sólo se admite una base nueva, sin productos, ventas, clientes, pedidos ni jornadas abiertas o cerradas. Después de aprobar no se puede volver a importar, incluso si se borraran productos. Las actualizaciones de código **nunca recargan el catálogo**.

Los 38 productos quedan incluidos en el menú y todos tienen stock almacenado **cero**. Eso no implica disponibilidad física: **9 controlan stock por unidad y 29 conservan el modelo sin control por unidad** del #35. Una bebida controlada con cero es rechazada al validar una venta; los productos sin control no acreditan existencias. No inventamos cantidades. Para ensayar ventas de bebidas, registrar una compra ficticia explícita desde Administración después de abrir cajas. No aprobar faltantes para simular un inventario existente. La política de inventario físico sigue pendiente de aceptación.

## 3. Usar, cerrar y respaldar

```powershell
& $AtajoAbadion iniciar
& $AtajoAbadion estado
& $AtajoAbadion backup
& $AtajoAbadion detener
```

Iniciar abre Edge con su perfil separado y banda **ABADION PRUEBAS — DATOS FICTICIOS**. Consultar las claves locales con `Get-Content -LiteralPath (Join-Path $DatosAbadion 'credenciales.json')`; no publicarlas. Abrir ambas cajas con fondos ficticios antes de operar. Cerrar la ventana de Edge no detiene el servidor: usar `detener`. Los datos permanecen después de detener e iniciar.

Los respaldos se hacen al crear la base, iniciar, cada hora, detener, aprobar catálogo y antes de actualizar o volver de versión. También hay backup manual, incluso con el servidor activo mediante control autenticado. Si el puerto corresponde a otra instancia se rechaza, sin detener procesos ajenos. No se fuerza el cierre de procesos.

## 4. Actualizar conservando stock, IDs e historial

Primero detener el servidor y cerrar la ventana del perfil de Edge de Pruebas. No cerrar otras ventanas de Edge del usuario.

```powershell
& $AtajoAbadion detener
Set-Location -LiteralPath $CodigoAbadion
git fetch origin
git switch integration/abadion-v1-pruebas-continuas
git pull --ff-only
$NuevaVersionAbadion = (git rev-parse HEAD).Trim()
$NuevaVersionAbadion
```

Revisar cambios y CI del SHA mostrado antes de activar:

```powershell
& $AtajoAbadion actualizar --origen $CodigoAbadion --commit $NuevaVersionAbadion
& $AtajoAbadion comprobar
& $AtajoAbadion iniciar
```

La actualización toma el bloqueo exclusivo y verifica la base actual; publica un backup y vuelve a validar hash, identidad e integridad. Exporta el commit a una carpeta de versión, instala dependencias en su propio entorno y comprueba hashes del código. El Python candidato abre la base en **sólo lectura** para validar UUID, esquema e integridad. Sólo entonces cambia `activa.json`. No ejecuta inicializadores ni modifica saldos, catálogo o historial. Un fallo de backup, instalación, código o esquema deja la versión activa anterior. No se actualiza con el servidor en uso. Conservar el mensaje que informa commit y nombre de backup.

## 5. Volver a la versión anterior sin perder operaciones

```powershell
& $AtajoAbadion detener
& $AtajoAbadion rollback
& $AtajoAbadion iniciar
```

Hace y verifica otro backup y valida la versión anterior contra la base actual, antes de cambiar el puntero. **Mantiene las operaciones posteriores a la actualización**, porque vuelve sólo el código. No hay versión anterior en la primera instalación. Si el esquema no es compatible, rechaza el rollback; no restaura silenciosamente una base antigua.

## 6. Recuperar un backup en otra carpeta, incluso con base dañada o ausente

Nunca sobrescribe el historial actual. Detener Pruebas. Elegir el nombre de backup y un directorio de destino nuevo, local y fuera de OneDrive, cuyo último componente sea `Pruebas`:

```powershell
Get-ChildItem -LiteralPath (Join-Path $DatosAbadion 'backups') -Filter '*.db' | Sort-Object Name
$BackupAbadion = Read-Host 'Nombre exacto del backup .db elegido'
$RecuperacionAbadion = Join-Path $env:LOCALAPPDATA ('Abadion\Recuperaciones\' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '\Pruebas')
& $AtajoAbadion recuperar --archivo $BackupAbadion --destino $RecuperacionAbadion
```

Valida hash, modo, UUID, esquema, integridad y referencias del backup antes de crear el destino. No abre la base dañada. Copia configuración y credenciales con acceso restringido, genera otro token de control y borra sesiones de la copia restaurada. Conserva el UUID del snapshot para verificar su origen. No instala un puntero activo ni reemplaza el original.

Para examinar la recuperación con el mismo código, usar la versión instalada explícita; mantener la instancia original detenida porque comparten 8079:

```powershell
$EstadoVersionAbadion = Get-Content -LiteralPath (Join-Path $DatosAbadion 'activa.json') -Raw | ConvertFrom-Json
$VersionInstaladaAbadion = Join-Path $DatosAbadion ('releases\' + $EstadoVersionAbadion.commit)
$PythonRecuperacionAbadion = Join-Path $VersionInstaladaAbadion '.venv\Scripts\python.exe'
$LauncherRecuperacionAbadion = Join-Path $VersionInstaladaAbadion 'scripts\abadion_pruebas.py'
& $PythonRecuperacionAbadion $LauncherRecuperacionAbadion --carpeta $RecuperacionAbadion comprobar
& $PythonRecuperacionAbadion $LauncherRecuperacionAbadion --carpeta $RecuperacionAbadion iniciar
# Tras revisar saldos, deuda, stock e historial:
& $PythonRecuperacionAbadion $LauncherRecuperacionAbadion --carpeta $RecuperacionAbadion detener
```

Un backup es un punto anterior: la copia recuperada no incluye movimientos posteriores a él. El original se conserva para compararlos. Para desastre de disco conservar además una copia externa de toda la carpeta Pruebas con sus manifiestos, configuración y código, con acceso privado. No hay retención automática ni borrado de versiones/backups; controlar espacio disponible. Si hay un archivo `activa.pendiente`, no borrarlo a ciegas: conservarlo y revisar la auditoría antes de reparar el puntero.

## Pruebas y seguimiento de incidencias

La matriz y resultados están en [informe-pruebas-continuas.md](informe-pruebas-continuas.md). Para repetir en un checkout de ensayo:

```powershell
$env:PYTHON_DOTENV_DISABLED = '1'
$env:PYTHONUTF8 = '1'
$env:NEGOCIO_DB_PATH = Join-Path $env:TEMP ('abadion-regresion-' + [guid]::NewGuid() + '.db')
$env:POS_TEST_BROWSER = "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe"
python -m pip install -r .\requirements-tablet-test.txt
python -m pytest -q -rs --junitxml=abadion-resultados.xml
```

Para cada error manual anotar SHA de `activa.json`, rol, pasos, resultado esperado y obtenido; ocultar claves y clientes. Corregir en una rama, ejecutar SQLite/API y Edge, revisar y actualizar por SHA. No usar `git pull` dentro de `releases`, no copiar archivos encima de una versión instalada y no volver a preparar la base.

**Pendientes:** aceptación familiar de precios/flujo, tacto físico en PCBOX, reinicio de Windows, corte de energía y recuperación externa en otra PC. Los ensayos automáticos y el toque emulado no sustituyen esas comprobaciones. No habilitar producción.
