@echo off
setlocal
cd /d "%~dp0"

if "%~1"=="" (
    set "MATHMASTER_BUILD_MODE=onedir"
) else (
    set "MATHMASTER_BUILD_MODE=%~1"
)
set "MATHMASTER_DEBUG=0"

python -m PyInstaller --noconfirm --clean --distpath dist --workpath build\release MathMaster.spec
if errorlevel 1 (
    echo MathMaster build failed.
    exit /b 1
)
if /I "%MATHMASTER_BUILD_MODE%"=="onefile" (
    echo Build complete. Output: dist\MathMaster.exe
) else (
    echo Build complete. Output: dist\MathMaster\MathMaster.exe
)
exit /b 0
