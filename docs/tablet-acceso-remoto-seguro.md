# PCBOX desde otra red: diseño de acceso remoto seguro (pendiente de implementar)

## Evidencia del 23/11/2026

- PCBOX Android 6, navegador integrado: el usuario **reportó** que completó el PIN de un *Protected Quick Tunnel* y vio la página estática `Abadion - Conexion segura` publicada desde `127.0.0.1:8877`.
- Edge en la PC: el usuario **reportó** login y operación ficticia correctos del laboratorio HTTPS del PR #20 en `https://127.0.0.1:8460`, con confianza de su CA local.
- Esas validaciones **no prueban** el POS conectado en PCBOX ni autorizan producción. No se midió rendimiento ni se comprobó en Android la confianza en la CA local.
- El servidor `scripts/servir_tablet_https.py` del PR #20 solo soporta HTTPS directo. `PerimetroTablet` rechaza `Forwarded` y `X-Forwarded-*`, exige esquema HTTPS, cliente permitido y Host/Origin exactos. El login usa `request.url.scheme` para la bandera Secure de cookies.
- El Quick Tunnel mostrado apunta a una **página estática ficticia** en `127.0.0.1:8877`, no a la API ni a bases.

## Decisión arquitectónica

**No** cambiar el puerto 8460, quitar TLS, alterar el perimetro directo ni introducir valores `trust_proxy_headers=True` globales. Implementar un **segundo launcher aislado** para acceso por túnel, con una rama y pruebas independientes; solo el launcher nuevo puede conocer esta arquitectura.

Camino propuesto para pruebas:

```
PCBOX / Android 6
  -> HTTPS público + PIN del Protected Quick Tunnel
  -> cloudflared (proceso local y protegido)
  -> conexión de origen solo loopback
  -> perímetro remoto explícito de Abadion
  -> POS autenticado + SQLite temporal exclusivamente ficticia
```

Se debe establecer y verificar una frontera de confianza para HTTPS terminado en Cloudflare. Nunca basarse en el valor de `X-Forwarded-Proto` aportado por un cliente; tampoco desactivar la comprobación de Origin para aceptar cualquier dominio. La URL temporal `trycloudflare.com` cambia en cada ejecución y debe validarse como hostname concreto, no comodín. Validar que el túnel realmente exige PIN desde sesión privada, incluso después de reiniciar.

**Condición antes de autorizar acceso a API:** documentar/implementar una forma verificable de atestiguar el tráfico autenticado en el origen. Evaluar las garantías del autenticador integrado de Protected Quick Tunnels y, para un túnel administrado, validación de JWT de Cloudflare Access (audiencia, firma, emisor, expiración) o `access.required` en cloudflared. No suponer que el Quick Tunnel provee el mismo JWT o audience tag que un túnel administrado. Un header o cookie presente sin verificación no prueba identidad.

## Controles obligatorios del launcher remoto

1. **Loopback exclusivo:** escuchar `127.0.0.1`, sin bind LAN, `0.0.0.0`, firewall ni router. El servidor HTTPS directo del PR #20 no cambia.
2. **Aislamiento financiero:** nueva base temporal, catálogo y contraseñas diferentes; el launcher jamás acepta rutas de bases existentes ni reutiliza `negocio.db`. Cierre normal elimina las pruebas; cierre abrupto requiere revisión de restos temporales. No acceder al WhatsApp ni al Entrenamiento instalado.
3. **Acceso de doble capa:** verificación de autenticación del túnel y sesión propia POS; no permitir acceso al catálogo/API anónima. Sin credenciales en CLI, logs o GitHub.
4. **Autoridad y origen exactos:** hostname público HTTPS único de la sesión, `Origin` exacto en cada método de escritura, rechazar host alternativo o ambiguo, evitar redirecciones abiertas y CSRF; nunca inferir esquema/host de headers no confiables.
5. **Cookies:** `Secure`, `HttpOnly`, `SameSite=Strict`, `Path=/pos-api`; logout y expiración válidos. Probar específicamente desde Android 6 que la cookie de login llega a los endpoints protegidos.
6. **Auditoría:** rechazar métodos, headers y rutas prohibidos; respuestas `no-store`, sin filtrar contraseñas, tokens, datos financieros ni identificadores sensibles. Limitar intentos por origen de conexión y, si es autenticable, identidad verificada. La IP de origen visible desde localhost no identifica directamente a la tablet.
7. **Desconexión:** caída del túnel o del servidor no debe abrir ruta alternativa; URL temporal y sesiones se invalidan al terminar. No suponer disponibilidad continua.
8. **Regresión:** conservar permisos ventas/admin, separación de cajas e idempotencia del PR #20. No reducir garantías del laboratorio HTTPS directo.

## Matriz de aceptación (pendiente)

| Caso | Criterio |
|---|---|
| Acceso anónimo al Quick Tunnel | PIN obligatorio; sin PIN no se llega a la página |
| Correo diferente | No obtiene acceso |
| Origen local directo no autenticado | Rechazo fuera del perímetro esperado |
| Host ajeno, Origin ajeno o ausente en escritura | Rechazo |
| `Forwarded` / `X-Forwarded-*` manipulados | No escalada ni bypass |
| Contraseña POS incorrecta / rol inadecuado | 401/403, limitación de intentos |
| Cookie tras login | Secure/HttpOnly/SameSite Strict y API autenticada |
| Logout / reinicio | Sesiones invalidadas |
| Android 6 vertical y horizontal | Login, carrito, apertura de cajas, venta ficticia e historial |
| Venta de $1.500 y reintento | $1.000 comidas, $500 bebidas/postres, una sola venta |
| Redirecciones y acceso directo a otros servicios | No disponibles |
| Archivos instalados y `negocio.db` de control | Inmutables (comprobar byte a byte) |
| Pruebas existentes del PR #20 | Sin regresiones |

## Próxima implementación

1. Prototipo de perímetro para túnel en módulo nuevo, sin alterar `PerimetroTablet`. Las condiciones de confianza deben ser explícitas y testeables; si no se puede autenticar el origen del tráfico, no habilitar la API.
2. Pruebas unitarias/integración negativas antes de abrir acceso remoto; browser Edge con el hostname real antes de prueba física.
3. Prueba **estática** en PCBOX ya superada según reporte; siguiente prueba física es login y catálogo ficticio *solo si* se cumplen todas las condiciones previas.
4. PR independiente en borrador sobre `feature/abadion-tablet-https-laboratorio`, sin merge. Reportar pruebas ejecutadas, omitidas y pendientes de forma separada.

## Referencias

- Cloudflare Quick Tunnels: https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/
- Cloudflare Tunnel origin Access validation: https://developers.cloudflare.com/tunnel/reference/origin-parameters/
- Laboratorio directo: `docs/tablet-https-laboratorio.md`

**Estado de esta rama:** documentación y diseño de seguridad únicamente. No existe todavía un modo de conexión remota habilitado para el POS.
