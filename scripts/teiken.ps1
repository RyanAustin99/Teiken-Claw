# Teiken Control Plane Launcher
# Usage: .\scripts\teiken.ps1 [args]

$ProjectRoot = $PSScriptRoot | Split-Path -Parent
Set-Location $ProjectRoot

$PythonExe = Join-Path $ProjectRoot "venv\Scripts\python.exe"
if (-not (Test-Path $PythonExe)) {
    Write-Host "Virtual environment not found. Run .\scripts\setup.ps1 first." -ForegroundColor Red
    exit 1
}

& $PythonExe -m app.control_plane.entrypoint @args
exit $LASTEXITCODE

