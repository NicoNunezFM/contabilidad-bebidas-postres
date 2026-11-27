# Validación de la propuesta de consolidación

Fecha: 27/11/2026. Todos los ensayos usan datos inventados y bases temporales.
No se ejecuta el bot ni se abre una instalación existente.

## Referencia histórica

PR #37, SHA `3c4ef418f161d232a21f059349e7249247f9dbd3`.
[CI de ese SHA](https://github.com/NicoNunezFM/contabilidad-bebidas-postres/actions/runs/45509425666):
Linux 493 aprobados / 36 omitidos; Windows candidata 48 aprobados; selección de flujos
Windows/Edge 173 aprobados. Sintaxis Node aprobada. Suites solapadas: no sumar cifras.

## Evidencia comprobada y registro de cierre

| Verificación | Evidencia |
| --- | --- |
| Inventario remoto | 41 ramas / 34 PR, sin cambios posteriores a #37 |
| Comparación contra la referencia | 149 archivos preexistentes sin modificar/eliminar; objetos de árboles operativos idénticos; ver conservacion-codigo.json |
| Compatibilidad legada → POS | 2 aprobadas; rechazo 404 y bytes de la base sin cambios |
| Sintaxis del adaptador Node | Aprobada con node --check; sin inicializar el cliente |
| Dependencias locales | pip check aprobado; entorno Python 3.12 disponible |
| Primera CI completa Linux de la consolidación, SHA 7a84c6e | 495 aprobadas, 36 omitidas, 0 fallidas, 0 errores; JUnit inspeccionado |
| Windows local de referencia y Windows/Edge consolidado | Resultados de cierre por ejecución y SHA en la descripción del PR #38; no inferir aprobación de esta tabla |
| CI del SHA final de esta propuesta | Consultar los checks y artefactos del PR #38; una ejecución de otro SHA no lo certifica |

El registro de cierre con cantidades aprobadas, fallidas, omitidas, repeticiones y pendientes
se mantiene en la [descripción del PR #38](https://github.com/NicoNunezFM/contabilidad-bebidas-postres/pull/38)
y enlaza las ejecuciones exactas. Esto permite registrar el resultado del último SHA sin
crear otro commit sólo para decir que el anterior pasó. Antes de aceptar el PR, comprobar
que sus checks correspondan a su cabeza actual. Un estado pendiente no es una aprobación.

La [primera CI Linux](https://github.com/NicoNunezFM/contabilidad-bebidas-postres/actions/runs/46023338197)
añade exactamente 2 casos aprobados a los 493 de #37; conserva los 36 omitidos: 30 requieren
navegador y 6 son controles nativos de Windows. El resumen JUnit está en
`evidencia-linux-inicial.json`. No se suman plataformas ni repeticiones como casos únicos.

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

La ejecución local de referencia se inició con la colección original antes de agregar
los dos casos. Código operativo y pruebas preexistentes permanecieron idénticos durante
la inspección; las herramientas que exportan HEAD pueden incluir la nueva documentación
y el auditor. La comparación estricta por SHA usa también la CI histórica inmutable de #37.
La suite consolidada completa Windows/Edge se ejecuta en CI. CI publica JUnit por plataforma
y capturas del navegador, con nombres de job conservados. Windows ahora ejecuta toda
la suite con Edge en lugar de repetir candidata más una selección de módulos.

## Pendientes ajenos a estas pruebas

No se certifican: migración del libro de aperturas de comandos, importación de datos
reales, activación productiva, respaldo externo, reinicio físico, corte eléctrico,
dispositivos del negocio o conexión con Meta/WhatsApp. Consultar los bloqueos contables
del informe. No hay medición de porcentaje de cobertura ni prueba de carga comercial.
