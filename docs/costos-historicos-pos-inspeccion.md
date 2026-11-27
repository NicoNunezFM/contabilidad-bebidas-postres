# Inspección previa — costos históricos POS

Base inspeccionada: PR #39, `4c312768528207d774247be42d075f1be8727d33`.
El PR remoto conserva esa cabeza. Copia independiente; ninguna base operativa abierta.

## Contratos comprobados antes de modificar código

| Contrato | Evidencia en la base | Consecuencia |
| --- | --- | --- |
| Bebidas: promedio ponderado de últimas tres compras no anuladas | `src/rentabilidad.py:_costo_unitario_bebida` | Es una estimación de reposición reciente, no FIFO ni costo real del lote vendido |
| Postres: última producción por nombre; alternativa receta activa | `src/rentabilidad.py:_costo_unitario_postre` | Producción guarda costo y versión, pero no hay asignación de lote a venta; se debe identificar como estimación |
| Receta: compras recientes de insumos, rendimiento y fijo por unidad | `src/costos_postres.py:obtener_receta`, `estimar_costo_receta`, `_costo_unitario_reciente` | Faltantes producen total NULL y parcial conocido; no convertirlos en cero |
| Adicional de catálogo: costo opcional | `src/adicionales.py`, `src/database.py:adicionales_catalogo` | Fuente declarada; el precio de venta no es costo |
| Rotisería, cheddar/huevo por destino y papas dobles | `src/pos_pedidos.py:_personalizar_preparacion`, `src/pos_menu_entrenamiento.py` | Solo precios; faltan composición, unidades e identificación de insumos/costo |
| Ingredientes quitados y observaciones | `src/pos_pedidos.py:calcular_pedido_pos` | Textos sin gramajes ni vínculo a receta; impiden certificar costo completo |
| Promoción de postres | `src/pos_pedidos.py:calcular_pedido_pos` | Separa líneas por precio efectivo; descuento afecta ingreso, no cantidad/costo |
| Venta POS atómica e idempotente | `src/pos_simulacion.py:transaccion_simulacion`, `registrar_venta_simulada` | BEGIN IMMEDIATE, recibo por usuario/solicitud, venta/pagos/stock en una conexión; insertar costos antes del commit |
| Pedidos convertidos en venta | `src/pos_simulacion.py:convertir_pedido_simulado` | Reutiliza la transacción y confirmador; no costear el presupuesto |
| Anulación/devolución parcial | `src/pos_simulacion.py:revertir_venta_simulada`, `src/pos_cobros.py:pos_unidades_devueltas` | Evento con unidades por línea; revierte stock y pagos según reglas existentes; revertir costo original proporcional, nunca costo actual |
| Fiado y abonos | `src/pos_cobros.py:estado_cuenta`, `terminar_evento` | Ingreso devengado al vender; abono solo cobro, no nuevo ingreso/costo |
| Ventas legadas separadas | `src/ventas.py`, `src/database.py:ventas`, `venta_adicionales`, `ventas_operaciones` | Ya guardan snapshots, algunos NULL; POS no inserta filas legadas; claves deben conservar origen |
| Informe de rentabilidad legado | `src/rentabilidad.py:_ventas_producto`, `rentabilidad_producto`, `rentabilidad_categoria` | Históricos guardados separados de estimación actual; hoy omite POS |
| Informe contable POS | `src/pos_contabilidad.py:calcular_periodo`, `src/reportes.py:resumen_por_periodo` | Tiene corte, devengado, cobrado, compras/gastos y cajas por sección; no es margen de mercadería |
| Compras atómicas #39 | `src/costos_postres.py:_comprar_insumo`, `src/gastos.py:registrar_gasto` | No modificar sus escrituras ni su recibo; preservar 570 pruebas |

## Decisión de integración

Captura inmutable por venta/línea, aditiva y sin backfill. La fuente se lee en la misma
conexión que confirma la venta. Los métodos existentes se conservan; no se introduce
una nueva valoración de inventario. Producciones y promedios se etiquetan estimados:
no acreditan qué lote se vendió. Un costo declarado de adicional se etiqueta conocido.
Rotisería sin fuente continúa desconocida. Personalizaciones sin composición conservan
componentes valorados, pero total y margen de la línea quedan desconocidos.

Informe histórico explícito separado del resultado contable, con cobertura y secciones.
Ingresos de productos se toman una vez de cada libro disjunto; envío se informa aparte,
sin adjudicarle costo de mercadería. Reversiones se fechan por evento; abonos no repiten
ventas. Bases anteriores se leen sin escribir y sus ventas sin captura permanecen NULL.

Resultado contable existente = ventas devengadas menos compras/gastos del período.
Flujo cobrado = cobros/reembolsos efectivamente registrados, diferente del devengado
cuando hay fiado. Margen bruto = ingreso de productos menos costo histórico de los
productos vendidos: comprar stock no equivale a consumirlo. No restar simultáneamente
compras y costo de ventas ni convertir margen parcial en rentabilidad total.
