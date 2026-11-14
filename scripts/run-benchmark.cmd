@echo off
setlocal
cd /d "%~dp0\.."

uv sync --frozen --extra dev --extra bench
if errorlevel 1 exit /b %errorlevel%

uv run --frozen --extra bench python benchmark\run_baseline.py %*
exit /b %errorlevel%
