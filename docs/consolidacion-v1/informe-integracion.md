# Informe de integración — Abadion V1

27/11/2026. Rama `consolidate/abadion-v1-estable`.

## Resultado y alcance

La propuesta parte de #37, `3c4ef418f161d232a21f059349e7249247f9dbd3`, sin cambios
posteriores encontrados en GitHub al iniciar. Las 41 ramas y 34 PR abiertos están en
la [matriz completa](matriz-ramas-prs.md); los SHA y bases remotos quedan en JSON.
No se fusiona en main, no se cierra ningún PR y no se cambia ninguna instalación.

**La consolidación conserva íntegros `src/`, `pos-web/`, el adaptador WhatsApp,
catálogos, launchers e instaladores del SHA de referencia.** La inspección no justifica
reimportar código lateral que ya fue adaptado. Los únicos añadidos ejecutables son
la herramienta de auditoría Git y dos casos de compatibilidad con bases temporales.
Se actualiza CI para main, stable/** y consolidate/**, ejecución manual, suite completa
Windows/Edge y evidencias JUnit. No se cambia una política contable durante esta fase.

El nombre de rama expresa el destino del trabajo; no certifica estabilidad productiva.
Persisten bloqueos contables y de migración enumerados abajo. No hay activación real.

## Inspección de cambios exclusivos y decisiones

| Origen | Evidencia exacta | Funcionalidad y decisión |
| --- | --- | --- |
| #11, e6fc2d1 / 7cbedc1 | `tests/test_pos_qa_integrado.py`, `scripts/abadion_entrenamiento.py:activar_contabilidad`; integración `6d7e8fd` | Conservar devolución, conciliación, recuperación y reserva de escritura antes de respaldo. Ya presentes: BEGIN IMMEDIATE precede al backup, que usa conexión lectora separada y elimina copia fallida. No cherry-pick. |
| #11, autorización ante diferencias | `git diff 7cbedc17 3c4ef418 -- tests/test_pos_caja_diaria.py`; commit `11732148b5d5943fcf93e41e86349febf52a237f` | La prueba fue renombrada de autorización a alerta porque cambió una regla operativa: Ventas puede cerrar con diferencia y aviso administrativo. No restaurar silenciosamente la regla vieja. El cierre unificado V3 exige Administración. |
| #12, 076f084 / b89aa97 | `src/pos_menu_entrenamiento.py` es idéntico al blob lateral; `_personalizar_preparacion` y sus modelos conservados en `src/pos_pedidos.py`; `tests/test_pos_entrenamiento.py`, `tests/test_pos_web.py` | Variantes, guarniciones, adicionales por destino, observaciones y resumen de cocina incorporados en #13. Espera de Edge sustituida por el helper actual. No reimportar. |
| #24, f2cc18f / cc3dcb0 / d160fc5 | `scripts/generar_demo_tablet.py` conserva el mismo AST de funciones; `tests/test_pos_web.py:test_pos_web_premium_catalogo_y_carrito` y controles tablet; `docs/pos-premium-windows.md` | Interfaz premium, indicador de catálogo y demo autónoma preservados/evolucionados por #27 y posteriores. No copiar HTML/demo anteriores ni sustituir el workflow actual. |
| #30, 6b53839 / 6d7fdc8 / 7361e3a | `docs/consolidacion-preproduccion-windows-v1.md` contiene la comparación #29/#30; `tests/test_preproduccion_consolidacion.py` | Staging de backup, rechazo de auxiliares, espera del backup en cierre y catálogo offline ya adaptados por #32. Esquema `identidad` y launcher #30 incompatibles con contrato `instalacion`/UUID. Conservar el contrato #29/#32; no importar funciones/test fixtures incompatibles. |
| #31 y #28, 35949f0 / a837332 / efcaab7 / 067b9ca | `git diff 067b9cab 3c4ef418 -- tests/test_pos_web.py`; `test_pos_web_comidas_complementos_y_cancelacion`, `test_pos_web_menu_tactil_editar_variante_y_resumen` | Comidas en pasos, complementos, agrupación de postres, controles de cantidad y retorno de foco ya presentes en #33. La prueba de complementos actual además corre en Preproducción. Conservar el flujo actual y no bajar al HTML anterior. |
| #8, 1e1768f..74ea4b7 | `docs/pos-entrenamiento-integrado.md`; commits `320f109`, `d78777d`, `6d7e8fd`; `scripts/abadion_entrenamiento.py` | Otra rama no ancestral: Entrenamiento, actualización de catálogo, pizzas y promoción de sabores mixtos incorporados mediante #9. Conservar implementación integrada con corte, clientes y reparto. |
| feature/comandos-whatsapp-v1, 40d4039..f6ce553 | `src/saldos_caja.py` y `tests/test_cajas_separadas.py` sólo existen en esa rama; cambios en caja/comandos/acciones/movimientos/database | Exclusivos reales: aperturas legadas por sección y corte por máximos de IDs, aportes/retiros por sección y gasto general por defecto a rotisería. **Pendientes, no obsoletos.** No integrar en #37 sin adapter/migración revisados: podría duplicar saldos, reinterpretar historia y romper reservas/deudas. Rama y commits se preservan. |
| feature(pos-tablet-v1 | Mismo SHA remoto `f6ce5534ed5506044155627b028b628f173ffd5b` | Alias duplicado exacto de la rama lateral de comandos. No eliminarlo; mismo bloqueo contable. |

Los símbolos ausentes en el JSON no equivalen automáticamente a funcionalidades perdidas:
hay pruebas renombradas, funciones reemplazadas por launchers y alternativas incompatibles.
La lista de commits exclusivos y los archivos afectados permite repetir la inspección.

## Funciones conservadas y evidencia de regresión

| Función | Evidencia existente conservada |
| --- | --- |
| POS, catálogo, variantes, promociones, táctil | `test_pos_precios.py`, `test_pos_personalizaciones.py`, `test_pos_web.py`, `test_catalogo_comercial.py` |
| Contabilidad, dos cajas, compras y cierres | `test_pos_contabilidad.py`, `test_jornada_contable.py`, `test_pos_caja_diaria.py`, `test_pos_compras_caja.py`, `test_saldo_unificado.py` |
| Pedidos, delivery y custodia | `test_issue15_base.py`, `test_pos_pedidos.py`, `test_lo_de_clau_delivery.py`, `test_lo_de_clau_edge.py` |
| Clientes, abonos FIFO y fiados directos | `test_pos_clientes.py`, `test_pos_cobros.py`, `test_fiado_directo.py` |
| Inventario, insumos, recetas, costos y rentabilidad legada | `test_inventario.py`, `test_movimientos_stock.py`, `test_stock_insumos.py`, `test_costos_postres.py`, `test_produccion_postres.py`, `test_rentabilidad.py` |
| Seguridad, aislamiento, backups y recuperación | `test_seguridad_api.py`, `test_preproduccion*.py`, `test_abadion_pruebas.py`, `test_backups.py`, `test_produccion_candidata.py`, `test_preparacion_unificada.py` |

## Riesgos y límites que mantienen el bloqueo

- **Migración de cajas legadas lateral pendiente.** No se descarta la función ni se
  declara compatible por compartir nombres de cajas. Ver [matriz SQLite](compatibilidad-bases.md).
- **Activación productiva no implementada.** V3 permanece bloqueada, sin saldos/corte,
  usuarios habilitados ni servidor. El ensayo sólo admite identidad ficticia.
- **Compra de insumos no atómica:** `costos_postres.py:registrar_compra_insumo` confirma
  el gasto antes de guardar compra/stock en otra conexión. Requiere corrección posterior
  y prueba de fallo intermedio; no se amplía el alcance de esta consolidación.
- **Rentabilidad POS incompleta:** el cálculo histórico de rentabilidad lee ventas
  legadas; el POS no congela el costo equivalente. No fabricar costos históricos.
- **Políticas de cierre distintas:** documentadas, conservadas; la aceptación operativa
  del cierre/diferencias sigue pendiente y no se infiere de una prueba aprobada.
- **Reinicio físico, pérdida de energía, dispositivos y respaldo externo:** no certificados
  por CI ni por estos ensayos locales. No se usaron datos ni dispositivos productivos.
- No se alteran permisos, filtro de grupos o credenciales del bot instalado. El adaptador
  sigue siendo whatsapp-web.js, sin Cloud API añadida. No se inicia ni se conecta.

## Orden propuesto para integración futura en main

1. Revisar este PR comparando con #37: procedencia, CI y documentación. Luego revisar el
   diff acumulado contra main; no aprobar únicamente el pequeño diff de consolidación.
2. Resolver/corregir integridad de compras y delimitación de rentabilidad en otra propuesta
   acotada; definir el tratamiento de cajas legadas con fixtures y revisión contable.
3. Mantener #30 y ramas laterales como evidencia, sin fusionarlas en bloque. Una lista
   posterior de PR sustituidos requerirá decisión del usuario; aquí no se cierran.
4. Revisar la propuesta acumulada #37 + consolidación hacia main (o retargetear este PR
   explícitamente tras esa revisión), conservar historia y exigir CI del SHA resultante.
   No hace falta fusionar los 34 borradores uno por uno: muchos ya son ancestros.
5. Sólo con los bloqueos resueltos decidir aceptación como rama estable de código.
   La apertura de producción constituye una etapa separada y requiere autorización propia.

No se ejecutó ninguno de esos merges. Las bases reales, instalaciones y bot permanecen
fuera de este trabajo. Los resultados exactos se registran en [validación](validacion.md).
