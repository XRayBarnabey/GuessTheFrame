# GuessTheFrame - stop local services (Windows 11 / PowerShell 5.1+)
$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Stop-FromPidFile($pidFile, $label) {
    if (-not (Test-Path $pidFile)) {
        Write-Host "$label : aucun PID enregistre." -ForegroundColor DarkGray
        return
    }
    $processId = (Get-Content $pidFile | Select-Object -First 1).Trim()
    if ($processId) {
        taskkill /PID $processId /T /F 2>$null | Out-Null
        Write-Host "$label : arret demande (PID $processId)." -ForegroundColor Yellow
    }
    Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
}

Stop-FromPidFile '.run\backend.pid' 'Backend'
Stop-FromPidFile '.run\frontend.pid' 'Frontend'

Write-Host 'Services arretes.' -ForegroundColor Green
