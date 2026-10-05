@echo off
setlocal

set "REPO_ROOT=%~dp0.."
pushd "%REPO_ROOT%" >nul || (
    echo ERROR: Cannot enter repository root: "%REPO_ROOT%"
    exit /b 1
)

where powershell >nul 2>&1 || (
    echo ERROR: Windows PowerShell is required by the existing demo runner.
    popd
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run-demo.ps1" %*
set "DEMO_EXIT=%ERRORLEVEL%"
popd
exit /b %DEMO_EXIT%
