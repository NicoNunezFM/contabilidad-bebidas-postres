# Evidencia de validación de seguridad

Base #41: 647 casos de referencia. La validación final está en curso; este archivo
se actualizará con SHA, jobs Linux/Windows/Edge y resultados JUnit antes de entregar.

## Ejecuciones intermedias

- Focal de regresión: 100 aprobados, 3 omitidos previstos.
- Primera suite nueva: 36 aprobados; ampliación: 40 aprobados.
- Focal con dependencias corregidas, seguridad, apertura y recuperación: 65 aprobados.
- Dependencias Python corregidas: pip-audit 2.10.1, sin avisos conocidos encontrados.
- Node: 162 paquetes inspeccionados; seis con avisos. Sin cambios de instalación.
- Primera ejecución completa detectó que el registro HTTP adicional alteraba un
  snapshot al reintentar una venta. Se corrigió el código para conservar idempotencia;
  no se relajó esa prueba de recuperación.

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
bloqueada. No confundir suite funcional aprobada con aprobación productiva.
