@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "ENV_PYTHON=%SCRIPT_DIR%.conda_envs\mujoco-maze\python.exe"

if exist "%ENV_PYTHON%" (
  "%ENV_PYTHON%" "%SCRIPT_DIR%run.py" %*
  exit /b %ERRORLEVEL%
)

where py >nul 2>nul
if %ERRORLEVEL%==0 (
  py -3 "%SCRIPT_DIR%run.py" %*
  exit /b %ERRORLEVEL%
)

where python >nul 2>nul
if %ERRORLEVEL%==0 (
  python "%SCRIPT_DIR%run.py" %*
  exit /b %ERRORLEVEL%
)

echo Python was not found. Install Miniconda/Anaconda, then run this again.
exit /b 1
