# GuessTheFrame - run automated tests (Windows 11 / PowerShell 5.1+)
$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not (Test-Path '.venv\Scripts\python.exe')) {
    throw 'Environnement Python absent. Lancez scripts\setup.ps1.'
}

Write-Host 'Tests backend...' -ForegroundColor Yellow
Push-Location backend
try {
    & ..\.venv\Scripts\python.exe -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw 'Les tests backend ont echoue.' }
} finally {
    Pop-Location
}

Write-Host 'Verification frontend (build + lint)...' -ForegroundColor Yellow
Push-Location frontend
try {
    & npm run build
    if ($LASTEXITCODE -ne 0) { throw 'Le build frontend a echoue.' }
    & npm run lint
    if ($LASTEXITCODE -ne 0) { throw 'Le lint frontend a echoue.' }
} finally {
    Pop-Location
}

Write-Host 'Tous les tests sont passes.' -ForegroundColor Green
