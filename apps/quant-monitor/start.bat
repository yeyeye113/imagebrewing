@echo off
title Quant Monitor Dashboard
echo ========================================
echo   Quant Trading Monitor - Port 8001
echo ========================================
echo.
echo Starting server at http://localhost:8001
echo Press Ctrl+C to stop
echo.
python "%~dp0server.py"
pause
