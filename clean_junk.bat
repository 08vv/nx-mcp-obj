@echo off
setlocal
cd /d "%~dp0"
title Clean NX MCP Workspace

echo ====================================================
echo             NX MCP Workspace Junk Cleaner
echo ====================================================
echo.

if not "%1"=="" (
    python clean_junk.py %*
    goto :end
)

echo Select cleaning mode:
echo   [1] Standard Clean (Remove all root scratch scripts, loose CAD/JSON/PNG debris, caches)
echo   [2] Deep Clean     (Standard clean + completely purge generated 'output/' artifacts)
echo   [3] Output Only    (Purge only 'output/' directory artifacts)
echo   [4] Dry Run        (Preview what would be deleted without touching files)
echo.
set /p choice="Enter choice [1-4] (Default: 1): "

if "%choice%"=="2" (
    echo.
    python clean_junk.py --all
) else if "%choice%"=="3" (
    echo.
    python clean_junk.py --output
) else if "%choice%"=="4" (
    echo.
    python clean_junk.py --dry-run
) else (
    echo.
    python clean_junk.py
)

:end
if errorlevel 1 (
    echo.
    echo [ERROR] Cleaning encountered an issue.
) else (
    echo.
    echo [SUCCESS] Cleanup finished!
)

echo.
echo Press any key to close this window...
pause >nul

