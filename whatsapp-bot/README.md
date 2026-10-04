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
