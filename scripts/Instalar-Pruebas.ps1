param(
    [string]$PythonAbadion = 'python',
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{40}$')][string]$Commit
)
$ErrorActionPreference = 'Stop'
$OrigenAbadion = Split-Path -Parent $PSScriptRoot
$DestinoAbadion = Join-Path $env:LOCALAPPDATA 'Abadion\Pruebas'
if (Test-Path -LiteralPath $DestinoAbadion) { throw 'Pruebas ya existe. Use actualizar; nunca reinstale encima.' }
if ($DestinoAbadion -match 'OneDrive' -or $DestinoAbadion.StartsWith('\\')) { throw 'Se requiere un disco local fuera de OneDrive.' }
$ActualAbadion = (& git -C $OrigenAbadion rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $ActualAbadion -ne $Commit) { throw 'El commit no coincide con el checkout revisado.' }
$CambiosAbadion = & git -C $OrigenAbadion status --porcelain --untracked-files=no
if ($LASTEXITCODE -ne 0 -or $CambiosAbadion) { throw 'El código tiene cambios locales. Use un checkout limpio.' }
$AncestroAbadion = $DestinoAbadion
while ($AncestroAbadion) {
    if (Test-Path -LiteralPath $AncestroAbadion) {
        if ((Get-Item -Force -LiteralPath $AncestroAbadion).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'No se admiten enlaces en la ruta.' }
    }
    $AncestroAbadion = Split-Path -Parent $AncestroAbadion
}
New-Item -ItemType Directory -Path $DestinoAbadion | Out-Null
if ((Get-Item -Force -LiteralPath $DestinoAbadion).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'No se admiten enlaces.' }
$UsuarioAbadion = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
& icacls.exe $DestinoAbadion /inheritance:r /grant:r "${UsuarioAbadion}:(OI)(CI)F" '*S-1-5-18:(OI)(CI)F' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'No se pudo restringir el acceso privado.' }
$HerramientasAbadion = Join-Path $DestinoAbadion 'herramientas'
& $PythonAbadion -m venv $HerramientasAbadion
if ($LASTEXITCODE -ne 0) { throw 'Falló el entorno de instalación. Conserve la carpeta para diagnóstico.' }
$EjecutableAbadion = Join-Path $HerramientasAbadion 'Scripts\python.exe'
& $EjecutableAbadion -m pip install -r (Join-Path $OrigenAbadion 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Fallaron las dependencias. No se creó la base.' }
$LauncherAbadion = Join-Path $OrigenAbadion 'scripts\abadion_pruebas.py'
$env:PYTHON_DOTENV_DISABLED = '1'
& $EjecutableAbadion $LauncherAbadion --carpeta $DestinoAbadion preparar
if ($LASTEXITCODE -ne 0) { throw 'Falló preparar. No borre ni reinicie datos.' }
& $EjecutableAbadion $LauncherAbadion --carpeta $DestinoAbadion actualizar --origen $OrigenAbadion --commit $Commit
if ($LASTEXITCODE -ne 0) { throw 'Falló activar. La base nueva se conserva sin catálogo; revise el error.' }
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'Abadion-Pruebas.ps1') -Destination $DestinoAbadion
Write-Output "Abadion Pruebas instalado y detenido en $DestinoAbadion. Revise y apruebe el catálogo antes de usarlo."
