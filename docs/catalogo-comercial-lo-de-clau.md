# Catálogo comercial de Lo de Clau — candidato aislado

Base exacta: PR #34, `c6b9f79b8eb945214dd4815e8af72b31c1bc969c`.
Rama `feature/abadion-catalogo-comercial`, apilada contra `feature/lo-de-clau-pedidos-delivery`.
No fusionar ni desplegar. No se aplica el catálogo a ninguna instalación existente.

## Fuente comercial y alcance

La conversación «Prueba carrito en Edge» corrigió el total a **38 productos**: 6 sándwiches, 9 al plato, 5 hamburguesas, 3 pizzas, 3 conos/bandejas, 6 postres y 6 Manaos. El historial accesible sólo devolvió los últimos cinco intercambios; no se presenta como una recuperación íntegra de las confirmaciones anteriores. Los precios se cotejaron con `scripts/catalogo-entrenamiento.json` y `docs/pos-menu-variantes.md`. En esta continuación el usuario confirmó la baja de ambas Big Mac, las cinco hamburguesas restantes, Clásica $7.000/$9.000 y Chocotorta/Oreo $3.000/$4.500. Ante la consulta por el resto pidió conservar los precios ya proporcionados; se conservaron los valores de esa plantilla, sin estimaciones ni aumentos.

Se agregan Pepitos chico $3.000, grande $4.500 y Fugazzeta $12.000. Mozzarella $10.000 y Especial $12.000. **Especial conserva el nombre SQLite `Jamón y morrones`** y su ID; la interfaz ya lo presenta como Especial desde #31.

Los dos adicionales son opciones por preparación, $1.000 por cheddar y $1.000 por huevo. No forman parte de los 38 productos ni se agregan automáticamente a cada línea mediante IDs de adicionales, para evitar cobrar dos veces. Se reutiliza el cálculo existente del servidor. Los recargos de papas dobles y el delivery de #34 se conservan.

La promoción reutiliza el grupo `todos`: descuento de $1.000 por cada dos unidades de postres chicos, combinando Chocotorta, Oreo y Pepitos. Tres cuestan $8.000 y cuatro $10.000. No se promocionan los grandes.

## Productos y precios en pesos

| Categoría | Producto | Precio | Control de stock |
| --- | --- | ---: | --- |
| Bebidas | Manaos Pomelo 600ml | $1.300 | Unidades |
| Bebidas | Manaos Cola 600ml | $1.300 | Unidades |
| Bebidas | Manaos Cola 2.25l | $2.000 | Unidades |
| Bebidas | Manaos Naranja 2.25l | $2.000 | Unidades |
| Bebidas | Manaos Manzana 2.25l | $2.000 | Unidades |
| Bebidas | Manaos Pomelo 2.25l | $2.000 | Unidades |
| Sándwiches | Grande de pollo individual | $7.500 | Sin control por producto |
| Sándwiches | Grande de carne individual | $8.500 | Sin control por producto |
| Sándwiches | Chico de pollo + papas | $7.000 | Sin control por producto |
| Sándwiches | Chico de carne + papas | $8.000 | Sin control por producto |
| Sándwiches | Grande de pollo + papas | $9.000 | Sin control por producto |
| Sándwiches | Grande de carne + papas | $10.000 | Sin control por producto |
| Conos | Conos | $3.500 | Sin control por producto |
| Conos | Bandeja chica | $4.500 | Sin control por producto |
| Conos | Bandeja grande | $5.500 | Sin control por producto |
| Al plato | Milanesa de pollo con fritas | $9.000 | Sin control por producto |
| Al plato | Milanesa de carne con fritas | $10.000 | Sin control por producto |
| Al plato | Milanesa de pollo con puré | $8.500 | Sin control por producto |
| Al plato | Milanesa de carne con puré | $9.500 | Sin control por producto |
| Al plato | Napo de pollo con fritas | $10.500 | Sin control por producto |
| Al plato | Napo de carne con fritas | $11.500 | Sin control por producto |
| Al plato | Napo de pollo con puré | $10.000 | Sin control por producto |
| Al plato | Napo de carne con puré | $11.000 | Sin control por producto |
| Al plato | Tortilla | $8.500 | Sin control por producto |
| Hamburguesas | Pollo con papas simple | $5.500 | Sin control por producto |
| Hamburguesas | Cheddar y huevo simple | $8.000 | Sin control por producto |
| Hamburguesas | Cheddar y huevo doble | $10.000 | Sin control por producto |
| Hamburguesas | Clásica simple | $7.000 | Sin control por producto |
| Hamburguesas | Clásica doble | $9.000 | Sin control por producto |
| Postres | Chocotorta grande | $4.500 | Unidades |
| Postres | Oreo grande | $4.500 | Unidades |
| Postres | Chocotorta chica | $3.000 | Sin control por producto |
| Postres | Oreo chico | $3.000 | Sin control por producto |
| Pizzas | Mozzarella | $10.000 | Sin control por producto |
| Pizzas | Especial (nombre histórico: Jamón y morrones) | $12.000 | Sin control por producto |
| Postres | Pepitos chico | $3.000 | Sin control por producto |
| Postres | Pepitos grande | $4.500 | Unidades |
| Pizzas | Fugazzeta | $12.000 | Sin control por producto |

## Conservación, bajas y disponibilidad

El JSON es independiente de las plantillas de Entrenamiento y del catálogo legado. No se cambian inicializadores, instalaciones, `negocio.db`, WhatsApp, accesos directos ni procesos instalados.

El importador existente marca **todos los productos omitidos** como `fuera_menu`: Pepsi lata, 7up lata, pollo doble, Big Mac simple/doble, Manaos Lima si existiera y productos ficticios/práctica. No borra sus filas, IDs, stock ni ventas. La vista previa debe revisarse completa: cualquier producto desconocido también queda omitido. El adicional de práctica queda inactivo, conservando sus históricos.

Se preservan los estados `sin_stock` anteriores. Por eso 38 productos del menú no implica 38 disponibles para vender. Pollo simple y cheddar/huevo que antes estaban agotados continúan agotados. Los productos nuevos tienen saldo cero; no se trasladan los 24 de práctica. El campo obligatorio `stock_inicial: 0` no es un conteo: el importador de preproducción lo fuerza a cero y conserva los saldos existentes. Pepitos grande controla unidades como los otros grandes; Pepitos chico conserva el modelo sin control por producto de los otros chicos. Cambiar ese modelo requiere una revisión independiente; este trabajo no inventa recetas ni existencias por ingrediente.

Los alias ya existentes conservan IDs para Chocotorta/Oreo sin tamaño, Clásica sin tilde y puré sin tilde. Ambigüedades se rechazan. Una base antigua con categoría `Sanguches` en vez de `Sándwiches`, o con distinto control de stock, **se rechaza sin modificarla**. No se fuerza una reclasificación contable.

## Vista previa, aprobación, hash y respaldo

Se reutiliza `src/pos_preproduccion.py`; no hay aplicación automática al iniciar. `validar-catalogo` requiere carpeta explícita y genera plan con IDs, precios anterior/propuesto, stock conservado, altas a cero, adicionales, promoción, omisiones y SHA-256 del JSON. La validación no escribe catálogo ni crea respaldo de aplicación.

`actualizar-catalogo` por CLI exige `--sha256`. Otro contenido con la huella anterior se rechaza. El hash identifica **el archivo**, no firma una aprobación humana ni vincula criptográficamente el estado previo de SQLite. La función interna admite omitirlo para sus llamadores existentes; no se presenta esa función como barrera de autorización. Antes de una futura aplicación autorizada deben detenerse las operaciones, regenerarse la vista previa y revisarse contra la misma base. Aquí no se autorizó ni ejecutó esa aplicación en una instalación existente.

El proceso toma lock exclusivo de mantenimiento, verifica ruta/UUID y esquema, reserva escritura, comprueba integridad y referencias, crea un respaldo SQLite consistente con SHA-256 y lo valida antes de cargar. Aplica en una transacción y verifica integridad; si falla el respaldo o la carga, no publica cambios parciales. Registra plan, hash y respaldo en auditoría. La repetición conserva datos funcionales; puede generar un nuevo respaldo/auditoría y consumir secuencias de adicionales por UPSERT. No se exige identidad byte a byte tras una aplicación.

SHA-256 del archivo entregado: `36bb753a5980a9fa445728ae13471e56b7325edea047e9e4b48a98eecff43486`.

## Matriz de aceptación automatizada

| Caso | Evidencia |
| --- | --- |
| 38 variantes, siete categorías, precios nuevos, cero inicial y dos adicionales | `test_composicion_precios_y_cero_stock` |
| SHA erróneo, CLI sin hash y reclasificación legacy bloqueados sin escritura | `test_comercial_hash_distinto_y_categoria_legacy_no_escriben`, `test_cli_comercial_no_aplica_sin_hash` |
| 1 a 5 postres, mismo sabor o combinación de tres sabores | seis casos `test_promo_tres_sabores` |
| Venta mixta con ambos adicionales, dos cajas, reintento UUID, anulación y stock | `test_adicionales_venta_mixta_idempotencia_devolucion_y_reinicio` |
| Vista previa sin escritura, bajas no vendibles, históricos/IDs/stock intactos, agotados e idempotencia | `test_actualizacion_desactiva_sin_borrar_historial` |
| Edge real: login, 38 variantes API, agrupación, Pepitos/Fugazzeta/Especial y aviso ficticio | `test_edge_catalogo_comercial` |
| Worker separado: venta promocionada, detener/arrancar y restaurar en otra carpeta temporal | `test_worker_catalogo_reinicio_backup_y_recuperacion` |
| Backup, WAL, corrupción, caída abrupta, rollback, restore, identidades y sesiones | suites `test_preproduccion*` |
| Premium y delivery: cobros, fiados, devoluciones, reparto, doble clic y contabilidad | regresión completa de #34, incluidas `test_lo_de_clau_delivery` y `test_lo_de_clau_edge` |

Los tests crean únicamente directorios temporales nuevos fuera de OneDrive y perfiles de Edge efímeros. Los conteos artificiales de 5/11 unidades están dentro de esos tests y jamás en el catálogo comercial. La CI incorpora el archivo nuevo en el job Windows/Edge.

## Guía de aceptación humana pendiente

1. Revisar la tabla de 38 variantes y las cinco hamburguesas; confirmar que Big Mac queda fuera del menú sin borrar ventas anteriores.
2. Revisar el plan del ensayo: tres altas, omisiones completas, IDs preservados, stock conservado y SHA del archivo. Ningún conteo inicial proviene del catálogo.
3. En un ensayo nuevo, revisar Pepitos chico/grande, Fugazzeta, Mozzarella y Especial. Comprobar agotados y unidades cero de bebidas/grandes. Registrar conteos ficticios sólo en ese ensayo si se necesita venderlos.
4. Vender dos chicos distintos por $5.000, tres por $8.000 y cuatro por $10.000; revisar el detalle del descuento y su devolución. Probar una comida con un cheddar y un huevo: recargo total $2.000.
5. Repetir cobro/doble clic, anular con motivo, consultar ambas cajas e históricos y exigir conciliación cuadrada. Probar retiro/delivery, su separación contable y entrega del envío según #34.
6. Detener y reiniciar el servidor de ensayo; recuperar un backup verificado en otra carpeta temporal y comparar catálogo, IDs, ventas, stock y saldos.
7. Registrar aceptación de la familia y revisión física táctil/reinicio del equipo. Estas comprobaciones manuales no se declaran realizadas por las pruebas automatizadas.

No ejecutar esos pasos sobre Entrenamiento o Preproducción instalados, ni usar dinero real. La aceptación no autoriza fusión ni despliegue: cualquier paso posterior se trata por separado.

## Reproducción segura de las pruebas

Desde esta rama, con dependencias existentes, PowerShell:

```powershell
$env:PYTHONUTF8 = '1'
$env:PYTHON_DOTENV_DISABLED = '1'
$env:POS_TEST_BROWSER = "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe"
python -m pytest -q
```

No se ejecuta el launcher instalado ni se pasan rutas persistentes. Los fixtures fijan bases temporales explícitas. El ensayo automatizado no requiere modificar ninguna instalación.

## Resultados de ejecución

Pruebas específicas del catálogo: **13 aprobadas**, incluidas API/SQLite, controles CLI/hash, Edge y worker real con reinicio y recuperación. Se repitieron las dos comprobaciones ampliadas de bajas y Edge después de agregar el control del adicional de práctica y la captura de escritorio. La regresión completa heredada está en ejecución; se actualizará este apartado con su resultado real.

Las primeras corridas de desarrollo detectaron errores en las pruebas nuevas (campo de descuento opcional, nombre de ruta de anulación y conteo de tarjetas agrupadas); se corrigieron sin cambiar el código contable ni la interfaz. La corrida restringida inicial se interrumpió porque el cliente de prueba quedó bloqueado; las verificaciones finales se ejecutan con conectividad local y Edge habilitados.
