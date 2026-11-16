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

`POST /pos-api/simulacion/ventas` recibe los `items` de la validación, un UUID `id_solicitud` y el `total_esperado_centavos` devuelto por el servidor. Requiere sesión POS y origen del servidor. La misma solicitud por el mismo usuario devuelve la venta ya registrada, incluso si cambia el catálogo. Reusar el UUID con datos distintos devuelve `409`.

La venta se guarda en `pos_ventas_simuladas` y descuenta stock ficticio dentro de una transacción `BEGIN IMMEDIATE`. El servidor vuelve a calcular el pedido en esa misma transacción. Un error revierte el registro y el descuento. La API exige que la base tenga la marca SQLite de simulación y que `POS_V1_SIMULACION=1`. El script solo crea archivos nuevos. Los registros están aislados de las ventas del bot y de la contabilidad existente.

Pruebas focalizadas: `python -m pytest -q tests/test_pos_simulacion.py`.
