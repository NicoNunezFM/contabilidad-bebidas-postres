# Menú táctil de Lo de Clau

Rama independiente `feature/abadion-pos-menu-variantes`, creada desde el commit `ba1e32679ab9ff0fc8e387d46cc8cce5cce6800b` del PR #9. El Issue #10 estaba abierto al comenzar. El PR de menú apunta a `feature/abadion-pos-entrenamiento-integrado` y permanece en borrador para revisión conjunta antes de integrar.

## Uso

En entrenamiento, hamburguesas, sándwiches y milanesas al plato tienen una tarjeta por familia. Al tocarla se eligen las variantes disponibles. Las opciones agotadas o sin precio permanecen visibles y deshabilitadas. Los selectores de tamaño de hamburguesa y de porción de papas tienen etiquetas distintas.

Cada comida permite cheddar y huevo extra, con cantidades separadas por preparación. Cada agregado cuesta $1.000 por unidad del producto pedido. Las guarniciones al plato son completas, papas o puré. El recargo de papas dobles de $2.000 corresponde a los combos con papas. El sándwich grande individual conserva su precio y presentación.

Las observaciones son opcionales, hasta 300 caracteres por línea. Se pueden editar con la variante. Las cantidades, ingredientes quitados, destinos de adicionales y notas aparecen en el resumen para cocina, accesible desde el pedido, y en el detalle del historial de venta. Los textos se insertan como texto y admiten caracteres como `<`.

## Conservación de datos y cálculo

- La familia es una agrupación visual. Cada variante mantiene el `id_producto` existente y su control de stock. No se reemplazan productos con un identificador genérico de familia.
- Los precios confirmados ya coincidían con la plantilla salvo cheddar y huevo simple y doble, corregidos a $8.000 y $10.000. Ambas variedades siguen agotadas. Pollo simple conserva $5.500, y pollo doble continúa sin precio y agotado. Big Mac mantiene sus valores y disponibilidad anteriores.
- Las pizzas, Pepsi, 7up, bandeja grande, postres chicos y promoción mixta de dos por $5.000 permanecen. Tortilla, bebidas y postres grandes conservan los precios confirmados.
- La validación y la confirmación recalculan importes en el servidor dentro de la transacción existente. Quitar ingredientes conserva el importe. Los destinos inválidos, repeticiones, cantidades inválidas y precios enviados por el cliente se rechazan.
- La solicitud guarda `adicionales_preparacion`, `papas_dobles` y `observacion` solamente cuando tienen contenido. Así se conserva la representación de las solicitudes anteriores para reintentos con UUID. El pedido calculado guarda el recargo, destinos, cantidades, nota y precio efectivo en el JSON histórico existente.
- El esquema de SQLite y los circuitos de caja, fiados, facturación y contabilidad conservan sus referencias a productos y sus transacciones. La venta mixta de regresión verifica el reparto de importes por sección, el stock y la conciliación.
- La actualización explícita de catálogo conserva los IDs, existencias y ventas anteriores. Ahora también conserva cualquier estado `sin_stock` previamente registrado aunque la plantilla lo marque disponible. El alta de las nuevas personalizaciones se limita al contexto de entrenamiento.
- No se ejecutó actualización alguna en la instalación de práctica del usuario. Las bases usadas en las pruebas se crean bajo directorios temporales fuera de OneDrive. No se despliega ni se publica el servidor de pruebas. El bot conserva su integración existente.

## Decisiones pendientes

- El catálogo actual descuenta stock por producto vendido y varias comidas no controlan existencias. Faltan recetas, unidades e insumos vinculados para descontar papas, cheddar o huevo por agregado. Se conserva el modelo actual y se registra el detalle de preparación para cocina. Definir consumos e inventario de ingredientes queda pendiente de decisión comercial.
- Los ingredientes de hamburguesas cheddar y huevo, pollo y Big Mac requieren confirmación. Se conservan sus opciones previamente configuradas. Se agregan los ingredientes confirmados para la clásica, sándwich de milanesa y napolitana, sin jamón añadido a la receta.
- Los precios de una instalación anterior se conservan hasta una actualización explícita de su catálogo local. El cambio de versión del código por sí solo agrega la presentación por familias y las personalizaciones sin reescribir los precios de una base instalada. Su actualización debe coordinarse después de revisar ambos PRs y el QA del Issue #10.
- Las nuevas opciones se habilitan en entrenamiento. La habilitación en ventas reales y la impresión o envío automático de comandas requieren un trabajo posterior autorizado.
- Quedan pendientes la revisión humana de comodidad en la tablet física y la confirmación comercial de ingredientes todavía ambiguos. Las pruebas Edge usan un navegador real en modo sin ventana.

## Evidencia automatizada

| Caso | Resultado esperado | Prueba |
| --- | --- | --- |
| Precios y variantes | Importes confirmados y agotados preservados | `test_menu_entrenamiento_variantes_precios_y_disponibilidad` |
| Adicionales, destinos y cantidades | $1.000 por agregado y $2.000 por papas dobles en combo | `test_personalizacion_menu_en_venta_sqlite_e_historial` |
| Venta mixta y registro | Precio efectivo, nota, stock, caja, historial y conciliación consistentes | `test_personalizacion_menu_en_venta_sqlite_e_historial` |
| Reintentos y compatibilidad | Mismo UUID devuelve la misma venta, nota distinta genera conflicto, formato antiguo conservado | `test_personalizacion_menu_en_venta_sqlite_e_historial` y regresión existente |
| Actualización de catálogo | IDs, stock, ventas y agotados preservados después de dos actualizaciones | `test_actualizacion_menu_conserva_ids_stock_historial_y_agotados` |
| Edge táctil | Tres tarjetas, variantes agotadas deshabilitadas, edición con notas y resumen seguro | `test_pos_web_menu_tactil_editar_variante_y_resumen` |
| Aislamiento | Aviso persistente, bases ficticias y sesiones aisladas | Suite de entrenamiento y Edge existente |

Los resultados finales de ejecución y los enlaces de CI se registran en el PR borrador.
