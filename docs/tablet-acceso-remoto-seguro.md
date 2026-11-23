# Acceso remoto del POS desde PCBOX

## Decisión del 23/11/2026

**POS remoto bloqueado.** Un Protected Quick Tunnel con `--allowed-mail`
exige un PIN por correo autorizado en el borde de Cloudflare. La documentación
no especifica para este producto una afirmación por solicitud que Abadion
pueda verificar en el origen, ni publica un emisor, audiencia y claves para
esa validación. Esto deja sin cumplir el requisito de acreditar la autenticación
del túnel en el origen. Una conexión local, un encabezado reenviado o una cookie
recibida no acreditan por sí solos que Cloudflare verificó el PIN.

En Cloudflare Access para aplicaciones configuradas sí se documenta el token
`Cf-Access-Jwt-Assertion` y la validación con firma, emisor, audiencia y vigencia.
Para túneles administrados también se documenta la comprobación de Access en
cloudflared, con equipo y audiencias configurados. Sigue pendiente conseguir una
garantía verificable para el túnel que se use en la prueba conectada.

- [Quick Tunnels y PIN por correo](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/)
- [Validación de JWT de Cloudflare Access](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/authorization-cookie/validating-json/)
- [Parámetros de origen del túnel administrado](https://developers.cloudflare.com/tunnel/reference/origin-parameters/)

## Evidencia y alcance

- La PCBOX con Android 6 ya mostró, según el reporte de Sergio, la página
  estática después de completar el PIN. En Edge también se reportó una
  operación ficticia del laboratorio HTTPS directo usando su CA local.
- Se inspeccionaron el launcher HTTPS, el perímetro, la creación aislada de
  SQLite, las sesiones y el router POS. El laboratorio crea una base nueva,
  rechaza cabeceras reenviadas y valida cliente, HTTPS, Host y Origin. Login
  y logout usan cookies separadas con ámbito `/pos-api`.
- [La CI del commit inicial del PR #21](https://github.com/NicoNunezFM/contabilidad-bebidas-postres/actions/runs/45255536675)
  concluyó correctamente con el conjunto existente de SQLite y Edge del
  PR #20. Esa ejecución incluye el test HTTPS preexistente con excepción SPKI
  limitada al certificado efímero. No acredita confianza en Android 6 ni
  acceso remoto. La prueba física de esta guía exige validación normal de TLS.
- Se lanzaron las pruebas Python/API sobre una copia del árbol de la base
  `c95b0c8` con SQLite ficticio. No se obtuvo un resultado final local. La
  ejecución local en Edge registró errores y se interrumpió sin completar.
  La consulta HTTP al servidor estático local falló por restricciones de
  acceso a sockets del entorno. No se ejecutó un nuevo túnel.
- El PR #21 conserva el bloqueo y solo actualiza documentación. No hay un
  launcher remoto del POS ni pruebas automatizadas de su autenticación.

## Condiciones para la prueba conectada

- Origen exclusivo en `127.0.0.1`, con un proceso separado del laboratorio del
  PR #20 y base ficticia temporal nueva. El túnel debe aportar una señal de
  autenticación que el origen o el conector puedan verificar.
- Host público concreto y Origin HTTPS exacto para escrituras. Rechazar
  tráfico sin prueba verificable, orígenes ausentes o ajenos, rutas fuera del
  POS y mecanismos que permitan alterar la autoridad o el esquema.
- Conservar autenticación propia, roles, cookies Secure/HttpOnly/SameSite=Strict,
  límite de intentos, logout y expiración. Verificar esos controles antes
  de ingresar credenciales desde la PCBOX.
- Validar compatibilidad TLS, navegación vertical y horizontal, carrito,
  extra ficticio, historial y reintento idempotente. Registrar una sola venta
  de $1.500, con $1.000 en comidas y $500 en bebidas/postres. Verificar la
  invalidación de sesiones al detener o reiniciar el laboratorio.
- Quick Tunnel cambia de hostname al reiniciar, requiere flujo interactivo
  y carece de garantía de disponibilidad. El navegador integrado de Android 6
  sigue pendiente de validación con el POS completo.

## Prueba física permitida: solo página estática

En la PC, abrir dos ventanas de PowerShell. Usar un puerto 8877 libre. En la
primera ventana, crear un directorio temporal nuevo con un único archivo y
servirlo en loopback:

```powershell
$directorio = New-Item -ItemType Directory -Path (Join-Path $env:TEMP ('abadion-pin-' + [guid]::NewGuid().ToString('N')))
$marca = 'ABADION-PIN-' + [guid]::NewGuid().ToString('N')
Set-Content -LiteralPath (Join-Path $directorio.FullName 'index.html') -Encoding ascii -Value "<!doctype html><meta charset=utf-8><title>Abadion</title><h1>$marca</h1>"
Write-Output $marca
python -m http.server 8877 --bind 127.0.0.1 --directory $directorio.FullName
```

En la segunda ventana, comprobar que solo escucha en `127.0.0.1` y que la
respuesta local muestra la marca recién generada. Confirmar que cloudflared
reconoce `--allowed-mail` antes de ejecutar el túnel:

```powershell
Get-NetTCPConnection -LocalPort 8877 -State Listen | Select-Object LocalAddress,LocalPort
(Invoke-WebRequest -Uri 'http://127.0.0.1:8877/' -TimeoutSec 5).Content
cloudflared --version
cloudflared tunnel --help | Select-String -SimpleMatch 'allowed-mail'
```

Si todo coincide, iniciar el túnel con una dirección de correo propia y exacta:

```powershell
$correo = Read-Host 'Correo exacto autorizado para recibir el PIN'
if ($correo -notmatch '^[^\s, *@]+@[^\s, *@]+\.[^\s, *@]+$') { throw 'Ingresá un correo individual.' }
cloudflared tunnel --url http://127.0.0.1:8877 --allowed-mail $correo
```

1. En Edge InPrivate, abrir la nueva URL HTTPS. Antes del PIN, la marca debe
   permanecer oculta. Verificar que un correo secundario propio fuera de la
   lista tampoco permite ver la marca.
2. En PCBOX, usar una conexión distinta de la PC y una sesión sin cookies
   previas del túnel. Abrir la misma URL HTTPS en el navegador integrado.
   Completar el PIN del correo autorizado y comprobar la misma marca. Ante
   advertencia de certificado, detener la prueba.
3. Detener cloudflared con Ctrl+C. En una ventana privada nueva comprobar
   que la URL anterior dejó de entregar la marca. Si se repite la prueba,
   comprobar que la URL nueva vuelve a pedir el PIN.
4. Detener el servidor estático con Ctrl+C. En esa misma ventana, borrar el
   único archivo creado y su directorio temporal:

```powershell
Remove-Item -LiteralPath (Join-Path $directorio.FullName 'index.html')
Remove-Item -LiteralPath $directorio.FullName
```

Registrar fecha, versión de cloudflared, navegador, tipo de red y resultado de
cada paso sin guardar PIN, cookies ni correos. El puerto 8877 sirve únicamente
el archivo generado. Mantener el POS fuera del túnel incluso si la prueba
estática pasa.
