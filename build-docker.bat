@echo off
echo ========================================
echo  Hindi Voice Generator - Docker Build
echo ========================================
echo.

docker version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Docker is not running.
    echo.
    echo Please:
    echo   1. Open Docker Desktop
    echo   2. Wait until it says "Docker Desktop is running"
    echo   3. Run this script again
    echo.
    pause
    exit /b 1
)

echo Building image: hindi-voice-generator ...
docker build -t hindi-voice-generator .

if errorlevel 1 (
    echo.
    echo BUILD FAILED. Check errors above.
    pause
    exit /b 1
)

echo.
echo ========================================
echo  Build successful!
echo  Next: run run-docker.bat
echo ========================================
pause
