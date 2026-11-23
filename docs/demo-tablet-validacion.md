# Demo táctil estática y prueba física PCBOX

## Identidad de la descarga (23/11/2026)

Se pudo acceder al archivo real de Windows en
`%LOCALAPPDATA%\Temp\abadion-tablet-preview\index.html` (307.515 bytes).
El `%TEMP%` del entorno de ejecución apunta a otra carpeta: su ausencia allí no significaba que faltara el original.
El historial de PowerShell contiene como última descarga:

```powershell
$archivo = Join-Path $env:TEMP "abadion-tablet-preview\index.html"
$url = "https://raw.githubusercontent.com/NicoNunezFM/contabilidad-bebidas-postres/bdfa181d535014cd42b40b07529091c98ca0f6c2/pos-web/index.html"
Invoke-WebRequest -Uri $url -OutFile $archivo -UseBasicParsing
```

La comparación se hizo contra los bytes de `git show COMMIT:pos-web/index.html`,
sin conversión de codificación ni saltos de línea. El objeto histórico está en
la ascendencia de la rama obtenida desde `origin`.

| Fuente | Bytes | SHA-256 | Coincide con descarga |
|---|---:|---|---|
| Archivo descargado y blob `bdfa181d535014cd42b40b07529091c98ca0f6c2` | 307515 | `cdf03a0d3463fb3b8d7349da34d878a6aa17fe6359d50b083dfe66905eadc547` | Sí, byte a byte |
| Blob del PR #18 `59b4810d8c9564e70abfeeadb423de5e4b423669` | 308662 | `6bbe35702c4c8f91e800c78cc327dda15b5e585735853748d7777389c6674bc5` | No |
| Archivo de trabajo de esta rama, `pos-web/index.html` | 312276 | `9c398f08ebc1ca59d552bea2bf162dcca10d3aa2a19aa9fac27e61c5f22021b7` | No |

El archivo de trabajo tiene CRLF por `core.autocrlf=true`; normalizando esos
saltos coincide con el blob `59b4810`, pero **no** con la descarga.
El POS operativo se conserva sin cambios en esta rama.
Los otros clones tampoco coinciden: `abadion-pos` (`dea47e6`, SHA-256
`4bf0252f31366a43081d67a288109e6d67b4fbc87410b33387a1d84b21488b0a`),
`abadion-entrenamiento` (`c51c2f7`, `3161579c010ea9ef67df698d877a64d3230dd65861520e31cd092ec2636d7a7e`)
y `abadion-pos-menu` (`b89aa97`, `a9e7d4892e64911d46e79c2b650fdba2266594f47c058790bafc65c7dc2f6a2f`).
No se actualizaron esos directorios.

Evidencia legible por máquina: [verificacion-demo-2026-11-23.json](verificacion-demo-2026-11-23.json).
Para repetir la comparación sin tocar la descarga:

```powershell
python scripts/verificar_demo_descargada.py "$env:LOCALAPPDATA\Temp\abadion-tablet-preview\index.html"
```

### Diferencias funcionales y evidencia física

- `bdfa181`: diseño compacto según ancho y botón de carrito controlado por el JavaScript principal.
- `59b4810`: detector Android/`?tablet=1`, diseño de escritorio preservado y casilla/etiqueta con CSS para alternar carrito aun sin ejecutar el código principal. Agrega pruebas Edge para esa alternativa.
- La conversación anterior confirma que el usuario vio **Pedido actual** y pudo volver a **Nueva venta**. Después informó catálogo vacío y estado «Comprobando conexión…». No se validaron productos, personalización ni cobros en PCBOX.
- No se puede atribuir con certeza esa ejecución física a un SHA: el servidor del historial lee `pagina = archivo.read_bytes()` una sola vez al arrancar. Descargar otro archivo después no cambia sus bytes en memoria hasta reiniciarlo. La coincidencia del archivo en disco con `bdfa181` sí está demostrada; la identidad de lo servido entonces, no.
- El catálogo ficticio ya existía dentro del JavaScript. Una API ausente no explica por sí sola su falta de renderizado; falta capturar el error del navegador integrado. No se afirma una causa definitiva.

## Página de prueba nueva

`pos-web/demo-tablet.html` es un archivo autónomo, construido mediante
`python scripts/generar_demo_tablet.py` a partir de los estilos, estructura,
catálogo de ejemplo y funciones locales del POS. No ejecuta el script operativo.
Usa JavaScript ES5 para este recorrido, sin UUID, fetch, almacenamiento persistente,
inicio de sesión ni conexión a API. Los productos y precios son ficticios.
Permite quitar ingredientes, agregar extras, editar, duplicar, quitar, limpiar,
buscar y finalizar un cobro ficticio; conserva los subtotales independientes de
comidas y bebidas/postres. Todo el pedido se pierde al recargar.

La demo tiene una identificación visible **DEMO ESTÁTICA v1** y un estado
**Demo estática lista** cuando realmente terminó de dibujar el catálogo.
Si este estado no aparece, el carrito por sí solo no confirma que funcione el código.

El servidor `scripts/servir_demo_tablet.py` entrega solamente esa página en `/`,
`/pos/` o `/demo-tablet.html`; rechaza otros archivos, API y métodos de escritura.
Incluye `Cache-Control: no-store` y CSP con `connect-src 'none'`.
No importa FastAPI ni SQLite. Por defecto solo escucha en localhost.

## Preparar la prueba física

Detener antes el servidor de demostración anterior del puerto 8765 con `Ctrl+C`.
Desde la carpeta de esta rama, sin reemplazar el archivo histórico:

```powershell
Get-FileHash .\pos-web\demo-tablet.html -Algorithm SHA256
python scripts/servir_demo_tablet.py
```

En Edge de la PC abrir `http://127.0.0.1:8765`. Para la tablet, detener ese servidor
con `Ctrl+C` y usar explícitamente la IP actual de la PC y la IP de origen de la
tablet que la PC observa. Sustituir los valores entre corchetes:

```powershell
python scripts/servir_demo_tablet.py --bind "[IP_PC]" --allow "[IP_TABLET_OBSERVADA]"
```

No usar los valores históricos de IP sin verificarlos. Abrir desde la tablet
`http://[IP_PC]:8765/`. Este comando sirve exclusivamente la demo; no iniciar
FastAPI en LAN. No abrir puertos del router. Si ya hay una regla temporal de
firewall para esta prueba, mantenerla limitada al dispositivo de prueba y cerrarla
al terminar. No se crearon ni cambiaron reglas durante este trabajo.
Un 403 requiere verificar la dirección observada por el servidor, sin quitar
la restricción. Reiniciar el servidor después de cambiar el archivo: conserva los
bytes en memoria desde el inicio. Confirmar versión visible y recargar la página.

SHA-256 del nuevo archivo autónomo generado (25.914 bytes):
`6815607af0b3684298b5f2a26c92b20fd998243bb0145a2ada9986d0c4e07832`.
Este hash identifica la demo nueva y es diferente del archivo histórico.

## Recorrido para horizontal y vertical

1. Verificar **DEMO ESTÁTICA v1**, **Demo estática lista** y siete hamburguesas.
2. Buscar `clasica`, comprobar el filtrado y borrar la búsqueda.
3. Agregar Clásica: marcar **Sin tomate** y **Queso extra**. Unidad esperada: $6.600.
4. Abrir carrito y comprobar ambos cambios. Editar y agregar Panceta: $7.600.
5. Duplicar: comidas $15.200. Quitar una copia: comidas $7.600.
6. Volver al catálogo; agregar Agua sin gas ($1.600) y Flan con Dulce de leche ($3.600).
7. Carrito esperado: 3 unidades; comidas $7.600; bebidas/postres $5.200; total $12.800.
8. Alternar catálogo/carrito tres veces. Confirmar que no se pierde el pedido.
9. Elegir Efectivo; abrir simulación, cancelar y comprobar que siguen las 3 unidades.
10. Confirmar simulación: carrito vacío y aviso de cobro simulado; no hay venta guardada.
11. Agregar otro producto; probar Limpiar/Cancelar y luego Limpiar/Confirmar.
12. Agregar nuevamente y recargar: carrito vacío. Repetir en la otra orientación.
13. Revisar desplazamiento de categorías, tamaño táctil, diálogo, teclado de búsqueda
    y ausencia de solapamientos. Si falla, registrar foto, texto de estado y paso exacto.
14. Detener el servidor y cerrar la regla temporal usada para la prueba.

## Validación física reportada el 23/11/2026

Fuente: usuario en la conversación «Prueba carrito en Edge»
(`6b046ad4-b4c8-83e8-b0d2-0932d9dfbf74`). Tras indicar «Funciono perfecto.
pude agregar los productos», recibió el recorrido de personalizar una Clásica,
agregar bebida y postre, comprobar subtotales, simular cobro y verificar el vaciado.
Respondió **«Pude hacer todo»**. La solicitud de continuación confirma expresamente
catálogo, personalizaciones, carrito, subtotales separados, cobro simulado y vaciado.
Se registra como **validación manual reportada**, no observación directa del agente.

El log aportado muestra `GET /` con 200 a las 14:42:21 del 23/11/2026 y
`GET /favicon.ico` con 404. El 404 del icono no impidió el recorrido reportado.
No se capturaron tiempos de respuesta, métricas de rendimiento, video ni capturas.
Modelo: PCBOX PCB-T715; navegador integrado Android. La versión exacta del motor,
orientaciones ensayadas, SHA servido y valores numéricos observados no fueron
aportados. El hash publicado arriba identifica el artefacto del repositorio,
pero no demuestra por sí solo los bytes recibidos por la tablet.

Esta validación corresponde a la **demo estática ficticia**; no acredita login,
HTTPS, persistencia en SQLite, movimientos de las dos cajas ni conexión al POS
completo de Entrenamiento. Tampoco modifica el resultado de la demo histórica.

## Registro de resultados

Validación local del 23/11/2026:

- Suite Python: **285 aprobadas, 12 omitidas**. Diez pruebas del POS en navegador
  y dos recorridos de demo se omiten cuando no se configura el navegador.
- Ejecución separada de `tests/test_pos_web.py tests/test_demo_tablet.py` con
  Microsoft Edge: **14 aprobadas**, incluidas las dos orientaciones de la demo.
- Repetición de las cuatro pruebas de demo con CSP activa: **4 aprobadas**.
- Regeneración y sintaxis verificadas después de eliminar espacios finales;
  `.gitattributes` fija LF en el HTML autónomo para conservar su hash en Windows.
- Los tests aíslan SQLite en directorios temporales; servidores de prueba en
  localhost. No se ejecutó la demo en LAN ni se modificó la configuración de FastAPI.

Comandos desde la raíz de esta rama (PowerShell):

```powershell
$env:PYTHONUTF8 = '1'
$env:PYTHON_DOTENV_DISABLED = '1'
python -m pytest -q
$env:POS_TEST_BROWSER = "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe"
python -m pytest -q tests/test_pos_web.py tests/test_demo_tablet.py
```

| Entorno / versión | Resultado al 23/11/2026 | Evidencia / pendiente |
|---|---|---|
| PCBOX PCB-T715 / Android 6.0.1 / navegador integrado, demo histórica | Navegación reportada funcional; catálogo vacío | Conversación «Prueba carrito en Edge». SHA servido no demostrado |
| Microsoft Edge PC / nueva demo / 1024×600 | Aprobado automáticamente | Personalizar, editar, duplicar, quitar, totales, cancelar, simular, limpiar, recargar |
| Microsoft Edge PC / nueva demo / 600×1024 | Aprobado automáticamente | Mismo recorrido, sin desbordamiento horizontal |
| PCBOX / nueva demo / orientación no informada | Recorrido principal aprobado por reporte del usuario | Catálogo, personalizaciones, carrito, subtotales, cobro simulado y vaciado; conversación citada |
| PCBOX / nueva demo / ambas orientaciones | Sin confirmación individual | Pendiente registro por orientación, versión exacta, captura y hash servido |

Registrar por cada prueba: fecha/hora, operador, modelo, nombre y versión del
navegador/WebView, orientación, URL, commit de la rama, SHA-256 del HTML servido,
estado visible, pasos aprobados/fallidos, resultado esperado/observado y captura.
No registrar clientes, ventas ni datos financieros reales.

No fusionar ni habilitar producción; conservar los PR en borrador.
