# Auditoría SQLite y preproducción persistente en Windows

Referencia inspeccionada: PR #27, `integration/abadion-premium-edge`, commit
`5d44eba6d18363789253d63df7cc58f448e849e1`. Fecha: 24 de noviembre de 2026.
Alcance: almacenamiento y operación local. Los tres ajustes visuales quedan fuera.
No se inspecciona el contenido de bases instaladas ni se cambia el bot o el acceso directo.

## Diagnóstico del código de referencia

| Componente | Creación y uso actual | Consecuencia |
| --- | --- | --- |
| `src/database.py:obtener_ruta_base` | ContextVar del POS local; luego `NEGOCIO_DB_PATH`; finalmente `negocio.db` junto al código | El servidor general puede crear o migrar una base equivocada al omitir configuración. La ruta de entorno puede ser relativa. |
| `inicializar_base_de_datos` | Crea y altera tablas en múltiples conexiones y commits, incluso backfill de categorías históricas | No es una migración global atómica; ejecutarlo sobre una base existente requiere respaldo y ensayo en copia. |
| `scripts/servir_pos_windows_ficticio.py` | `TemporaryDirectory`, `preparar_base`, servidor loopback 8076 | Los movimientos pertenecen a una práctica descartable. Un cierre normal elimina su directorio. No inicia Node ni WhatsApp. |
| `scripts/abadion_entrenamiento.py` | Archivo nuevo privado, esquema general más simulación, clientes, caja y contabilidad; usuarios públicos de práctica y catálogo con stock ficticio | No sirve como inicializador definitivo sin separar identidad, credenciales y stock inicial. |
| `src/pos_entrenamiento_db.py` | `%LOCALAPPDATA%\Abadion\Entrenamiento`, identidad, app id y versión; lock de proceso; rechaza alias y OneDrive | Entrenamiento sí persiste. Su comando `reiniciar` reemplaza la base y elimina prácticas deliberadamente. No reutilizarlo para preproducción. |
| `cargar_catalogo` | Conserva IDs y stock existente, inserta stock inicial sólo en productos nuevos, modifica precios/categorías y desactiva ausentes | Recargar un JSON puede sobreescribir precios editados en el POS. Hacer diff y respaldo previo; nunca importar movimientos ni cantidades ficticias. |
| `src/backups.py` | SQLite backup API, integrity_check, publicación sin reemplazo, últimos 14 archivos diarios | Se invoca al arrancar API general, después de inicializar. No es un reloj diario: un servidor que sigue encendido no vuelve a respaldar. Un archivo diario existente se acepta sin revalidar; no verifica FK ni ensaya restauración. |
| Activaciones de Entrenamiento | Copias SQLite previas a clientes, fondos y contabilidad | `respaldar_sqlite` no comprueba integridad. No existe una herramienta integral de restauración operativa en estos lanzadores. |
| `whatsapp-bot/index.js` | Node carga su `.env`; `API_URL` predeterminada `http://127.0.0.1:8000/comandos`, token Bearer, `LocalAuth` | No abre SQLite directamente. Escribe por la API general. Iniciar el POS no inicia el bot; no copiar su sesión, token ni `.env`. |
| `src/api.py` | Arranque general inicializa costos, catálogo y respaldo; modos ficticios salen antes | No usar `api:app` para el nuevo entorno local. Sólo montar router POS; `/comandos` no debe existir. |

También se leyó, sin ejecutarlo, el archivo local `Iniciar Abadion/abadion_launcher.py`
existente en la PC (no pertenece al commit auditado). Su `CHECKOUT` apunta a una carpeta
temporal de Windows y ejecuta `servir_pos_windows_ficticio.py` en 8076. Reutiliza una
sesión activa, pero al detenerla informa que elimina la base ficticia. Si Windows limpia
el checkout temporal puede dejar de arrancar. Esta instalación y su acceso directo se
conservan intactos. Para la futura preproducción conviene código en
`%LOCALAPPDATA%\Abadion\App\preproduccion\<commit>` y datos en la carpeta separada
indicada abajo; no reutilizar el acceso directo actual para el nuevo modo.

## Riesgos y controles

| Prioridad | Riesgo | Control de diseño |
| --- | --- | --- |
| Alta | Confundir entrenamiento, negocio y preproducción | Ruta dedicada, nombre fijo, marcador con UUID de instalación, apertura `mode=rw` sin autocreación; rechazo desde conexión general incluso si se renombra el archivo. |
| Alta | Arrancar con usuarios públicos o stock de práctica | Construcción nueva desde esquema, contraseñas privadas solicitadas con entrada oculta, catálogo explícito saneado a stock cero y sin ventas, compras, clientes, deudas, sesiones ni cajas abiertas. |
| Alta | Restaurar con escritores activos o WAL pendiente | Lock de mantenimiento compartido con servidor, no reemplazar si hay auxiliares; respaldo previo; restaurar en archivo temporal nuevo, comprobar y publicar sólo al final. |
| Alta | Fuga por WhatsApp o red | Servidor exclusivo loopback 8077, hosts permitidos, cookies propias, sin rutas de comandos ni proceso bot. Las defensas no sustituyen ACL: un proceso con permisos directos puede escribir SQLite. |
| Media | Copias en el mismo disco no cubren robo o fallo del disco | Copias verificadas locales más exportación cifrada fuera del equipo bajo responsable; ensayo periódico en otra carpeta. SHA256 detecta corrupción accidental, no autentica ante un atacante con acceso al respaldo y manifiesto. |
| Media | Catálogo cambia el pasado o reintroduce stock | Actualización offline transaccional, respaldo previo, IDs y cantidades conservados; revisión humana de categorías y precios; altas nuevas a cero. Categorías históricas fijadas por tablas/triggers existentes. |
| Media | Cortes eléctricos y segundo servidor | synchronous FULL, transacciones existentes, lock de proceso; verificar reinicio abrupto y restauración. No prometer tolerancia a fallos de hardware. |
| Media | Dependencia del directorio de trabajo o `.env` heredado | Ruta absoluta fuera de OneDrive/UNC, fijar contexto por solicitud, no arrancar API general. Código separado de datos. |

## Diseño de instalación

| Ambiente | Datos | Ejecución |
| --- | --- | --- |
| Entrenamiento existente | Sin cambios en `%LOCALAPPDATA%\Abadion\Entrenamiento` | Lanzador y acceso directo actuales, sin cambios |
| Preproducción propuesta | `%LOCALAPPDATA%\Abadion\Preproduccion\abadion-preproduccion.db` | Lanzador nuevo y manual, loopback 8077, sólo datos de ensayo |
| Producción futura | `%LOCALAPPDATA%\Abadion\Produccion` o ProgramData con cuenta de servicio y ACL explícitas | No crear ni habilitar en este trabajo |

La carpeta de preproducción contiene `instalacion.json` con UUID, el catálogo revisado,
`backups/` con SQLite y manifiesto SHA256 y `uso.lock`. Código versionado en checkout
independiente; datos fuera del repositorio y fuera de OneDrive. Una cuenta de Windows
dedicada y ACL limitadas al operador y administradores son requisitos antes de datos
sensibles; no se cambian permisos de la PC durante esta auditoría.

El inicializador sólo admite una carpeta nueva, construye y valida en carpeta temporal
hermana y publica la carpeta completa sin reemplazar otra instalación. La reutilización
del esquema de simulación y del ContextVar local mantiene las reglas contables del PR
27; el marcador de preproducción es distinto del de Entrenamiento. No hay comando de
reinicio destructivo ni cambio automático de versión. Una versión incompatible detiene
el arranque. No se llama a inicializadores sobre instalaciones existentes al servir.

El catálogo se proporciona explícitamente: revisar precios, productos, promociones y
`controla_stock` antes de aplicarlo. La herramienta fuerza a cero todas las cantidades
iniciales y elimina el adicional conocido `Extra de práctica (ejemplo)`. No identifica
otros artículos ficticios por su nombre: la revisión del catálogo sigue siendo necesaria.
`catalogo.json` conserva la selección inicial; posteriores actualizaciones reciben un
archivo explícito y no se aplican automáticamente al reiniciar.

Las copias automáticas se hacen al arrancar, cada hora mientras el servidor está activo
y al cerrar normalmente; un error periódico debe quedar visible en el registro y un
error inicial impide servir. No se promete una copia final ante caída abrupta. Se conservan
las copias sin borrado automático en esta primera versión; revisar espacio semanalmente.
RPO objetivo: una hora con servidor activo y respaldo sano. RTO objetivo a validar: 30 minutos.
Responsable propuesto: administrador de Abadion; confirmar responsable y exportación externa
antes de habilitar datos sensibles.

La restauración requiere la pareja `.db` y `.json`, hash, UUID, integridad y FK válidas;
revoca sesiones, conserva copia anterior y sólo se ejecuta offline bajo lock. Restaurar
una copia implica perder operaciones posteriores a ella en la base activa: retener el
respaldo previo para conciliarlas, sin reinsertarlas automáticamente.

## Plan de pruebas y aceptación

1. Preparación en directorios temporales: rechazar carpeta existente, alias, OneDrive,
   base ajena, credenciales débiles e identidad/versiones incorrectas. Confirmar stock
   cero, contraseñas públicas inutilizables e historial vacío.
2. API local: abrir ambas cajas, vender con idempotencia, comprar, cobrar fiado,
   controlar stock, cerrar y comprobar totales por sección con los tests contables
   existentes. Reiniciar proceso y verificar que datos y UUID sobreviven.
3. Respaldo durante escritura SQLite, integridad, FK y SHA; corrupción del respaldo o
   manifiesto debe impedir restaurar. Restaurar y comparar tablas, cajas y existencias.
4. Mantenimiento: rechazar segundo servidor y restauración mientras hay lock;
   catálogo conserva IDs, historial y stock; productos nuevos empiezan en cero.
5. En Windows destino, pendiente de aceptación manual: reiniciar Windows, simular
   cierre forzado en operación, ensayar disco lleno/permisos denegados y falla de copia,
   comprobar recuperación y registrar tiempos reales. Hacer jornada completa ficticia.
6. Confirmar bot actual y Entrenamiento sin cambios y tres ajustes UI en rama propia.
   No fusionar ni habilitar producción con este PR.

## Límites de seguridad

La identidad evita errores operativos de las herramientas cooperantes; no es cifrado ni
aislamiento de procesos bajo la misma cuenta. SQLite y respaldos incluyen datos personales
si se los carga. Usar BitLocker y copias cifradas antes de datos sensibles. El acceso local
HTTP reutiliza autenticación, roles y validación de origen existentes; no habilitar LAN,
túneles o acceso remoto. La integración futura del bot requiere token y sesión separados,
pruebas de idempotencia/concurrencia y decisión posterior. No se modifica el bot actual.

El rechazo por marcador de la conexión general se incorpora en esta rama. Una versión
antigua del servidor general no conoce ese control: no configurar su `NEGOCIO_DB_PATH`
con la ruta nueva. La separación de puerto y ausencia de `/comandos` evita que el bot
escriba por la aplicación nueva. El aislamiento frente a software antiguo con acceso
directo al archivo requiere cuenta/ACL de Windows, pendiente de preparar en el destino.

## Comandos para una instalación de ensayo posterior

Ejecutar desde el checkout de esta rama, con sus dependencias instaladas. Estos comandos
son instrucciones de operación; no se ejecutaron contra la instalación de la PC durante
la auditoría. No apuntar a la carpeta de Entrenamiento ni copiar `negocio.db`.

```powershell
$env:PYTHON_DOTENV_DISABLED = '1'
$env:PYTHONUTF8 = '1'
$datosEnsayo = Join-Path $env:LOCALAPPDATA 'Abadion\Preproduccion'
$catalogoRevisado = Join-Path $env:TEMP 'abadion-catalogo-revisado.json'
Copy-Item -LiteralPath .\scripts\catalogo-entrenamiento.json -Destination $catalogoRevisado
notepad.exe $catalogoRevisado
# Revisar y guardar el JSON. El código no reutiliza sus cantidades iniciales.
python .\scripts\abadion_preproduccion.py --carpeta $datosEnsayo preparar --catalogo $catalogoRevisado
# Solicita dos contraseñas con entrada oculta. Usuarios nuevos:
# admin-preproduccion y ventas-preproduccion.
python .\scripts\abadion_preproduccion.py --carpeta $datosEnsayo servir
# Abrir manualmente http://127.0.0.1:8077/pos/
```

Con el servidor detenido mediante Ctrl+C:

```powershell
python .\scripts\abadion_preproduccion.py --carpeta $datosEnsayo respaldar
# Conservar la pareja .db y .json que devuelve el comando.
python .\scripts\abadion_preproduccion.py --carpeta $datosEnsayo actualizar-catalogo --catalogo $catalogoRevisado
$copiaElegida = Read-Host 'Ruta absoluta del respaldo .db que se quiere recuperar'
python .\scripts\abadion_preproduccion.py --carpeta $datosEnsayo restaurar --respaldo $copiaElegida --confirmar 'RESTAURAR PREPRODUCCION'
python .\scripts\abadion_preproduccion.py --carpeta $datosEnsayo servir
```

Antes de actualizar catálogo, comparar con los precios actuales del POS: el JSON vuelve
a establecer esos precios y categorías. La copia previa permite recuperar el estado
completo, no combinar automáticamente catálogos ni movimientos posteriores.

La exportación externa debe copiar ambas partes de un respaldo terminado a un soporte
cifrado. Conservar al menos 14 días y una copia mensual, verificar SHA256 después del
traslado y ensayar recuperación. No sincronizar el SQLite activo con OneDrive. La
automatización de exportación externa, ACL y recuperación de contraseña de administrador
son tareas operativas pendientes; no se configura ninguna tarea programada ni acceso directo.

## Validación de la candidata

Windows, Python 3.12.9: **336 casos únicos aprobados y 19 omitidos**, verificados por
tramos. El tramo inicial aprobó 247 con 2 omitidos; desde compatibilidad de tablet hasta
el final se aprobaron 91 con 17 omitidos, con 2 casos comunes entre tramos. La verificación
de JavaScript mediante Node requiere `PYTHONUTF8=1` en esta PC. Los casos omitidos
requieren herramientas/condiciones de navegador o laboratorio no disponibles para esas
pruebas locales; no constituyen una aceptación visual de la candidata.

Las **11 pruebas nuevas** cubren historial vacío, usuarios privados, stock cero,
rechazo de rutas y bases ajenas, idempotencia de venta/compra, compra cruzada entre cajas,
venta con stock, fiado y cobro, conciliación y cierres, reapertura de aplicación, hash e
integridad, restauración y revocación de sesiones, bloqueo de mantenimiento, actualización
de catálogo, copia con WAL confirmado y recuperación de un fallo periódico del respaldo.
Un archivo testigo que simula `negocio.db` conservó exactamente sus bytes.

Para reproducir la suite desde este checkout sin acceder a bases instaladas:

```powershell
$env:PYTHON_DOTENV_DISABLED = '1'
$env:PYTHONUTF8 = '1'
$env:NEGOCIO_DB_PATH = Join-Path $env:TEMP 'abadion-auditoria-suite-ficticia.db'
python -m pytest -q
```

No se creó la instalación propuesta en LocalAppData, no se reinició Windows, no se
configuró una cuenta/ACL ni exportación externa y no se hizo la jornada manual del punto
5. La integración con GitHub debe conservar el PR como borrador y esperar el resultado
de CI y estas aceptaciones antes de cualquier decisión sobre instalación o producción.
