@echo off
setlocal
cd /d "%~dp0"

if "%~1"=="" (
    set "MATHMASTER_BUILD_MODE=onedir"
) else (
    set "MATHMASTER_BUILD_MODE=%~1"
)
set "MATHMASTER_DEBUG=1"

python -m PyInstaller --noconfirm --clean --distpath dist\debug --workpath build\debug MathMaster.spec
if errorlevel 1 (
    echo Diagnostic build failed.
    exit /b 1
)
if /I "%MATHMASTER_BUILD_MODE%"=="onefile" (
    echo Diagnostic build complete. Launch dist\debug\MathMaster.exe and keep its console open.
) else (
    echo Diagnostic build complete. Launch dist\debug\MathMaster\MathMaster.exe and keep its console open.
)
exit /b 0
