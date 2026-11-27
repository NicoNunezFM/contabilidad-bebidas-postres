# Migraciones explícitas de bases ficticias — Fase 2.5

Estado: propuesta para revisión; **producción bloqueada**. Base de código: PR #42,
`1ec1ab98755a248f86c3a50ba3164320e4381448`. La matriz previa está en
[inspeccion.md](inspeccion.md). Este procedimiento no autoriza intervenir bases reales.

## Contrato y alcance

`src/migraciones.py` conoce un único paso, `0005-garantias-39-42`, de 4 a 5.
Acepta solamente instalaciones persistentes ficticias Pruebas/Preproduccion con ABP1,
UUID canónico coincidente con instalación, rutas directas y catálogo SQL reconocido.
No decide el linaje por nombre de archivo ni inventa una correspondencia entre el
número antiguo 4 y un PR: #38–#42 compartían ese número.

`src/migraciones_contrato.json` enumera objetos y grupos opcionales completos.
`scripts/generar_contrato_migraciones.py` permite reproducirlo con una instalación
ficticia temporal; no debe regenerarse durante una actualización de instalación.
Un objeto desconocido, trigger cambiado o grupo incompleto exige revisión manual.
La comparación conserva literales SQL; no sustituye una auditoría semántica manual.

| Objeto nuevo gestionado | Contenido / garantía |
| --- | --- |
| `abadion_esquema` | Una fila: UUID, modo, versión 5 y mínimo de código 5 |
| `abadion_migraciones` | Paso único, UUID/FK, versiones, checksum del contrato/paso, fecha UTC y hashes del esquema anterior/posterior y datos anteriores |
| Cuatro triggers | Prohíben UPDATE/DELETE de esos dos registros desde SQL ordinario |
| `PRAGMA user_version=5` | Se confirma con DDL y registro; los launchers antiguos que exigen 4 lo rechazan |
| `instalacion.json.esquema_minimo=5` | Piso externo conservador para impedir restauraciones/arranques accidentales con una base anterior |

El paso reutiliza exclusivamente los creadores DDL de compras atómicas (#39), costos
históricos (#40) y seguridad (#42). Crea tablas ausentes vacías: no completa costos de
ventas anteriores, no inventa sesiones, no reconstruye eventos ni mueve caja/stock.
No habilita módulos comerciales opcionales. Las creaciones diferidas conocidas se
mantienen; esta entrega no convierte todos los inicializadores legados en migraciones.
El inicializador global rechaza bases gestionadas/futuras antes de ejecutar sus ALTERs.

Para una versión 6 será necesario otro paso revisado, congelar la definición histórica
del paso 5 y ampliar explícitamente contratos, lectores y pruebas. Cambiar el catálogo
publicado sin ese proceso invalida el checksum y bloquea la apertura. No hay downgrade.

## Transacción explicada

Una transacción SQLite hace que varios cambios se vean como una sola confirmación.
Si falla un INSERT, un trigger, la validación final o el COMMIT, no se publica la mitad
del esquema. No se usa `executescript`, que puede confirmar implícitamente.

Secuencia de `migrar`:

1. Adquirir el bloqueo de instalación ya existente. El servidor debe estar detenido;
   no se fuerza el cierre de ningún proceso.
2. Abrir la base existente con `mode=rw`, activar FK y `synchronous=FULL`, y reservar
   el escritor con `BEGIN IMMEDIATE`. Otro escritor falla/espera según su timeout;
   ningún escritor puede intercalar operaciones dentro del corte.
3. Validar identidad, versión, catálogo, `integrity_check` y `foreign_key_check`.
4. Respaldar mediante SQLite Backup API desde **otra conexión de lectura**. La conexión
   reservada todavía no escribió: ambas ven el mismo corte. Comparar esquema y todas
   las filas, publicar sin sobrescribir y verificar hash, identidad, integridad y FK
   mediante las herramientas existentes. Una copia inválida impide iniciar el DDL.
5. Publicar de forma atómica el piso externo 5 y ejecutar el DDL aditivo en la conexión
   reservada. Comparar todas las filas anteriores y exigir tablas nuevas vacías.
6. Insertar el registro de migración, cambiar `user_version`, verificar otra vez y
   confirmar. Repetir el comando sobre una base 5 válida no crea otro paso ni backup.

La huella compara tipo y valor de cada columna, rowid cuando corresponde, número y
multiplicidad de filas; incluye `sqlite_sequence`. Distingue NULL, entero, real, texto
y BLOB. Se conserva su hash, no datos personales. Las pruebas operativas contrastan
además saldos, ventas, fiados, stock y snapshots de costos con movimientos ficticios.
Los hashes del registro certifican el corte de migración; no se comparan con los datos
actuales después de cada venta, porque estos cambian legítimamente.

El archivo de configuración y SQLite no comparten transacción. Por eso el piso se
publica **antes**: una caída puede dejar piso 5 y base 4, nunca una falsa confirmación
de esquema 5. El nuevo launcher bloquea ese estado; el migrador puede reintentarlo.
Un `.pendiente` dejado por interrupción de publicación se rechaza conservadoramente;
no se elimina automáticamente. La recuperación aislada permite conservar la fuente.
Una copia sin manifiesto por interrupción de publicación no se considera respaldo válido.

## Procedimiento de ensayo

Usar un entorno de dependencias de `requirements-tablet-test.txt`, sin `.env`, y rutas
nuevas fuera de instalaciones y carpetas sincronizadas. Ejemplo PowerShell, siempre
con datos ficticios (cada destino debe ser inexistente al prepararlo):

```powershell
$env:PYTHON_DOTENV_DISABLED = '1'
$ensayo = Join-Path $env:TEMP ('abadion-migracion-' + [guid]::NewGuid())
$origen = Join-Path $ensayo 'Pruebas'
python scripts/abadion_migraciones.py preparar --carpeta $origen
python scripts/abadion_migraciones.py diagnosticar --carpeta $origen
python scripts/abadion_migraciones.py migrar --carpeta $origen
$recuperada = Join-Path ($ensayo + '-recuperada') 'Pruebas'
python scripts/abadion_migraciones.py recuperar-actual --carpeta $origen --destino $recuperada
```

`preparar` reutiliza el preparador existente y migra la nueva instalación. Para una
Preproduccion ficticia usar ese nombre de carpeta y `--preproduccion` al preparar.
`diagnosticar` inspecciona en lectura; no migra ni importa. Los comandos no arrancan
servidores, no activan releases y siempre informan `produccion_habilitada: false`.

Para actualizar una instalación ficticia 4 compatible: detener su proceso, comprobar
el backup y la procedencia del código, disponer offline del código que entiende 5,
ejecutar diagnóstico y migración explícitos, verificar y recién después ensayar su
launcher compatible. Los mecanismos existentes de releases por hash se conservan;
no se hace activación automática ni se introduce migración al arrancar el servidor.
No cambiar `user_version` manualmente para que acepte código antiguo.

## Fallos y recuperación

| Situación | Acción conservadora |
| --- | --- |
| DDL/validación/COMMIT falla | Rollback SQLite completo. Mantener copia previa; reintentar explícitamente tras resolver el fallo |
| Proceso interrumpido antes del COMMIT | Dejar a SQLite recuperar su journal; no borrar `-journal`, `-wal` ni `-shm`; reintentar con código compatible |
| Proceso interrumpido después del COMMIT | El paso ya figura en 5; repetir verifica y no duplica |
| Configuración pendiente, fuente íntegra | `recuperar-actual` a carpeta nueva; diagnosticar y completar migración allí si sigue en 4 |
| Base gestionada con operaciones posteriores | Recuperar desde snapshot **actual**, bajo reserva de escritor; jamás reemplazar por pre-backup |
| Backup anterior a `esquema_minimo` | Rechazar restauración; tampoco se restaura encima de una base gestionada existente |
| Fuente corrupta, ausente o versión desconocida | Recuperación actual rechazada; intervención y selección documentada de respaldo verificado, sin prometer preservar operaciones posteriores a él |

`recuperar-actual` reutiliza la recuperación aislada existente: nuevo directorio,
misma identidad de base, nuevo token de control y ACL Windows existentes. Conserva
usuarios/credenciales y registros financieros; invalida sesiones restauradas, como
ya hacía la herramienta anterior. No elimina ni activa el origen. Nunca ejecutar
origen y copia simultáneamente: representan la misma instalación, no dos empresas.
La excepción controlada que permite copiar una fuente 4 con piso pendiente 5 sirve
solamente para crear ese destino nuevo y retomar la migración; no autoriza downgrade.

El snapshot actual conserva todas las operaciones confirmadas **hasta el corte**.
No se promete pérdida cero frente a corrupción física irrecuperable, pérdida del
disco o escrituras realizadas después del último respaldo disponible. Nunca se
resuelve eso sobreescribiendo una instalación existente automáticamente.

## Bloqueos y riesgos residuales

- Los libros WhatsApp sin correspondencia inequívoca permanecen excluidos. El paso
  estructural no importa, vincula, deduplica ni concilia esos registros. Conservar
  filas opacas existentes no significa aprobar su integración contable.
- Para integrar legados se necesitan IDs originales de compra/venta/cobro/deuda,
  secciones, unidades, medios de pago, cortes de apertura y correspondencias
  comprobables; las diferencias requieren decisión comercial autorizada. No se
  inferirán por semejanza, sumas de saldos ni precios/recetas actuales.
- Un catálogo cerrado rechaza variantes inocuas además de variantes peligrosas.
  Es un bloqueo revisable, no motivo para relajar validaciones en una instalación.
- Los marcadores y hashes no prueban que un propietario del equipo no haya cargado
  datos reales ni protegen contra un administrador que cambie simultáneamente código,
  manifiestos y SQLite. El respaldo no lleva firma criptográfica independiente.
- La transacción bloquea escritores mientras calcula hashes y respaldo: medir con
  tamaños representativos antes de considerar otro entorno. La validación completa
  privilegia conservación, no una actualización en caliente.
- Se conservan controles de seguridad de #42. El bot y sus dependencias quedan
  intactos: su control de nueve avisos en seis paquetes continúa siendo bloqueante.
- Pasar estas pruebas no autoriza producción, importación de legados ni restauraciones
  sobre instalaciones existentes. No demuestra resistencia a todo fallo de hardware.

## Validación reproducible

```powershell
python -m pytest -q -ra --junitxml=resultados-windows-edge.xml
python scripts/verificar_referencia_pruebas.py resultados-windows-edge.xml --windows-edge --salida referencia-windows.json
python -B scripts/auditar_consolidacion.py --verificar
python -B scripts/auditar_endpoints.py
```

En Windows, definir `POS_TEST_BROWSER` con Edge para ejecutar los casos de navegador;
en Linux CI las omisiones de UI Windows están identificadas explícitamente. El
manifiesto `casos-referencia-692.json` conserva las identidades de los 692 casos de #42,
sin modificar esas pruebas. Los nuevos casos están en `tests/test_migraciones.py`.
Se generan bases de los cinco commits #38–#42 mediante sus preparadores originales,
en carpetas temporales, y se comprueba cada fila antes/después. La CI necesita el
historial Git completo para reproducir esa procedencia.

La evidencia final se publica con el PR: JUnit completo, verificación del manifiesto,
conciliación ficticia y controles de dependencias separados. Comparar contra la CI
final de #42 (run 46070961495), no contra un job todavía en ejecución. Linux local no
está disponible en este equipo (WSL no instalado); Ubuntu se valida en CI.
