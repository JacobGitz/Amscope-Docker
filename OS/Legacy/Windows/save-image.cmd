:: save-image.bat (Windows)
@echo off
REM Launches the save-image PowerShell script. 
powershell -NoProfile -ExecutionPolicy Bypass -NoExit -File "%~dp0save-image.ps1"
echo.
echo Press any key to close this window ...
pause > nul
