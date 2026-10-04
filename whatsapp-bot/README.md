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
