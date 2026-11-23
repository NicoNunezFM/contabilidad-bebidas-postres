# Abadion POS premium

El diseño usa la marca dorada de Abadion, navegación azul marino, tarjetas claras, búsqueda en el encabezado y un panel lateral para el pedido. Las fotos disponibles pertenecen al catálogo ilustrativo. Las tarjetas conectadas que carecen de una foto propia usan un ícono por categoría. El catálogo SQLite sigue siendo la fuente de precios, disponibilidad, familias y personalizaciones.

En escritorio el carrito permanece junto al catálogo. En la PCBOX el catálogo ocupa el ancho disponible y el botón inferior **Ver carrito y cobro** alterna las vistas. Los accesos lateral y superior usan los permisos de la sesión del POS. **Guardar pedido sin venta** sigue siendo una acción separada de **Confirmar venta simulada**.

## Prueba local en Windows

Desde una copia del repositorio en la rama `feature/abadion-pos-premium-ui`, abrí una ventana de PowerShell. Si la instalación local ya usa el puerto 8060, detené esa instancia antes de iniciar la prueba. Estos comandos usan un directorio temporal nuevo para Entrenamiento. El cambio de variables termina al cerrar la ventana.

```powershell
py -3.12 -m venv .venv-pos-premium
.\.venv-pos-premium\Scripts\python.exe -m pip install -r requirements-tablet-test.txt
$env:PYTHON_DOTENV_DISABLED = '1'
$env:LOCALAPPDATA = Join-Path $env:TEMP ("abadion-premium-" + [guid]::NewGuid())
New-Item -ItemType Directory -Path $env:LOCALAPPDATA | Out-Null
$env:NEGOCIO_DB_PATH = Join-Path $env:LOCALAPPDATA 'pruebas-ficticias.db'
.\.venv-pos-premium\Scripts\python.exe scripts\abadion_entrenamiento.py preparar
.\.venv-pos-premium\Scripts\python.exe scripts\abadion_entrenamiento.py servir
```

1. En Edge, abrí [POS de prueba](http://127.0.0.1:8060/pos/). Las cuentas y claves ficticias de Entrenamiento están en `USUARIOS` de `scripts/abadion_entrenamiento.py`.
2. Ingresá como Ventas. Agregá una comida y una bebida. Probá una personalización, un extra y las cantidades del carrito. Revisá los subtotales de rotisería y de bebidas y postres.
3. Validá el pedido y elegí **Guardar pedido sin venta**. Comprobá que aparece en **Pedidos** y que el **Historial simulado** sigue vacío. Pasalo a preparación y confirmá una venta ficticia desde el pedido cuando corresponda.
4. Volvé a entrar como Administración y verificá los accesos de precios, extras y cajas. Probá también el carrito en [modo PCBOX](http://127.0.0.1:8060/pos/?tablet=1), con la emulación de Edge en 1024 × 600 y 600 × 1024 píxeles CSS.
5. Detené el servidor con `Ctrl+C`. Para ver solo la demostración offline, abrí `pos-web/demo-tablet.html`.

## Pruebas y capturas

Ejecutá estas pruebas desde una segunda ventana de PowerShell. Para generar capturas también en local, definí `POS_UI_CAPTURAS` con un directorio de salida.

```powershell
$env:PYTHON_DOTENV_DISABLED = '1'
$env:NEGOCIO_DB_PATH = Join-Path $env:TEMP ("abadion-pytest-" + [guid]::NewGuid() + ".db")
.\.venv-pos-premium\Scripts\python.exe -m pytest -q
$env:POS_TEST_BROWSER = "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe"
$env:POS_UI_CAPTURAS = Join-Path $env:TEMP 'abadion-pos-capturas'
.\.venv-pos-premium\Scripts\python.exe -m pytest -q tests/test_pos_web.py tests/test_demo_tablet.py tests/test_tablet_https.py
```

GitHub Actions publica las capturas en el artefacto `abadion-pos-capturas`. El recorrido visual comprueba las columnas, el ancho del documento, la alternancia del carrito y la conservación de sus cuatro líneas de ejemplo. El recorrido conectado confirma el registro del pedido y consulta el historial antes de convertirlo en venta.

## PCBOX y Android 6

La comprobación automatizada en Edge reproduce los tamaños de prueba de la PCBOX PCB-T715. Quedan por verificar el tamaño CSS efectivo, el rendimiento, el motor del navegador integrado y la confianza en certificados en el equipo físico. La alternancia del carrito sigue usando un control HTML nativo. Los flujos conectados mantienen los requisitos de JavaScript y de contexto seguro del POS existente. Si el navegador integrado no ejecuta el POS completo, la demo offline permite verificar la navegación básica y las personalizaciones ficticias.
