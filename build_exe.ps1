$ErrorActionPreference = "Stop"

Push-Location $PSScriptRoot
try {
    python -m PyInstaller --noconfirm --clean .\MathMaster.spec
}
finally {
    Pop-Location
}
