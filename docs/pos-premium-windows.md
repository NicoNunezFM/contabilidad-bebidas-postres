# POS premium integrado para Windows y Edge

## Plan de integración

La base es el PR #26 en `98f3c01`. El PR #24 en `d160fc5` diverge desde `1c0f218` y solamente se incorpora su interfaz premium para el POS, junto con las pruebas pertinentes. Se integra el HTML y las pruebas por comparación de tres versiones. Los launchers remotos, la demo estática y su generador quedan fuera de esta etapa. El backend contable e historial provienen del PR #26.

La interfaz premium conserva los contratos del catálogo, pedidos, ventas, clientes, caja diaria y reportes. Los controles operativos de #26 agregan propuesta y diferencia de apertura, alertas, permisos de caja y confirmación del faltante. El PR visual no incluye compras administrativas en su navegación. Se conectan las operaciones al router ficticio de compras de #25 y se reutilizan autenticación, guardado de reintentos y validación del servidor. La prueba Windows usa el launcher de Entrenamiento mediante un directorio temporal explícito y sólo loopback.

## Selección de comidas y complementos

La rama `feature/abadion-premium-catalogo-tres-pasos` parte del PR #27 en `5d44eba`. El catálogo SQLite se presenta en el orden Todas, Sándwiches, Al plato, Hamburguesas, Pizzas, Conos, Postres y Bebidas. Las categorías adicionales aparecen al final. «Todas» conserva el orden de cada grupo que entrega el catálogo.

El POS usa `familia_menu` y `variante_menu` cuando el catálogo las provee. La personalización usa el endpoint vigente de ingredientes, adicionales y opciones de preparación. Si falta un paso visual, el flujo avanza al siguiente. Tras elegir cualquier comida, el POS ofrece las bebidas y los postres del catálogo cargado. Se pueden cargar varias unidades y ambos tipos de complemento en el mismo pedido. Los complementos con stock controlado muestran el máximo que queda al descontar lo que ya está en el carrito. La validación y confirmación de stock del servidor siguen vigentes.

Volver conserva las selecciones del borrador. Cancelar, X y Escape descartan el borrador, con la acción de regreso propia de los diálogos que la incluyen. Al confirmar, cada producto se agrega como línea independiente. Al editar una línea o agregar una bebida o postre directamente, se conserva el flujo habitual.

En el launcher ficticio de Windows, seleccioná un sándwich, una milanesa al plato, una hamburguesa, una pizza y un cono. Comprobá que todos lleguen al ofrecimiento, incluso cuando se omite la selección de variante. Volvé desde el ofrecimiento y revisá los ingredientes y cantidades elegidos. Confirmá una comida con dos bebidas y un postre y verificá los subtotales antes de guardar el pedido o cobrarlo. Repetí el flujo cancelando en cada ventana y verificá el carrito. La demo HTML autónoma incluye la X y sigue usando su catálogo de ejemplo sin SQLite.

La prueba `test_pos_web_comidas_complementos_y_cancelacion` usa una base temporal de Entrenamiento. Si se define `POS_UI_CAPTURAS`, genera una captura por paso. El trabajo de Edge en Windows publica esas capturas con los resultados del PR.

## Matriz funcional

| Área | Ventas | Administración | Evidencia |
| --- | --- | --- | --- |
| Sesión, catálogo, búsqueda, personalizaciones y carrito | Disponible | Disponible | Regresión del POS y prueba visual premium |
| Pedidos pendientes, preparación, seguimiento y venta | Disponible | Disponible | Regresión Edge de pedidos, incluida conversión |
| Cobros, advertencia y confirmación de faltantes | Disponible | Disponible | Prueba Edge de faltante y jornada |
| Clientes, fiados, abonos y cuentas corrientes | Disponible | Disponible | Regresión Edge de Entrenamiento |
| Apertura, referencia y diferencias por caja | Disponible | Disponible | API con horas controladas y regresión de caja |
| Arqueos, cierres y registro del motivo | Disponible | Disponible | Jornada Edge con diferencia observada |
| Alertas, historial y auditoría | Historial de caja | Historial y alertas administrativas | Jornada Edge y pruebas de API |
| Aportes y retiros | Disponible | Disponible | Jornada contable y pruebas de ambos roles |
| Compras, devoluciones totales y anulaciones | — | Disponible | Alta desde Edge y reversos en API |
| Gastos y transferencias entre cajas | — | Disponible | Regresión de caja y contabilidad integrada |
| Reportes globales y diezmo | — | Disponible | Jornada Edge y verificación de restauración |

La página de Compras lista operaciones de la API nueva. Presenta el pendiente inicial como dato histórico. La liquidación posterior de proveedores por compra individual y los reintegros parciales siguen pendientes del contrato contable.

La demo estática deriva del HTML del POS. Se regeneró con el generador del PR visual para preservar la comprobación existente de que el HTML autónomo carece de acceso a la API. La PCBOX, Android 6 y el túnel remoto quedan fuera de la validación.

## Prueba manual desde Windows

Requisitos de esta prueba: Git, Microsoft Edge y Python 3.12. En PowerShell:

```powershell
$ErrorActionPreference = 'Stop'
$RaizAbadion = Join-Path ([System.IO.Path]::GetTempPath()) ("abadion-edge-" + [guid]::NewGuid())
git clone --branch feature/abadion-premium-catalogo-tres-pasos --single-branch https://github.com/NicoNunezFM/contabilidad-bebidas-postres.git $RaizAbadion
if ($LASTEXITCODE -ne 0) { throw 'No se pudo descargar la rama.' }
Set-Location -LiteralPath $RaizAbadion
py -3.12 -m venv .venv
if ($LASTEXITCODE -ne 0) { throw 'No se pudo crear el entorno Python.' }
$PythonAbadion = Join-Path $RaizAbadion '.venv\Scripts\python.exe'
& $PythonAbadion -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'No se pudieron instalar las dependencias.' }
$env:PYTHON_DOTENV_DISABLED = '1'
& $PythonAbadion scripts/servir_pos_windows_ficticio.py --puerto 8076
```

Abrí `http://127.0.0.1:8076/pos/` en Microsoft Edge y verificá el aviso de Entrenamiento. Para practicar como Ventas, ingresá con `ventas-prueba` / `Ventas-Prueba-8060`. Para operar Compras y reportes, cerrá esa sesión e ingresá con `admin-prueba` / `Admin-Prueba-8060`.

1. En Caja diaria, abrí Rotisería con $1.000 y Postres/Bebidas con $500. Una base nueva carece de cierre anterior para proponer.
2. En el catálogo, agregá comida y bebida. Validá el carrito y cobrá en efectivo por sección. Anotá el subtotal de cada sección. Alternativamente guardá el pedido pendiente y confirmalo desde Seguimiento.
3. En Administración, registrá una compra ficticia de una bebida con costo unitario y pago de $100. Elegí efectivo de Rotisería. En Compras comprobá el costo atribuido a postres/bebidas y el pagador de Rotisería.
4. Para arquear, sumá al importe inicial los cobros de cada caja y restá $100 únicamente de Rotisería. Cerrá ambas cajas. Si ingresás una diferencia deliberada, completá el motivo y comprobá su aparición en Alertas de cierre.
5. En Contabilidad, contrastá los cobros y el costo de $100 con el reporte. Para detener el ejercicio, apretá Ctrl+C en la terminal del servidor. Con una salida normal, el launcher elimina su base temporal. El checkout y el entorno virtual quedan en `$RaizAbadion`.

Si 8076 ya está ocupado, volvé a ejecutar el launcher con `--puerto 8077` y usá ese puerto en Edge. Cada arranque crea su propia base nueva. La instalación familiar queda fuera de la ruta de ejecución.

