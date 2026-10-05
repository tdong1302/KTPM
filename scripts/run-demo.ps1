param(
    [int]$Port = 8765,
    [switch]$KeepData
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $repoRoot

$demoDir = Join-Path $repoRoot "artifacts\demo"
$databasePath = Join-Path $demoDir "eventhub-demo.sqlite3"
$stdoutPath = Join-Path $demoDir "server.stdout.log"
$stderrPath = Join-Path $demoDir "server.stderr.log"
New-Item -ItemType Directory -Path $demoDir -Force | Out-Null

if (Test-NetConnection -ComputerName 127.0.0.1 -Port $Port -InformationLevel Quiet -WarningAction SilentlyContinue) {
    throw "Port $Port is already occupied. Use -Port with another local port."
}

uv sync --frozen --extra dev
if ($LASTEXITCODE -ne 0) {
    throw "Frozen dependency installation failed."
}

if (-not $KeepData -and (Test-Path -LiteralPath $databasePath)) {
    $resolvedDemoDir = (Resolve-Path -LiteralPath $demoDir).Path
    $resolvedDatabase = (Resolve-Path -LiteralPath $databasePath).Path
    if (-not $resolvedDatabase.StartsWith($resolvedDemoDir + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to reset a database outside artifacts/demo."
    }
    Remove-Item -LiteralPath $resolvedDatabase -Force
}

$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
$environmentNames = @("DATABASE_URL", "DB_AUTO_CREATE", "JWT_SECRET", "BCRYPT_ROUNDS", "ENVIRONMENT", "APP_NAME")
$originalEnvironment = @{}
foreach ($name in $environmentNames) {
    $originalEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
}

$server = $null
try {
    $databaseUrlPath = $databasePath.Replace("\", "/")
    $env:DATABASE_URL = "sqlite+pysqlite:///$databaseUrlPath"
    $env:DB_AUTO_CREATE = "true"
    $env:JWT_SECRET = "local-functional-demo-secret-at-least-32-characters"
    $env:BCRYPT_ROUNDS = "4"
    $env:ENVIRONMENT = "demo"
    $env:APP_NAME = "EventHub-KTPM Functional Demo"

    $server = Start-Process `
        -FilePath $python `
        -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", $Port) `
        -WorkingDirectory $repoRoot `
        -RedirectStandardOutput $stdoutPath `
        -RedirectStandardError $stderrPath `
        -WindowStyle Hidden `
        -PassThru

    & $python scripts/demo_api.py `
        --base-url "http://127.0.0.1:$Port" `
        --output-dir $demoDir `
        --storage-label "SQLite local functional demo (not PostgreSQL concurrency evidence)"
    if ($LASTEXITCODE -ne 0) {
        throw "Functional demo failed. Inspect artifacts/demo/latest-demo-report.md and server.stderr.log."
    }
}
finally {
    if ($null -ne $server -and -not $server.HasExited) {
        Stop-Process -Id $server.Id -Force
        $server.WaitForExit()
    }
    foreach ($name in $environmentNames) {
        [Environment]::SetEnvironmentVariable($name, $originalEnvironment[$name], "Process")
    }
}

Write-Host "Demo completed. Open artifacts/demo/latest-demo-report.md"
Write-Host "Swagger can be explored separately with the manual steps in docs/demo-guide.md"
