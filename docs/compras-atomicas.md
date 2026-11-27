# Compras atómicas de insumos — informe técnico y guía de transacciones

Base: PR #38, `6a193c1b79d456a95a832b70447010da287724b1`.
Rama: `fix/abadion-compras-atomicas`. Datos exclusivamente ficticios; sin instalación,
merge, bot ni habilitación productiva. La [inspección previa](compras-atomicas-inspeccion.md)
documenta el recorrido anterior, entradas, confirmaciones, triggers y dependencias.

## Problema reproducido

En una exportación aislada del SHA base se inyectó un trigger que rechaza la inserción
de la compra. La prueba `test_regresion_gasto_huerfano` falló exactamente porque quedaron
**1 gasto y 0 compras**, aunque el stock no aumentó. Es un fallo esperado de la referencia,
no un resultado aprobado ni un fallo de la corrección. No se cambió una base existente.

## Cambio y propiedad de la transacción

`registrar_compra_insumo` y `registrar_compra_insumo_paquetes` delegan en `_comprar_insumo`.
El dueño abre una conexión mediante el mecanismo existente de identidad/aislamiento,
ejecuta `BEGIN IMMEDIATE` y reserva el único escritor antes de consultar insumo,
presentación o stock. Ambos resolutores reutilizan esa conexión.

La operación completa realiza, en este orden:

1. Comprueba el recibo idempotente si hay identificador de solicitud.
2. Resuelve el insumo/presentación y valida cantidades e importes finitos.
3. Registra el gasto con la misma conexión y las mismas categorías contables.
4. Guarda la compra y su vínculo al gasto.
5. Incrementa el stock si el insumo lo controla; conserva el anterior si no lo controla.
6. Guarda UUID de operación, solicitud, origen y resultado completo.
7. Ejecuta **un solo COMMIT**, después de completar todos los registros.

Si falla cualquier paso antes o durante COMMIT, el dueño ejecuta ROLLBACK y propaga
la excepción. Un rechazo de validación devuelve el error tras revertir su transacción.
También se prueban excepciones Python y una interrupción abrupta del proceso.

`gastos.registrar_gasto` conserva su interfaz y comportamiento autónomo. Con el parámetro
privado `_conexion` exige una transacción activa y no ejecuta BEGIN, COMMIT, ROLLBACK ni
cierra esa conexión; los errores SQLite se propagan al dueño. No se permite un gasto
subordinado fuera de una transacción. La API pública no acepta conexiones del cliente.

## SQLite explicado con este caso

Una conexión es una sesión con SQLite. Una transacción agrupa las escrituras que deben
tener un destino común. COMMIT publica el grupo completo; ROLLBACK descarta el grupo
todavía pendiente. Dos conexiones que confirman por separado no forman una transacción
conjunta: revertir la segunda no puede deshacer el gasto confirmado por la primera.

`BEGIN IMMEDIATE` reserva la escritura desde el principio. Dos compras concurrentes
esperan su turno antes de leer el stock anterior, evitando cantidades perdidas y recibos
duplicados. Un bloqueo que excede el timeout produce un error sin escrituras parciales;
se puede reintentar con la misma clave. No se implementan reintentos automáticos ciegos.

Los lectores de otra conexión ven el estado anterior hasta la confirmación; una prueba
consulta gasto, compra, inventario y costo desde otro lector justo después del INSERT
del gasto y comprueba que todavía no aparece ninguno de los efectos nuevos.

Los triggers SQLite participan en la misma transacción: si `pos_contable_gastos_alta`
generó un costo y luego falla el inventario, también se revierte ese costo. Se ensaya
una clave foránea diferida que rechaza el COMMIT real, además de fallos por triggers.

Una terminación sin ejecutar `finally` no convierte las escrituras pendientes en
confirmadas: SQLite recupera su journal al reabrir la base ficticia en modo escribible.
Esto se prueba con un proceso hijo que termina inmediatamente después del gasto.
No equivale a certificar un corte eléctrico físico, el disco o dispositivos reales.

Si COMMIT terminó y se pierde la respuesta, la compra ya está completa. No sería correcto
revertirla por un fallo de transporte posterior: el recibo persistido permite recuperar
el resultado original con la misma clave, sin repetir dinero ni stock.

## Idempotencia y trazabilidad

La nueva tabla `operaciones_compras_insumos` enlaza un único recibo con cada compra nueva.
Guarda UUID, canal, solicitud opcional, índice de línea, datos canónicos, origen,
resultado completo y fecha. Tiene FK a compras, unicidad por compra y unicidad por
`(canal, id_solicitud, indice_linea)`. El recibo se escribe antes del mismo COMMIT.

- Python y `/acciones`: identificador opcional `id_solicitud` y contexto opcional.
- Comandos: se reutiliza `contexto.id_mensaje`, que el adaptador ya enviaba; sin tocar Node.
- Bloques: índice estable de la línea no vacía; dos líneas idénticas son dos compras y
  al repetir el bloque se recupera cada recibo, sin fusionarlas por contenido.
- Una clave repetida con los mismos datos/origen devuelve el resultado original, incluso
  si luego cambió la presentación o la fecha corriente. Con otros datos/origen se rechaza;
  `/acciones` responde 409. La equivalencia es de solicitud canónica, no una heurística
  que intente adivinar si dos compras parecidas son la misma.
- Sin clave, cada invocación es una compra nueva y tiene su propio UUID. No hay forma
  segura de distinguir un reintento de dos compras legítimas iguales sin identificador.
- `mensajes_procesados` sigue siendo el registro exterior de recepción/respuesta. Puede
  quedar Procesando/Requiere_revision tras una interrupción; no genera un gasto parcial
  ni se borra automáticamente para forzar otro intento. La política exterior se conserva.
  Un mensaje ya completado puede resolverse antes en esa capa con su respuesta guardada;
  la comprobación de conflicto propia de la compra ocurre cuando se llega a esta operación.

Los resultados guardados representan la operación original, no una consulta del saldo
actual ni una cancelación de posteriores anulaciones. No se reescribe historial previo.

## Reglas contables preservadas

Compras de INSUMOS soporta el gasto inmediato en Materia prima / bebidas_postres / postres.
Caja legada descuenta ese gasto por consulta; no se crea un segundo movimiento de caja.
En el contexto contable integrado se conserva el trigger y su costo, sin inventar un
receptor físico. Los costos de receta se actualizan al leer las compras vigentes; no
se crea una caché ni se modifica el costo histórico de producción/ventas anteriores.

Este circuito no soportaba crédito ni selección de cuenta pagadora. Las acciones ahora
rechazan esos campos explícitos para no interpretar financiación como gasto pagado.
El texto del comercio no se usa para inferir un medio de pago. Añadir crédito a insumos
requiere otra decisión comercial; aquí no se incorpora. Las compras de PRODUCTOS pagadas
y financiadas conservan su circuito, con deuda y stock en la transacción que ya utilizaban;
se incluyen pruebas de regresión de ambos casos.

## Esquema, compatibilidad y límites

La tabla de recibos se crea al inicializar una base ficticia nueva y, para una copia
ficticia anterior, dentro de la propia transacción de compra con CREATE IF NOT EXISTS.
Incluso esa creación se revierte si falla la compra. No se cambian columnas monetarias,
versiones/marcadores POS ni libros anteriores. Un contrato incompatible falla y revierte;
no existe fallback que confirme solamente el gasto. No se ejecutó migración en instalaciones.

Las candidatas bloqueadas siguen rechazándose mediante `obtener_conexion`; no se modifican
sus preparadores o apertura. La suite completa comprueba identidad, bloqueos y recuperación.

Persisten estos límites:

- No se buscan ni reparan gastos huérfanos históricos en bases reales.
- Se conserva la representación monetaria REAL del módulo; no se cambia el modelo de
  redondeo ni se promete una migración a centavos como parte de esta corrección.
- Código anterior al fix no entiende estos recibos y conserva el defecto: no se certifica
  volver a ese código y continuar escribiendo/reintentando compras con las garantías nuevas.
- No se habilitan compras a crédito de insumos, movimientos físicos inferidos, nueva UI,
  cambios del bot ni producción. Persisten otros bloqueos descritos en la consolidación.

## Pruebas y referencia

Se conservan sin modificar los 531 casos de #38. La referencia histórica aprobó Linux
495 / 36 omitidos y Windows/Edge 531 / 0 omitidos:
[CI de #38](https://github.com/NicoNunezFM/contabilidad-bebidas-postres/actions/runs/46025273435).

`tests/test_compras_insumos_atomicas.py` agrega éxito, trazabilidad, gasto huérfano,
fallos en gasto/compra/stock/recibo/commit con y sin integración, lectores concurrentes,
commit real rechazado, caída de proceso, gasto subordinado, duplicados/conflictos,
compras concurrentes, paquetes, stock no controlado, bloques, acciones/comandos,
valores inválidos, creación de esquema revertida y regresión de productos a crédito.
También rechaza como éxito un INSERT que un trigger omita silenciosamente: gasto,
compra y recibo deben haberse insertado realmente antes de confirmar.

La primera tanda focal aprobó 79 casos (incluye suites preexistentes y casos nuevos;
no sumar con otras ejecuciones). Una ejecución inicial en el entorno restringido se
interrumpió sin resultado útil y se repitió con conexiones locales habilitadas; no se
cuenta como aprobación ni como fallo de aserción. La prueba roja sobre #38 es esperada.

Los resultados completos, fallos/omisiones y pendientes se registran en la descripción
del PR del fix, con enlaces al SHA y JUnit de Linux y Windows/Edge. CI ya ejecuta ambas
suites completas; no se reducen aserciones ni se omiten pruebas para aprobar esta rama.
El registro de cierre en la PR permite informar resultados del último SHA sin generar
otro commit sólo para declarar que pasó el anterior.
