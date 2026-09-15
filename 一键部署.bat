@echo off
setlocal
chcp 65001 >nul
title Intelligent Data Analysis Assistant - Setup

set "SCRIPT_DIR=%~dp0"
set "DEPLOY_SCRIPT=%SCRIPT_DIR%deploy.ps1"

cd /d "%SCRIPT_DIR%"
if errorlevel 1 goto project_path_failed

if exist "%DEPLOY_SCRIPT%" goto deploy_script_found
echo.
echo [SETUP FAILED] The deployment script was not found.
echo.
pause
exit /b 1

:project_path_failed
echo.
echo [START FAILED] Cannot open the project directory.
echo.
pause
exit /b 1

:deploy_script_found
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%DEPLOY_SCRIPT%"
set "EXIT_CODE=%ERRORLEVEL%"

if "%EXIT_CODE%"=="0" exit /b 0
echo.
echo [SETUP FAILED] PowerShell returned exit code %EXIT_CODE%.
echo Keep this window open and capture the error shown above.
echo.
pause

exit /b %EXIT_CODE%
