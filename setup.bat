@echo off
rem SD Studio setup. The real work is in setup.ps1 (it can print Japanese;
rem .bat files must stay ASCII-only or cmd misreads them).
setlocal
pushd "%~dp0"
if not exist "%~dp0setup.ps1" (
  echo [SD Studio] setup.ps1 was not found next to setup.bat.
  echo [SD Studio] If you opened this from inside a ZIP file, extract the whole ZIP first.
  pause
  exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1" %*
echo.
pause
