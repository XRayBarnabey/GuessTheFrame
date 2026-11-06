# GuessTheFrame - start backend and frontend (Windows 11 / PowerShell 5.1+)
$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not (Test-Path '.venv\Scripts\python.exe')) {
    throw 'Environnement Python absent. Lancez scripts\setup.ps1.'
}
if (-not (Test-Path '.env')) {
    throw 'Fichier .env absent. Lancez scripts\setup.ps1.'
}
if (-not (Test-Path 'frontend\node_modules')) {
    throw 'Dependances frontend absentes. Lancez scripts\setup.ps1.'
}

New-Item -ItemType Directory -Force -Path .run, logs | Out-Null

function Stop-Existing($pidFile) {
    if (Test-Path $pidFile) {
        $oldPid = (Get-Content $pidFile | Select-Object -First 1).Trim()
        if ($oldPid) {
            taskkill /PID $oldPid /T /F 2>$null | Out-Null
        }
        Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
    }
}

Stop-Existing '.run\backend.pid'
Stop-Existing '.run\frontend.pid'

Write-Host 'Application des migrations...' -ForegroundColor DarkGray
& .\.venv\Scripts\python.exe -m alembic -c backend\alembic.ini upgrade head | Out-Null

Write-Host 'Demarrage du backend (http://127.0.0.1:5274)...' -ForegroundColor Yellow
$backend = Start-Process -FilePath '.\.venv\Scripts\python.exe' `
    -ArgumentList @('-m','uvicorn','app.main:app','--app-dir','backend','--host','127.0.0.1','--port','5274','--reload') `
    -WorkingDirectory $root `
    -RedirectStandardOutput 'logs\backend.out.log' `
    -RedirectStandardError 'logs\backend.err.log' `
    -PassThru -WindowStyle Hidden
$backend.Id | Set-Content '.run\backend.pid'

Write-Host 'Demarrage du frontend (http://localhost:5174)...' -ForegroundColor Yellow
$frontend = Start-Process -FilePath 'cmd.exe' `
    -ArgumentList @('/c','npm','run','dev','--','--host','0.0.0.0','--port','5174') `
    -WorkingDirectory (Join-Path $root 'frontend') `
    -RedirectStandardOutput (Join-Path $root 'logs\frontend.out.log') `
    -RedirectStandardError (Join-Path $root 'logs\frontend.err.log') `
    -PassThru -WindowStyle Hidden
$frontend.Id | Set-Content '.run\frontend.pid'

function Wait-Port($port, $timeoutSeconds) {
    $deadline = (Get-Date).AddSeconds($timeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $client = New-Object System.Net.Sockets.TcpClient
            $client.Connect('127.0.0.1', $port)
            $client.Close()
            return $true
        } catch {
            Start-Sleep -Milliseconds 500
        }
    }
    return $false
}

$backendReady = Wait-Port 5274 45
$frontendReady = Wait-Port 5174 45

if (-not $backendReady -or -not $frontendReady) {
    Write-Host ''
    Write-Host 'Le demarrage semble incomplet.' -ForegroundColor Red
    Write-Host 'Consultez logs\backend.err.log et logs\frontend.err.log.' -ForegroundColor Red
    if (-not $backendReady) { Write-Host 'Backend non disponible sur le port 5274.' -ForegroundColor Red }
    if (-not $frontendReady) { Write-Host 'Frontend non disponible sur le port 5174.' -ForegroundColor Red }
    exit 1
}

Write-Host ''
Write-Host 'GuessTheFrame est demarre.' -ForegroundColor Green
Write-Host 'Interface : http://localhost:5174' -ForegroundColor Cyan
Write-Host 'API       : http://127.0.0.1:5274/api/health' -ForegroundColor DarkGray
Write-Host 'Arret     : scripts\stop.ps1' -ForegroundColor DarkGray
Write-Host ''

Start-Process 'http://localhost:5174'
