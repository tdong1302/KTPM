param(
    [ValidateSet("api-only", "development", "postgres-test")]
    [string]$Mode = "development"
)

$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
python scripts/preflight.py --mode $Mode
exit $LASTEXITCODE
