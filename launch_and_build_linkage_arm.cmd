@echo off
echo ============================================================
echo   NX Offset Linkage Arm - Launch and Build
echo ============================================================
echo.
echo This script:
echo   1. Launches NX with the MCP bridge (socket port 43210)
echo   2. Waits 120s for NX to fully initialize
echo   3. Automatically builds offset_linkage_arm.prt
echo.
echo NOTE: If NX is already open with the bridge running (port 43210),
echo       you can run build_offset_linkage_arm.py directly instead.
echo.

set NX_ROOT=C:\Program Files\Siemens\NX2206
set UGRAF="%NX_ROOT%\NXBIN\ugraf.exe"
set NX_WORK_DIR=%NX_ROOT%\UGII
set BRIDGE_SCRIPT=%~dp0src\nx_mcp\bridge\nx_bridge.py
set BUILD_SCRIPT=%~dp0build_offset_linkage_arm.py

echo [STEP 1] Writing live bridge config...
echo {"part_path": "", "port": 43210} > "%~dp0live_bridge_config.json"

echo [STEP 2] Killing any old NX session...
taskkill /F /IM ugraf.exe 2>nul
timeout /t 3 /nobreak > nul

echo [STEP 3] Launching NX with bridge script...
cd /d "%NX_WORK_DIR%"
start "NX MCP Bridge" %UGRAF% -nx -auto="%BRIDGE_SCRIPT%"

echo NX is starting...
echo Waiting 120 seconds for NX to fully initialize...
timeout /t 120 /nobreak

echo.
echo [STEP 4] Running build script...
cd /d "%~dp0"
python "%BUILD_SCRIPT%"

echo.
echo Done! Check above for success/error.
echo If it failed, try running: python build_offset_linkage_arm.py
echo after NX is fully loaded.
pause
