param(
    [string]$PythonAbadion = 'python',
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{40}$')][string]$Commit,
    [string]$DestinoAbadion = (Join-Path $env:LOCALAPPDATA 'Abadion\CandidataOffline')
)
$ErrorActionPreference = 'Stop'
$OrigenAbadion = Split-Path -Parent $PSScriptRoot
if (Test-Path -LiteralPath $DestinoAbadion) { throw 'El destino ya existe; nunca reinstalar encima.' }
if (-not [IO.Path]::IsPathRooted($DestinoAbadion) -or $DestinoAbadion -match 'OneDrive' -or $DestinoAbadion.StartsWith('\\')) { throw 'Se requiere una ruta local absoluta fuera de sincronizacion.' }
$DestinoAbadion = [IO.Path]::GetFullPath($DestinoAbadion)
$AncestroAbadion = $DestinoAbadion
while ($AncestroAbadion) {
    if (Test-Path -LiteralPath $AncestroAbadion) {
        if ((Get-Item -Force -LiteralPath $AncestroAbadion).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Ruta indirecta rechazada.' }
    }
    $AncestroAbadion = Split-Path -Parent $AncestroAbadion
}
$ActualAbadion = (& git -C $OrigenAbadion rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $ActualAbadion -ne $Commit) { throw 'El commit no coincide con la version revisada.' }
$CambiosAbadion = & git -C $OrigenAbadion status --porcelain
if ($LASTEXITCODE -ne 0 -or $CambiosAbadion) { throw 'Se requiere un checkout limpio.' }
New-Item -ItemType Directory -Path $DestinoAbadion | Out-Null
# El destino acaba de crearse: reemplazar la DACL completa, incluidas ACEs explicitas predeterminadas.
$PermisosCandidata = [System.Security.AccessControl.DirectorySecurity]::new()
$PermisosCandidata.SetAccessRuleProtection($true, $false)
$HerenciaCandidata = [System.Security.AccessControl.InheritanceFlags]::ObjectInherit -bor [System.Security.AccessControl.InheritanceFlags]::ContainerInherit
$SidsCandidata = @([System.Security.Principal.WindowsIdentity]::GetCurrent().User, [System.Security.Principal.SecurityIdentifier]::new('S-1-5-18'))
foreach ($SidCandidata in $SidsCandidata) {
    $ReglaCandidata = [System.Security.AccessControl.FileSystemAccessRule]::new($SidCandidata, [System.Security.AccessControl.FileSystemRights]::FullControl, $HerenciaCandidata, [System.Security.AccessControl.PropagationFlags]::None, [System.Security.AccessControl.AccessControlType]::Allow)
    $PermisosCandidata.AddAccessRule($ReglaCandidata)
}
Set-Acl -LiteralPath $DestinoAbadion -AclObject $PermisosCandidata
$HerramientasAbadion = Join-Path $DestinoAbadion 'herramientas'
& $PythonAbadion -m venv $HerramientasAbadion
if ($LASTEXITCODE -ne 0) { throw 'No se pudo preparar el entorno.' }
$EjecutableAbadion = Join-Path $HerramientasAbadion 'Scripts\python.exe'
& $EjecutableAbadion -m pip install -r (Join-Path $OrigenAbadion 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Dependencias incompletas; conservar destino para diagnostico.' }
$env:PYTHON_DOTENV_DISABLED = '1'
# Exporta solo archivos versionados permitidos; nunca .env, DB, bot ni sesiones.
$PrepararReleaseAbadion = 'import sys; from pathlib import Path; sys.path.insert(0,sys.argv[1]); from scripts.abadion_pruebas import preparar_release; preparar_release(Path(sys.argv[2]),Path(sys.argv[1]),sys.argv[3])'
& $EjecutableAbadion -c $PrepararReleaseAbadion $OrigenAbadion $DestinoAbadion $Commit
if ($LASTEXITCODE -ne 0) { throw 'Fallo la exportacion verificada; no se creo base.' }
$ReleaseAbadion = Join-Path (Join-Path $DestinoAbadion 'releases') $Commit
$PythonReleaseAbadion = Join-Path $ReleaseAbadion '.venv\Scripts\python.exe'
$BaseAbadion = Join-Path $DestinoAbadion 'ProduccionCandidata'
& $PythonReleaseAbadion (Join-Path $ReleaseAbadion 'scripts\abadion_candidata.py') preparar --carpeta $BaseAbadion
if ($LASTEXITCODE -ne 0) { throw 'Preparacion rechazada. Conservar destino; no reutilizarlo.' }
Write-Output 'Candidata preparada, bloqueada y sin servidor. No hay activacion ni accesos directos.'
