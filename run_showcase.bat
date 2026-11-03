@echo off
rem =============================================================================
rem FILE:         run_showcase.bat
rem WHAT IT DOES: Windows launcher for run_showcase.py: double-click it, or run it from a
rem               terminal with the same options (e.g. run_showcase.bat --gate-demo).
rem NEEDS:        the .venv from README.md "Setup" and Ollama running.
rem =============================================================================
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo No .venv found. Follow README.md "Setup" first.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" run_showcase.py %*
pause
