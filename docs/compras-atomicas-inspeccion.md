# Compras de insumos: inspección previa a la corrección

Base inspeccionada: PR #38, `6a193c1b79d456a95a832b70447010da287724b1`.
GitHub seguía apuntando a ese SHA al iniciar; no había PR posterior al #38.
Inspección exclusivamente de código y pruebas, sin abrir bases reales.

## Comportamiento anterior y alcance

`src/costos_postres.py:registrar_compra_insumo` resuelve el insumo con una conexión
de lectura y convierte unidades. Luego llama `gastos.registrar_gasto`, que abre otra
conexión, ejecuta BEGIN IMMEDIATE, inserta el gasto y hace COMMIT. Recién después
abre la conexión que inserta `compras_insumos`, suma `insumos.stock_base` y confirma.
Si esta segunda etapa falla, su ROLLBACK no puede deshacer el gasto ya confirmado.
La lectura de stock anterior y la validación de disponibilidad también ocurren en
momentos distintos. No existe una clave de solicitud propia de la compra de insumos.

`registrar_compra_insumo_paquetes` resuelve presentación en conexiones separadas y
delega en la misma función; ambas rutas comparten el defecto. Los puntos de entrada
son funciones Python, `acciones.accion_registrar_compra_insumo[_paquetes]`, el endpoint
autenticado `/acciones` y los intérpretes de `/comandos`, incluidos bloques multilínea.
Los intérpretes ya pasan contexto, pero las acciones de insumos no lo reenvían.
El adaptador Node no necesita ni recibe cambios.

## Registros y dependencias

- `compras_insumos.id_gasto` referencia el gasto; `id_insumo` referencia el insumo.
- `registrar_gasto` clasifica Materia prima / bebidas_postres / postres.
- Caja legada calcula egresos leyendo gastos vigentes; no hay un movimiento físico
  adicional que deba duplicarse. Las reservas y deudas son otros libros.
- Si hay integración contable ficticia, el trigger `pos_contable_gastos_alta` inserta
  un costo en `pos_costos_contables` dentro de la transacción del gasto.
- El costo de receta se calcula leyendo las últimas tres compras de insumo vigentes;
  no hay una caché de costos que requiera una escritura separada.
- Insumos sin control de stock conservan su cantidad, aunque registran compra y gasto.
- No hay medio de pago ni financiación en compras de insumos. Sí hay compras a crédito
  de PRODUCTOS en `compras.registrar_compra`, con cursor compartido para deuda y stock.
  Se preserva y prueba ese circuito; añadir crédito a INSUMOS sería otra funcionalidad.
- El registro exterior `mensajes_procesados` tiene sus propias confirmaciones para
  recepción/respuesta. Un mensaje interrumpido queda en revisión; no debe confundirse
  ese estado de transporte con una compra financiera parcialmente confirmada.

## Pruebas existentes revisadas antes de modificar

`test_costos_postres`, `test_stock_insumos`, `test_presentaciones_insumos`,
`test_produccion_postres`, `test_gastos`, `test_pos_contabilidad`,
`test_compras_packs`, `test_idempotencia_y_anulaciones`, `test_seguridad_api`.
Cubren resultados correctos, conversiones, costos, producción y reintentos externos,
pero no una falla entre gasto y compra, ni el rechazo de COMMIT de esta operación.

## Decisión previa

Un único dueño de conexión y BEGIN IMMEDIATE para toda la compra; gasto subordinado
sin COMMIT/ROLLBACK/cierre propios; resolución y lecturas dentro de ese corte. Incluir
resultado idempotente y trazabilidad en la misma transacción. Diferenciar líneas de un
bloque mediante índice estable. No deduplicar por coincidencia de importes/productos.
No migrar ni reparar operaciones históricas o instalaciones; producción sigue bloqueada.
