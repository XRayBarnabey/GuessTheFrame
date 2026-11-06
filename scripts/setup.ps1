# GuessTheFrame - local setup (Windows 11 / PowerShell 5.1+)
$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host ''
Write-Host 'GuessTheFrame - installation locale' -ForegroundColor Cyan
Write-Host '-----------------------------------' -ForegroundColor DarkGray

function Require-Command($name, $hint) {
    if (-not (Get-Command $name -ErrorAction SilentlyContinue)) {
        throw "Commande introuvable : $name. $hint"
    }
}

Require-Command 'node' 'Installez Node.js 20+ depuis https://nodejs.org/'
Require-Command 'npm' 'npm doit etre installe avec Node.js.'

try {
    $pyVersion = & py -3.12 --version 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $pyVersion) {
        throw "Python 3.12 introuvable."
    }
} catch {
    throw "Python 3.12 est requis. Installez-le depuis https://www.python.org/downloads/windows/ et cochez 'Add python.exe to PATH'."
}

if (-not (Test-Path '.venv\Scripts\python.exe')) {
    Write-Host 'Creation de l environnement virtuel Python 3.12...' -ForegroundColor Yellow
    & py -3.12 -m venv .venv
}

Write-Host 'Installation des dependances backend...' -ForegroundColor Yellow
& .\.venv\Scripts\python.exe -m pip install --upgrade pip | Out-Null
& .\.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt
if ($LASTEXITCODE -ne 0) { throw 'Echec de l installation des dependances Python.' }

if (-not (Test-Path '.env')) {
    Write-Host 'Creation du fichier .env avec des secrets aleatoires...' -ForegroundColor Yellow
    $rng = New-Object System.Security.Cryptography.RNGCryptoServiceProvider
    $keyBytes = New-Object byte[] 32
    $rng.GetBytes($keyBytes)
    $encryptionKey = [Convert]::ToBase64String($keyBytes).Replace('+','-').Replace('/','_')
    $tokenBytes = New-Object byte[] 32
    $rng.GetBytes($tokenBytes)
    $setupToken = -join ($tokenBytes | ForEach-Object { $_.ToString('x2') })
    (Get-Content '.env.example' -Raw) `
        -replace 'GTF_ENCRYPTION_KEY=change-me', "GTF_ENCRYPTION_KEY=$encryptionKey" `
        -replace 'GTF_SETUP_TOKEN=change-me', "GTF_SETUP_TOKEN=$setupToken" |
        Set-Content -Encoding ASCII '.env'
    Write-Host 'Fichier .env cree.' -ForegroundColor Green
} else {
    Write-Host 'Fichier .env deja present, conserve.' -ForegroundColor DarkGray
}

Write-Host 'Application des migrations SQLite...' -ForegroundColor Yellow
& .\.venv\Scripts\python.exe -m alembic -c backend\alembic.ini upgrade head
if ($LASTEXITCODE -ne 0) { throw 'Echec des migrations de base de donnees.' }

Write-Host 'Installation des dependances frontend...' -ForegroundColor Yellow
Push-Location frontend
try {
    & npm install
    if ($LASTEXITCODE -ne 0) { throw 'Echec de npm install.' }
} finally {
    Pop-Location
}

if (Get-Command ffmpeg -ErrorAction SilentlyContinue) {
    Write-Host 'FFmpeg detecte dans le PATH.' -ForegroundColor Green
} else {
    Write-Host 'FFmpeg non detecte. Installez-le avec : winget install Gyan.FFmpeg' -ForegroundColor Yellow
}

Write-Host ''
Write-Host 'Installation terminee.' -ForegroundColor Green
Write-Host 'Jeton d installation (GTF_SETUP_TOKEN) :' -ForegroundColor Cyan
$setupLine = Get-Content '.env' | Where-Object { $_ -like 'GTF_SETUP_TOKEN=*' }
if ($setupLine) { Write-Host ($setupLine -replace 'GTF_SETUP_TOKEN=', '') -ForegroundColor White }
Write-Host ''
Write-Host 'Demarrez avec : scripts\start.ps1' -ForegroundColor Cyan
Write-Host 'Adresse : http://localhost:5174' -ForegroundColor Cyan
