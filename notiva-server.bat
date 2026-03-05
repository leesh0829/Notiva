@echo off
setlocal EnableExtensions

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

set "BACKEND_DIR=%ROOT%\backend"
set "FRONTEND_DIR=%ROOT%\frontend"
set "BACKEND_TITLE=NOTIVA_BACKEND_SERVER"
set "FRONTEND_TITLE=NOTIVA_FRONTEND_SERVER"

set "ACTION=%~1"
if "%ACTION%"=="" set "ACTION=start"

if /I "%ACTION%"=="start" goto :start
if /I "%ACTION%"=="stop" goto :stop
if /I "%ACTION%"=="restart" goto :restart
if /I "%ACTION%"=="status" goto :status

echo Usage: %~nx0 ^<start^|stop^|restart^|status^>
exit /b 1

:start
if not exist "%BACKEND_DIR%\app\main.py" (
  echo [error] backend directory not found: "%BACKEND_DIR%"
  exit /b 1
)
if not exist "%FRONTEND_DIR%\package.json" (
  echo [error] frontend directory not found: "%FRONTEND_DIR%"
  exit /b 1
)
if not exist "%BACKEND_DIR%\.venv\Scripts\python.exe" (
  echo [error] backend virtualenv is missing: "%BACKEND_DIR%\.venv"
  echo         run once: cd backend ^&^& python -m venv .venv ^&^& .venv\Scripts\pip install -r requirements.txt
  exit /b 1
)

call :window_exists "%BACKEND_TITLE%"
if "%WINDOW_EXISTS%"=="1" (
  echo [backend] already running.
) else (
  start "%BACKEND_TITLE%" cmd /k "cd /d ""%BACKEND_DIR%"" && set PYTHONPATH=%BACKEND_DIR% && .venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000"
  echo [backend] started on http://127.0.0.1:8000
)

call :window_exists "%FRONTEND_TITLE%"
if "%WINDOW_EXISTS%"=="1" (
  echo [frontend] already running.
) else (
  start "%FRONTEND_TITLE%" cmd /k "cd /d ""%FRONTEND_DIR%"" && npm run dev"
  echo [frontend] started on http://127.0.0.1:3000
)

echo.
echo Use "%~nx0 stop" to close both servers.
exit /b 0

:stop
call :kill_window "%BACKEND_TITLE%"
if "%KILLED%"=="1" (
  echo [backend] stopped.
) else (
  echo [backend] not running.
)

call :kill_window "%FRONTEND_TITLE%"
if "%KILLED%"=="1" (
  echo [frontend] stopped.
) else (
  echo [frontend] not running.
)
exit /b 0

:restart
call :stop
timeout /t 1 /nobreak >nul
call :start
exit /b 0

:status
call :window_exists "%BACKEND_TITLE%"
if "%WINDOW_EXISTS%"=="1" (
  echo [backend] running
) else (
  echo [backend] stopped
)

call :window_exists "%FRONTEND_TITLE%"
if "%WINDOW_EXISTS%"=="1" (
  echo [frontend] running
) else (
  echo [frontend] stopped
)
exit /b 0

:window_exists
set "WINDOW_EXISTS=0"
for /f "tokens=*" %%L in ('tasklist /v /fi "imagename eq cmd.exe" ^| findstr /I /C:"%~1"') do (
  set "WINDOW_EXISTS=1"
)
exit /b 0

:kill_window
set "KILLED=0"
taskkill /f /t /fi "imagename eq cmd.exe" /fi "windowtitle eq %~1*" >nul 2>&1
if not errorlevel 1 set "KILLED=1"
exit /b 0
