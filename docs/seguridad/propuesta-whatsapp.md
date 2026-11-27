# WhatsApp: inspección y propuesta independiente

No se cambió `whatsapp-bot/`, su lock, sus sesiones, configuración, credenciales ni
instalación. No se inició el adaptador ni se enviaron mensajes reales.

## Evidencia del código

En `whatsapp-bot/index.js`, `ALLOW_GROUPS` es falso por defecto y los grupos habilitados
deben estar en una lista explícita. Sin embargo, la comprobación de número autorizado
del remitente se aplica únicamente a mensajes privados: un mensaje de grupo admitido
no pasa por la misma lista individual (`mensajeDeGrupo`, `grupoAutorizado`,
`numeroAutorizado`). Es un hueco comprobado de política en el código, condicionado a
que se habiliten grupos y a la pertenencia a uno autorizado. No se afirma que grupos
estén realmente habilitados ni que un intruso haya ejecutado operaciones.
Referencias: [configuración:22](../../whatsapp-bot/index.js#L22),
[grupoAutorizado:225](../../whatsapp-bot/index.js#L225),
[filtro de grupo:613](../../whatsapp-bot/index.js#L613),
[filtro de remitente solo privado:646–650](../../whatsapp-bot/index.js#L646).

La resolución del contacto contiene alternativas para números/LID. La representación
del mensaje es una frontera de confianza: hay que verificar identidad estable y
comportamiento ante ausencia/ambigüedad, no aceptar el nombre mostrado como identidad.
El backend `/comandos` verifica un token de servicio; los datos user_id/numero/grupo
del body no prueban por sí mismos la identidad humana. No existe una matriz humana
de permisos por comando comparable a los roles POS. Poseer el token del bot concede
capacidad de invocar comandos: no debe confundirse con autorizar al remitente.

Los logs actuales pueden incluir números, IDs de contactos/grupos y errores del
adaptador. LocalAuth y archivos de sesión son credenciales persistentes sensibles.
No se leyeron sus valores reales. El análisis de dependencias encontró avisos
conocidos; no se intentó explotarlos ni actualizar el paquete como parte de esta fase.

## Propuesta para autorizar en otra etapa

1. Definir una matriz explícita de operación → rol humano: consultas, ventas,
   gastos, caja, anulaciones/cierres. Acordar permisos comerciales antes de modificar.
2. Exigir simultáneamente grupo autorizado y remitente autorizado en grupos. Resolver
   el remitente estable y fallar cerrado ante identidad ausente/ambigua; probar LID,
   cambios de participantes, mensajes reenviados, remitente removido y grupos nuevos.
3. Autorizar operaciones también en backend. La identidad debe venir de un adaptador
   autenticado y de un contrato verificable; no confiar en un rol arbitrario del JSON.
   Evaluar token con alcance por operación y revocación, sin reutilizar la cookie POS.
4. Mantener idempotencia de mensajes, límites temporales y trazabilidad mínima sin
   teléfonos, textos completos, IDs externos ni tokens en logs generales. Definir
   retención, acceso y un vínculo interno para investigar incidentes.
5. Probar y actualizar dependencias en una copia con sesión ficticia, evaluar Node
   soportado y compatibilidad del adaptador. No reinstalar sobre el bot actual.
6. Asegurar permisos del host, backups y transporte. Proponer rotación de tokens
   reales y sesiones solo mediante procedimiento autorizado; no ejecutarla aquí.

Orden propuesto: acordar permisos/identidad → pruebas de denegación → adaptador y
backend aislados → dependencias → revisión manual → piloto ficticio autorizado.
Conservar bloqueo productivo y de integración legada hasta resolver estas decisiones.
