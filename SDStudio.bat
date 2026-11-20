@echo off
rem SD Studio launcher: start the engine if it is not running, wait until it
rem answers, then open the studio in the default browser.
setlocal
pushd "%~dp0"
set "CURL=%SystemRoot%\System32\curl.exe"
set "WAIT=%SystemRoot%\System32\timeout.exe"
if not exist "%CURL%" (
  echo [SD Studio] curl.exe was not found. Windows 10 version 1803 or later is required.
  pause
  exit /b 1
)

rem No config yet, or ComfyUI was moved since setup: run setup (again).
if not exist "config.bat" goto setup
call "config.bat"
if not exist "%PYTHON%" goto setup
if not exist "%COMFYUI_DIR%\main.py" goto setup
goto ready

:setup
echo [SD Studio] Running setup first.
call "%~dp0setup.bat"
if not exist "config.bat" exit /b 1
call "config.bat"
if not exist "%PYTHON%" exit /b 1

:ready
set "URL=http://127.0.0.1:%PORT%"
rem /studio/api/ping answers only when the engine is SD Studio.
"%CURL%" -sf -o nul "%URL%/studio/api/ping" && goto open
rem Something else answers on the port: most likely a ComfyUI started on its
rem own. Starting a second engine there would only fail.
"%CURL%" -s -o nul "%URL%/" && goto busy

if exist "engine.failed" del "engine.failed"
echo [SD Studio] Starting the engine. The first start can take a minute or two.
echo [SD Studio] It runs in the "SD Studio engine" window on the taskbar; close that window to stop it.
start "SD Studio engine" /min "%~dp0start.bat"

set /a tries=0
:wait
"%WAIT%" /t 2 /nobreak >nul
"%CURL%" -sf -o nul "%URL%/studio/api/ping" && goto open
if exist "engine.failed" goto failed
set /a tries+=1
if %tries% lss 150 goto wait
echo [SD Studio] The engine did not answer within 5 minutes.
echo [SD Studio] Check the "SD Studio engine" window on the taskbar for errors.
pause
exit /b 1

:failed
echo [SD Studio] The engine failed to start. The error is shown in the
echo [SD Studio] "SD Studio engine" window on the taskbar.
echo [SD Studio] If ComfyUI was moved or updated, run setup.bat again.
pause
exit /b 1

:busy
echo [SD Studio] Port %PORT% is already used by another program (a ComfyUI left running?).
echo [SD Studio] Close it and try again, or run setup.bat and choose another port.
pause
exit /b 1

:open
start "" "%URL%/studio"
exit /b 0
