# Evidencia de validación de seguridad

Base #41: 647 casos de referencia. Código bajo validación:
`b04100ec1311cf0f39d1b29857f7122d72b505dc`. Total actual: 692 casos, incluidos
45 nuevos. No se eliminaron ni renombraron casos de referencia.

## Suites completas y controles

| Entorno / control | Aprobados | Fallidos | Omitidos | Estado |
| --- | --- | --- | --- | --- |
| Linux, suite completa | 654 | 0 | 38 | Conforme; omisiones de Windows/Edge identificadas en JUnit |
| Windows/Edge local, suite completa | 692 | 0 | 0 | Conforme; todos los 647 casos originales y los 45 nuevos |
| Windows/Edge, suite completa CI | Sin resultado | Sin resultado | Sin resultado | Inconclusa al corte; no se cuenta como aprobada |
| Dependencias Python en CI | Sin avisos conocidos | 0 | 0 | Conforme |
| Dependencias Node, inspección del lock | 162 paquetes inspeccionados | 6 paquetes con 9 avisos | 0 | Control fallido visible; bot sin cambios |
| Inventario de rutas / procedencia | 83 rutas / referencia de consolidación | 0 | 0 | Conforme |

Ejecución de CI: [run 46067197677](https://github.com/NicoNunezFM/contabilidad-bebidas-postres/actions/runs/46067197677).
El control Node ha fallado: no hay exenciones ni pruebas deshabilitadas para obtener
un resultado favorable. Por tanto, esta entrega no tiene una CI completamente
aprobada. Ese control no impide ejecutar las suites funcionales independientes.

La ejecución remota Windows seguía activa después de más de 30 minutos; el conector
no proporcionó sus logs en curso y la consulta web tampoco permitió recuperarlos.
Se mantiene **pendiente la validación Windows de CI**. Esto no se sustituye por una
afirmación de éxito remoto: la suite local completa aprobada es una evidencia
distinta. La publicación final de documentación puede iniciar otra ejecución del
workflow; el código, pruebas, dependencias y configuración ejecutables permanecen
idénticos al SHA validado indicado arriba. Consultar el estado actual en el PR.

Artefactos descargables desde el run: `abadion-resultados-linux` y
`abadion-resultados-windows-edge` contienen JUnit y comparación por identidad de casos;
`abadion-conciliacion-jornada-*` conserva evidencia financiera ficticia;
`abadion-preproduccion-edge` contiene capturas de interfaz; `abadion-seguridad-*`
contiene auditorías de dependencias. Los artefactos de CI tienen vencimiento; los
resúmenes permanentes y hashes se conservan en este directorio.

La comparación automática exige todos los 647 IDs, sin duplicados ni fallos. En
Windows/Edge también rechaza cualquier omisión. Linux conserva 609 casos de base
aprobados y 38 omitidos por plataforma, más los 45 nuevos aprobados. No se interpreta
una omisión Linux como un caso probado en Windows.

La [comparación Windows local](referencia-windows-local.json) y su
[JUnit](junit-windows-local.xml) conservan evidencia permanente. En la copia publicada
del XML solo se reemplazó el hostname por una etiqueta de entorno ficticio; no se
alteraron casos, tiempos, estados ni conteos. El nombre del equipo no forma parte
de la validación de aplicación.

Entorno local observado: Python 3.12.9, Windows compilación 10.0.26300, SQLite
3.45.3, ejecutable Edge 158.0.4370.45, FastAPI 0.135.1, Starlette 1.10.0,
cryptography 50.0.0 y python-dotenv 1.2.2. Se utilizó un entorno Python separado
y perfiles de navegador temporales. Las advertencias de deprecación de on_event
y de TestClient/httpx se conservan como deuda técnica; no se ocultaron ni se
convirtieron en omisiones.

La [comparación de jornada ficticia con #41](comparacion-jornada.json) conserva los
importes de caja, banco, devengado, cobrado, compras, gastos, resultado, diezmo,
costos y margen; la conciliación sigue cuadrada. Una diferencia de arqueo ficticia
de −10 centavos continúa explícita: cuadrar los libros no certifica efectivo físico.

## Ejecuciones intermedias

- Focal de regresión: 100 aprobados, 3 omitidos previstos.
- Primera suite nueva: 36 aprobados; ampliación: 40 aprobados.
- Focal con dependencias corregidas, seguridad, apertura y recuperación: 65 aprobados.
- Dependencias Python corregidas: pip-audit 2.10.1, sin avisos conocidos encontrados.
- Node: 162 paquetes inspeccionados; seis con avisos. Sin cambios de instalación.
- Primera ejecución completa detectó que el registro HTTP adicional alteraba un
  snapshot al reintentar una venta. Se corrigió el código para conservar idempotencia;
  no se relajó esa prueba de recuperación.
- Primera suite completa Windows intermedia: 637 aprobados y 10 fallidos de 647;
  [lista de fallos](resultado-intermedio.json). Causas: evento adicional en reintentos,
  referencias de sesión al restaurar, dos contratos de catálogo sin sesión y una
  expectativa de propagación del driver. Se corrigieron código/compatibilidad y los
  tres contratos de prueba indicados abajo. No se oculta esta ejecución intermedia.
- Prueba adicional de arranque sin rutas/detalles de backup: 2 aprobados. `pip check`
  en el entorno temporal corregido no encontró incompatibilidades declaradas.
- Suite local completa Windows/Edge intermedia con 42 casos nuevos: 689 aprobados,
  cero fallos y cero omisiones; comparación automática de los 647 IDs conforme.
  Las dos pruebas posteriores de arranque se ejecutaron separadamente. La suite
  definitiva de 692 casos se identifica por SHA y run de CI en la tabla superior.
- Regresión encontrada durante la implementación: logout anónimo agregaba filas de
  auditoría. La prueba falló antes de corregirlo y pasó después. Ahora verifica 25
  solicitudes sin cambios de bytes/filas y con 20 registros como máximo; también una
  cookie inventada sobre un esquema previo, sin migración. Focal posterior: 47 aprobados.
- Las ejecuciones CI intermedias de Windows sustituidas por commits nuevos se
  cancelaron automáticamente y no se cuentan como suites aprobadas ni como fallos de
  pruebas. Sus resultados parciales no reemplazan la suite definitiva.

## Cambios justificados de tres pruebas existentes

`test_pos_simulacion.test_revalida_total_y_revierte_si_falla_el_stock` conserva el
trigger de fallo, el rechazo de total inválido y todas las comprobaciones de stock,
ventas y movimientos revertidos. La frontera HTTP ahora convierte la excepción
SQLite en HTTP 500 genérico: la prueba exige exactamente esa respuesta en lugar de
que TestClient propague el detalle del driver. No se reduce la cobertura contable
ni se elimina el caso. Las pruebas internas de rollback siguen exigiendo excepciones.

`test_consultar_adicionales_pos` y `test_consultar_personalizaciones_pos` ahora
comprueban primero el rechazo sin sesión y después ejecutan todas sus comprobaciones
originales bajo sesión ficticia de Ventas. Incluyen los mismos precios, ingredientes,
activos y exclusión de costos internos. Esto valida el catálogo privado corregido;
no se vuelve a abrirlo para obtener resultados favorables. Se conservan los IDs de
los 647 casos de referencia.

## Reproducción aislada

```powershell
$env:PYTHON_DOTENV_DISABLED='1'
$env:PYTHONUTF8='1'
$env:POS_TEST_BROWSER='C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
python -m pytest -q -ra --junitxml=resultados-windows-edge.xml
python -B scripts/auditar_endpoints.py
python -m pip_audit -r requirements-tablet-test.txt --format json --output dependencias-python.json
python scripts/auditar_dependencias_node.py --salida dependencias-node.json
```

Pytest asigna a cada caso su propia base temporal ficticia. No usar estas instrucciones
contra una instalación ni con credenciales reales. En Linux, los casos que requieren
Windows/Edge se omiten explícitamente y se validan en el job correspondiente.

Los casos nuevos cubren revocación al cambiar credenciales/rol/estado/nombre,
rehabilitación sin revivir tokens, cambio entre password y emisión, tokens y fechas
manipulados, sesiones previas, cookies/duraciones, límite temporal/concurrencia/memoria,
CSRF/orígenes duplicados, todos los endpoints privados y administrativos, datos de
errores, SQL parametrizado, auditoría mínima/inmutable, revocación antes de una
escritura, rollback financiero, concurrencia/idempotencia e independencia del logger.

Limitaciones: sin escaneo de red/infraestructura real, sin credenciales reales, sin
pentest exhaustivo, sin ensayo de abuso distribuido ni verificación del bot activo.
Los avisos Node mantienen un control CI fallido deliberadamente visible y producción
bloqueada. También quedan pendientes el cierre verificable de Windows en CI y la
validación del perímetro/host real. No confundir suite funcional aprobada con
aprobación productiva.
