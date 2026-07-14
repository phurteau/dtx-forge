@echo off
REM DTX Forge - start the local server, wait until it's ready, then open the browser.
REM (The server needs ~15-30s to import torch on first launch, so we must NOT open
REM the browser immediately or it shows "can't reach this page".)
cd /d "%~dp0"

REM launch the server in its own window so this script can poll it
start "DTX Forge server" cmd /c "python app.py"

echo Starting DTX Forge... (importing libraries, this can take 15-30 seconds)

REM poll the server up to ~60s; open the browser as soon as it answers
powershell -NoProfile -Command ^
  "$u='http://127.0.0.1:8765/'; for($i=0;$i -lt 120;$i++){ try{ if((Invoke-WebRequest $u -UseBasicParsing -TimeoutSec 2).StatusCode -eq 200){ Start-Process $u; exit 0 } }catch{}; Start-Sleep -Milliseconds 500 }; Write-Host 'Server did not start in time; open http://127.0.0.1:8765 manually once it is ready.'"

echo.
echo DTX Forge is running. Close the "DTX Forge server" window to stop it.
