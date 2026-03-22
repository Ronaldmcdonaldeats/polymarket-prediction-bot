@echo off
cd "C:/Users/Ronald mcdonald/claude/polymarket pred"

:check_ollama
curl -s http://localhost:11434/api/tags > nul 2>&1
if errorlevel 1 (
    echo Waiting for Ollama...
    timeout /t 5 /nobreak > nul
    goto check_ollama
)

call python main.py
pause
