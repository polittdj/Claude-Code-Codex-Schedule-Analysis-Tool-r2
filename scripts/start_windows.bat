@echo off
setlocal enabledelayedexpansion
title Schedule Forensics Tool

echo.
echo ==========================================
echo   Schedule Forensics Tool - Starting Up
echo ==========================================
echo.

REM ── Find portable Java (set JAVA_HOME to extracted JDK folder) ──────────────
REM Check if JAVA_HOME is already set (user set it pointing to portable JDK)
if defined JAVA_HOME (
    echo Using Java from: %JAVA_HOME%
    goto :java_ok
)

REM Auto-detect portable JDK in common locations
set "JAVA_SEARCH_PATHS=%~dp0java %USERPROFILE%\java %USERPROFILE%\Desktop\java %USERPROFILE%\Downloads\java"
for %%P in (%JAVA_SEARCH_PATHS%) do (
    if exist "%%P\bin\java.exe" (
        set "JAVA_HOME=%%P"
        goto :java_found
    )
)

REM Check if java is already on PATH (system Java)
where java >nul 2>&1
if %errorlevel% == 0 goto :java_ok

echo ERROR: Java not found!
echo.
echo Please follow these steps:
echo 1. Go to: https://adoptium.net/temurin/releases/
echo 2. Choose: Windows, x64, JDK 21, .zip
echo 3. Extract the zip to: %~dp0java
echo    (so that %~dp0java\bin\java.exe exists)
echo 4. Run this file again.
echo.
pause
exit /b 1

:java_found
echo Found portable Java at: %JAVA_HOME%
set "PATH=%JAVA_HOME%\bin;%PATH%"

:java_ok

REM ── Check Python ─────────────────────────────────────────────────────────────
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python not found. Please install Python 3.11+ from https://python.org
    pause
    exit /b 1
)
python --version

REM ── Install Python dependencies ───────────────────────────────────────────────
echo.
echo Installing Python dependencies (first run takes a minute)...
pip install -r "%~dp0..\backend\requirements.txt" --quiet
if %errorlevel% neq 0 (
    echo ERROR: pip install failed. See error above.
    pause
    exit /b 1
)
echo Done.

REM ── Start the server ──────────────────────────────────────────────────────────
echo.
echo Starting server...
echo.
echo ==========================================
echo   Open your browser to:
echo   http://localhost:8000
echo.
echo   Keep this window open while using the tool.
echo   Close it to shut down.
echo ==========================================
echo.

cd /d "%~dp0.."
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000

pause
