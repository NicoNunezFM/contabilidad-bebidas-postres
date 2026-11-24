# Abadion V1.0 en Windows y Edge

## Procedencia y conflictos

| Referencia | Commit | Aporte |
| --- | --- | --- |
| Ancestro común | `5d44eba6d18363789253d63df7cc58f448e849e1` | POS Premium anterior a los cambios de ambos caminos |
| PR #28 | `35949f0f100161154a4bb3712598d4f6ebb1821d` | Orden visual, X, Escape y flujo de tres pasos |
| PR #31 | `067b9cab161b872e5856edf71734cad57ff02efd` | Incluye #28 y agrega variantes de bebidas y postres, Especial y controles táctiles |
| PR #32 | `5537d8c0f889ac8f3b9d4a3ef9e0cbd9017698be` | Base directa de esta rama y fuente de todos los componentes de preproducción |

El árbol de #31 aporta `pos-web/index.html`, la demo autónoma y las guías de interfaz. Las dos ramas cambiaron `.github/workflows/abadion-pos.yml` y `tests/test_pos_web.py`. El workflow conserva el conjunto de #32 y publica las capturas del flujo en preproducción. La prueba del aviso incorpora la espera de #29 al archivo de #31. El flujo táctil se ejecuta también contra la app de preproducción, en una SQLite que carga el catálogo de ensayo por el actualizador de #32. El fixture elimina el adicional reservado de Entrenamiento y sus referencias antes de validar el JSON.

La contabilidad, los permisos, los launchers y los módulos de almacenamiento y respaldo provienen íntegramente de #32. `Especial` es el nombre visible de la pizza del catálogo y mantiene su ID e historial.

## Cobertura

| Parte | Evidencia reproducible |
| --- | --- |
| Catálogo y controles | Edge verifica orden, variantes, arriba/abajo de 48 px, mouse, teclado y toque emulado, grupos de Manaos y postres, Especial y postre del catálogo sin opciones de cocina |
| Borrador y carrito | La prueba Edge parametrizada cubre retroceso, cancelación, X, Escape, foco, límites por existencia y doble clic en confirmar. Verifica líneas, unidades y subtotales por grupo |
| Preparación, cobros y permisos | Regresión Edge de pedidos, caja diaria, fiado, devolución y acceso por rol. En la jornada por HTTP, Ventas recibe 403 al intentar una devolución y Administración puede confirmarla |
| Jornada persistente | Worker real en un puerto efímero. Apertura, venta mixta con reintento, devolución con reintento, compra, gasto, fiado con abono parcial, dos arqueos y dos cierres. Saldos esperados en centavos: comidas 11.000, bebidas y postres 12.000. Saldo de deuda 1.500. Stock final: 7 comidas y 11 bebidas |
| Reinicio y restauración | Detención cooperativa y nuevo proceso contra la misma SQLite. Se verifica el snapshot y se recupera en una carpeta independiente de la misma identidad. Se compara la conciliación, los dos historiales de caja, las ventas, la cuenta del cliente y el stock, y se verifica la auditoría de la recuperación |
| SQLite y catálogo | Suites de #32 para bloqueo, interrupciones y WAL, copias verificadas, rechazo de corrupción y catálogo con vista previa, SHA-256 y conservación de IDs e históricos |

Los resultados de GitHub Actions del commit integrado se publican en el PR. Quedan fuera del alcance de esta corrida el reinicio físico de Windows, el uso de una pantalla táctil física y la recuperación desde un respaldo externo en otra PC.

## Repetir en Windows

En PowerShell con Git, Edge y Python 3.12:

```powershell
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true
$qa = Join-Path ([IO.Path]::GetTempPath()) ('abadion-v1-' + [guid]::NewGuid())
git clone --single-branch --branch integration/abadion-v1-pos-persistente https://github.com/NicoNunezFM/contabilidad-bebidas-postres.git $qa
if ($LASTEXITCODE -ne 0) { throw 'Falló git clone' }
Set-Location -LiteralPath $qa
py -3.12 -m venv .venv
if ($LASTEXITCODE -ne 0) { throw 'Falló la creación del entorno' }
$python = Join-Path $qa '.venv\Scripts\python.exe'
& $python -m pip install -r requirements-tablet-test.txt
if ($LASTEXITCODE -ne 0) { throw 'Falló la instalación de dependencias' }

$env:PYTHON_DOTENV_DISABLED = '1'
$env:PYTHONUTF8 = '1'
$env:NEGOCIO_DB_PATH = Join-Path $qa 'negocio-qa-ficticio.db'
$env:POS_TEST_BROWSER = "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe"
$env:POS_UI_CAPTURAS = Join-Path $qa 'capturas'
if (!(Test-Path -LiteralPath $env:POS_TEST_BROWSER)) { throw 'Ajustá POS_TEST_BROWSER a la ruta de Edge' }

& $python -m pytest -q tests/test_preproduccion_jornada_v1.py tests/test_preproduccion_catalogo_edge.py tests/test_pos_web.py
if ($LASTEXITCODE -ne 0) { throw 'Falló la validación de integración' }
& $python -m pytest -q --junitxml=regresion-v1.xml
if ($LASTEXITCODE -ne 0) { throw 'Falló la regresión' }
```

Los tests de Edge y la jornada integrada usan puertos efímeros. La prueba heredada del launcher que necesita el 8078 se omite si el puerto está ocupado. La guía de catálogo, respaldo y restauración offline describe los comandos de mantenimiento sobre una carpeta nueva. [Consolidación Windows](consolidacion-preproduccion-windows-v1.md)
