@echo off
rem sdgen command line, run with ComfyUI's own Python. Usage: sdgen --help
setlocal
if not exist "%~dp0config.bat" (
  echo [SD Studio] config.bat not found. Run setup.bat first.
  exit /b 1
)
call "%~dp0config.bat"
if not exist "%PYTHON%" (
  echo [SD Studio] Python in config.bat was not found. Run setup.bat again.
  exit /b 1
)
set "SD_STUDIO_PORT=%PORT%"
"%PYTHON%" -s "%~dp0sdgen.py" %*
