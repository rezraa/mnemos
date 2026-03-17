@echo off
REM Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
REM Start the Mnemos MCP server and dashboard
REM Usage: server.bat [--dashboard-only | --mcp-only]

cd /d "%~dp0"

REM Activate venv if it exists
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
)

if "%1"=="--dashboard-only" (
    echo Starting Mnemos Dashboard on http://localhost:8420
    python -m mnemos.dashboard.app
    goto :eof
)

if "%1"=="--mcp-only" (
    echo Starting Mnemos MCP Server...
    mnemos
    goto :eof
)

if "%1"=="" (
    echo Starting Mnemos Dashboard on http://localhost:8420
    start "Mnemos Dashboard" python -m mnemos.dashboard.app
    echo Starting Mnemos MCP Server...
    start "Mnemos MCP" mnemos
    echo.
    echo Both servers running in separate windows.
    goto :eof
)

echo Usage: server.bat [--dashboard-only ^| --mcp-only]
