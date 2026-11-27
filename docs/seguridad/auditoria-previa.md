# Auditoría previa — autenticación y permisos

Base: PR #41, `3c5b5ae53b4a1d660314923f48b6f96349171a0e`.
Inspección y reproducciones exclusivamente sobre código y bases ficticias aisladas.
Este informe y el inventario se prepararon antes de modificar código de aplicación.

## Superficie e inventario

El [inventario de base](endpoints-base.json) registra 83 combinaciones método/ruta,
función, archivo, línea y dependencias de FastAPI. Se revisaron también controles
inline que no aparecen como Depends, factories de Entrenamiento/Pruebas/Preproducción,
perímetro HTTPS/Access, scripts offline, SQLite y adaptador WhatsApp.

| Superficie | Permiso vigente / decisión de conservación |
| --- | --- |
| `/`, shell `/pos/` y recursos estáticos | Públicos; sin datos de clientes ni tokens. Las factories ficticias deshabilitan docs/OpenAPI |
| Login | Público con Origin; corregir abuso y errores sin imponer cuentas personales ni MFA |
| Logout | Origin; revoca solo el primer perfil presente para volver de Administración a Ventas. Conservar este contrato |
| Indicadores `/pos-api/simulacion/estado` | Públicos deliberadamente: necesarios antes del login, solo capacidades de un modo ficticio marcado |
| Catálogo de productos | Público solo en simulación ficticia; en API legada requiere sesión. Conservar menú ficticio previo al login |
| Catálogo adicional / personalizaciones | En base quedan públicos también fuera de simulación; alinear con la política del catálogo de productos |
| POS comercial ordinario | Administración o Ventas según dependencia; no asumir que la interfaz constituye autorización |
| Precios, configuración, compras POS, anulaciones/devoluciones, fondos/rendición, transferencias, cierres de período, contabilidad/conciliación | Administración, con Origin en mutaciones; conservar todos los permisos actuales |
| Apertura, arqueo, cierre diario, aporte/retiro/gasto, pedido/venta, cliente/abono | Permisos de Ventas y Administración existentes. No restringirlos por una decisión comercial nueva |
| Corrección global de abono de cliente | Administración, Origin, sesión y actor esperado |
| API contable y `/acciones` | Bearer de integración; una cookie POS no lo sustituye |
| `/comandos` | Bearer de integración o bot separado; autorización funcional del remitente no está en el backend actual |
| Control de proceso `/_preprod/*` y `/_pruebas/*` | Token de control propio, hostname local y contexto ficticio; no exponer por el túnel |
| Cloudflare laboratorio | Loopback, host exacto, HTTPS proxy validado, JWT RS256 con issuer/audience/email/fechas; luego sesión POS |

## Hallazgos comprobados antes de cambiar código

| ID | Gravedad | Evidencia / precondición | Corrección prevista |
| --- | --- | --- | --- |
| SEC-01 | Alta | En SQLite ficticio, token sigue válido tras cambiar password_hash; deshabilitar rechaza pero rehabilitar revive el token | Revocación transaccional ante cambio de credenciales/rol/estado e identidad de emisión vinculada a sesión |
| SEC-02 | Alta condicionada | Token de Ventas adopta rol admin después de una promoción legítima en DB; el portador puede cambiar el nombre de cookie. Requiere token previo y cambio autorizado de rol; no prueba que Ventas pueda cambiar su rol | Revocar al modificar rol y verificar estado de emisión; no reutilizar token viejo tras promoción |
| SEC-03 | Media | Login POS general no tiene límite; el único limitador está en PerimetroTablet. PBKDF2 costoso y contraseñas compartidas aumentan impacto | Límite temporal por origen de conexión/base, acotado en memoria, sin bloqueo global de cuenta y sin prolongarlo por intentos rechazados |
| SEC-04 | Media | Rutas de adicionales y personalizaciones sin autenticación en modo legado, aunque productos sí la exige | Aplicar la misma política de catálogo; mantener el catálogo ficticio público aprobado |
| SEC-05 | Media | Validación estándar puede devolver input de contraseña y errores de backend pueden incluir detalle SQLite | Errores seguros sin input/ctx/secretos; resultados de error DB genéricos en frontera HTTP |
| SEC-06 | Baja | Lecturas privadas no tienen no-store uniforme; no hay auditoría central de login/denegaciones | Encabezados y eventos mínimos de seguridad, sin cuerpos, tokens, IPs ni nombres suministrados |

SEC-01/02 se reprodujeron sin contraseñas reales ni publicar tokens. Los JSON de evidencia
solo contienen booleanos de reproducción. Los permisos administrativos ya están
controlados en backend; no se observó una ruta que permita a Ventas cambiar su rol.

Referencias congeladas de la base auditada:
[emisión de sesión](https://github.com/NicoNunezFM/contabilidad-bebidas-postres/blob/3c5b5ae53b4a1d660314923f48b6f96349171a0e/src/pos_auth.py#L96),
[validación de sesión](https://github.com/NicoNunezFM/contabilidad-bebidas-postres/blob/3c5b5ae53b4a1d660314923f48b6f96349171a0e/src/pos_auth.py#L150),
[login](https://github.com/NicoNunezFM/contabilidad-bebidas-postres/blob/3c5b5ae53b4a1d660314923f48b6f96349171a0e/src/pos_api.py#L144),
[adicionales](https://github.com/NicoNunezFM/contabilidad-bebidas-postres/blob/3c5b5ae53b4a1d660314923f48b6f96349171a0e/src/pos_api.py#L809),
[personalizaciones](https://github.com/NicoNunezFM/contabilidad-bebidas-postres/blob/3c5b5ae53b4a1d660314923f48b6f96349171a0e/src/pos_api.py#L843).

## Hipótesis y riesgos que no se presentan como explotación comprobada

- Carrera entre autenticación/revocación y apertura de la transacción financiera:
  se revisará el estado de sesión dentro de la transacción de escritura, sin alterar
  la atomicidad de #39–#41. El riesgo se distingue de una explotación remota demostrada.
- Comparación lexicográfica de vencimiento y ausencia de límite ligado a creación:
  endurecer fechas, sin reducir duraciones aprobadas de 8 h / 30 días.
- Origin duplicado y cabeceras proxy ambiguas: rechazar ambigüedad. No se afirma
  que un navegador pueda emitir libremente esos headers ni que haya CSRF explotable.
- El tiempo de respuesta para usuario inexistente difiere del de contraseña incorrecta;
  posible enumeración por tiempo, sin medición estadística concluyente.
- API general sin un perímetro de producción aprobado; HTTP local no es HTTPS remoto.
  No se cambia router, firewall, DNS, túnel, reglas Access ni configuración real.
- Credenciales de preparadores ficticios y cookies de navegador requieren ACL del
  usuario del sistema. La candidata tiene controles Windows nativos más estrictos;
  no se supone que estén aplicados a instalaciones existentes ni se alteran sus ACL.
- Auditoría de dependencias y asesorías remotas se documentará con fecha/versiones;
  un escáner limpio no demuestra ausencia de vulnerabilidades.

## Controles ya presentes

PBKDF2-SHA256, 600000 iteraciones, sal aleatoria de 16 bytes y compare_digest;
tokens aleatorios de 256 bits, solo SHA256 guardado en sesiones; activo comprobado;
cookies HttpOnly, SameSite strict, Secure cuando HTTPS; Origin en mutaciones POS;
Bearer de integración/bot distintos y validación fail-closed de su configuración;
consultas SQL parametrizadas en los accesos revisados; marcas de bases ficticias,
aislamiento de contextos y bloqueo de candidata productiva.

## Modelo de amenazas y límites

Activos: sesiones, credenciales, datos personales, ventas, cajas, deuda, stock y costos.
Actores: cliente anónimo, perfil Ventas, administrador legítimo, portador de token robado,
remitente/grupo WhatsApp autorizado y dueño del archivo/host. Fronteras: navegador/API,
perímetro Access/POS, token de servicio/identidad humana, transacción SQLite y sistema
de archivos. Un propietario del equipo o lector de credenciales de control no está
aislado criptográficamente por los roles de la aplicación.

No se utilizarán credenciales reales ni se escaneará infraestructura remota. Las
cuentas compartidas se conservan. Cuentas individuales, MFA, cambio de duraciones,
gestor de secretos y políticas nuevas del bot requieren autorización independiente.

Fuentes primarias: [sesiones OWASP](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html),
[autenticación OWASP](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html),
[validación JWT de Cloudflare](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/authorization-cookie/validating-json/).
