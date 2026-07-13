@echo off
REM DTX Forge - launch as a native desktop window (no browser, no console)
cd /d "%~dp0"
start "" pythonw desktop.py
