@echo off
echo ========================================
echo  Hindi Voice Generator - Docker Run
echo ========================================
echo.

docker version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Docker is not running. Start Docker Desktop first.
    pause
    exit /b 1
)

if not exist output mkdir output

echo Stopping old container if exists...
docker stop hindi-voice-generator 2>nul
docker rm hindi-voice-generator 2>nul

echo.
echo Starting container...
echo Open in browser: http://localhost:8501
echo Press Ctrl+C to stop
echo.

docker run --name hindi-voice-generator ^
  -p 8501:8501 ^
  -v "%cd%\output:/app/output" ^
  -e DEFAULT_VOICE=hi-IN-SwaraNeural ^
  -e OUTPUT_FORMAT=wav ^
  hindi-voice-generator
