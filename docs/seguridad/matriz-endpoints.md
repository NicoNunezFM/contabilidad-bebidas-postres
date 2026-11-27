# Matriz de endpoints y permisos

Generada desde las rutas efectivas; controles de factories y perímetro en el informe técnico.
La API general conserva docs/OpenAPI públicos de desarrollo; no deben publicarse como perímetro productivo.
El shell estático `/pos/` es público. GET no autoriza escrituras ni cambios de privilegios.

Nota de inspección de controles internos: en `POST /pos-api/simulacion/caja-diaria/{caja}/movimientos`,
`tipo=gasto` exige Administración ([control:361](../../src/pos_api.py#L361));
la clasificación Administración o Ventas de la ruta corresponde a sus otros tipos.
Se mantiene esta restricción comercial existente, además del control de sesión.
En `POST /pos-api/simulacion/pedidos/{id_pedido}/estado`, cancelar exige Administración
([control:265](../../src/pos_seguimiento.py#L265)); otras transiciones admiten ambos perfiles.
El historial de ventas se filtra por actor para Ventas y el abono unitario valida
propiedad mediante `consultar_venta` ([control:371](../../src/pos_simulacion.py#L371)).
Clientes, abonos globales y seguimiento de pedidos conservan el acceso compartido
vigente; no se introdujo una nueva política de propiedad individual.

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
| `GET /` | Shell público, sin datos comerciales | No aplica (lectura o Bearer explícito) | [src/api.py:329](../../src/api.py#L329) |
| `POST /comandos` | Bearer bot o integración; identidad humana pendiente (bot sin cambios) | No aplica (lectura o Bearer explícito) | [src/api.py:762](../../src/api.py#L762) |
| `GET /productos` | Bearer integración; cookie POS y token bot insuficientes | No aplica (lectura o Bearer explícito) | [src/api.py:341](../../src/api.py#L341) |
| `GET /stock` | Bearer integración; cookie POS y token bot insuficientes | No aplica (lectura o Bearer explícito) | [src/api.py:357](../../src/api.py#L357) |
| `POST /ventas` | Bearer integración; cookie POS y token bot insuficientes | No aplica (lectura o Bearer explícito) | [src/api.py:383](../../src/api.py#L383) |
| `PATCH /ventas/{id_venta}/anular` | Bearer integración; cookie POS y token bot insuficientes | No aplica (lectura o Bearer explícito) | [src/api.py:400](../../src/api.py#L400) |
| `POST /compras` | Bearer integración; cookie POS y token bot insuficientes | No aplica (lectura o Bearer explícito) | [src/api.py:418](../../src/api.py#L418) |
| `PATCH /compras/{id_compra}/anular` | Bearer integración; cookie POS y token bot insuficientes | No aplica (lectura o Bearer explícito) | [src/api.py:435](../../src/api.py#L435) |
| `POST /gastos` | Bearer integración; cookie POS y token bot insuficientes | No aplica (lectura o Bearer explícito) | [src/api.py:453](../../src/api.py#L453) |
| `PATCH /gastos/{id_gasto}/anular` | Bearer integración; cookie POS y token bot insuficientes | No aplica (lectura o Bearer explícito) | [src/api.py:472](../../src/api.py#L472) |
| `POST /inventario` | Bearer integración; cookie POS y token bot insuficientes | No aplica (lectura o Bearer explícito) | [src/api.py:490](../../src/api.py#L490) |
| `GET /reportes/hoy` | Bearer integración; cookie POS y token bot insuficientes | No aplica (lectura o Bearer explícito) | [src/api.py:507](../../src/api.py#L507) |
| `GET /reportes/semana` | Bearer integración; cookie POS y token bot insuficientes | No aplica (lectura o Bearer explícito) | [src/api.py:518](../../src/api.py#L518) |
| `GET /reportes/mes` | Bearer integración; cookie POS y token bot insuficientes | No aplica (lectura o Bearer explícito) | [src/api.py:524](../../src/api.py#L524) |
| `GET /caja` | Bearer integración; cookie POS y token bot insuficientes | No aplica (lectura o Bearer explícito) | [src/api.py:534](../../src/api.py#L534) |
| `GET /caja/secciones/{seccion}` | Bearer integración; cookie POS y token bot insuficientes | No aplica (lectura o Bearer explícito) | [src/api.py:540](../../src/api.py#L540) |
| `GET /recaudado/{categoria}` | Bearer integración; cookie POS y token bot insuficientes | No aplica (lectura o Bearer explícito) | [src/api.py:560](../../src/api.py#L560) |
| `POST /caja/aportes` | Bearer integración; cookie POS y token bot insuficientes | No aplica (lectura o Bearer explícito) | [src/api.py:583](../../src/api.py#L583) |
| `POST /caja/retiros` | Bearer integración; cookie POS y token bot insuficientes | No aplica (lectura o Bearer explícito) | [src/api.py:599](../../src/api.py#L599) |
| `PATCH /caja/movimientos/{id_movimiento}/anular` | Bearer integración; cookie POS y token bot insuficientes | No aplica (lectura o Bearer explícito) | [src/api.py:615](../../src/api.py#L615) |
| `GET /diezmo/{anio}/{mes}` | Bearer integración; cookie POS y token bot insuficientes | No aplica (lectura o Bearer explícito) | [src/api.py:633](../../src/api.py#L633) |
| `POST /diezmo/reservas` | Bearer integración; cookie POS y token bot insuficientes | No aplica (lectura o Bearer explícito) | [src/api.py:645](../../src/api.py#L645) |
| `POST /diezmo/entregas` | Bearer integración; cookie POS y token bot insuficientes | No aplica (lectura o Bearer explícito) | [src/api.py:673](../../src/api.py#L673) |
| `POST /cierres/semanales` | Bearer integración; cookie POS y token bot insuficientes | No aplica (lectura o Bearer explícito) | [src/api.py:705](../../src/api.py#L705) |
| `GET /cierres/semanales` | Bearer integración; cookie POS y token bot insuficientes | No aplica (lectura o Bearer explícito) | [src/api.py:721](../../src/api.py#L721) |
| `POST /cierres/mensuales` | Bearer integración; cookie POS y token bot insuficientes | No aplica (lectura o Bearer explícito) | [src/api.py:734](../../src/api.py#L734) |
| `GET /cierres/mensuales` | Bearer integración; cookie POS y token bot insuficientes | No aplica (lectura o Bearer explícito) | [src/api.py:750](../../src/api.py#L750) |
| `POST /acciones` | Bearer integración; cookie POS y token bot insuficientes | No aplica (lectura o Bearer explícito) | [src/api.py:812](../../src/api.py#L812) |
