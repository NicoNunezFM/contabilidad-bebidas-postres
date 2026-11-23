# Tablet y Entrenamiento: laboratorio HTTPS ficticio

## Estado y decisión del 23/11/2026

La demo estática del PR #19 tiene validación física **reportada** del recorrido
principal en PCBOX. No demuestra que el POS completo ejecute todo su JavaScript
en ese navegador, ni login, TLS, persistencia o asientos de caja.

Esta rama independiente prepara el primer POS conectado de laboratorio. Reutiliza
el router, las sesiones y la contabilidad de **Entrenamiento**, con una base
temporal nueva por ejecución. No usa la carpeta instalada ni acepta un argumento
para importar o seleccionar bases. El catálogo contiene solo Comida ficticia
($1.000), Bebida ficticia ($200), Postre ficticio ($300) y Extra ficticio ($100).

Se elige **TLS directo**, sin proxy: tablet → HTTPS/TLS 1.2 o superior → Uvicorn →
aplicación de Entrenamiento → SQLite temporal. Evita introducir confianza en
cabeceras reenviadas y permite conservar la comprobación de Origin del POS.
Un proxy/VPN entre redes requerirá otra etapa y pruebas propias; no se publica
ningún puerto del router. La implementación y pruebas de esta rama no inician
el laboratorio en LAN ni crean reglas de firewall.

Referencias de diseño: [TLS y cabeceras proxy en Uvicorn](https://uvicorn.dev/settings/)
y [validación de Host en Starlette](https://www.starlette.io/middleware/).
La configuración se comprobó con las versiones fijadas en requirements.txt.

## Aislamiento y controles

- `scripts/servir_tablet_https.py` crea un directorio temporal fuera de OneDrive
  y una base desde cero. Incorpora un marcador adicional que distingue el
  laboratorio del Entrenamiento instalado. Un marcador no certifica la procedencia
  de cualquier archivo: la garantía de este launcher es que no recibe archivos
  de base como entrada y solo crea su propio directorio nuevo.
- Contraseñas de al menos 12 caracteres, distintas para `tablet-ventas` y
  `tablet-admin`, solicitadas sin mostrarlas ni pasarlas como argumentos. Las
  credenciales públicas de Entrenamiento se sustituyen antes de servir.
- Contraseñas y sesiones conservan el hash y los permisos del POS. Cookies con
  nombres separados, `Secure`, `HttpOnly`, `SameSite=Strict` y ruta `/pos-api`.
  Máximo 10 intentos de login por dispositivo por minuto; se reinicia al detener.
- Bind por defecto `127.0.0.1`; solo IPv4 explícita de loopback o RFC1918.
  Sin `0.0.0.0`, comodines, rangos ni IP pública. En LAN exige `--allow` explícito.
  La IP es un filtro adicional; la autenticación sigue siendo obligatoria.
- HTTPS directo obligatorio, TLS mínimo 1.2, Host y puerto exactos, Origin exacto
  en escrituras. Se rechazan cabeceras Forwarded/X-Forwarded-*; `proxy_headers=False`.
  No existe listener ni redirección HTTP. No hay ruta alternativa de texto plano.
- Página y banderas de modo son públicas dentro del filtro de dispositivo. El
  endpoint `/pos-api/simulacion/estado` solo devuelve booleanos para que la pantalla
  se configure antes del login. Catálogo y demás API exigen sesión.
- Sin caché, sin acceso a rutas contables generales (`/caja`, `/comandos`), archivos
  de base, Swagger o bot. El router POS conserva sus permisos de ventas/admin.
- Aviso visible **LABORATORIO FICTICIO TEMPORAL - SIN VALIDEZ CONTABLE**.
  Al detener normalmente se eliminan las prácticas; un cierre abrupto podría
  dejar la carpeta temporal. No reutilizarla. No hay recuperación duradera.

El launcher existente `scripts/abadion_entrenamiento.py servir` sigue en HTTP
localhost y conserva su comportamiento. El POS agrega únicamente un reintento
de carga del catálogo tras iniciar sesión, necesario si el catálogo inicial recibió
401. Las reglas contables, dos cajas y WhatsApp no se modifican. No ejecutar el
laboratorio con la API general.

## Etapas y condiciones de avance

1. **Laboratorio local automatizado:** login, cookies, permisos, cajas separadas,
   idempotencia y transporte HTTPS en loopback. Certificados efímeros para tests.
2. **Confianza en el dispositivo físico:** preparar certificado y cadena para la
   IP privada actual de la PC (SAN de tipo IP, no solo Common Name); verificar
   vigencia, fecha de PC/tablet, huella y confianza en el navegador integrado.
   Mantener la clave privada en la PC, fuera de Git/OneDrive. Si se utiliza una CA
   local, trasladar únicamente su certificado público por un canal verificado y
   retirarlo de la tablet tras la prueba. Su compatibilidad sigue pendiente.
3. **Prueba física conectada:** usar únicamente este launcher y catálogo ficticio,
   red controlada y acceso acotado. No usar advertencias ignoradas, excepciones de
   certificado, HTTP o reducción de versión TLS para hacerla funcionar.
4. **Persistencia de práctica futura:** después de superar la etapa anterior,
   diseñar instalación ficticia durable con credenciales propias, revocación,
   respaldo consistente y cierre de caja. Todavía no conectar el Entrenamiento
   instalado ni el negocio real. Acceso entre redes mediante VPN queda aparte.

La obtención e instalación de un certificado confiable **no se automatiza ni se
realiza en este trabajo**. Esta rama ofrece un launcher preparado para recibir
certificado/clave, no una instalación de tablet completada.

## Guía para la siguiente prueba física

Primero comprobar en Edge que el certificado es confiable, vigente y cubre la IP
actual de la PC. Confirmar lo mismo en la PCBOX antes de escribir una contraseña.
No reutilizar automáticamente las IP históricas de la demo. Registrar versión
real del navegador/WebView y fecha/hora del dispositivo.

Desde la carpeta de la rama, con las dependencias del proyecto instaladas y el
servidor de demo anterior detenido, reemplazar los valores entre corchetes:

```powershell
$env:PYTHON_DOTENV_DISABLED = '1'
python scripts/servir_tablet_https.py --cert "[CERTIFICADO_PEM]" --key "[CLAVE_PRIVADA_PEM]"
```

Ese primer comando escucha únicamente en loopback (puerto 8460). Abrir
`https://127.0.0.1:8460/pos/?tablet=1`; el certificado debe cubrir también loopback.
Ingresar con `tablet-ventas` y la contraseña nueva elegida en consola.

Para la prueba física posterior, detener con Ctrl+C y volver a iniciar con
direcciones verificadas (se creará otra base vacía y se pedirán contraseñas nuevas):

```powershell
python scripts/servir_tablet_https.py --bind "[IP_PRIVADA_PC]" --allow "[IP_TABLET_OBSERVADA]" --cert "[CERTIFICADO_PEM]" --key "[CLAVE_PRIVADA_PEM]"
```

Solo se prevé HTTPS 8460. Si se necesita habilitar acceso de Windows, limitarlo
al puerto, perfil de red y origen de prueba; no abrir router ni FastAPI HTTP.
No se realizó ese cambio en este trabajo. El firewall y la red deben estar bajo
control antes de usar la opción LAN. No quitar `--allow` para resolver un 403.

Recorrido de aceptación (repetir horizontal y vertical):

1. Abrir `https://[IP_PRIVADA_PC]:8460/pos/?tablet=1` sin advertencias TLS y
   comprobar el aviso de laboratorio. Registrar commit y huella del certificado.
2. Ingresar como `tablet-ventas`; confirmar que solo aparecen los tres productos
   ficticios del laboratorio. Si no aparece el aviso o catálogo, detener la prueba.
3. Abrir **Caja diaria** y dar apertura ficticia de $0 a ambas cajas.
4. Agregar una comida, una bebida y un postre, sin extras. Validar: comidas $1.000,
   bebidas/postres $500, total $1.500. Confirmar una única venta en efectivo.
5. Comprobar en historial que hay una sola venta y que las cajas reflejan $1.000
   y $500 respectivamente. Recargar la página y verificar historial/caja de nuevo:
   SQLite se conserva durante esa ejecución. No confundir esto con conservar carrito.
6. Probar un pedido con Extra ficticio; confirmar diferencia de $100 antes de
   cobrar. Probar cancelar, cambiar orientación y volver al catálogo.
7. Cerrar sesión; verificar que no se puede consultar catálogo ni operar sin login.
   Si se revisan opciones de administrador, usar `tablet-admin` y su otra clave.
8. Registrar esperado/observado, paso exacto, orientación y capturas sin contraseñas
   ni cookies. No medir ni declarar rendimiento sin mediciones propias.
9. Detener con Ctrl+C y cerrar el acceso temporal usado. Al reiniciar no deben
   existir ventas previas; no sustituir esa base por una copia de datos reales.

## Cómo repetir las pruebas automáticas

Ejecuciones locales del 23/11/2026:

- Suite completa: **300 aprobadas, 14 omitidas** (sin configurar navegador).
- Selección `test_pos_web.py`, `test_demo_tablet.py`, `test_tablet_https.py` con
  Microsoft Edge: **31 aprobadas**. Incluye login HTTPS/catálogo/logout en
  1024×600 y 600×1024; no equivale a una ejecución en Android.
- Venta ficticia por API: separación de cajas y reintento sin duplicación;
  rechazo de credenciales públicas, rol de ventas/admin y cierre de sesión.
- Transporte TLS real en loopback: certificado de test verificado por httpx,
  rechazo sin confianza y rechazo de HTTP al mismo puerto.
- Repetición final de `test_tablet_https.py`: **17 aprobadas**, con un archivo
  `negocio.db` ficticio de control que permanece byte a byte intacto en cada caso.
- Sintaxis de WhatsApp (`node --check`), regeneración de demo sin diferencias
  y revisión de espacios (`git diff --check`) correctas.
- Persisten dos advertencias previas por `on_event` de FastAPI; no son errores.

Estas ejecuciones locales no certifican la instalación de una CA ni la
compatibilidad TLS/JavaScript del navegador integrado de PCBOX. La CI del nuevo
PR se informa separadamente; no se presupone su resultado.

```powershell
$env:PYTHONUTF8 = '1'
$env:PYTHON_DOTENV_DISABLED = '1'
python -m pip install -r requirements-tablet-test.txt
python -m pytest -q
$env:POS_TEST_BROWSER = "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe"
python -m pytest -q tests/test_pos_web.py tests/test_demo_tablet.py tests/test_tablet_https.py
```

Los tests HTTPS generan certificado/clave de una hora en directorios temporales.
httpx verifica cadena y SAN con ese certificado; una petición sin esa confianza y
una petición HTTP al puerto TLS deben fallar. Edge usa exclusivamente una excepción
SPKI para la clave efímera del test en su perfil temporal; **esto no demuestra
confianza de certificados en PCBOX** ni autoriza excepciones en la prueba física.
No se instala una CA en Windows y no se usa `verify=False`.

Los PR #18, #19 y el de este laboratorio deben permanecer en borrador, sin merge
ni despliegue. La aprobación física de la demo no habilita producción.
