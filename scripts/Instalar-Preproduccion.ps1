param([string]$PythonAbadion = 'python')
$ErrorActionPreference = 'Stop'
$OrigenAbadion = Split-Path -Parent $PSScriptRoot
$DestinoAbadion = Join-Path $env:LOCALAPPDATA 'Abadion\Preproduccion'
if (Test-Path -LiteralPath $DestinoAbadion) { throw 'La instalacion existe. No se sobrescribe; consulte la guia.' }
if ($DestinoAbadion -match 'OneDrive' -or $DestinoAbadion.StartsWith('\\')) { throw 'Se requiere un disco local fuera de OneDrive.' }
New-Item -ItemType Directory -Path $DestinoAbadion | Out-Null
$UsuarioAbadion = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
& icacls.exe $DestinoAbadion /inheritance:r /grant:r "${UsuarioAbadion}:(OI)(CI)F" '*S-1-5-18:(OI)(CI)F' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'No se pudo restringir el acceso a los datos privados.' }
$CodigoAbadion = Join-Path $DestinoAbadion 'app'
New-Item -ItemType Directory -Path $CodigoAbadion | Out-Null
# Explicit allowlist: no databases, .env, WhatsApp, Git credentials or other checkouts.
foreach ($NombreAbadion in @('src', 'scripts', 'pos-web', 'docs', 'requirements.txt')) {
    Copy-Item -LiteralPath (Join-Path $OrigenAbadion $NombreAbadion) -Destination $CodigoAbadion -Recurse
}
& $PythonAbadion -m venv (Join-Path $CodigoAbadion '.venv')
if ($LASTEXITCODE -ne 0) { throw 'Fallo la creacion del entorno Python.' }
$EjecutableAbadion = Join-Path $CodigoAbadion '.venv\Scripts\python.exe'
& $EjecutableAbadion -m pip install -r (Join-Path $CodigoAbadion 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Fallo la instalacion de dependencias. No se creo la base.' }
$LauncherAbadion = Join-Path $CodigoAbadion 'scripts\abadion_preproduccion.py'
$env:PYTHON_DOTENV_DISABLED = '1'
& $EjecutableAbadion $LauncherAbadion --carpeta $DestinoAbadion preparar
if ($LASTEXITCODE -ne 0) { throw 'Fallo la preparacion. Conserve la carpeta y revise el error; no reinicie datos.' }
foreach ($AccionAbadion in @('iniciar', 'detener', 'estado', 'backup')) {
    $TextoAbadion = "@echo off`r`nset PYTHON_DOTENV_DISABLED=1`r`n`"$EjecutableAbadion`" `"$LauncherAbadion`" --carpeta `"$DestinoAbadion`" $AccionAbadion`r`nif errorlevel 1 pause`r`n"
    [System.IO.File]::WriteAllText((Join-Path $DestinoAbadion "$AccionAbadion-preproduccion.cmd"), $TextoAbadion, [System.Text.Encoding]::Default)
}
Write-Output "PREPRODUCCION instalada y detenida en $DestinoAbadion. Credenciales privadas: credenciales.json."
