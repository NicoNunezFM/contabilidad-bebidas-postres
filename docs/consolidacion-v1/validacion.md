# Validación de la propuesta de consolidación

Fecha: 27/11/2026. Todos los ensayos usan datos inventados y bases temporales.
No se ejecuta el bot ni se abre una instalación existente.

## Referencia histórica

PR #37, SHA `3c4ef418f161d232a21f059349e7249247f9dbd3`.
[CI de ese SHA](https://github.com/NicoNunezFM/contabilidad-bebidas-postres/actions/runs/45509425666):
Linux 493 aprobados / 36 omitidos; Windows candidata 48 aprobados; selección de flujos
Windows/Edge 173 aprobados. Sintaxis Node aprobada. Suites solapadas: no sumar cifras.

## Verificaciones de esta propuesta

| Verificación | Resultado al preparar el borrador |
| --- | --- |
| Inventario remoto | 41 ramas / 34 PR, sin cambios posteriores a #37 |
| Comparación contra la referencia | Sin diferencias en src, POS, bot, requisitos, catálogos, launchers o instaladores |
| Compatibilidad legada → POS | 2 aprobadas; rechazo 404 y bytes de la base sin cambios |
| Sintaxis del adaptador Node | Aprobada con node --check; sin inicializar el cliente |
| Dependencias locales | pip check aprobado; entorno Python 3.12 disponible |
| Suite completa Windows sin navegador, referencia | En ejecución; se completará con resultados y evidencia |
| Suite completa consolidada Windows/Edge | Pendiente; Edge está disponible |
| CI Linux y Windows/Edge del nuevo SHA | Pendiente de publicación y ejecución |

Los estados pendientes no constituyen aprobaciones. El historial de la PR registrará
la evidencia final y el SHA al que corresponde. Un SHA anterior no valida otro posterior.

## Ejecución reproducible

En un entorno de desarrollo aislado: PYTHON_DOTENV_DISABLED=1, PYTHONUTF8=1 y
NEGOCIO_DB_PATH apuntando a un archivo ficticio nuevo. Los fixtures fijan una base
temporal por prueba; no se proporciona una ruta real. Para Edge: POS_TEST_BROWSER
debe apuntar al ejecutable y POS_UI_CAPTURAS a una carpeta de evidencia temporal.

```text
python -m pytest -q --junitxml=referencia-windows.xml
python -m pytest -q --junitxml=consolidada-windows-edge.xml
python -B scripts/auditar_consolidacion.py --verificar
node --check whatsapp-bot/index.js
git diff --check
```

La primera ejecución se inició en el SHA de referencia antes de cambiar pruebas;
la segunda se realizará sobre el commit consolidado. CI publica JUnit por plataforma
y capturas del navegador, con nombres de job conservados. Windows ahora ejecuta toda
la suite con Edge en lugar de repetir candidata más una selección de módulos.

## Pendientes ajenos a estas pruebas

No se certifican: migración del libro de aperturas de comandos, importación de datos
reales, activación productiva, respaldo externo, reinicio físico, corte eléctrico,
dispositivos del negocio o conexión con Meta/WhatsApp. Consultar los bloqueos contables
del informe. No hay medición de porcentaje de cobertura ni prueba de carga comercial.
