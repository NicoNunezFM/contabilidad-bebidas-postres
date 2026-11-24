# POS Premium táctil V1

Base de trabajo: PR #28, commit `35949f0f100161154a4bb3712598d4f6ebb1821d`.

## Diseño antes de la implementación

- La oferta del tercer paso tendrá grupos plegables. Los tamaños de Manaos y los tipos de postre se reconocen en el catálogo cargado. Cada fila usa el ID, precio y stock de su producto. Las bebidas restantes siguen accesibles en «Otras bebidas». Las variantes sin un grupo conocido conservan una entrada propia.
- El borrador del tercer paso mantiene cantidades por ID al volver al paso anterior. La confirmación reutiliza las líneas y la validación del pedido. La cancelación descarta el borrador.
- El catálogo principal agrupa los postres por tipo. Su selector permite elegir variantes y cantidades. Los postres entran al carrito mediante las líneas normales del POS.
- «Especial» es un nombre de presentación para la pizza «Jamón y morrones». La plantilla, SQLite, los identificadores, las personalizaciones y los registros históricos conservan sus datos.
- Los controles de cantidad usan botones nativos de al menos 48 px. El carrito y las variantes descuentan las unidades ya presentes en otras líneas del mismo producto. Se mantienen los límites de 99 unidades por línea, 30 por adicional de preparación y una unidad por extra de catálogo, según las reglas actuales.

## Catálogo SQLite ficticio

| Opción visible | Variantes detectadas | Precio unitario de la base ficticia |
| --- | --- | --- |
| Manaos chica (600 ml) | Pomelo, Cola | $1.300 |
| Manaos grande (2,25 l) | Cola, Naranja, Manzana, Pomelo | $2.000 |
| Otras bebidas | Pepsi lata, 7up lata | $1.600 |
| Chocotorta | Chico, Grande | $3.000, $4.500 |
| Oreo | Chico, Grande | $3.000, $4.500 |
| Pepitos | Sin variantes en la base ficticia | — |
| Especial | ID 40 en esta base | $12.000 |

La base ficticia controla el stock individual de todas las bebidas y los postres grandes. Usa el descuento de $1.000 por par de postres chicos, incluso con tipos distintos. Los importes del selector son subtotales antes de esa promoción. El botón «Validar pedido» y el cobro aplican el cálculo vigente del servidor.

## Prueba en Microsoft Edge

Desde el directorio de esta rama, con Python y las dependencias de `requirements-tablet-test.txt` disponibles, ejecutá en PowerShell:

```powershell
$env:PYTHON_DOTENV_DISABLED = '1'
python scripts/servir_pos_windows_ficticio.py --puerto 8076
```

1. Abrí [el POS ficticio](http://127.0.0.1:8076/pos/) en Edge. Ingresá con `ventas-prueba` y `Ventas-Prueba-8060` para validar o registrar una venta ficticia.
2. Elegí una hamburguesa clásica, personalizala y continuá. Abrí los dos grupos Manaos, seleccioná sabores distintos con sus cantidades y agregá postres chicos y grandes. Usá «Volver», continuá y comprobá que las cantidades siguen seleccionadas.
3. Probá «Cancelar» o la X con productos ya seleccionados. Volvé a armar el pedido y agregalo. Desde la pestaña «Postres», elegí Oreo y un tamaño para agregarlo directamente. Desde «Pizzas», verificá Especial a $12.000.
4. Usá Tab y Enter en los controles y repetí con la emulación de dispositivo de Edge. Validá un pedido mixto con dos postres chicos y comprobá el descuento y la separación de las cajas.
5. Cerrá el servidor con Ctrl+C. El launcher crea una base temporal nueva en cada arranque.

Para la regresión automatizada se puede definir `POS_TEST_BROWSER` con la ruta de Edge y `POS_UI_CAPTURAS` con un directorio de salida, y ejecutar `python -m pytest -q`. GitHub Actions publica las capturas como artefacto del trabajo de Edge.
