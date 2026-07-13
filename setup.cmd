@echo off
REM DTX Forge - one-time setup
cd /d "%~dp0"

echo Installing core dependencies...
python -m pip install -r requirements.txt
echo.

REM --- fetch deno (JavaScript runtime for YouTube) into assets\bin ---
if not exist "assets\bin\deno.exe" (
  echo Downloading deno ^(needed for YouTube downloads^)...
  if not exist "assets\bin" mkdir "assets\bin"
  powershell -NoProfile -Command "try { Invoke-WebRequest 'https://github.com/denoland/deno/releases/latest/download/deno-x86_64-pc-windows-msvc.zip' -OutFile \"$env:TEMP\deno.zip\"; Expand-Archive \"$env:TEMP\deno.zip\" -DestinationPath 'assets\bin' -Force; Write-Host 'deno installed.' } catch { Write-Host 'deno download failed - YouTube may not work, but Upload file still will.' }"
)
echo.

echo Optional: drum "Quiet"/"Remove" modes need Demucs + torch ^(~2 GB^).
set /p yn="Install Demucs now for drum separation? [y/N] "
if /i "%yn%"=="y" python -m pip install demucs soundfile
echo.

echo Setup complete. Run  "DTX Forge.cmd"  ^(app window^) or  run.cmd  ^(browser^).
pause
