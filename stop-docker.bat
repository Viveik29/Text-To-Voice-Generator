@echo off
echo Stopping and removing container...
docker stop hindi-voice-generator 2>nul
docker rm hindi-voice-generator 2>nul
echo Done.
pause
