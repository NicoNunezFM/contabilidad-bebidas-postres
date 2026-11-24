# Consolidación técnica de PREPRODUCCIÓN Windows

Fecha: 24/11/2026. Candidata para datos ficticios; no instalada, sin merge ni producción.

## Comparación de tres vías y procedencia

| Referencia | Commit auditado | Función |
| --- | --- | --- |
| PR #27 | `5d44eba6d18363789253d63df7cc58f448e849e1` | Ancestro común comprobado con `git merge-base` |
| PR #29 | `1d3ce73d506be7435ace94912e6f42d10ec2cbeb` | Base preferida, padre de esta rama |
| PR #30 | `7361e3a27f962c209a2e629b6c2e54176aa32286` | Alternativa consultada; ningún merge ni cherry-pick |

Rama: `consolidate/preproduccion-windows-v1`. Destino del borrador:
`feature/abadion-v1-preproduccion-persistente`, nunca main ni #27 directamente.
Se creó un clon independiente `abadion-consolidacion` desde #29, sin modificar los dos
checkouts originales. No se consultaron ni abrieron datos de la preproducción instalada,
Entrenamiento persistente, negocio, WhatsApp o PCBOX. La instalación reportada por el
usuario en `%LOCALAPPDATA%\Abadion\Preproduccion`, puerto 8078, no se actualizó.

Comandos de comparación reproducibles (sólo objetos Git):

```text
git merge-base 1d3ce73 7361e3a
git diff 5d44eba 1d3ce73 --stat
git diff 5d44eba 7361e3a --stat
git diff 1d3ce73 7361e3a -- src/database.py src/pos_entrenamiento_db.py src/pos_preproduccion.py scripts/abadion_preproduccion.py
git diff 1d3ce73 HEAD -- pos-web whatsapp-bot scripts/Instalar-Preproduccion.ps1 src/database.py src/pos_entrenamiento_db.py
```

La última comparación debe quedar vacía. #29 agrega/modifica 9 archivos (899 altas,
4 bajas); #30, 7 (782 altas, 3 bajas). La comparación directa entre alternativas
abarca 11 rutas, incluidas guías y pruebas distintas; no son cambios acumulables.

## Matriz de diferencias y auditoría por componente

| Archivo / función | #29 respecto de #27 | #30 respecto de #27 | Decisión y riesgo |
| --- | --- | --- | --- |
| `src/database.py`, `obtener_ruta_base/obtener_conexion` | Contexto exclusivo `RUTA_PREPRODUCCION`; abre con UUID; comprueba marcador en lectura antes de conexión general escribible, incluso renombrada | Usa `RUTA_ENTRENAMIENTO` y nombre de archivo como despacho; general comprueba marcador después de abrir | Conservar #29 íntegro. No introducir selección por nombre ni debilitar el contexto. El fallback general a negocio.db sigue existiendo fuera del launcher; esta candidata nunca inicia la API general. |
| `src/pos_entrenamiento_db.py`, `abrir_base_entrenamiento` | Rechaza marcador de preproducción | Igual intención, distinto texto | Conservar #29; no ejecutar comandos de Entrenamiento. `comprobar_archivo` rechaza alias, enlaces y hardlinks; el lock `uso.lock` es común a servidor y mantenimiento cooperantes. |
| `src/pos_preproduccion.py`, `carpeta_segura/configuracion` | Ruta absoluta directa, local, fuera de OneDrive; JSON con modo, ruta, UUID y token de control | Exige absoluta desde entrada y ofrece `carpeta_local`; JSON sin control | Conservar contrato #29. No sustituir configuración ni copiar la de #30. La ruta forma parte de la identidad; no mover instalaciones. |
| `verificar/abrir_base` | Tabla `pos_preproduccion(modo, instalacion)`; app id, versión, UUID; URI mode=rw/ro, FK y synchronous FULL | Tabla homónima con columna `identidad`; firma de apertura diferente | Incompatibilidad alta. Conservar exactamente esquema y firmas #29. No hay migraciones al servir ni autocreación de base ausente. |
| `scripts/abadion_preproduccion.py`, `preparar` | Catálogo vacío, contraseñas aleatorias, cuentas `*-preprod`, JSON privado y backup inicial | Catálogo desde JSON con stock cero, contraseñas interactivas, cuentas `*-preproduccion`, otra publicación inicial | Conservar inicializador #29; sólo opera sobre instalaciones temporales nuevas en pruebas. No reutilizar `preparar` para reparar ni cargar catálogo en bases existentes. |
| `crear_app` / middleware | Contextos exclusivos, cookies #29, banner, TrustedHost 127.0.0.1, sólo router POS; controles status/stop/backup con Bearer propio | Otro nombre de cookies; sin controles; contexto por nombre | Conservar API, cookies, tokens y banner #29. Roles y origen provienen de `pos_api`; `/comandos` no existe. No se carga `.env` en worker ni se inicia bot. |
| `iniciar/consulta/main` | 8078, worker oculto, perfil Edge propio, sanea entorno, verifica UUID/ruta del servidor, segundo inicio reutiliza, puerto ajeno rechazado | Comando `servir` 8077 con Ctrl+C | Conservar #29. Añadir sólo `validar-catalogo` y `actualizar-catalogo`, con carpeta explícita; aplicación CLI exige hash revisado. No apuntar #30 a 8078 ni al directorio instalado. |
| `respaldo` | Lock de hilos, backup API, identidad, integridad/FK, manifiesto SHA, auditoría; crea destino final antes de copiar | Staging temporal antes de publicación; no lock de hilos ni auditoría #29 | Adaptar staging a #29, conservar lock y formato JSON. Sincronizar archivos antes de publicar; manifiesto al final; limpiar ambos si falla. Un corte puede dejar DB sin manifiesto: no es copia válida. No hay transacción atómica de dos archivos ni garantía frente a fallo físico del disco. |
| `validar_respaldo/restaurar` | Hash/UUID, staging, backup previo, DELETE sesiones, reemplazo offline; recuperación explícita de destino ausente | Validador separado rechaza auxiliares del backup; revoca sesiones; sin recuperación ausente | Incorporar validador y rechazo de WAL/SHM/journal del snapshot. Mantener nombre interno, lock del caller, sesiones y recuperación de #29. No aceptar rutas externas como #30. |
| Lifespan de `crear_app` | Inicial/hora/cierre; cancela tarea que puede tener `to_thread` aún vivo | Event de cierre y espera cooperativa de tarea | Adaptar coordinación de #30: esperar backup en curso antes del final y liberar lock. Reintentar tras fallo periódico; fallo inicial impide servir. No existe backup final garantizado si se mata el proceso. |
| `actualizar_catalogo` #30 | No existe en #29 | Lock, backup, transacción, sanea stock, reutiliza `cargar_catalogo` | Adaptar al UUID/abridor #29; BEGIN IMMEDIATE antes del backup, verificar snapshot, integridad antes/después, hash del contenido leído una sola vez, auditoría. No importar la tabla ni launcher de #30. |
| `scripts/abadion_entrenamiento.py`, modelos / `clave_producto/cargar_catalogo` | Comunes en #27, sin cambios en #29 | Reutilizados sin cambios | Mantener archivo compartido intacto; envolverlo con validaciones propias. Precio en centavos estricto, límites, duplicados/referencias/promoción verificados por modelos. Alias conocidos conservan IDs; nombres ambiguos existentes se rechazan. |
| `scripts/Instalar-Preproduccion.ps1` | ACL usuario/SYSTEM, allowlist, entorno propio, no sobrescribe instalación | Sin equivalente | Conservar sin ejecutar ni modificar. No actualizar código instalado como parte de este PR. |
| `.github/workflows/abadion-pos.yml` | UTF-8 y pruebas #29 en Edge Windows | UTF-8 y pruebas alternativas | Mantener #29 y agregar pruebas de consolidación a Windows. Ubuntu ejecuta suite completa; no incorporar los tests #30 sin adaptación porque prueban otro contrato. |
| `tests/test_pos_web.py` | Espera visibilidad del aviso para evitar carrera | Sin cambio | Conservar el ajuste de test de #29. Ningún cambio de UI. |
| Guías y tests propios de cada alternativa | Guía de instalación #29, 8 pruebas | Auditoría #30 y 11 pruebas de otro contrato | Esta matriz reúne hallazgos, sin copiar comandos incompatibles; pruebas nuevas portan escenarios al contrato #29. Mantener guía original como evidencia histórica y enlazar esta ampliación. |

## Contrato del catálogo consolidado

La vista previa muestra hash SHA-256 de los bytes UTF-8/UTF-8-BOM del JSON, precios
anteriores y propuestos, IDs conservados, stock conservado, altas nuevas, omisiones,
adicionales y promociones. No respalda ni cambia filas de negocio; usa lock y transacción
de lectura validada para obtener una vista coherente. SQLite puede crear sus auxiliares
de coordinación, sin cambiar el catálogo. Revisar el catálogo completo, no sólo las altas.

La aplicación lee una sola vez el archivo, verifica el hash solicitado, obtiene el mismo
lock del worker y reserva escritura antes del backup. La identidad, integridad y FK del
origen y de la copia son obligatorias. Si validación, backup o carga fallan, no se confirma
la transacción. El log JSONL se escribe después del commit: si falla la auditoría, conservar
backup y comprobar estado antes de reintentar; el error no significa que se revirtió el
commit. SQLite y JSONL no constituyen una transacción distribuida.

La publicación del backup reutiliza únicamente `_publicar_respaldo` de `src/backups.py`
(rename sin reemplazo en Windows, enlace exclusivo en POSIX), sin invocar su selección
de base ni su retención diaria. Ante colisión se eliminan sólo los archivos publicados
por la operación fallida; se conservan snapshots y manifiestos preexistentes.

Se preservan filas, IDs y stock de productos existentes. Altas nuevas a cero aunque el
JSON proponga otra cantidad. Ausentes quedan `fuera_menu`, sin borrar productos ni ventas.
Precios nuevos sólo afectan cotizaciones futuras; la prueba compara todas las tablas no
catalogales y los informes tras una venta. El cargador conserva `sin_stock` anterior.
No cambia categorías ni `controla_stock` existentes: se rechazan para revisión separada.
No importa ventas, compras, usuarios, deudas, saldos ni sesiones desde otro entorno.

Los alias conocidos de #27 (por ejemplo `Clasica simple` a `Clásica simple`) conservan
ID. Un renombre arbitrario no es una migración: se interpreta como alta y omisión; debe
detectarse en la vista previa y corregirse antes de aplicar. El formato no acepta IDs
inyectados desde otro catálogo. Adicionales existentes requieren nombre exacto para no
duplicarlos por mayúsculas. El adicional de ejemplo provoca rechazo explícito, sin
eliminación silenciosa. No se afirma detectar otros artículos ficticios por nombre.
Las categorías nuevas admiten el texto validado por el modelo de #27; la clasificación
existente asigna Bebidas/Postres a esa caja y el resto a Comidas. Revisar nombres y
clasificación en la vista previa: esta candidata no crea una nueva taxonomía comercial.

Repetir el mismo JSON mantiene filas, IDs, stock e históricos: idempotencia funcional.
Cada aplicación genera otra copia y evento; el UPSERT compartido puede avanzar
`sqlite_sequence` de adicionales sin crear filas. No se promete identidad binaria de SQLite.
Los precios editados desde el POS pueden ser reemplazados por el JSON revisado; comparar
vista previa. Stock físico, categorías y saldos iniciales requieren una operación distinta.

## Ensayo reproducible exclusivamente ficticio

Desde esta rama, con dependencias ya instaladas. No ejecutar estos comandos sobre la
instalación existente. `$env:TEMP` debe estar fuera de OneDrive y el servidor 8078 libre.

```powershell
$env:PYTHONUTF8 = '1'
$env:PYTHON_DOTENV_DISABLED = '1'
$env:NEGOCIO_DB_PATH = Join-Path $env:TEMP 'abadion-consolidacion-guard-ficticio.db'
$env:POS_TEST_BROWSER = "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe"
python -X utf8 -m pytest -q
if ($LASTEXITCODE -ne 0) { throw 'Pruebas fallidas; no instalar' }
```

Para probar manualmente un JSON de ensayo revisado, usar carpeta NUEVA:

```powershell
$ensayoAbadion = Join-Path $env:TEMP ('abadion-consolidacion-' + [guid]::NewGuid() + '\Preproduccion')
$scriptAbadion = '.\scripts\abadion_preproduccion.py'
python $scriptAbadion --carpeta $ensayoAbadion preparar
if ($LASTEXITCODE -ne 0) { throw 'Preparación fallida' }
# Crear y revisar un JSON ficticio propio; no copiar un catálogo real sin autorización.
$jsonEnsayoAbadion = Read-Host 'Ruta absoluta del JSON ficticio revisado'
python $scriptAbadion --carpeta $ensayoAbadion validar-catalogo --catalogo $jsonEnsayoAbadion
if ($LASTEXITCODE -ne 0) { throw 'Catálogo rechazado' }
# Revisar precios, IDs, stock cero, omisiones, adicionales y promociones antes de aplicar.
$hashEnsayoAbadion = Read-Host 'SHA-256 mostrado por la vista previa revisada'
python $scriptAbadion --carpeta $ensayoAbadion actualizar-catalogo --catalogo $jsonEnsayoAbadion --sha256 $hashEnsayoAbadion
if ($LASTEXITCODE -ne 0) { throw 'Aplicación fallida; revisar base y copia previa' }
```

No ejecutar #30 sobre esta carpeta. No se incluye despliegue ni sustitución de ejecutables
instalados. Cualquier actualización futura exige autorización explícita, servidor detenido,
backup verificado y ensayo de una copia aislada antes de tocar la instalación.

## Riesgos residuales y aceptación

| Riesgo | Resultado o límite |
| --- | --- |
| Corrupción de snapshot o manifiesto | Rechazo antes de reemplazar; hash, UUID, SQLite/FK y ausencia de auxiliares obligatorios |
| Corrupción del destino | Restore normal falla al respaldarlo; conservar base y auxiliares en cuarentena con proceso detenido; sólo después recuperación `--base-ausente` de #29. Ensayado con datos falsos |
| WAL abierto / caída de proceso | Backup API incluye commits y excluye transacción abierta; reapertura recupera commits y revierte escritura incompleta. Restore rechaza auxiliares pendientes; no borrarlos |
| Escritor ajeno que ignora lock | BEGIN IMMEDIATE serializa escritura del catálogo; el reemplazo offline presupone procesos cooperantes. ACL y separación operativa siguen necesarias |
| Software viejo o acceso del mismo usuario | Marcadores no son una barrera contra acceso directo. No reconfigurar otros servidores a esta SQLite. Sin cambios de ACL en este trabajo |
| Cortes de luz / disco lleno real | Inyección de errores y caída de proceso no equivalen a fallo eléctrico ni disco realmente lleno. Reinicio físico, presión real de disco/permisos y jornada manual siguen pendientes |
| Pérdida del disco / retención | Snapshots locales sin borrado automático; respaldo externo cifrado y recuperación en otra PC pendientes |
| Instalación y producción | No instaladas ni habilitadas por este PR; preproducción instalada sin tocar; no merge de #29/#30, #28 o cambios posteriores de UI |

## CI y resultados de esta consolidación

Comprobación remota del 24/11/2026, commits exactos:

- #29: [run 45399739289](https://github.com/NicoNunezFM/contabilidad-bebidas-postres/actions/runs/45399739289), `sqlite-ficticio` y `pos-edge`: **success**.
- #30: [run 45400075202](https://github.com/NicoNunezFM/contabilidad-bebidas-postres/actions/runs/45400075202), ambos jobs: **success**. Al primer chequeo aún estaba en progreso; se verificaron luego ambos jobs terminados.

Validación local en Windows / Python 3.12.9 / Edge:

- Primera ejecución de preproducción: **30 aprobadas**, incluida la suite original de
  #29, API, reinicio real del proceso servidor, restore bloqueado activo y Edge vacío.
- Versión final de catálogo y publicación de backups: **31 aprobadas**, incluidos
  Edge con catálogo cargado, conservación de tablas históricas tras venta, stock, IDs,
  omisiones, alias, idempotencia funcional, SHA revisado, rechazo de datos inválidos,
  backup fallido, rollback de carga, WAL confirmado/no confirmado, caída abrupta,
  corrupción con hash recalculado, cuarentena/recuperación, auxiliares, lock entre
  procesos, colisiones DB/JSON y cierre esperando snapshot en curso.
- Regresión completa con Edge: en ejecución al publicar inicialmente el borrador;
  se actualizará esta evidencia al terminar. CI propia del nuevo PR también pendiente.
- `git diff --check` y compilación de los archivos Python modificados: correctos.

Los XML de pruebas locales quedan fuera del repositorio en
`../abadion-consolidacion-resultados.xml` y
`../abadion-consolidacion-catalogo-resultados.xml`. Las ejecuciones se solapan; no sumar
sus casos como si todos fueran únicos. Los avisos observados en la ejecución final de
31 casos son dos deprecaciones del `on_event` existente en la API general importada
por el arnés Edge; no son fallos de prueba.

Incidentes corregidos durante desarrollo: Windows rechazó fsync con descriptor sólo
lectura (se usa r+b); el entorno restringido bloqueó la creación del socket local de
TestClient (se ejecutó luego con acceso local permitido). Una expectativa inicial de
identidad binaria falló por el avance legítimo de sqlite_sequence del UPSERT; se verifica
idempotencia funcional preservando todas las filas de negocio. Ninguna ejecución
interrumpida o fallida se presenta como aprobada.
