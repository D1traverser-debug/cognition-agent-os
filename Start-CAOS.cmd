@echo off
where py >nul 2>nul
if errorlevel 1 (
  python "%~dp0start_caos.py" %*
) else (
  py -3 "%~dp0start_caos.py" %*
)
set "caos_exit=%errorlevel%"
if not "%caos_exit%"=="0" pause
exit /b %caos_exit%
