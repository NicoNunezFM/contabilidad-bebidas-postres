# POS ficticio remoto con Cloudflare Access

## Requisitos y estado

El PR #21 incorpora un laboratorio para un túnel administrado. El servidor
escucha en `127.0.0.1:8461`, crea SQLite temporal desde cero y exige un JWT
de usuario de la aplicación Access en cada solicitud. El launcher HTTPS
directo del PR #20 sigue disponible en su puerto habitual. El túnel, la
cuenta y DNS deben ser configurados por su titular. En este trabajo no se
crearon recursos en Cloudflare ni se conectó una PCBOX.

Se requiere una cuenta, una organización Zero Trust, un dominio activo en
Cloudflare bajo el control del titular y un subdominio dedicado de primer
nivel, por ejemplo `pos-lab.example.com`. La activación de Zero Trust puede
pedir un medio de pago incluso al elegir Free. Access Free cubre hasta 50
usuarios por USD 0. El registro y la renovación de un dominio nuevo dependen
del TLD y el registrador. Si ya existe un dominio elegible, el subdominio puede
reutilizarlo. No se compró ni se confirmó titularidad de ningún dominio.

- [Configuración de Zero Trust](https://developers.cloudflare.com/learning-paths/cybersafe/account-creation/create-zero-trust-org/)
- [Publicación de una aplicación HTTP con Access](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/self-hosted-public-app/)
- [Precios Zero Trust](https://www.cloudflare.com/plans/zero-trust-services/)

La PCBOX usa únicamente navegador. Debe confiar en las cadenas TLS del
subdominio y del equipo Access, aceptar cookies y completar el OTP y el
login POS. Universal SSL requiere SNI y en Free requiere ECDSA. Cloudflare
documenta que la cadena actual de Let's Encrypt puede fallar en Android 7.0
y anteriores. Cuando esté disponible, evaluar una cadena compatible como
Google Trust Services. La prueba previa del PIN de Quick Tunnel en esa
PCBOX no verifica este hostname, el flujo de Access ni el JavaScript del POS.
Si hay una alerta TLS, bucle de login o falla del carrito, detener la prueba
y registrar versión del navegador y paso exacto. Mantener validación TLS normal.

- [Compatibilidad TLS](https://developers.cloudflare.com/ssl/reference/browser-compatibility/)
- [Cadenas y dispositivos antiguos](https://developers.cloudflare.com/ssl/troubleshooting/general-ssl-errors/)

## Configuración en Cloudflare

1. Activar la zona DNS del dominio y comprobar que el certificado de borde
   esté activo. Crear la organización Zero Trust y anotar el nombre del equipo.
2. En Zero Trust → Access controls → Applications, crear una aplicación
   **Self-hosted** para el hostname exacto, sin filtro de ruta, de modo que
   cubra también los endpoints API. Habilitar **One-time PIN** por correo.
   Crear una política **Allow** para una única dirección exacta que controles,
   sin reglas Bypass ni Service Auth. Usar una duración corta, por ejemplo
   30 minutos. Copiar el **Application Audience (AUD)**.
3. Crear un túnel Cloudflared administrado desde **Networking → Tunnels**.
   En **Routes → Add route → Published application**, publicar ese mismo
   hostname entero hacia `http://127.0.0.1:8461`. Mantener el Host público
   original y habilitar **Protect with Access** con el mismo equipo y AUD.
4. Habilitar HTTPS en el borde y redirigir HTTP a HTTPS para ese hostname
   antes del login. No crear reenvíos de puertos. La PC necesita salida al
   equipo Access por HTTPS para descargar claves y conectividad de salida
   de cloudflared. Si la red ya bloquea esa conexión, detener la prueba en
   ese entorno.

- [Crear un túnel administrado](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/get-started/create-remote-tunnel/)
- [Parámetros de origen y Access](https://developers.cloudflare.com/tunnel/reference/origin-parameters/)
- [Formato del JWT de aplicación](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/authorization-cookie/application-token/)

## Comandos en la PC

Desde un checkout aislado del PR #21, con Python 3.12, dependencias del
proyecto y cloudflared 2025.4.0 o posterior. En la primera consola:

```powershell
$env:PYTHON_DOTENV_DISABLED = '1'
$env:PYTHONUTF8 = '1'
python -m pip install -r requirements-tablet-test.txt
$hostPos = Read-Host 'Hostname de la aplicación, sin https://'
$equipo = Read-Host 'Prefijo del equipo en cloudflareaccess.com'
$aud = Read-Host 'Application Audience (AUD)'
python scripts/servir_tablet_access.py --host $hostPos --equipo $equipo --audiencia $aud
```

Ingresar el mismo correo configurado en Access y dos contraseñas de prueba
distintas de al menos 12 caracteres. En otra consola, guardar el token del
conector en un archivo de acceso privado, fuera del repositorio y OneDrive.
El comando toma la ruta del archivo, así el token queda fuera de la línea de
comandos. En PowerShell:

```powershell
cloudflared --version
$rutaToken = Read-Host 'Ruta absoluta del archivo privado con el token del túnel'
Get-NetTCPConnection -LocalPort 8461 -State Listen | Select-Object LocalAddress,LocalPort
cloudflared tunnel run --token-file $rutaToken
```

Comprobar que solo se escucha en `127.0.0.1`. En una tercera consola podés
verificar el rechazo local en una solicitud sin JWT, con el hostname y
esquema declarados explícitamente:

```powershell
$hostPos = Read-Host 'Hostname del POS ficticio'
curl.exe -i -H "Host: $hostPos" -H "X-Forwarded-Proto: https" http://127.0.0.1:8461/pos/
```

Resultado esperado: HTTP 403. El HTTP anterior es interno a loopback.
Toda conexión del navegador al hostname público usa HTTPS.

- [cloudflared y archivo de token](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/configure-tunnels/run-parameters/)

## Venta ficticia desde la PCBOX

1. En Edge InPrivate, visitar `https://HOST-POS/pos/?tablet=1`. Verificar
   que la sesión anónima queda en Access y que un correo fuera de la
   política no llega al POS. Autenticar el correo permitido y comprobar
   que Abadion pide sus propias credenciales. Repetir desde la tablet
   en otra red antes de cargar contraseñas POS.
2. Iniciar sesión como `tablet-ventas`. En **Caja diaria**, abrir las cajas
   de comidas y bebidas/postres con $0. En el catálogo, agregar una Comida
   ficticia, una Bebida ficticia y un Postre ficticio.
3. Probar un Extra ficticio y quitarlo antes de cobrar. Confirmar en
   efectivo una vez los $1.500. En el historial debe haber una sola venta.
   Verificar $1.000 en comidas y $500 en bebidas/postres. La repetición con
   el mismo identificador se valida por API. Un pedido nuevo puede generar
   una segunda venta válida.
4. Cerrar sesión en Abadion y comprobar que para volver a operar pide su
   contraseña. Cerrar la sesión de Access con `https://HOST-POS/cdn-cgi/access/logout`.
   Detener cloudflared y el launcher con Ctrl+C. El cierre normal elimina
   la base temporal. Desactivar la ruta de laboratorio hasta otra prueba.

## Decisiones de seguridad

Access verifica el PIN en el borde y el conector puede validar el JWT antes
de reenviar. El origen vuelve a verificar firma RS256, `kid`, emisor,
audiencia, tipo, correo y vigencia. Obtiene claves actuales y anteriores por
HTTPS del equipo configurado, sin seguir redirecciones. Usa caché por
cinco minutos y rechaza solicitudes al no poder renovar la caché. Un
`kid` desconocido puede requerir esperar al siguiente refresco.

El origen rechaza conexiones fuera de loopback, Host ambiguo y HTTP del
visitante según el esquema que Cloudflare sobrescribe. Solo después de
validar el JWT construye la vista HTTPS de la aplicación y elimina headers
reenviados. El perímetro de Abadion valida el Origin exacto en escrituras y
mantiene cookies Secure, HttpOnly y SameSite=Strict, roles separados y
límite de login. El JWT es una credencial bearer hasta su expiración.
Mantener privada la PC, la sesión del navegador y el token del conector.

## Alternativas si faltan recursos

| Opción | Costo o límite |
|---|---|
| Dominio existente bajo tu control | Access Free puede cubrir la prueba sin comprar otro dominio. Requiere zona activa, HTTPS y permiso para configurar DNS y Access. |
| Registrar un dominio | Costo anual de registro y renovación según extensión y registrador. No hace falta un plan de Access pago para una sola tablet. |
| Laboratorio HTTPS directo del PR #20 | Sigue disponible para práctica ficticia en una red controlada con certificado confiable. No resuelve la PCBOX en otra red. |
| Protected Quick Tunnel | Sin compra de dominio y apto para la demo estática. Cloudflare documenta el PIN por correo, pero no un JWT verificable en el origen para este tipo de túnel. |

Para repetir el Quick Tunnel estático, consultá la [guía previa](https://github.com/NicoNunezFM/contabilidad-bebidas-postres/blob/6cdf0963000e494d53e92eed427afbbe3a3e3a46/docs/tablet-acceso-remoto-seguro.md#prueba-f%C3%ADsica-permitida-solo-p%C3%A1gina-est%C3%A1tica).

## Resultados automatizados y limitaciones

- Windows, Python 3.12: 12 pruebas de firma y claims aprobadas con una clave
  RSA efímera. Incluyen equipo, audiencia, identidad, algoritmo, tipo y vigencia.
- Las pruebas de integración ASGI con SQLite ficticio están incluidas en la
  suite de CI. En el entorno local restringido, asyncio de Windows quedó
  bloqueado al crear su socket interno de loopback. La ejecución de Edge
  tampoco pudo iniciar el servidor de pruebas, y la prueba de conectividad
  HTTP local obtuvo WinError 10013. El resultado de la nueva ejecución de CI
  puede consultarse en **Checks** del PR #21.
- Pendiente en el entorno físico: HTTPS normal de ambos dominios, OTP,
  cookies, Origin de las escrituras, carrito, historial, cajas y logout en
  Edge y en el navegador integrado de la PCBOX desde otra red.
