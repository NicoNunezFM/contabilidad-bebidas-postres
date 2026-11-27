# Abadion — revisión de seguridad 2.4

Propuesta del [PR #42 en borrador](https://github.com/NicoNunezFM/contabilidad-bebidas-postres/pull/42),
contra la rama del PR #41. **Producción e integración legada continúan bloqueadas.**
No se modificaron bases ni instalaciones reales, infraestructura o bot de WhatsApp.

| Documento | Contenido |
| --- | --- |
| [Auditoría previa](auditoria-previa.md) | Hallazgos comprobados, gravedad, hipótesis y referencias congeladas de #41 |
| [Matriz de endpoints](matriz-endpoints.md) | Sesiones, roles, credenciales de servicio, CSRF y restricciones internas por operación |
| [Informe técnico](informe-tecnico.md) | Autenticación y autorización explicadas, correcciones, modelo de amenazas, esquema y recuperación |
| [Pruebas](pruebas.md) | Suites, comparación de los 647 casos, cambios justificados de pruebas, omisiones y limitaciones |
| [Jornada ficticia](comparacion-jornada.json) | Comparación de saldos, costos y resultados contra #41 |
| [Propuesta WhatsApp](propuesta-whatsapp.md) | Grupos/remitentes/permisos/logs y actualización aislada de dependencias; sin aplicar cambios al bot |

Los inventarios JSON y los informes de dependencias de este directorio contienen
evidencia reproducible del código/manifiestos, no información de una instalación real.
Un resultado favorable de pruebas no demuestra seguridad completa. Los avisos Node,
la validación del perímetro/host real y las decisiones enumeradas en el informe
requieren una etapa independiente antes de considerar producción.
