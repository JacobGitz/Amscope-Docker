@echo off
REM frontend-launch.cmd — double-click to run the PowerShell launcher
REM Keeps the window open so you can always see errors.

powershell -NoProfile -ExecutionPolicy Bypass -NoExit ^
  -File "%~dp0frontend-launch.ps1"

echo.
echo Press any key to close this window …
pause > nul
