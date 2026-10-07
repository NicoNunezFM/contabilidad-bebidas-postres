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

Las ventas nuevas guardan un snapshot del costo al momento de vender. Las ventas anteriores a esta funcionalidad quedan sin costo congelado y se reportan como historial incompleto. Los adicionales todavía no tienen costo propio modelado.

El comando `stock insumos` también muestra equivalencias aproximadas en paquetes cuando el insumo tiene presentaciones configuradas. Por ejemplo, 354 g de Oreo equivalen a 3 paquetes de 118 g o 1 tripack de 354 g.


### Costo congelado por venta

Cada venta nueva de Bebidas y Postres guarda el costo unitario disponible en ese momento.

Para bebidas, el snapshot usa el promedio ponderado de las últimas compras vigentes del producto. Para postres, usa el costo de la última producción registrada o, si todavía no hubo producción, la mejor estimación disponible de la receta actual.

Esto permite que una compra o producción posterior cambie el costo actual sin modificar la rentabilidad histórica de ventas anteriores.

Las ventas registradas antes de esta funcionalidad quedan sin snapshot y se informan como historial incompleto. No se reconstruye su costo automáticamente porque hacerlo con precios actuales produciría una falsa precisión.

Los adicionales vendidos junto con un producto todavía no tienen costo propio modelado. Si una venta incluye adicionales, su rentabilidad histórica se marca como no exacta hasta que exista un catálogo de costos para esos adicionales.


## Adicionales configurables

Los adicionales pueden tener precio de venta y costo unitario configurados.

Ejemplos:

```text
adicionales
adicional huevo precio 1000 costo 300
adicional cheddar precio 1200 costo 450
```

Si el precio está configurado, una venta puede escribirse sin repetirlo:

```text
venta 1 sanguche grande con 2 huevos
```

Abadion calcula el precio total del adicional y guarda también su costo unitario como snapshot histórico. Si se informa un precio explícito en la venta, ese precio pisa el precio configurado, pero el costo sigue tomándose del catálogo.

Los adicionales conocidos se crean inicialmente sin inventar precios ni costos: huevo, cheddar, doble porción y extra papa. Hasta que se configuren, Abadion sigue pidiendo el precio explícito.


## Deudas del negocio

El módulo de deudas registra saldos de tarjetas o cuentas utilizadas para financiar reposición del negocio.

Carga inicial:

```text
saldo inicial deuda naranja 100000
saldo inicial deuda bbva 50000
```

Consultas:

```text
deudas negocio
deuda naranja
cuanto falta pagar de naranja
historial deuda naranja
que deuda vence primero
```

Movimientos:

```text
compra deuda naranja 25000 reposicion bebidas
pago deuda naranja 30000
pagamos 30000 de naranja
ajustar deuda naranja 85000
vencimiento deuda naranja 2026-10-20
```

Un pago de deuda se registra también como retiro de caja del negocio. El saldo inicial no afecta caja porque representa deuda existente antes de comenzar el seguimiento.

Las compras de packs pueden financiarse directamente:

```text
compra 2 packs manaos cola por 17000 con naranja
compra 1 pack manaos cola chica a 8500 cada pack con tarjeta bbva
```

En una compra financiada, el stock aumenta y la deuda aumenta, pero la compra no se descuenta de caja en ese momento. La salida de caja ocurre cuando se registra el pago de la deuda.


### Dinero reservado para deudas

Una reserva representa dinero que ya está apartado para pagar una deuda, pero que todavía no fue enviado a la tarjeta o acreedor.

Ejemplos:

```text
reservar deuda naranja 100000
liberar reserva deuda naranja 20000
deuda naranja
deudas negocio
```

La reserva no reduce el saldo de la deuda y no genera una salida física de caja. Sí reduce el saldo disponible, porque ese dinero deja de estar libre para otros usos.

Cuando se registra el pago:

```text
pago deuda naranja 30000
```

Abadion aplica automáticamente hasta $30.000 de la reserva existente. La deuda baja, la caja física baja y la reserva baja por el mismo importe. De esta forma el saldo disponible no se descuenta dos veces.

Ejemplo de estado:

```text
Deuda pendiente: $389.547,18
Reservado: $100.000,00
Todavía por cubrir: $289.547,18
```

Los importes de deuda aceptan centavos con formato argentino, por ejemplo `389.547,18`.


## Movimientos manuales de caja

Los aportes y retiros pueden registrarse directamente desde WhatsApp.

Ejemplos:

```text
aporte 100000
aporte 100000 dinero recibido para pagar deuda naranja
retiro 25000 compra personal
```

Un aporte aumenta la caja física y disponible. Un retiro la reduce.

Si después se reserva parte del dinero para una deuda:

```text
reservar deuda naranja 100000
```

el dinero sigue físicamente en caja, pero deja de contarse como disponible. El comando `caja` muestra también el total reservado para deudas.


## Importación automática desde Naranja por Gmail

La integración con Gmail usa OAuth de solo lectura y únicamente genera deuda automática cuando el aviso de compra identifica:

```text
Adicional - Claudia Elizabet Rotondo
```

Los avisos de la tarjeta titular de Sergio no se cargan como deuda del negocio.

El flujo es:

```text
Gmail -> parser Naranja -> importaciones_deuda
      -> movimiento deuda Naranja
      -> pendiente_clasificacion
```

La importación no aumenta stock ni registra un gasto. La clasificación posterior deberá reutilizar el `id_movimiento_deuda` ya generado para evitar duplicar la deuda.

Cada correo se identifica por la combinación `fuente + id_externo`, por lo que el mismo mensaje de Gmail no puede aumentar la deuda dos veces.

Antes de activar la sincronización hay que definir una fecha/hora de corte. Esto evita volver a sumar consumos que ya estaban incluidos en el saldo inicial:

```env
NARANJA_IMPORTAR_DESDE=2026-10-07T17:30:00
GMAIL_CREDENTIALS_PATH=gmail_credentials.json
GMAIL_TOKEN_PATH=gmail_token.json
```

Las credenciales OAuth y el token están excluidos de Git.

Para instalar las dependencias:

```powershell
pip install -r requirements.txt
```

Para ejecutar una sincronización manual inicial:

```powershell
python src/gmail_naranja.py
```

La primera autorización abre el flujo OAuth de Google. El scope utilizado es exclusivamente `gmail.readonly`.

Los correos anteriores al corte pueden guardarse como históricos sin aumentar la deuda. Compras en otra moneda quedan en revisión y tampoco modifican automáticamente el saldo.


### Consultar compras Naranja pendientes

Los avisos de la tarjeta adicional que ya aumentaron la deuda, pero todavía no fueron clasificados, pueden consultarse desde WhatsApp:

```text
compras naranja pendientes
pendientes naranja
```

La respuesta muestra el ID de importación, importe, comercio, fecha y el movimiento de deuda asociado.

Para ver una importación puntual:

```text
importacion 7
```

Esta consulta es solo informativa. Todavía no modifica stock, gastos ni compras. La clasificación posterior reutilizará el movimiento de deuda existente para no aumentar Naranja por segunda vez.


### Conversaciones normales dentro del grupo

Por defecto, Abadion no responde en grupos cuando la API devuelve `COMANDO_NO_RECONOCIDO`. Esto permite conversar normalmente en el grupo sin que el bot responda a frases como `hoy`, `sí`, preguntas entre personas u otros mensajes que no sean comandos.

La opción se controla con:

```env
SILENT_UNKNOWN_GROUP_MESSAGES=true
```

Los comandos válidos y los errores de comandos reconocidos siguen respondiéndose normalmente. En chats privados autorizados, el comportamiento de ayuda para comandos no reconocidos se mantiene.
