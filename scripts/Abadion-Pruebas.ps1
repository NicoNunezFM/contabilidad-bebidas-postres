param(
    [Parameter(Position=0)][string]$Accion = 'estado',
    [Parameter(ValueFromRemainingArguments=$true)][string[]]$ArgumentosAbadion
)
$ErrorActionPreference = 'Stop'
$DestinoAbadion = $PSScriptRoot
if ((Split-Path -Leaf $DestinoAbadion) -ne 'Pruebas') { throw 'Este comando sólo funciona dentro de Abadion\Pruebas.' }
$ActivaAbadion = Get-Content -LiteralPath (Join-Path $DestinoAbadion 'activa.json') -Raw | ConvertFrom-Json
$InstanciaAbadion = Get-Content -LiteralPath (Join-Path $DestinoAbadion 'instalacion.json') -Raw | ConvertFrom-Json
if ($ActivaAbadion.commit -notmatch '^[0-9a-f]{40}$' -or $ActivaAbadion.instancia -ne $InstanciaAbadion.id -or $InstanciaAbadion.modo -ne 'ABADION-PRUEBAS-FICTICIAS-V1') { throw 'La versión activa no coincide con la instancia.' }
$VersionAbadion = Join-Path $DestinoAbadion ('releases\' + $ActivaAbadion.commit)
$EjecutableAbadion = Join-Path $VersionAbadion '.venv\Scripts\python.exe'
$LauncherAbadion = Join-Path $VersionAbadion 'scripts\abadion_pruebas.py'
$env:PYTHON_DOTENV_DISABLED = '1'
& $EjecutableAbadion $LauncherAbadion --carpeta $DestinoAbadion $Accion @ArgumentosAbadion
if ($LASTEXITCODE -ne 0) { throw 'La operación no se completó. Los datos se conservan; revise el mensaje anterior.' }
