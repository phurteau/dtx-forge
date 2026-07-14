@echo off
REM ============================================================
REM  DTX Forge - clean up downloaded data (uninstall helper)
REM ============================================================
REM  DTX Forge is portable: to remove the app itself, just delete
REM  this folder. But the drum-separation model weights it downloads
REM  on first use live in your user profile and are NOT removed with
REM  the app folder. This script reclaims that space (often 1 GB+).

setlocal
set "TARGET=%LOCALAPPDATA%\DTXForge"

echo.
echo This removes DTX Forge's downloaded models, cache and logs:
echo     "%TARGET%"   (often 1 GB or more)
echo.
echo Your charts and the DTX Forge app folder are NOT touched.
echo.
set /p "ANS=Remove this data now? [y/N] "
if /i not "%ANS%"=="y" (
    echo Cancelled - nothing was removed.
    goto :end
)

rmdir /s /q "%TARGET%" 2>nul
if exist "%TARGET%" (
    echo.
    echo Some files are in use - close DTX Forge and run this again.
) else (
    echo.
    echo Done. To finish removing the app, just delete this DTX Forge folder.
)

:end
echo.
pause
endlocal
