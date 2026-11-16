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
