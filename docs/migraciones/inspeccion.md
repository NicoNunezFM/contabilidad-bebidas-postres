# Inspección previa y matriz de compatibilidad — Fase 2.5

Base inspeccionada antes de modificar aplicación: PR #42,
`1ec1ab98755a248f86c3a50ba3164320e4381448`. Solo fuentes y fixtures ficticios.

La CI final de esa base (run 46070961495) ya terminó: Windows/Edge 692 aprobados,
Linux 654 aprobados/38 omisiones; seguridad Python aprobada. Node falló por los avisos
conocidos, separado de regresiones funcionales. Esta evidencia sustituye la falta de
resultado remoto documentada al cerrar 2.4; no se cambió su rama ni su informe histórico.

## Evidencia del código

- `src/database.py:1364` inicializa con varias conexiones/commits, ALTERs condicionales
  y backfills. No constituye una migración global atómica ni asigna identidad legada.
- `src/pos_simulacion.py:28,109–191` define ABP1/esquema 4 y un conversor 3→4 que
  reescribe JSON/eventos. No debe usarse para esta consolidación de registros inciertos.
- `src/pos_preproduccion.py:42–80` exige modo, UUID, ruta y versión exactos; `respaldo`
  usa SQLite Backup API, manifiesto SHA256 e integridad/FK. `restaurar` descarta sesiones.
- `src/pos_entrenamiento_db.py:50–124` protege archivos, identidad y exclusión de proceso.
- `scripts/abadion_pruebas.py:147–263` publica releases por hash, comprueba en lectura
  antes de activar, respalda antes de actualizar y recupera en otra carpeta. Conservar.
- `scripts/abadion_candidata.py` protege ABC1/V3, usuarios inactivos y SQL bloqueado;
  no es una instalación operativa ni un destino de migración.

## Matriz

| Familia / procedencia | Identificación y dependencias | Decisión |
| --- | --- | --- |
| Legado sin versión | app_id 0, user_version 0, libros REAL/categorías históricas | Intervención y conciliación comercial; no adoptar ni cambiar marcadores automáticamente |
| Cajas laterales de WhatsApp | `saldos_iniciales_caja`, cortes por ID, secciones y aperturas distintas | Rechazar migración; no deduplicar por semejanza ni sumar aperturas |
| POS esquema 3 | ABP1, versión 3, movimientos anteriores | Intervención independiente; el conversor existente reconstruye eventos y queda fuera del mecanismo nuevo |
| Entrenamiento / tablet | ABP1/4 y marcador entrenamiento/laboratorio | Reconocer pero rechazar en el migrador de instalaciones persistentes; conservar sus preparadores |
| Variante #30 | `pos_preproduccion(modo, identidad)` | Rechazar: incompatible con UUID/columna `instalacion` del linaje elegido |
| #38 | `6a193c1…`, ABP1/4 y modo/UUID/ruta válidos | Migrable si el catálogo estructural coincide; sin interpretar registros legados |
| #39 | `4c31276…`, mismo número 4; `operaciones_compras_insumos` | Validar tabla de idempotencia y conservar íntegros sus recibos |
| #40 | `91f293b…`, mismo número 4; `pos_costos_lineas` y triggers | Crear vacío si ausente; conservar snapshots presentes. Nunca completar ventas antiguas con costos actuales |
| #41 | `3c5b5ae…`, mismo número 4; lectores/recibos financieros reforzados | No reescribir saldos/eventos; verificar conservación exacta |
| #42 | `1ec1ab9…`, mismo número 4; contexto de sesión y auditoría | Conservar usuarios y sesiones vinculadas; sesiones antiguas sin contexto siguen requiriendo login |
| Nueva instalación gestionada | ABP1/5, UUID/modo coincidentes y libro de migraciones verificable | Creación explícita usando preparador validado; actualización offline transaccional |
| Versión futura, catálogo alterado o migración parcial | Versión >5, objetos desconocidos, contratos incompletos o libro inconsistente | Rechazar antes de escribir; revisión manual |
| Candidata ABC1/V1/V2/V3 | app_id/tabla candidata, corte pendiente y usuarios inactivos | Rechazar; producción permanece bloqueada |

## Diseño acordado por la inspección

Migración explícita 4→5: lock de instalación más reserva SQLite de escritura, snapshot
verificado del mismo corte, contrato estructural cerrado y hash tipado de todas las
filas existentes. Reutilizar exclusivamente DDL aditivo de #39/#40/#42, sin commits
internos ni backfill. Registrar identidad, versión y checksum dentro de la misma
transacción que cambia user_version. Ante fallo SQLite revierte; jamás restaurar
automáticamente un backup anterior encima de operaciones nuevas.

Los módulos opcionales no habilitados no se activarán por migrar: sus objetos, si
existen, deberán coincidir con contratos conocidos y grupos completos. Las creaciones
diferidas existentes se inventariarán; el registro nuevo versiona el paso gestionado,
no atribuye retrospectivamente un PR a una base cuyo número de versión era ambiguo.

Recuperación nueva: tomar snapshot actual verificado bajo ambos bloqueos y reutilizar
la recuperación aislada de Pruebas. No seleccionar un pre-backup obsoleto para volver
atrás. Corrupción irrecuperable y operaciones posteriores al último backup no permiten
prometer pérdida cero: requieren intervención y fuentes autorizadas, sin inventarlas.
