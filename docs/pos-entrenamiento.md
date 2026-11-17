# Abadion Entrenamiento para Lo de Clau

Practicá pedidos, cobros, fiados y cierre de las dos cajas. La página muestra **MODO ENTRENAMIENTO - SIN VALIDEZ CONTABLE** desde que abre. La caja, las ventas y los fiados empiezan vacíos. Los productos con control de stock empiezan con 24 unidades de práctica.

## Primera vez en Windows

Usá PowerShell con Git y Python 3.12. Estos pasos descargan la rama desde el checkout de etapa 6 y crean una carpeta de código aparte en tu disco local. Si ya hiciste la instalación, pasá a «Abrir el POS».

```powershell
$Origen = 'C:\Users\sergi\OneDrive\Desktop\Proyectos\abadion-etapa6-pruebas'
$Abadion = Join-Path $env:LOCALAPPDATA 'Abadion'
$Codigo = Join-Path $Abadion 'codigo-entrenamiento'
if (Test-Path -LiteralPath $Codigo) { throw "La carpeta $Codigo ya existe." }
New-Item -ItemType Directory -Path $Abadion -Force | Out-Null
git -C $Origen fetch origin refs/heads/feature/abadion-entrenamiento
if ($LASTEXITCODE -ne 0) { throw 'Falló la descarga de la rama de entrenamiento.' }
git -C $Origen worktree add --detach $Codigo FETCH_HEAD
if ($LASTEXITCODE -ne 0) { throw 'Falló la creación del checkout de entrenamiento.' }
Set-Location -LiteralPath $Codigo
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts/abadion_entrenamiento.py preparar
```

La base se genera en `%LOCALAPPDATA%\Abadion\Entrenamiento\abadion-entrenamiento.db`, fuera de OneDrive. El comando `preparar` se detiene si ya existe el archivo. La carpeta sincronizada de etapa 6 conserva su checkout y sus archivos.

## Abrir el POS

```powershell
Set-Location -LiteralPath (Join-Path $env:LOCALAPPDATA 'Abadion\codigo-entrenamiento')
.\.venv\Scripts\python.exe scripts/abadion_entrenamiento.py servir
```

En el equipo donde corre el servidor, abrí [Abadion Entrenamiento](http://127.0.0.1:8060/pos/). El servidor escucha solo en `127.0.0.1`. Una tablet Windows puede ejecutar allí la misma instalación y usar su propia base. Para usar la base de la PC desde otra tablet, se requiere acceso remoto privado a la pantalla de esa PC. La dirección local escrita en el navegador de otra tablet apunta a esa tablet. El launcher no habilita el acceso por Wi-Fi ni publica el POS en Internet.

| Perfil | Usuario | Contraseña de práctica |
| --- | --- | --- |
| Ventas | `ventas-prueba` | `Ventas-Prueba-8060` |
| Administración | `admin-prueba` | `Admin-Prueba-8060` |

1. Iniciá sesión como ventas. En **Caja diaria**, abrí Rotisería / Comidas con $300 y Bebidas y Postres con $100 de fondo ficticio.
2. Armá un pedido con una hamburguesa y una bebida. Probá pagar una parte en efectivo y otra por transferencia. Elegí **Pendiente / Fiado** y usá un nombre como «Cliente de práctica A» para el saldo.
3. Abrí **Historial simulado**, registrá un abono y revisá el saldo. Probá una devolución con la cuenta de administración.
4. Guardá un arqueo en **Caja diaria** y cerrá la caja. Repetí con la otra caja. Si hay una diferencia, probá ingresar un motivo y autorizar el cierre con administración.

## Editar el catálogo y volver a empezar

El primer arranque genera `%LOCALAPPDATA%\Abadion\Entrenamiento\catalogo-entrenamiento.json`. La fuente de nombres, categorías y precios de referencia es [el catálogo del repositorio](../src/catalogo.py). Confirmá qué productos siguen en el menú y cuáles son los precios vigentes. El «Extra de práctica (ejemplo)» y su precio son ficticios.

Para ajustar el menú de práctica, abrí el JSON con el Bloc de notas y guardalo en UTF-8.

- En `productos`, editá nombre, categoría y precio. `precio_centavos` es un entero. Por ejemplo, `650000` equivale a $6.500.
- Conservá `Bebidas` y `Postres` para los productos que pertenecen a esa caja. `controla_stock` indica si el POS debe descontar unidades. Usá cantidades ficticias en `stock_inicial`.
- Cargá los adicionales y su precio en `adicionales`. En cada producto, poné los nombres exactos de los adicionales habilitados. Para un producto sin extras, usá `[]`.

Para aplicar el JSON y borrar las prácticas, cerrá las pestañas del POS y detené el servidor con **Ctrl+C**. En la misma carpeta de código, ejecutá:

```powershell
.\.venv\Scripts\python.exe scripts/abadion_entrenamiento.py reiniciar
```

Escribí `REINICIAR ENTRENAMIENTO`. El comando verifica el archivo y su marca, carga el JSON y reemplaza el SQLite solo después de que se prepara la nueva base. Se borran pedidos, ventas, fiados, cobros, arqueos, cierres, sesiones y cambios de menú hechos desde el POS. El JSON conserva los cambios que guardaste allí. Volvé a ejecutar `servir`, abrí el POS e iniciá sesión otra vez.

## Integración posterior con etapa 7

La rama parte del PR #6 en `03343c524128b408951e9ccd7fb7cf42fcd5a485`. El servidor de entrenamiento monta solo el router del POS y sirve su interfaz con la banda fija. Reutiliza los esquemas ficticios del POS, el puente y la caja diaria. El SQLite y el JSON local quedan fuera de Git.

Cuando etapa 7 esté lista, en una copia de integración aplicá los commits de entrenamiento sobre su punta mediante `git rebase --onto <punta-etapa-7> 03343c5 <rama-de-integracion>` o cherry-pick. Revisá en especial la resolución de SQLite, el router y la selección del flujo simulado. Después repetí las pruebas de aislamiento, reinicio, cobros, conciliación y navegador con una base de entrenamiento nueva. Conservá el JSON como única entrada del catálogo para regenerar la base.
