# Matriz de endpoints y permisos

Generada desde las rutas efectivas; controles de factories y perímetro en el informe técnico.
La API general conserva docs/OpenAPI públicos de desarrollo; no deben publicarse como perímetro productivo.
El shell estático `/pos/` es público. GET no autoriza escrituras ni cambios de privilegios.

| Método/ruta | Permiso | CSRF | Referencia |
| --- | --- | --- | --- |
| `POST /pos-api/login` | Público: Origin exacto y límite temporal de intentos | Origin exacto, sin duplicados, Sec-Fetch-Site; SameSite strict | [src/pos_api.py:145](../../src/pos_api.py#L145) |
| `GET /pos-api/yo` | Administración o Ventas | No aplica (lectura o Bearer explícito) | [src/pos_api.py:207](../../src/pos_api.py#L207) |
| `POST /pos-api/pedidos/validar` | Administración o Ventas | Origin exacto, sin duplicados, Sec-Fetch-Site; SameSite strict | [src/pos_api.py:212](../../src/pos_api.py#L212) |
| `GET /pos-api/simulacion/estado` | Público: capacidades ficticias sin datos personales | No aplica (lectura o Bearer explícito) | [src/pos_api.py:226](../../src/pos_api.py#L226) |
| `GET /pos-api/simulacion/caja-diaria` | Administración o Ventas | No aplica (lectura o Bearer explícito) | [src/pos_api.py:282](../../src/pos_api.py#L282) |
| `GET /pos-api/simulacion/caja-diaria/{caja}/historial` | Administración o Ventas | No aplica (lectura o Bearer explícito) | [src/pos_api.py:289](../../src/pos_api.py#L289) |
| `GET /pos-api/simulacion/caja-diaria/alertas` | Administración | No aplica (lectura o Bearer explícito) | [src/pos_api.py:301](../../src/pos_api.py#L301) |
| `GET /pos-api/simulacion/caja-diaria/{caja}/historial/{id_jornada}` | Administración o Ventas | No aplica (lectura o Bearer explícito) | [src/pos_api.py:312](../../src/pos_api.py#L312) |
| `POST /pos-api/simulacion/caja-diaria/{caja}/apertura` | Administración o Ventas | Origin exacto, sin duplicados, Sec-Fetch-Site; SameSite strict | [src/pos_api.py:332](../../src/pos_api.py#L332) |
| `POST /pos-api/simulacion/caja-diaria/{caja}/arqueo` | Administración o Ventas | Origin exacto, sin duplicados, Sec-Fetch-Site; SameSite strict | [src/pos_api.py:340](../../src/pos_api.py#L340) |
| `POST /pos-api/simulacion/caja-diaria/{caja}/cierre` | Administración o Ventas | Origin exacto, sin duplicados, Sec-Fetch-Site; SameSite strict | [src/pos_api.py:348](../../src/pos_api.py#L348) |
| `POST /pos-api/simulacion/caja-diaria/{caja}/movimientos` | Administración o Ventas | Origin exacto, sin duplicados, Sec-Fetch-Site; SameSite strict | [src/pos_api.py:356](../../src/pos_api.py#L356) |
| `GET /pos-api/simulacion/compras` | Administración | No aplica (lectura o Bearer explícito) | [src/pos_api.py:374](../../src/pos_api.py#L374) |
| `POST /pos-api/simulacion/compras` | Administración | Origin exacto, sin duplicados, Sec-Fetch-Site; SameSite strict | [src/pos_api.py:384](../../src/pos_api.py#L384) |
| `POST /pos-api/simulacion/compras/{id_compra}/{evento}` | Administración | Origin exacto, sin duplicados, Sec-Fetch-Site; SameSite strict | [src/pos_api.py:392](../../src/pos_api.py#L392) |
| `GET /pos-api/simulacion/clientes` | Administración o Ventas | No aplica (lectura o Bearer explícito) | [src/pos_api.py:408](../../src/pos_api.py#L408) |
| `POST /pos-api/simulacion/clientes` | Administración o Ventas | Origin exacto, sin duplicados, Sec-Fetch-Site; SameSite strict | [src/pos_api.py:413](../../src/pos_api.py#L413) |
| `GET /pos-api/simulacion/clientes/{id_cliente}` | Administración o Ventas | No aplica (lectura o Bearer explícito) | [src/pos_api.py:420](../../src/pos_api.py#L420) |
| `POST /pos-api/simulacion/clientes/{id_cliente}/abonos/vista-previa` | Administración o Ventas | Origin exacto, sin duplicados, Sec-Fetch-Site; SameSite strict | [src/pos_api.py:425](../../src/pos_api.py#L425) |
| `POST /pos-api/simulacion/clientes/{id_cliente}/abonos` | Administración o Ventas | Origin exacto, sin duplicados, Sec-Fetch-Site; SameSite strict | [src/pos_api.py:431](../../src/pos_api.py#L431) |
| `POST /pos-api/simulacion/clientes/{id_cliente}/abonos/{uuid_abono}/correccion` | Administración | Origin exacto, sin duplicados, Sec-Fetch-Site; SameSite strict | [src/pos_api.py:438](../../src/pos_api.py#L438) |
| `POST /pos-api/simulacion/ventas` | Administración o Ventas | Origin exacto, sin duplicados, Sec-Fetch-Site; SameSite strict | [src/pos_api.py:448](../../src/pos_api.py#L448) |
| `POST /pos-api/simulacion/pedidos` | Administración o Ventas | Origin exacto, sin duplicados, Sec-Fetch-Site; SameSite strict | [src/pos_api.py:458](../../src/pos_api.py#L458) |
| `GET /pos-api/simulacion/pedidos/{id_pedido}/cotizacion` | Administración o Ventas | No aplica (lectura o Bearer explícito) | [src/pos_api.py:468](../../src/pos_api.py#L468) |
| `POST /pos-api/simulacion/pedidos/{id_pedido}/venta` | Administración o Ventas | Origin exacto, sin duplicados, Sec-Fetch-Site; SameSite strict | [src/pos_api.py:476](../../src/pos_api.py#L476) |
| `GET /pos-api/simulacion/pedidos` | Administración o Ventas | No aplica (lectura o Bearer explícito) | [src/pos_api.py:487](../../src/pos_api.py#L487) |
| `POST /pos-api/simulacion/pedidos/{id_pedido}/estado` | Administración o Ventas | Origin exacto, sin duplicados, Sec-Fetch-Site; SameSite strict | [src/pos_api.py:500](../../src/pos_api.py#L500) |
| `GET /pos-api/simulacion/ventas` | Administración o Ventas | No aplica (lectura o Bearer explícito) | [src/pos_api.py:514](../../src/pos_api.py#L514) |
| `POST /pos-api/simulacion/ventas/{id_venta}/anulacion` | Administración | Origin exacto, sin duplicados, Sec-Fetch-Site; SameSite strict | [src/pos_api.py:523](../../src/pos_api.py#L523) |
| `POST /pos-api/simulacion/ventas/{id_venta}/abonos` | Administración o Ventas | Origin exacto, sin duplicados, Sec-Fetch-Site; SameSite strict | [src/pos_api.py:534](../../src/pos_api.py#L534) |
| `POST /pos-api/simulacion/ventas/{id_venta}/devoluciones` | Administración | Origin exacto, sin duplicados, Sec-Fetch-Site; SameSite strict | [src/pos_api.py:545](../../src/pos_api.py#L545) |
| `POST /pos-api/simulacion/ventas/{id_venta}/fondos-reparto/{tipo}` | Administración | Origin exacto, sin duplicados, Sec-Fetch-Site; SameSite strict | [src/pos_api.py:556](../../src/pos_api.py#L556) |
| `POST /pos-api/simulacion/cobros/{id_cobro}/rendiciones` | Administración | Origin exacto, sin duplicados, Sec-Fetch-Site; SameSite strict | [src/pos_api.py:575](../../src/pos_api.py#L575) |
| `POST /pos-api/simulacion/cajas/transferencias` | Administración | Origin exacto, sin duplicados, Sec-Fetch-Site; SameSite strict | [src/pos_api.py:590](../../src/pos_api.py#L590) |
| `POST /pos-api/simulacion/cierres` | Administración | Origin exacto, sin duplicados, Sec-Fetch-Site; SameSite strict | [src/pos_api.py:600](../../src/pos_api.py#L600) |
| `GET /pos-api/simulacion/cierres/{periodo}` | Administración | No aplica (lectura o Bearer explícito) | [src/pos_api.py:610](../../src/pos_api.py#L610) |
| `GET /pos-api/simulacion/cajas` | Administración | No aplica (lectura o Bearer explícito) | [src/pos_api.py:617](../../src/pos_api.py#L617) |
| `GET /pos-api/simulacion/contabilidad` | Administración | No aplica (lectura o Bearer explícito) | [src/pos_api.py:622](../../src/pos_api.py#L622) |
| `GET /pos-api/simulacion/conciliacion` | Administración | No aplica (lectura o Bearer explícito) | [src/pos_api.py:637](../../src/pos_api.py#L637) |
| `GET /pos-api/simulacion/conciliacion-financiera` | Administración | No aplica (lectura o Bearer explícito) | [src/pos_api.py:644](../../src/pos_api.py#L644) |
| `GET /pos-api/simulacion/cajas/movimientos` | Administración | No aplica (lectura o Bearer explícito) | [src/pos_api.py:653](../../src/pos_api.py#L653) |
| `POST /pos-api/logout` | Origin exacto; revoca cookie presentada, idempotente sin sesión | Origin exacto, sin duplicados, Sec-Fetch-Site; SameSite strict | [src/pos_api.py:662](../../src/pos_api.py#L662) |
| `GET /pos-api/admin/verificar` | Administración | No aplica (lectura o Bearer explícito) | [src/pos_api.py:682](../../src/pos_api.py#L682) |
| `PATCH /pos-api/admin/productos/{id_producto}/precio` | Administración | Origin exacto, sin duplicados, Sec-Fetch-Site; SameSite strict | [src/pos_api.py:694](../../src/pos_api.py#L694) |
| `GET /pos-api/catalogo/productos` | Público solo con marca ficticia válida; sesión en legado | No aplica (lectura o Bearer explícito) | [src/pos_api.py:781](../../src/pos_api.py#L781) |
| `GET /pos-api/catalogo/adicionales` | Público solo con marca ficticia válida; sesión en legado | No aplica (lectura o Bearer explícito) | [src/pos_api.py:822](../../src/pos_api.py#L822) |
| `GET /pos-api/catalogo/productos/{id_producto}/personalizaciones` | Público solo con marca ficticia válida; sesión en legado | No aplica (lectura o Bearer explícito) | [src/pos_api.py:856](../../src/pos_api.py#L856) |
| `PUT /pos-api/admin/productos/{id_producto}/personalizaciones` | Administración | Origin exacto, sin duplicados, Sec-Fetch-Site; SameSite strict | [src/pos_api.py:893](../../src/pos_api.py#L893) |
| `PATCH /pos-api/admin/adicionales/{id_adicional}/precio` | Administración | Origin exacto, sin duplicados, Sec-Fetch-Site; SameSite strict | [src/pos_api.py:1032](../../src/pos_api.py#L1032) |
| `GET /pos-api/simulacion/saldo-unificado` | Administración o Ventas | No aplica (lectura o Bearer explícito) | [src/pos_api.py:1122](../../src/pos_api.py#L1122) |
| `POST /pos-api/simulacion/saldo-unificado/deudas/{numero}/pago` | Administración | Origin exacto, sin duplicados, Sec-Fetch-Site; SameSite strict | [src/pos_api.py:1128](../../src/pos_api.py#L1128) |
| `POST /pos-api/simulacion/saldo-unificado/bebidas/{producto}/validar` | Administración | Origin exacto, sin duplicados, Sec-Fetch-Site; SameSite strict | [src/pos_api.py:1136](../../src/pos_api.py#L1136) |
| `POST /pos-api/simulacion/saldo-unificado/pagos/{numero}/reverso` | Administración | Origin exacto, sin duplicados, Sec-Fetch-Site; SameSite strict | [src/pos_api.py:1144](../../src/pos_api.py#L1144) |
| `GET /pos-api/simulacion/saldo-unificado/conciliacion` | Administración | No aplica (lectura o Bearer explícito) | [src/pos_api.py:1152](../../src/pos_api.py#L1152) |
| `POST /pos-api/simulacion/saldo-unificado/cierres` | Administración | Origin exacto, sin duplicados, Sec-Fetch-Site; SameSite strict | [src/pos_api.py:1158](../../src/pos_api.py#L1158) |
| `GET /` | Shell público, sin datos comerciales | No aplica (lectura o Bearer explícito) | [src/api.py:338](../../src/api.py#L338) |
| `POST /comandos` | Bearer bot o integración; identidad humana pendiente (bot sin cambios) | No aplica (lectura o Bearer explícito) | [src/api.py:771](../../src/api.py#L771) |
| `GET /productos` | Bearer integración; cookie POS y token bot insuficientes | No aplica (lectura o Bearer explícito) | [src/api.py:350](../../src/api.py#L350) |
| `GET /stock` | Bearer integración; cookie POS y token bot insuficientes | No aplica (lectura o Bearer explícito) | [src/api.py:366](../../src/api.py#L366) |
| `POST /ventas` | Bearer integración; cookie POS y token bot insuficientes | No aplica (lectura o Bearer explícito) | [src/api.py:392](../../src/api.py#L392) |
| `PATCH /ventas/{id_venta}/anular` | Bearer integración; cookie POS y token bot insuficientes | No aplica (lectura o Bearer explícito) | [src/api.py:409](../../src/api.py#L409) |
| `POST /compras` | Bearer integración; cookie POS y token bot insuficientes | No aplica (lectura o Bearer explícito) | [src/api.py:427](../../src/api.py#L427) |
| `PATCH /compras/{id_compra}/anular` | Bearer integración; cookie POS y token bot insuficientes | No aplica (lectura o Bearer explícito) | [src/api.py:444](../../src/api.py#L444) |
| `POST /gastos` | Bearer integración; cookie POS y token bot insuficientes | No aplica (lectura o Bearer explícito) | [src/api.py:462](../../src/api.py#L462) |
| `PATCH /gastos/{id_gasto}/anular` | Bearer integración; cookie POS y token bot insuficientes | No aplica (lectura o Bearer explícito) | [src/api.py:481](../../src/api.py#L481) |
| `POST /inventario` | Bearer integración; cookie POS y token bot insuficientes | No aplica (lectura o Bearer explícito) | [src/api.py:499](../../src/api.py#L499) |
| `GET /reportes/hoy` | Bearer integración; cookie POS y token bot insuficientes | No aplica (lectura o Bearer explícito) | [src/api.py:516](../../src/api.py#L516) |
| `GET /reportes/semana` | Bearer integración; cookie POS y token bot insuficientes | No aplica (lectura o Bearer explícito) | [src/api.py:527](../../src/api.py#L527) |
| `GET /reportes/mes` | Bearer integración; cookie POS y token bot insuficientes | No aplica (lectura o Bearer explícito) | [src/api.py:533](../../src/api.py#L533) |
| `GET /caja` | Bearer integración; cookie POS y token bot insuficientes | No aplica (lectura o Bearer explícito) | [src/api.py:543](../../src/api.py#L543) |
| `GET /caja/secciones/{seccion}` | Bearer integración; cookie POS y token bot insuficientes | No aplica (lectura o Bearer explícito) | [src/api.py:549](../../src/api.py#L549) |
| `GET /recaudado/{categoria}` | Bearer integración; cookie POS y token bot insuficientes | No aplica (lectura o Bearer explícito) | [src/api.py:569](../../src/api.py#L569) |
| `POST /caja/aportes` | Bearer integración; cookie POS y token bot insuficientes | No aplica (lectura o Bearer explícito) | [src/api.py:592](../../src/api.py#L592) |
| `POST /caja/retiros` | Bearer integración; cookie POS y token bot insuficientes | No aplica (lectura o Bearer explícito) | [src/api.py:608](../../src/api.py#L608) |
| `PATCH /caja/movimientos/{id_movimiento}/anular` | Bearer integración; cookie POS y token bot insuficientes | No aplica (lectura o Bearer explícito) | [src/api.py:624](../../src/api.py#L624) |
| `GET /diezmo/{anio}/{mes}` | Bearer integración; cookie POS y token bot insuficientes | No aplica (lectura o Bearer explícito) | [src/api.py:642](../../src/api.py#L642) |
| `POST /diezmo/reservas` | Bearer integración; cookie POS y token bot insuficientes | No aplica (lectura o Bearer explícito) | [src/api.py:654](../../src/api.py#L654) |
| `POST /diezmo/entregas` | Bearer integración; cookie POS y token bot insuficientes | No aplica (lectura o Bearer explícito) | [src/api.py:682](../../src/api.py#L682) |
| `POST /cierres/semanales` | Bearer integración; cookie POS y token bot insuficientes | No aplica (lectura o Bearer explícito) | [src/api.py:714](../../src/api.py#L714) |
| `GET /cierres/semanales` | Bearer integración; cookie POS y token bot insuficientes | No aplica (lectura o Bearer explícito) | [src/api.py:730](../../src/api.py#L730) |
| `POST /cierres/mensuales` | Bearer integración; cookie POS y token bot insuficientes | No aplica (lectura o Bearer explícito) | [src/api.py:743](../../src/api.py#L743) |
| `GET /cierres/mensuales` | Bearer integración; cookie POS y token bot insuficientes | No aplica (lectura o Bearer explícito) | [src/api.py:759](../../src/api.py#L759) |
| `POST /acciones` | Bearer integración; cookie POS y token bot insuficientes | No aplica (lectura o Bearer explícito) | [src/api.py:821](../../src/api.py#L821) |
