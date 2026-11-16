# Abadion POS V1

## 1. Validar un pedido

En el catálogo de SQLite, armá un pedido de prueba y elegí **Validar pedido de prueba**. El POS muestra el total calculado por el servidor. El botón de cobro del catálogo SQLite sigue deshabilitado.

`POST /pos-api/pedidos/validar` requiere sesión POS de ventas o administración y el encabezado `Origin` del servidor. Ejemplo de cuerpo con IDs ficticios:

```json
{"items":[{"id_producto":1,"cantidad":2,"ingredientes_quitados":["Limón"],"ids_adicionales":[1]}]}
```

- SQLite aporta el precio base, los extras activos permitidos y los ingredientes removibles. Cada adicional seleccionado se aplica a cada unidad de la línea.
- El servidor suma las cantidades de todas las líneas del mismo producto para comprobar su stock. Respeta `controla_stock` y mantiene las personalizaciones de cada línea.
- Los importes de respuesta son centavos enteros. El precio unitario de catálogo se redondea al centavo más cercano, con los medios centavos hacia arriba, antes de multiplicar por la cantidad.
- `404` indica que falta un producto. `409` indica problemas de precio o stock. `422` indica un pedido o personalización inválidos.
- La consulta usa una transacción de solo lectura. La validación refleja la disponibilidad al momento de consultar y no reserva unidades, registra ventas ni movimientos de caja.

### Pruebas

En PowerShell, desde el repositorio:

```powershell
$env:NEGOCIO_DB_PATH = Join-Path $env:TEMP 'abadion-pos-v1-pruebas.db'
python -m pytest -q tests/test_pos_pedidos.py
```

Las pruebas inicializan bases SQLite ficticias por caso mediante `tmp_path`.

## 2. Registrar ventas simuladas

Prepará una base nueva y arrancá FastAPI localmente. El script pide contraseñas para `admin` y `ventas` y carga dos productos ficticios.

```powershell
$rutaPos = Join-Path $env:TEMP 'abadion-pos-v1-simulacion.db'
python scripts/preparar_simulacion_pos.py $rutaPos
# Continuá solo si la creación fue exitosa.
$env:NEGOCIO_DB_PATH = $rutaPos
$env:POS_V1_SIMULACION = '1'
python -m uvicorn api:app --app-dir src --host 127.0.0.1
```

`POST /pos-api/simulacion/ventas` recibe los `items` de la validación, un UUID `id_solicitud`, el `total_esperado_centavos` devuelto por el servidor y el `medio_pago`. Requiere sesión POS y origen del servidor. La misma solicitud por el mismo usuario devuelve la venta ya registrada con su estado de anulación actual, incluso si cambia el catálogo. Reusar el UUID con datos distintos devuelve `409`.

La venta se guarda en `pos_ventas_simuladas` y descuenta stock ficticio dentro de una transacción `BEGIN IMMEDIATE`. El servidor vuelve a calcular el pedido en esa misma transacción. Un error revierte el registro y el descuento. La API exige que la base tenga la marca SQLite de simulación y que `POS_V1_SIMULACION=1`. Con esa opción, FastAPI valida la base antes de arrancar y conserva el catálogo ficticio preparado por el script. El script solo crea archivos nuevos. Los registros están aislados de las ventas del bot y de la contabilidad existente.

Pruebas focalizadas: `python -m pytest -q tests/test_pos_simulacion.py`.

## 3. Cajas y medios de pago simulados

Agregá `medio_pago` al cuerpo del registro de venta. Los valores admitidos son `efectivo`, `transferencia` y `mercado_pago`. Cada venta usa un solo medio para el pedido completo. Estos valores sirven para clasificar importes ficticios en SQLite.

Las líneas de bebidas y postres se imputan a `bebidas_postres`. Las demás se imputan a `comidas`. Un pedido mixto genera un movimiento por cada caja involucrada. La venta, el descuento de stock y los movimientos se confirman juntos.

`GET /pos-api/simulacion/cajas` requiere sesión de administración y muestra los saldos en centavos por caja y medio de pago. Las pruebas cubren pedidos mixtos, permisos y reversión de los movimientos ante un fallo de stock.

## 4. Anulaciones, historial y permisos

- `POST /pos-api/simulacion/ventas/{id_venta}/anulacion` recibe `{"motivo":"Error de prueba"}` y requiere sesión de administración y origen del servidor. Restaura el stock descontado al registrar la venta y agrega movimientos inversos con la caja y el medio originales. Guarda el motivo, el usuario y la fecha UTC. Repetir la anulación devuelve `409`.
- `GET /pos-api/simulacion/ventas` muestra el historial más reciente primero. Una sesión de ventas ve sus propias operaciones y administración puede ver todas. Pasá `limite` de 1 a 100 y usá `siguiente_antes_de` como `antes_de` para obtener la página siguiente. Cada venta conserva los precios y personalizaciones del momento del registro.
- Las rutas de simulación quedan deshabilitadas por defecto. Para probarlas con este esquema, prepará una base ficticia nueva con el script de esta revisión. El flujo web valida el pedido, mientras que registro simulado, cajas, historial y anulación se prueban mediante la API. La rama no integra procesamiento de pagos.

### Ejemplo local de venta ficticia

En otra terminal, con FastAPI ejecutándose sobre la base preparada en la etapa 2:

```powershell
$origenPos = 'http://127.0.0.1:8000'
$apiPos = "$origenPos/pos-api"
$cabeceras = @{ Origin = $origenPos }
$cuenta = Get-Credential -UserName ventas -Message 'Cuenta de la base ficticia'
$login = @{ usuario = $cuenta.UserName; contrasena = $cuenta.GetNetworkCredential().Password }
Invoke-RestMethod "$apiPos/login" -Method Post -Headers $cabeceras -ContentType 'application/json' -Body ($login | ConvertTo-Json) -SessionVariable sesionPos
Remove-Variable login, cuenta

$pedido = @{ items = @(@{ id_producto = 1; cantidad = 2 }, @{ id_producto = 2; cantidad = 1 }) }
$validado = Invoke-RestMethod "$apiPos/pedidos/validar" -Method Post -WebSession $sesionPos -Headers $cabeceras -ContentType 'application/json' -Body ($pedido | ConvertTo-Json -Depth 5)
$venta = $pedido + @{
    id_solicitud = [guid]::NewGuid().ToString()
    total_esperado_centavos = $validado.total_centavos
    medio_pago = 'efectivo'
}
$registrada = Invoke-RestMethod "$apiPos/simulacion/ventas" -Method Post -WebSession $sesionPos -Headers $cabeceras -ContentType 'application/json' -Body ($venta | ConvertTo-Json -Depth 5)
Invoke-RestMethod "$apiPos/simulacion/ventas" -WebSession $sesionPos
```

Para consultar ambas cajas o anular `$registrada.id_venta`, iniciá sesión con la cuenta ficticia de `admin` y usá esa sesión en las rutas indicadas arriba.

La suite focalizada comprueba permisos, origen, paginación, reintentos, concurrencia sobre stock y reversión contable. Para probar toda la regresión con bases ficticias:

```powershell
$env:NEGOCIO_DB_PATH = Join-Path $env:TEMP 'abadion-pos-v1-suite.db'
python -m pytest -q
```
