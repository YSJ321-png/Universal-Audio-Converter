@echo off
echo Starting server...
start "AudioServer" python server.py
timeout /t 3 /nobreak >nul
echo Opening converter...
start http://localhost:8000/converter.html
exit