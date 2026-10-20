# Helyi futtatás Docker nélkül (Windows / PowerShell):  .\scripts\run-local.ps1
# Első futáskor létrehozza a Python környezetet és telepíti a frontend függőségeit, majd buildel és elindítja a szervert:
#   http://localhost:8420
# Felhasználó létrehozása / adatok betöltése egy MÁSIK PowerShell ablakban:
#   .\scripts\run-local.ps1 -Cli create-user --name ferfi --gender male --height 175 --age 30 --target-weight 70
#   .\scripts\run-local.ps1 -Cli import-legacy --name ferfi data\exports\male_results_2026_w42.json
param(
    [switch]$SkipBuild,
    [string]$Cli,
    [Parameter(ValueFromRemainingArguments = $true)] [string[]]$CliArgs
)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$python = Join-Path $root 'backend\.venv\Scripts\python.exe'

# A helyi adatbázis a gitignore-olt backend\data mappában van (a szerveren lévőtől független).
$env:WORKOUT_DB = Join-Path $root 'backend\data\local.db'
$env:STATIC_DIR = Join-Path $root 'frontend\dist'

if (-not (Test-Path $python)) {
    Write-Host 'Python környezet létrehozása (első futás)...'
    python -m venv (Join-Path $root 'backend\.venv')
    & $python -m pip install --quiet -r (Join-Path $root 'backend\requirements.txt')
}

if ($Cli) {
    # A relatív fájlútvonalak a repó gyökeréhez képest értendők.
    $resolved = $CliArgs | ForEach-Object { if (Test-Path (Join-Path $root $_)) { Join-Path $root $_ } else { $_ } }
    Push-Location (Join-Path $root 'backend')
    try { & $python -m app.cli $Cli @resolved } finally { Pop-Location }
    exit $LASTEXITCODE
}

if (-not $SkipBuild) {
    Push-Location (Join-Path $root 'frontend')
    try {
        if (-not (Test-Path 'node_modules')) { npm install --no-audit --no-fund }
        npm run build
    } finally { Pop-Location }
}

Write-Host "`nSzerver: http://localhost:8420   (leállítás: Ctrl+C)`n"
Push-Location (Join-Path $root 'backend')
try { & $python -m uvicorn app.main:app --host 127.0.0.1 --port 8420 } finally { Pop-Location }
