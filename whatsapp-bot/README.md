# Bot de WhatsApp - Lo de Clau

Este módulo conecta WhatsApp con la API Python del proyecto.

## Flujo actual

WhatsApp -> `whatsapp-web.js` -> `POST /comandos` -> Python -> SQLite -> respuesta a WhatsApp.

La interpretación con IA se agregará después sin cambiar la lógica de negocio.

## Requisitos

- Node.js 18 o superior.
- API Python funcionando.
- Un número autorizado en `.env`.

## Instalación

Desde esta carpeta:

```powershell
npm install
```

Copiar `.env.example` a `.env` y completar `ALLOWED_NUMBERS`.

Luego iniciar:

```powershell
npm start
```

La primera vez aparecerá un QR. Escanearlo desde:

WhatsApp -> Dispositivos vinculados -> Vincular un dispositivo.

La sesión queda almacenada localmente mediante `LocalAuth`, por lo que normalmente no hay que escanear el QR en cada inicio.

## Seguridad inicial

- Los números no incluidos en `ALLOWED_NUMBERS` son ignorados.
- Los grupos están deshabilitados por defecto.
- Los mensajes duplicados se ignoran mientras el proceso está encendido.
- Los archivos de sesión y `.env` no deben subirse a Git.

## Si el mensaje llega a WhatsApp pero el bot no responde

Con `DEBUG_MESSAGES=true`, la terminal muestra el identificador recibido, el número resuelto y el motivo si el mensaje fue ignorado. Algunas cuentas nuevas de WhatsApp usan IDs `@lid`; el bot intenta convertirlos al número telefónico antes de aplicar la lista blanca.

Si aparece `Remitente no autorizado`, copiá el número que figura como `Número resuelto` a `ALLOWED_NUMBERS` y reiniciá el bot.


## Protección contra mensajes duplicados

El bot envía a la API el ID único de cada mensaje de WhatsApp. La API lo guarda en SQLite antes de ejecutar el comando y conserva la respuesta final. Si el mismo mensaje vuelve a llegar después de reiniciar Node, la API devuelve la respuesta guardada sin repetir la venta, merma, consumo o anulación.

## Corrección de ventas

Las ventas se agrupan por operación. Desde WhatsApp se puede usar:

```text
anular ultima venta
anular operacion 14
```

La anulación marca todas las líneas de la operación como anuladas y devuelve al stock los productos inventariables. Las ventas anuladas dejan de participar en los totales de caja y reportes.


## Uso en grupo

El flujo previsto para Lo de Clau es usar el bot dentro de un grupo específico.

1. Crear el grupo y agregar la cuenta de WhatsApp vinculada al bot.
2. Dejar `DEBUG_MESSAGES=true`.
3. Enviar `menu` dentro del grupo.
4. La terminal mostrará un valor `from` terminado en `@g.us`.
5. Copiar ese ID completo a `ALLOWED_GROUP_IDS`.
6. Configurar `ALLOW_GROUPS=true` y reiniciar el bot.

Ejemplo:

```env
ALLOW_GROUPS=true
ALLOWED_GROUP_IDS=1234567890-1234567890@g.us
```

Por seguridad, si `ALLOW_GROUPS=true` pero `ALLOWED_GROUP_IDS` está vacío, el bot ignora todos los grupos.

Dentro de un grupo autorizado, cualquier integrante del grupo puede usar el bot. En chats privados se sigue aplicando `ALLOWED_NUMBERS`.

## Menú de WhatsApp

Enviar:

```text
menu
```

devuelve un menú numerado con consultas y movimientos frecuentes.

Para elegir una opción:

```text
opcion 1
```

Las opciones de consulta, como stock, precios o caja, se ejecutan directamente. Las opciones que modifican datos muestran primero el formato que debe escribirse, por ejemplo cómo registrar una venta o una merma.


## Bienvenida de Abadion

Cuando `SEND_GROUP_WELCOME=true`, el bot envía automáticamente una presentación breve de Abadion a cada grupo incluido en `ALLOWED_GROUP_IDS`.

El mensaje es:

```text
Bienvenidos a Abadion.

Desde este grupo, Abadion va a centralizar la gestión de Lo de Clau: ventas, stock, caja, movimientos y consultas.

Pueden interactuar directamente con el sistema escribiendo los comandos disponibles.

Para empezar, escriban menu.
```

La bienvenida se envía una sola vez por grupo. El estado queda almacenado localmente en `.welcome_state.json`, por lo que no vuelve a enviarse aunque Node o la PC se reinicien.

La bienvenida nunca se envía en chats privados ni en grupos que no estén autorizados.


## Auditoría y seguridad de ventas

Los comandos enviados desde WhatsApp incluyen información de origen para que las operaciones puedan auditarse. Las ventas guardan el canal, operador, grupo e ID del mensaje que las originó.

Las respuestas de venta muestran el número de operación:

```text
Operación: #123
```

En un grupo, `anular ultima venta` busca la última venta activa registrada por la misma persona que envía el comando. Esto evita que una persona anule accidentalmente la venta más reciente de otro integrante.

La anulación también registra quién la realizó y qué mensaje de WhatsApp la solicitó.

## Backups automáticos

Al iniciar FastAPI, Abadion crea como máximo un backup diario de SQLite en la carpeta `backups/`.

Los backups se crean usando la API de backup de SQLite y se conservan los últimos 14 archivos diarios. La carpeta queda excluida de Git.

## Comandos interrumpidos

Si un mensaje queda marcado como `Procesando` durante más de cinco minutos por un cierre inesperado, Abadion no lo ejecuta nuevamente de forma automática. Lo marca como `Requiere_revision` para evitar duplicar ventas o movimientos.


## Lenguaje real del grupo

Abadion admite atajos frecuentes del grupo además de los comandos formales.

Reglas actuales:

- `hamburguesa simple` -> `Clasica simple`
- `hamburguesa doble` -> `Clasica doble`
- `napo` -> `Napo de pollo con fritas`
- `postre` no se adivina: pregunta Oreo o Chocotorta
- `mila` asume guarnición de fritas, pero si no se indica pollo/carne mantiene la ambigüedad
- `manaos <sabor>` sin tamaño -> botella 2.25 l
- `sanguche chico` -> chico de pollo con papas
- `sanguche grande` -> grande de pollo con papas

También reconoce precios abreviados como `1 de 6`, `5x8` o `5x8 y 2x7`. Un número menor a 100 en este formato se interpreta en miles. La venta solo se registra si el precio identifica un producto de forma unívoca; en caso contrario Abadion pide aclaración.

### Contexto temporal

Los encabezados `Gastos`, `Postres`, `Bebidas` y `Comida` activan un contexto por operador y grupo durante 15 minutos.

Ejemplo:

```text
Gastos
Verdulería 9000
Carne 20000
Total gastado 29000
```

Las dos líneas intermedias se registran como gastos. La línea de total se reconoce como comprobación y no se registra nuevamente.

Los mensajes multilínea con el mismo formato también se procesan respetando el encabezado.


## Compras por pack

Las Manaos grandes de 2.25 l usan 6 unidades por pack.
Las Manaos chicas de 600 ml usan 12 unidades por pack.

Ejemplos:

```text
compra 2 packs manaos cola por 17000
compra 1 pack manaos cola chica a 8500 cada pack
```

En el primer caso se agregan 12 botellas grandes al stock.
En el segundo se agregan 12 botellas chicas.

`por` indica el costo total de la compra.
`a` indica el precio de cada pack.

El costo es obligatorio para una compra, porque también debe quedar correctamente registrado en compras y caja. Si solo se quiere corregir el conteo físico, se usa `inventario <producto> <cantidad real>`.


## Cajas por sección

Abadion mantiene dos vistas virtuales de caja:

- Bebidas + Postres.
- Comidas, que por ahora agrupa todas las demás categorías.

Comandos:

```text
caja bebidas postres
caja comidas
recaudado bebidas
recaudado postres
recaudado comidas
```

También entiende consultas como:

```text
cuanta plata recaude en bebidas
ventas postres
```

La caja Bebidas + Postres muestra por separado cuánto se recaudó en bebidas y cuánto en postres, además del total de ventas, compras directas y saldo operativo.

Las cajas se calculan a partir de la categoría de cada producto, por lo que también separan ventas históricas ya registradas. Las compras vinculadas a productos se descuentan de la sección correspondiente.

Por ahora los gastos generales no tienen sección asignada y continúan apareciendo únicamente en la caja general. Por ese motivo el valor de cada caja de sección se denomina saldo operativo y no saldo final. El siguiente paso será permitir gastos asociados a Bebidas + Postres o Comidas.


## Costos y recetas de postres

Abadion guarda un historial de insumos de postres con cantidad comprada, costo y comercio. Cada compra detallada se registra también como gasto de la caja Bebidas + Postres.

Ejemplos:

```text
insumo galletitas oreo 700 g 7000 Carrefour
insumo dulce de leche 1 kg 11000 Carrefour
gasto postres crema de leche 500 ml 5000 en Carrefour
```

También se pueden registrar gastos generales de postres sin desglose:

```text
gasto postres Carrefour 20000
```

Un gasto general queda en el historial y en la caja de Bebidas + Postres, pero no se usa para calcular el costo de una receta porque no informa qué cantidad de cada insumo se compró. No conviene registrar el mismo ticket como gasto general y además volver a cargar todas sus líneas como insumos, porque duplicaría el egreso.

Consultas disponibles:

```text
historial gastos postres
receta oreo
receta chocotorta
costo 10 oreos
cuanto me vale hacer 10 oreos
```

El costo estimado usa el promedio ponderado de las últimas 3 compras de cada insumo y escala la receta según la cantidad solicitada. Si falta historial de precio de algún ingrediente, Abadion muestra un costo parcial y detalla los insumos faltantes.

Las recetas se guardan versionadas en SQLite. La versión base actual mantiene el rendimiento de 10 postres y el costo fijo de elaboración de $500 por postre definido para el proyecto.


### Recetas actuales

Las recetas activas son versión 2 y rinden aproximadamente 10 unidades.

**Oreo**

- 700 g de galletitas Oreo para el armado.
- 100 g extra de Oreo para decoración.
- 900 g de dulce de leche.
- 600 ml de crema de leche.
- 300 ml de leche.
- 10 potes.

Equivale por unidad a aproximadamente 70 g de Oreo base + 10 g de decoración, 90 g de dulce de leche, 60 ml de crema, 30 ml de leche y 1 pote.

**Chocotorta**

- 1100 g de Chocolinas.
- 500 g de dulce de leche.
- 500 g de queso crema.
- 900 ml de café con leche preparado.
- 10 potes.

El armado de una unidad se toma como 45 g de Chocolinas + 45 ml de café + 50 g de relleno, otra capa igual y 20 g finales de Chocolinas.

Los ingredientes usados "a ojo", como azúcar impalpable o cantidades adicionales para humedecer, quedan anotados pero no se incluyen numéricamente en el costo hasta medir su consumo.

El pote forma parte del costo de receta, pero Abadion no reutiliza el precio viejo de planillas históricas. Para que entre en el cálculo hay que cargar una compra actual, por ejemplo:

```text
insumo pote 100 unidades 35000 Papelera
```

Las recetas versión 1 permanecen guardadas como historial pero quedan inactivas.


## Producción de postres

La producción conecta receta, costos históricos y stock del postre terminado.

Ejemplos:

```text
produccion 10 oreo
produccion 10 chocotorta
historial produccion
```

Al registrar una producción, Abadion:

1. Busca la receta activa y su versión.
2. Calcula las cantidades teóricas necesarias para la tanda.
3. Calcula el costo estimado usando el promedio ponderado de las últimas 3 compras de cada insumo.
4. Guarda una fotografía de esos costos en la producción, para que los cambios de precio futuros no modifiquen el costo histórico de la tanda.
5. Guarda el detalle de insumos consumidos teóricamente.
6. Aumenta el stock del postre terminado.

Una producción no genera otro gasto de caja. Los egresos ya fueron registrados cuando se compraron los insumos.

Por seguridad, si falta el precio histórico de algún insumo, la producción no se registra y el stock del postre no cambia. Primero deben cargarse los costos faltantes.

Ejemplo de respuesta:

```text
Producción registrada
Producción: #12
10 x Oreo
Receta: v2
Costo de insumos: $26.300
Costo de elaboración: $5.000
Costo total estimado: $31.300
Costo por unidad: $3.130
Stock Oreo: 4 -> 14
```

La producción valida el stock físico de materias primas antes de registrar la tanda. Si falta cualquier insumo inventariable, no descuenta nada y tampoco aumenta el stock del postre terminado. Si alcanza, descuenta los insumos y aumenta el stock del postre dentro de la misma transacción.


### Galletitas compradas por paquete

Las galletitas se compran por paquete, pero las recetas consumen gramos. Abadion convierte automáticamente la presentación comprada a gramos para el historial de costos.

Presentaciones configuradas:

- Oreo: 118 g, x4 de 258 g y tripack de 354 g.
- Chocolinas: 170 g y 250 g.

Ejemplos:

```text
insumo oreo 3 paquetes 118g 4288 Carrefour
insumo oreo 1 pack x4 3406 Carrefour
insumo chocolinas 4 paquetes 250g 12000 Carrefour
insumo chocolinas 2 paquetes 170g 3000 Carrefour
```

Ejemplo de conversión:

```text
3 paquetes de Oreo de 118 g
= 354 g ingresados al historial de insumos
```

El precio queda asociado al total comprado y Abadion calcula el costo por gramo para las recetas.

Como hay más de una presentación de Oreo y Chocolinas, el tamaño debe indicarse en el mensaje. Abadion no supone un peso de paquete si puede haber más de una presentación.


## Stock físico de insumos

Las compras detalladas de materias primas ahora también alimentan el stock físico.

Ejemplos:

```text
insumo oreo 3 paquetes 118g 4288 Carrefour
insumo dulce de leche 2 kg 10000 Carrefour
insumo pote 100 unidades 35000 Papelera
```

Las galletitas se compran por paquete, pero el stock se conserva en gramos para poder descontar exactamente lo que usa la receta.

Consultas:

```text
stock insumos
que necesito para hacer 20 oreos
```

Corrección por conteo físico:

```text
inventario insumo oreo 1350g
inventario insumo dulce de leche 2.4kg
inventario insumo pote 37 unidades
```

`inventario insumo` fija el stock a la cantidad real contada y guarda un ajuste auditado; no suma esa cantidad.

Al registrar una producción, Abadion valida todos los insumos antes de modificar existencias. Si alguno no alcanza, la operación completa se rechaza.

`Café con leche preparado` se considera una preparación interna y no controla stock físico. Continúa formando parte de la receta de Chocotorta para el cálculo de cantidad/costo, pero no se trata como una materia prima almacenada.


## Rentabilidad de bebidas y postres

Abadion puede consultar rentabilidad actual de productos y categorías.

Ejemplos:

```text
rentabilidad oreo
ganancia chocotorta
rentabilidad bebidas
rentabilidad postres
rentabilidad bebidas postres
```

Para bebidas, el costo unitario se estima con el promedio ponderado de las últimas 3 compras no anuladas del producto.

Para postres, se usa primero el costo unitario de la última producción registrada. Si todavía no hubo producción, se intenta estimar el costo con la receta activa y los precios históricos de insumos.

La respuesta por producto incluye:

- precio de venta;
- costo unitario estimado;
- ganancia bruta por unidad;
- margen sobre venta;
- markup sobre costo;
- unidades vendidas e ingresos registrados;
- costo de ventas y ganancia bruta histórica estimados.

La ganancia histórica todavía es una estimación: las ventas actuales no guardan un snapshot del costo al momento exacto de la venta. Por eso se utiliza el mejor costo actual disponible. Una etapa posterior puede congelar el costo por venta para obtener rentabilidad histórica contable más precisa.

El comando `stock insumos` también muestra equivalencias aproximadas en paquetes cuando el insumo tiene presentaciones configuradas. Por ejemplo, 354 g de Oreo equivalen a 3 paquetes de 118 g o 1 tripack de 354 g.
