# Abadion — propuesta de consolidación V1

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
