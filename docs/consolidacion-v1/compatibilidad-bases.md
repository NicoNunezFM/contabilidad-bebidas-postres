# Matriz de integración y compatibilidad SQLite

Fecha de inspección: 27/11/2026. Referencia `3c4ef418f161d232a21f059349e7249247f9dbd3`.
No se abrió ninguna base real. La clasificación se deriva del código y de fixtures.

| Familia | Identidad y contrato | Compatibilidad / decisión | Evidencia |
| --- | --- | --- | --- |
| Legado main | Tablas productos/ventas/compras/gastos/movimientos; sin marcador POS | Conservar backend e historial. No convertir en instalación POS cambiando variables o app_id. | `src/database.py`, `src/pos_simulacion.py:transaccion_simulacion` |
| Cajas de comandos laterales f6ce5534 | `saldos_iniciales_caja`, monto REAL, cortes por máximos de IDs, secciones rotiseria/bebidas_postres; movimientos con sección | **BLOQUEADA la migración**. Es una funcionalidad exclusiva pendiente, no descartada. POS usa otros eventos/cortes y centavos; sumar ambos saldos duplicaría aperturas. Los lectores generales no constituyen un validador de esta familia: no apuntarlos a ella. | `f6ce5534:src/saldos_caja.py`, `src/caja.py`, `tests/test_consolidacion_compatibilidad.py` |
| Simulación POS esquema 3 | application_id `0x41425031`, user_version 3 | Existe `migrar_esquema_simulacion_v3` para copias ficticias. No es migración general de negocio ni candidata. | `src/pos_simulacion.py:135` |
| Simulación/Entrenamiento esquema 4 | application_id `0x41425031`, user_version 4; Entrenamiento exige nombre e identidad propios | Usar sólo su contexto/launcher. Clientes, contabilidad y reparto tienen preparadores específicos con lock y respaldo. No ejecutar en instalaciones existentes en esta fase. | `src/pos_entrenamiento_db.py`, `scripts/abadion_entrenamiento.py`, `tests/test_pos_qa_integrado.py` |
| Alternativa #30 | Tabla `pos_preproduccion(modo, identidad)`, configuración y funciones distintas | **Incompatible** con #29/#32/#37. No copiar configuración, launcher ni esquema. Escenarios útiles adaptados en #32. | `7361e3a2:src/pos_preproduccion.py`; `tests/test_preproduccion_consolidacion.py:test_esquema_alternativo_30_no_se_migra` |
| Preproducción #29/#32 | Tabla `pos_preproduccion(modo, instalacion)`, UUID/ruta en instalación; `PREPRODUCCION-FICTICIA-V1`; archivo propio | Contrato conservado. Catálogo offline valida hash, mantiene IDs/stock y respalda. Restauración exige hash, identidad, integridad y mantenimiento offline. | `src/pos_preproduccion.py`, `scripts/abadion_preproduccion.py` |
| Pruebas #36 | `ABADION-PRUEBAS-FICTICIAS-V1`, archivo/cookies/perfil propios y aprobación de catálogo | Compatible con el código #37 dentro de su modo; versiones de código se verifican en lectura antes de activar. No equivale a base productiva. | `scripts/abadion_pruebas.py`, `tests/test_abadion_pruebas.py` |
| Unificado ficticio #37 | POS 4 más `pos_saldos_iniciales`, stock progresivo, deudas/pagos/reversos/cierres y ensayo | Sólo base ficticia nueva. No se transforman instalaciones con operaciones previas. Ensayo exige exactamente dos cajas, corte y catálogo; no activa producción. | `src/pos_saldo_unificado.py:20`, `src/pos_apertura_ensayo.py:64`, `tests/test_preparacion_unificada.py` |
| Candidatas V1/V2 | Identidades previas de preparación | Sin actualización o migración automática a V3; conservar y no reparar. Preparación en otro destino nuevo. | `docs/corte-produccion-base-limpia.md`, `scripts/abadion_candidata.py` |
| Candidata V3 | `0x41424331`, `PRODUCCION-CANDIDATA-BLOQUEADA-V3`, usuarios inactivos, SQL bloqueado y saldos/corte NULL | Continúa bloqueada incluso renombrada o si se altera sólo app_id. No servidor ni activación. Backup/restore a destino nuevo conserva bloqueo y permisos exactos. | `src/database.py:29`, `scripts/abadion_candidata.py`, `tests/test_produccion_candidata.py` |

## Conflictos detectados antes de integrar

1. **Aperturas de caja:** los cortes por IDs legados no se equiparan al corte temporal/eventos
   POS. Hay que conciliar qué historial incluye cada saldo antes de construir un adaptador.
2. **Unidades monetarias:** REAL en legado frente a enteros de centavos en POS; hay conversiones
   y reglas de redondeo. No renombrar columnas ni sumar importes sin contrato explícito.
3. **Secciones:** `rotiseria` lateral frente a `comidas` POS, y `bebidas_postres` compartida.
   Equivalencia de nombre no garantiza equivalencia del libro o saldo.
4. **Caja diaria:** #11 exigía autorización administrativa ante diferencias; `11732148`
   sustituyó esa regla por cierre de Ventas con alerta. Se conserva la política de #37.
   El cierre unificado nuevo sí es administrativo y no cierra jornadas ni ajusta saldos.
5. **Configuración y respaldos:** #30 tiene otra columna de identidad y otra configuración;
   reemplazar funciones del mismo nombre rompería reconocimiento, restauración y control.
6. **Personalizaciones/UI:** copiar HTML o tests de #24/#31 enteros podría perder clientes,
   fiados directos, catálogo comercial, pedidos sencillos y pantallas de saldo unificado.
7. **Historial de ventas/costos:** rentabilidad legada consulta `ventas`; el POS usa su propio
   registro. Preservado como limitación conocida; no se inventan snapshots históricos.

## Condiciones para una futura migración del legado lateral

Conservar la rama y su historial; inventariar contratos sin abrir bases reales; preparar
fixtures inventados con compras financiadas, reservas, anulaciones anteriores/posteriores
al corte, aportes/retiros por sección y gastos por defecto. Diseñar un mapa de eventos y
apertura que pruebe conservación de saldo, deuda y stock, idempotencia y rollback completo.
Sólo una revisión posterior puede autorizar su implementación. No usar apertura nueva
para ocultar diferencias. En esta propuesta no hay importador ni migración habilitada.
