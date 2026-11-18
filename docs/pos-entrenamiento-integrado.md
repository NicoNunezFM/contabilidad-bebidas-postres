# Abadion POS · Integración de etapa 7 con Entrenamiento

Este borrador combina la contabilidad ficticia de la etapa 7 con la aplicación de entrenamiento de Lo de Clau. Parte del PR #7 sin modificar el PR #8, los datos oficiales, ni `negocio.db`.

## Alcance y decisiones

- El servidor de práctica conserva la pantalla **MODO ENTRENAMIENTO - SIN VALIDEZ CONTABLE**, sus usuarios, el catálogo de 40 productos, las pizzas y la promoción de postres chicos combinados.
- Las nuevas bases de entrenamiento se crean con un corte contable ficticio, el diario de las dos cajas y los cierres semanales/mensuales del ensayo. Desde administración aparece **Contabilidad**, que separa devengado, cobrado, fiado, compras, gastos y diezmo.
- El diezmo de fiados se reconoce cuando se cobra. Dos postres chicos de sabores mezclados suman $5.000; las operaciones registran $1.000 de descuento por par en Bebidas y Postres.
- Las bases de práctica **anteriores** pueden habilitar la contabilidad con el comando explícito `activar-contabilidad`, después de detener el servidor. El comando valida la marca de entrenamiento, crea una copia SQLite previa, agrega el corte y los triggers contables de forma transaccional; no borra ventas, stock, fiados, cajas ni el catálogo.
- **El corte es prospectivo**: las operaciones de práctica anteriores siguen visibles en su historial, pero no se vuelven a sumar como ventas nuevas al diezmo. Los saldos de fiados anteriores siguen pendientes y sus abonos posteriores pueden aparecer en el cálculo del nuevo período.
- No se habilita producción, ni conexión a terceros, ni acceso de red. La app solo escucha en `127.0.0.1:8060`. No se fusionan PR.

## Actualizar la instalación existente en Windows

**Solo cuando se aprueben las verificaciones del PR.** La instalación anterior funciona; no se modifica automáticamente.

1. Detené el servidor con `Ctrl+C`. Cerrá las pestañas del POS. No ejecutes `preparar` ni `reiniciar`.
2. Abrí PowerShell y guardá una copia completa de la carpeta de práctica, con el servidor detenido:

```powershell
$ErrorActionPreference = 'Stop'
$Codigo = Join-Path $env:LOCALAPPDATA 'Abadion\codigo-entrenamiento'
$Datos = Join-Path $env:LOCALAPPDATA 'Abadion\Entrenamiento'
$Respaldo = Join-Path $env:LOCALAPPDATA ('Abadion\Respaldos\antes-integracion-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Path $Respaldo -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $Datos 'abadion-entrenamiento.db') -Destination $Respaldo
Copy-Item -LiteralPath (Join-Path $Datos 'catalogo-entrenamiento.json') -Destination $Respaldo
Set-Location -LiteralPath $Codigo
git status -sb
```

3. Revisá que no haya modificaciones locales del código. Descargá y seleccioná la versión integrada:

```powershell
git fetch origin refs/heads/feature/abadion-pos-entrenamiento-integrado
if ($LASTEXITCODE -ne 0) { throw 'Falló la descarga de la rama integrada.' }
git switch --detach FETCH_HEAD
if ($LASTEXITCODE -ne 0) { throw 'No se pudo cambiar el código.' }
git log -1 --oneline
```

4. **Con el servidor detenido**, activá la contabilidad ficticia conservando la base existente:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts/abadion_entrenamiento.py activar-contabilidad
```

El comando informa la ruta del respaldo SQLite creado y registra el nuevo corte. Si lo ejecutás otra vez, detecta que ya estaba activado.

5. Iniciá la aplicación y probá un pedido nuevo después del corte:

```powershell
.\.venv\Scripts\python.exe scripts/abadion_entrenamiento.py servir
```

Abrí http://127.0.0.1:8060/pos/. Con `admin-prueba`, comprobá **Contabilidad**. Registrá dos postres chicos de sabores diferentes ($5.000), dejá una parte fiada, cobrá un abono y revisá el diezmo. Confirmá que historial, stock y caja anterior siguen disponibles.

## Pruebas del desarrollo

Ejecutar la suite de SQLite/API, el navegador Edge y la comprobación de sintaxis Node en GitHub Actions. Verificar específicamente el aislamiento de `negocio.db`, la migración con respaldo, el catálogo y las promociones, la conservación de IDs históricos y la nueva contabilidad. **No actualizar la instalación de la familia hasta confirmar los resultados.**

## Pendientes para producción

Siguen sin aprobarse medios y receptores de gastos/compras, prorrateo residual, límites de fiados, reembolsos, conciliación de comprobantes duplicados, operación del bot real y fecha/saldos del corte definitivo. No convertir esta base de entrenamiento en la base financiera oficial.
