# Fase 2.4 — Seguridad, autenticación y permisos

Fecha: 27/11/2026. Base exacta #41: `3c5b5ae53b4a1d660314923f48b6f96349171a0e`.
Rama: `security/abadion-autenticacion-permisos`. Propuesta en borrador, sin producción.

## Evidencia y alcance

La [auditoría previa](auditoria-previa.md) diferencia seis hallazgos reproducidos de
hipótesis. El [inventario previo](endpoints-base.json) se obtuvo antes de modificar
código. La [matriz completa](matriz-endpoints.md) y su
[versión verificable](endpoints-consolidados.json) describen las 83 combinaciones
método/ruta de la API general. `python -B scripts/auditar_endpoints.py` verifica las
dependencias efectivas, controles CSRF y referencias; una ruta nueva sin contrato falla.

No se inspeccionaron configuraciones, sesiones, credenciales, bases o instalaciones
reales. El análisis remoto de dependencias envía nombres/versiones públicos de los
manifiestos, nunca credenciales ni datos comerciales. Solo se crearon bases ficticias,
entornos temporales y esta rama. No cambió el adaptador ni los manifiestos de Node.

## Autenticación y autorización, explicado

Autenticar es comprobar qué perfil presentó la contraseña. Autorizar es comprobar
si ese perfil puede ejecutar una operación concreta. Ocultar un botón no autoriza:
cada ruta privada exige sesión o credencial de servicio y cada ruta administrativa
comprueba el rol en el servidor. Ventas mantiene sus operaciones diarias; no puede
anular ventas ni administrar precios cambiando una cookie o enviando un rol en JSON.

La contraseña se verifica con el PBKDF2-SHA256 existente, sal aleatoria y 600000
iteraciones. No se almacena texto claro. Cada inicio correcto recibe un token
aleatorio nuevo de 256 bits; SQLite guarda SHA256 del token, no su valor utilizable.
La cookie es HttpOnly, SameSite strict, Path `/pos-api` y Secure sobre HTTPS.
Se conservan Administración y Ventas compartidas, con 8 horas y 30 días de duración.
Cerrar Administración sigue permitiendo volver a la sesión de Ventas abierta.

Una cookie válida no basta si la cuenta fue deshabilitada, cambió su contraseña,
nombre o rol. La sesión está vinculada a una huella del estado del usuario en el
momento de emisión; el trigger de cambio revoca todas sus sesiones en la misma
transacción SQLite. Rehabilitar una cuenta no rehabilita tokens antiguos. La huella
también detecta cambios si un esquema previo carecía del trigger. No se reconstruyen
huellas de sesiones anteriores: deben volver a iniciar sesión.

## Correcciones y contratos

| Hallazgo | Implementación | Validación / limitación |
| --- | --- | --- |
| SEC-01/02, revocación y adopción de rol | `pos_auth.py`, `pos_seguridad.preparar_esquema`: vínculo al estado de emisión, trigger de revocación, fechas UTC parseadas y duración máxima desde creación | Cambios de clave/rol/activo/nombre, desactivar/rehabilitar, token renombrado, fechas manipuladas, sesión previa sin contexto |
| Carrera verificación/emisión | Verifica contraseña fuera del bloqueo y revalida huella tras `BEGIN IMMEDIATE`; emisión de sesión/contexto/evento atómica | Cambio de clave entre verificación e inserción y fallo de auditoría revierten emisión |
| Carrera permiso/escritura financiera | Revalidación dentro de `transaccion_simulacion(escritura=True)` y las tres transacciones de administración de catálogo | Revocación después de la dependencia HTTP y antes del bloqueo rechaza sin stock ni movimientos parciales |
| SEC-03, abuso | 20 solicitudes válidas de login/minuto por peer real y base, ventana temporal, Retry-After, memoria limitada a 4096 claves, cerrojo entre threads | Intentos rechazados no prolongan bloqueo; no hay bloqueo permanente por usuario. Laboratorio conserva límite previo más estricto de 10/minuto |
| Posible enumeración por tiempo | PBKDF2 ficticio para usuario inexistente | Iguala trabajo criptográfico; no garantiza tiempos indistinguibles de red/DB |
| SEC-04, catálogo legado | Adicionales/personalizaciones exigen el mismo contrato de sesión que productos | Menú ficticio deliberadamente público se conserva; perímetro tablet exige sesión adicional |
| CSRF/ambigüedad | Origin único exacto contra scheme/host efectivos, Host único; rechaza Sec-Fetch-Site cross-site; controles backend en todas las mutaciones POS | No cambia experiencia comercial ni exige token CSRF nuevo. Access valida proxy antes de aplicar este control |
| SEC-05, errores | Elimina input/ctx de validaciones; errores SQLite genéricos en POS y API general; sanea ERROR_BASE_DATOS de módulos legados y mensajes de arranque del backup | No devuelve contraseñas ni texto del driver y no imprime rutas personales del respaldo. Excepciones inesperadas siguen respuesta genérica del servidor sin debug; logs del host requieren política propia |
| SEC-06, cache y trazabilidad | No-store/nosniff/no-referrer/DENY en respuestas POS; eventos mínimos, sin cuerpos, tokens, IPs ni nombres suministrados | Login/emisión/revocación/cambio de usuario persistidos; denegaciones en logger acotado, sin escribir en operación revertida |

La revalidación financiera tiene un orden claro: quien obtiene primero el bloqueo
de escritura se ejecuta primero. Si la venta ya obtuvo el bloqueo y validó la sesión,
una revocación concurrente espera a su commit. Si la revocación confirmó primero,
la venta se rechaza antes de escribir. No se promete cancelar retroactivamente una
venta que ya estaba autorizada dentro de su transacción.

El límite es por proceso y conexión real: no usa X-Forwarded-For falsificable.
Tras Cloudflare todos los clientes comparten el peer local y, por tanto, el cupo.
Reiniciar o usar varios workers reinicia/multiplica cupos; un ataque distribuido
puede excederlos. Un control de borde compartido requiere un diseño y autorización
de infraestructura aparte. No se presenta este límite como protección completa de DoS.

## Auditoría e integridad

`eventos_seguridad_pos` registra fecha UTC, tipo, ID numérico interno cuando está
disponible, plantilla de ruta y estado. No copia bodies, passwords, hashes de
contraseña, cookies, tokens, números telefónicos ni direcciones. El inicio correcto
tiene evento de emisión con ID; en logout el evento de revocación identifica usuario.
Los triggers rechazan UPDATE/DELETE de auditoría. Un dueño del archivo puede eliminar
triggers: no es un registro externo inviolable ni prueba legal de autoría individual.

Las operaciones comerciales conservan su auditoría transaccional existente en los
eventos POS. El transporte solo emite metadatos seguros al logger: no agrega una
fila SQLite en cada reintento comercial. Esto conserva la idempotencia y snapshots
de recuperación sin generar movimientos de caja/gastos. Las denegaciones y errores
no escriben en SQLite. La emisión/revocación de sesión y cambio de usuario requieren
su evento dentro de la transacción: ante fallo revierten.

El evento HTTP adicional de login/logout/configuración es de mejor esfuerzo y
posterior al resultado; si no puede persistirse emite advertencia genérica y no
convierte una operación ya confirmada en un error aparente. Debe definirse retención,
rotación y recolección del logger antes de producción. No hay purga automática de
sesiones/eventos, ni se borra historial para hacer pasar pruebas.

## Compatibilidad de esquemas y recuperación

| Elemento | Cambio | Contrato |
| --- | --- | --- |
| `usuarios_pos`, `sesiones_pos` | Columnas conservadas | Usuarios/roles/duración intactos; las sesiones nuevas tienen fechas ISO UTC explícitas |
| `sesiones_pos_contexto` | Tabla aditiva PK token_hash, FK a token único, huella de 64 caracteres | Sin backfill de sesiones antiguas; reautenticación requerida |
| `eventos_seguridad_pos` | Tabla aditiva, ID/fecha/evento/usuario/ruta/estado | Sin datos comerciales ni credenciales, sin FK que obligue a conservar nombres personales |
| Triggers | Revocación ante cambio de usuario y dos de inmutabilidad de eventos | Se crean idempotentemente dentro de transacción de inicialización/emisión |
| Tablas financieras/costos/stock | Sin cambios de esquema/reglas | Mantienen garantías #39–#41; check de sesión se realiza antes de escribir |
| Bases ficticias anteriores | Lectura de sesión sin contexto rechazada, login crea estructuras nuevas | No se toca una base anterior para validar su token; no se usa estado actual para reconstruir credenciales antiguas |
| Backups/restore | SQLite conserva tablas/triggers nuevos; restore elimina contexto y sesiones | Conserva la invalidación de sesiones ya existente en recuperación. Se elimina primero el contexto para no dejar referencias huérfanas, también en conexiones con FK deshabilitadas. Una copia manual ajena al procedimiento no garantiza revocación |
| Rollback de versión | La versión previa ignora la huella nueva | No autorizado en producción: volver al código vulnerable anula estas garantías. Validar recuperación en copia, no retirar triggers en una base real |

Se probarán bases vacías y previas ficticias, integridad/FK, backup/restore y
recuperación de candidata. No se migró ninguna instalación existente.
La apertura de ensayo distingue las dos tablas de seguridad de los libros comerciales:
su lista de configuración permite autenticarse antes de abrir la jornada, sin permitir
movimientos financieros previos ni desactivar la candidata bloqueada.

## Superficies adicionales y permisos

| Factory/perímetro | Endpoints adicionales | Permisos / fuente |
| --- | --- | --- |
| Entrenamiento | GET `/`, `/pos/`, `/pos/index.html` | Públicos, HTML sin tokens; `src/pos_entrenamiento_web.py:57–64`; POS comparte el router seguro, cookies propias, TrustedHost, sin OpenAPI |
| Pruebas / Preproducción | GET `/_pruebas/status` o `/_preprod/status`; POST `…/stop`, `…/backup` | Bearer de control exacto, hostname 127.0.0.1; `scripts/abadion_preproduccion.py:149–168`. Token no es sesión POS ni rol Ventas. Status muestra carpeta únicamente al control autorizado |
| Pruebas / Preproducción | GET `/`, `/pos/`, `/pos/index.html` | Públicos locales, aviso ficticio; mismo router POS, contexto/base/cookies separados |
| Tablet HTTPS | Router POS y shell de laboratorio | Peer privado explícito, host exacto, HTTPS directo, rechazo de proxies, origen y límite previo; `src/pos_tablet_laboratorio.py:24–96` |
| Access | Mismas rutas de laboratorio | Loopback del proxy, host, X-Forwarded-Proto validado, JWT RS256, issuer/audience/email/iat/nbf/exp; luego sesión POS. `src/pos_tablet_access.py`. No sustituye permisos comerciales |
| API general | Docs/OpenAPI de desarrollo y estáticos | Públicos sin DB; API contable privada con Bearer. No es una configuración productiva aprobada |

Los permisos de archivos revisados pertenecen a los preparadores y controles
ficticios existentes. No se cambiaron ACL, archivos reales, firewall ni túneles.
SQLite confía en el sistema operativo: quien puede leer DB/backups puede leer datos
y hashes; quien puede escribirlos puede alterar permisos/triggers. El directorio
sincronizado del repositorio no es una ubicación productiva aprobada para datos.

## Dependencias y CI

Python: `python-dotenv` 1.2.1 → 1.2.2; `cryptography` 46.0.5 → 50.0.0.
Se eligió la primera versión que cubre todos los avisos del escáner, con verificación
funcional y de JWT/TLS en entornos separados. No se cambiaron métodos de valoración
ni autenticación. La auditoría de base arrojó 13 entradas, **7 avisos únicos** en dos
paquetes (varios duplicados). La resolución corregida no arrojó avisos conocidos
en la consulta realizada; no demuestra ausencia de vulnerabilidades nuevas.

Las condiciones de explotación de las bibliotecas no equivalen a una explotación
de Abadion: dotenv requiere escritura local/symlinks y sus funciones set/unset;
el aviso PKCS7 de cryptography requiere descifrado de datos de atacante. En el
POS inspeccionado se utiliza verificación de JWT. Se corrigen dependencias de todos
modos. Fuentes: [dotenv](https://github.com/advisories/GHSA-mf9w-mj56-hr94),
[cryptography](https://github.com/advisories/GHSA-g6cj-pr64-35w5).

Node: inspección de 162 nombres de paquete del lock, sin instalación ni scripts.
Se encontraron 9 avisos en seis paquetes: basic-ftp (3), extract-zip (2), glob (1),
ip-address (1), minimatch (1), zod (1). La suma es **9**. La lista detallada y URLs
del registro están en `dependencias-node-base.json`. Hay severidades alta y media.
La presencia/versiones afectadas está verificada; la posibilidad de explotarlas
a través del flujo concreto del bot no se demostró. Requiere evaluación aparte.

CI conserva suites completas Linux y Windows/Edge y publica JUnit y jornada
ficticia. Agrega inventario efectivo de rutas, `pip-audit` y auditoría pública del
lock Node. El control Node **debe fallar mientras existan estos avisos**; no se usa
continue-on-error, exclusiones ni una lista de avisos permitidos para simular verde.
Un error de red también falla. Su corrección queda bloqueada por la restricción de
no modificar el bot. Los jobs funcionales son independientes y pueden aprobar.

## Riesgos residuales y decisiones pendientes

### Modelo de amenazas por frontera

| Frontera / activo | Amenaza | Control y riesgo residual |
| --- | --- | --- |
| Navegador → sesión POS | Robo/reutilización de cookie, CSRF, fuerza bruta | Token aleatorio hasheado, HttpOnly/SameSite/Origin, TTL y revocación; un equipo/navegador comprometido puede robar una sesión activa |
| Ventas → administración | Rol en body, cambio de nombre de cookie, rol cambiado con token viejo | Dependencias backend, vinculación a rol/credenciales y revocación; administrador y dueño del host mantienen capacidad privilegiada |
| Dependencia HTTP → commit financiero | Usuario revocado después de autorizar, carrera entre threads | Revalidación después de BEGIN IMMEDIATE; orden transaccional definido, sin cancelación retroactiva |
| Access → laboratorio → POS | Proxy/header/JWT falso o sesión POS sin Access | Validación de peer, host, esquema y JWT existente; solo se probó con claves/respuestas ficticias, configuración real fuera de alcance |
| Bot/token servicio → persona/operación | Grupo admitido con remitente sin permiso, identidad declarada en body | Bearer de servicio existente no prueba identidad humana; bloqueo y propuesta independiente, sin cambio del bot |
| SQLite/backups → sistema operativo | Lectura de datos/hashes, manipulación de DB/triggers, backup alterado | ACL/preparadores y manifests existentes, integridad/FK y limpieza de sesiones al restaurar; acceso del dueño del host fuera del aislamiento POS |
| Dependencias/CI → aplicación | Paquete vulnerable, resolución transitiva cambiante, acción comprometida | Auditorías con fallo visible y pruebas de plataforma; falta lock transitivo completo y pin por SHA de acciones, sin afirmar cadena de suministro invulnerable |
| Aplicación → registros | Token/contraseña o PII en error/log | Metadatos mínimos y errores saneados; logs heredados del bot, OS y proxy requieren etapa independiente y política de retención |

Se mantiene el bloqueo productivo. Pendientes: propuesta del bot y sus dependencias,
perímetro real e identidad Access autorizados, endurecimiento del host/ACL y backups,
recolección/retención de logs, pruebas de carga/ataques distribuidos y un plan de
recuperación con revocación de sesiones. No se realizó un pentest remoto ni se
validó infraestructura real. La suite no demuestra ausencia de XSS ni de todas las
inyecciones; no se instala CSP restrictiva sin estudiar compatibilidad del POS.

Las cuentas compartidas impiden atribución individual y aumentan el impacto de
una contraseña filtrada. Cuentas personales, MFA, cambios de duración, nuevas reglas
de grupos/personas del bot y un gestor de secretos son alternativas pendientes de
autorización, no cambios encubiertos en esta entrega. No se obliga a adoptar ninguno.
La integración de registros legados continúa bloqueada.

La validación final, fallos iniciales, comparación de 647 casos y evidencias de CI
se documentan por separado en [pruebas](pruebas.md). Aprobar pruebas no declara
Abadion completamente seguro ni autoriza habilitar producción.
