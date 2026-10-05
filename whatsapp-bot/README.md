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
