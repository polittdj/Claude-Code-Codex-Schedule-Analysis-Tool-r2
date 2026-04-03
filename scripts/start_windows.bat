@echo off
setlocal enabledelayedexpansion
title Schedule Forensics Tool

echo.
echo ==========================================
echo   Schedule Forensics Tool - Starting Up
echo ==========================================
echo.

REM ── Find portable Java (set JAVA_HOME to extracted JDK folder) ──────────────

REM First check JAVA_HOME if already set — but VALIDATE it (bin\java.exe must exist).
REM A previous bad run may have set JAVA_HOME to the scripts\java wrapper folder.
if defined JAVA_HOME (
    if exist "%JAVA_HOME%\bin\java.exe" (
        echo Using Java from: %JAVA_HOME%
        set "PATH=%JAVA_HOME%\bin;%PATH%"
        goto :java_ok
    )
    REM JAVA_HOME is set but invalid — clear it and search below
    set "JAVA_HOME="
)

REM Search for portable JDK extracted into scripts\java\ or a subdirectory of it.
REM When you unzip a JDK .zip, it creates a subfolder like jdk-21.0.x+y\ inside.
set "_SCRIPTS_JAVA=%~dp0java"

REM Direct: scripts\java\bin\java.exe (user extracted without subfolder)
if exist "%_SCRIPTS_JAVA%\bin\java.exe" (
    set "JAVA_HOME=%_SCRIPTS_JAVA%"
    goto :java_found
)

REM One level deep: scripts\java\<any-subfolder>\bin\java.exe
for /d %%D in ("%_SCRIPTS_JAVA%\*") do (
    if exist "%%D\bin\java.exe" (
        set "JAVA_HOME=%%D"
        goto :java_found
    )
)

REM Common alternate locations
for %%P in ("%USERPROFILE%\java" "%USERPROFILE%\Desktop\java" "%USERPROFILE%\Downloads\java") do (
    if exist "%%~P\bin\java.exe" (
        set "JAVA_HOME=%%~P"
        goto :java_found
    )
    for /d %%D in ("%%~P\*") do (
        if exist "%%D\bin\java.exe" (
            set "JAVA_HOME=%%D"
            goto :java_found
        )
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
echo 3. Extract the zip to: %~dp0java\
echo    The zip contains a folder like jdk-21.x.x+y — that is fine.
echo    Result should be: %~dp0java\jdk-21...\bin\java.exe
echo 4. Run this file again.
echo.
pause
exit /b 1

:java_found
echo Found portable Java at: %JAVA_HOME%
set "PATH=%JAVA_HOME%\bin;%PATH%"
REM Persist correct JAVA_HOME for child processes (Python/JPype)
setx JAVA_HOME "%JAVA_HOME%" >nul 2>&1

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
