@echo off
rem SD Studio engine: ComfyUI in headless mode with the studio UI node loaded.
rem Runs in the foreground. Closing this window stops the engine.
rem It is usually started by SDStudio.bat or sdgen; `start` runs it under
rem cmd /K, hence the plain `exit` (not `exit /b`) to close the window.
setlocal
pushd "%~dp0"
if not exist "config.bat" (
  echo [SD Studio] config.bat not found. Run setup.bat first.
  pause
  exit 1
)
call "config.bat"

set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"
set "SD_STUDIO_ROOT=%ROOT%"
if not exist "%ROOT%\outputs" mkdir "%ROOT%\outputs"
if exist "%ROOT%\engine.failed" del "%ROOT%\engine.failed"

title SD Studio engine (port %PORT%)
rem The UI node is found through extra_model_paths.yaml, so nothing is copied
rem into ComfyUI itself; ComfyUI's own extra_model_paths.yaml still applies.
rem --temp-directory keeps ComfyUI's startup cleanup away from the temp folder
rem of a ComfyUI that may be running from the same install.
"%PYTHON%" -s "%COMFYUI_DIR%\main.py" --listen 127.0.0.1 --port %PORT% --output-directory "%ROOT%\outputs" --temp-directory "%ROOT%" --extra-model-paths-config "%ROOT%\extra_model_paths.yaml" --preview-method auto %COMFY_ARGS%

rem Normal shutdown (sdgen --stop) ends quietly. A crash or a failed start
rem (negative codes included) keeps the window open so the error can be read,
rem and leaves engine.failed so the launcher can say so at once.
set "RC=%errorlevel%"
if "%RC%"=="0" exit
>"%ROOT%\engine.failed" echo %RC%
echo.
echo [SD Studio] The engine stopped with an error (code %RC%). See the messages above.
pause
exit
