# Abadion POS · Adaptación de pantalla táctil 7" y Chrome 101

## Alcance y base

Este trabajo parte del PR #17, commit `8a4906f0e7d5573efccd3c0004397c80dfc77c70`.
No agrega un servidor LAN ni modifica la base de datos, los cobros, el bot de WhatsApp o las migraciones.

La tablet de prueba es PCBOX PCB-T715, Android 6.0.1, Chrome 101. La PC y la tablet se comunicaron en una red de invitados; el servidor HTTP de demostración anterior devolvía 403 porque la tablet aparecía ante la PC como `172.18.66.184`, aunque mostraba una dirección diferente en su configuración.

## Interfaz

- En navegadores Android (o mediante `?tablet=1` durante pruebas) con viewport de hasta 1100 px, el catálogo ocupa el área principal y se muestra un control persistente **Ver carrito y cobro**. El diseño de Windows/Edge no cambia aunque la ventana sea estrecha.
- El control es un `label` asociado a una casilla HTML y alterna entre catálogo y carrito mediante CSS, incluso si el JavaScript principal no llega a ejecutarse en un navegador antiguo. No destruye el contenido del carrito ni afecta los diálogos.
- Categorías y operaciones permiten desplazamiento horizontal. Se amplían los botones para uso táctil.
- El POS de escritorio permanece con el diseño existente; los estilos nuevos se activan por media query de pantalla táctil.
- En Entrenamiento, el banner permanece visible sin forzar la barra lateral fija en pantalla táctil.

## Compatibilidad y seguridad

- `senalTiempoPos` utiliza `AbortSignal.timeout` cuando existe y `AbortController` con un temporizador cuando no existe (Chrome 101).
- `uuidPos` usa `crypto.randomUUID` si está disponible; de lo contrario genera UUID v4 mediante `crypto.getRandomValues`. No utiliza `Math.random`.
- **En una URL HTTP de red LAN, las operaciones siguen bloqueadas:** `uuidPos` exige `window.isSecureContext`. Una página de demostración no equivale al servidor FastAPI real.
- El servidor de Entrenamiento conserva `127.0.0.1` como bind y `TrustedHostMiddleware` restringido. No se creó ningún punto de exposición adicional.
- Android 6 y Chrome 101 están obsoletos y no deben usarse para datos financieros reales ni en redes que no estén bajo control.

## Pruebas automáticas

`python -m pytest -q tests/test_pos_tablet_compat.py` valida estructura de interfaz, presencia de controles, código JavaScript, generación de UUID, bloqueo fuera de un contexto seguro y respaldo de timeout. En CI se ejecuta junto con toda la suite Python.

Microsoft Edge prueba además la alternancia nativa del carrito en el modo de tablet; estas pruebas no reemplazan la validación en el dispositivo físico ni garantizan que el motor obsoleto ejecute el JavaScript del POS.

## Verificación manual sin backend

1. Detener la demostración anterior del puerto 8765 con `Ctrl+C`.
2. Mantener la regla de firewall temporal cerrada al terminar; no exponer el POS real.
3. Utilizar una página **estática aislada** que sirva solamente `pos-web/index.html` desde la rama y puerto de prueba. La API y operaciones de escritura deben continuar deshabilitadas.
4. En la tablet horizontal, comprobar tres columnas de productos si el viewport lo permite, categorías desplazables y botón **Ver carrito y cobro**.
5. Alternar carrito y catálogo varias veces; comprobar que se conserva el contenido del carrito y que los botones y modales no se superponen.
6. Comprobar también en vertical y revisar la legibilidad y rendimiento de la pantalla de 7 pulgadas.

## Etapa posterior: acceso operativo

Requiere diseñar y probar un canal HTTPS cifrado y autenticado desde la tablet a la PC, con certificado confiable para Chrome 101, restricción de red/receptor, firewall acotado, control de origen y sesiones y sin exponer HTTP FastAPI a la red de invitados. No usar una allowlist de IP traducida por el router como única autenticación.

Antes de instalar en Entrenamiento: backup consistente de la carpeta `%LOCALAPPDATA%\Abadion\Entrenamiento`, pruebas CI verdes y ensayos en copias ficticias. Para uso desde otra red o desde casa: estudiar VPN de acceso privado; no publicar puertos de Abadion a Internet.

## Pendientes

- Validar físicamente el diseño táctil en la PCBOX y ajustar si algo no cabe.
- Probar en Chrome 101 con **HTTPS confiable** el inicio de sesión y operaciones ficticias de extremo a extremo.
- Definir topología final del servidor en casa, acceso privado entre redes y mantenimiento de la PC encendida.
- Conservar el PR en borrador hasta estas validaciones; no activar producción.
