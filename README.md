# Abadion — propuesta de consolidación V1

Esta rama añade la [corrección de compras atómicas de insumos](docs/compras-atomicas.md),
basada en el PR #38. Incluye inspección previa, decisiones contables, trazabilidad y
pruebas de fallos/concurrencia. Los informes de consolidación de abajo conservan la
evidencia histórica del PR #38; no afirman que el código del fix sea idéntico a esa base.

Software de gestión de Lo de Clau: POS, contabilidad operativa, dos cajas, pedidos,
delivery, clientes/fiados, inventario, recetas/costos, permisos y recuperación.

**Esta rama es una propuesta en borrador para datos ficticios. Producción continúa bloqueada.**
La existencia de CI aprobada no autoriza apertura, migraciones ni reemplazo del bot.

Referencia: PR #37, commit `3c4ef418f161d232a21f059349e7249247f9dbd3`.
El relevamiento remoto del 27/11/2026 no encontró cambios posteriores.

## Documentación de consolidación

- [Informe, decisiones laterales y riesgos](docs/consolidacion-v1/informe-integracion.md).
- [Todas las ramas y PR relevados](docs/consolidacion-v1/matriz-ramas-prs.md).
- [Compatibilidad de bases y conflictos](docs/consolidacion-v1/compatibilidad-bases.md).
- [Validación y comparación con la referencia](docs/consolidacion-v1/validacion.md).
- [PR #38: resultados finales por SHA y estado de los bloqueos](https://github.com/NicoNunezFM/contabilidad-bebidas-postres/pull/38).
- [Inventario GitHub fechado](docs/consolidacion-v1/inventario-github.json) y
  [comparación estructural reproducible](docs/consolidacion-v1/comparacion-ramas.json).

## Desarrollo y pruebas aisladas

Python 3.12; Node 20 para comprobar sintaxis del adaptador sin iniciarlo.
Instalar `requirements-tablet-test.txt` en un entorno de desarrollo separado.
Antes de ejecutar pruebas, establecer `PYTHON_DOTENV_DISABLED=1` y
`NEGOCIO_DB_PATH` a una ruta ficticia nueva. Para las pruebas visuales, establecer
`POS_TEST_BROWSER` al ejecutable de Edge. Ejecutar `python -m pytest -q`.
Los fixtures crean bases en directorios temporales. No usar bases de instalaciones.

`python -B scripts/auditar_consolidacion.py --verificar` comprueba el informe contra
los objetos Git del inventario; requiere historia completa (`fetch-depth: 0`).
No importa la aplicación, no abre SQLite y no consulta configuraciones privadas.

No ejecutar la API general contra una base real para evaluar esta rama: su inicio
incluye inicialización de esquema. Las herramientas de Pruebas y Preproducción tienen
identidades y rutas propias. Consultar la matriz antes de utilizar cualquiera.

La candidata V3 sólo se prepara en un destino nuevo mediante su herramienta offline;
no tiene comando de activación ni servidor. Las guías históricas documentan etapas
distintas y no son instrucciones acumulables para actualizar una instalación.

Costos históricos del POS: [inspección y contratos](docs/costos-historicos-pos-inspeccion.md)
y [modelo, cobertura, transacciones y compatibilidad](docs/costos-historicos-pos.md).
La propuesta captura costos solo en ventas nuevas, conserva los faltantes como
desconocidos y mantiene bloqueada la producción.
