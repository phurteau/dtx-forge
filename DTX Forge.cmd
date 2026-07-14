@echo off
REM DTX Forge - launch as a native desktop window (no browser)
cd /d "%~dp0"

REM Prefer pythonw (no console window). Fall back to the pyw launcher, then plain
REM python. Microsoft Store Python often exposes "python" but not "pythonw", so we
REM degrade gracefully instead of failing with "cannot find pythonw".
set "LAUNCH="
where pythonw >nul 2>nul && set "LAUNCH=pythonw"
if not defined LAUNCH ( where pyw >nul 2>nul && set "LAUNCH=pyw" )
if not defined LAUNCH ( where python >nul 2>nul && set "LAUNCH=python" )

if not defined LAUNCH (
  echo Could not find Python on your PATH.
  echo.
  echo Install Python 3.10+ from https://www.python.org/downloads/ and tick
  echo "Add Python to PATH", or just use the standalone DTX Forge.exe build
  echo ^(download DTX-Forge-EXE.zip from the GitHub Releases page - no Python needed^).
  echo.
  pause
  goto :eof
)

start "" %LAUNCH% desktop.py
