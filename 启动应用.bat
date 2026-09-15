@echo off
setlocal
chcp 65001 >nul
title Intelligent Data Analysis Assistant

set "SCRIPT_DIR=%~dp0"
set "VENV_PYTHON=%SCRIPT_DIR%.venv\Scripts\python.exe"

cd /d "%SCRIPT_DIR%"
if errorlevel 1 goto project_path_failed

if exist "%VENV_PYTHON%" goto python_found
echo.
echo [START FAILED] The project virtual environment was not found.
echo Run the setup launcher once before using this daily launcher.
echo.
pause
exit /b 1

:project_path_failed
echo.
echo [START FAILED] Cannot open the project directory.
echo.
pause
exit /b 1

:python_found
if /I not "%~1"=="--check" goto verify_streamlit
echo [CHECK PASSED] Project path and virtual-environment Python are available.
exit /b 0

:verify_streamlit
"%VENV_PYTHON%" -c "import streamlit" >nul 2>nul
if errorlevel 1 goto streamlit_missing

echo ============================================
echo   Intelligent Data Analysis Assistant
echo ============================================
echo.
echo Starting the existing local environment...
echo Close this window to stop the application.
echo.
"%VENV_PYTHON%" -m streamlit run app.py
set "EXIT_CODE=%ERRORLEVEL%"

if "%EXIT_CODE%"=="0" exit /b 0
echo.
echo [START FAILED] Streamlit returned exit code %EXIT_CODE%.
echo Keep this window open and capture the error shown above.
echo.
pause
exit /b %EXIT_CODE%

:streamlit_missing
echo.
echo [START FAILED] Streamlit is unavailable in the existing environment.
echo Run the setup launcher once, then try again.
echo.
pause
exit /b 1
