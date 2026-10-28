param([string]$ListenAddress = '127.0.0.1', [int]$Port = 8765, [string]$Certificate, [string]$PrivateKey)
$ErrorActionPreference = 'Stop'
$teamRoot = $PSScriptRoot
$teamPython = Join-Path $teamRoot 'runtime\python\python.exe'
if (-not (Test-Path -LiteralPath $teamPython)) { $teamPython = Join-Path $teamRoot '.venv\Scripts\python.exe' }
$teamLog = Join-Path $teamRoot 'Logs'
New-Item -ItemType Directory -Path $teamLog -Force | Out-Null
$teamPidFile = Join-Path $teamLog 'team-server.pid'
if (Test-Path -LiteralPath $teamPidFile) {
    $teamExistingId = [int](Get-Content -LiteralPath $teamPidFile)
    $teamExisting = Get-CimInstance Win32_Process -Filter "ProcessId = $teamExistingId" -ErrorAction SilentlyContinue
    if ($teamExisting -and $teamExisting.CommandLine -like ('*' + (Join-Path $teamRoot 'team_server.py') + '*')) {
        Write-Output 'The Team server is already running. Use Status Team Server.ps1.'
        exit 0
    }
}
$teamArguments = @('"' + (Join-Path $teamRoot 'team_server.py') + '"', 'serve', '--host', $ListenAddress, '--port', $Port)
if ($Certificate -and $PrivateKey) { $teamArguments += @('--cert', '"' + $Certificate + '"', '--key', '"' + $PrivateKey + '"') }
$teamProcess = Start-Process -FilePath $teamPython -ArgumentList $teamArguments -WorkingDirectory $teamRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $teamLog 'team-server.out.log') -RedirectStandardError (Join-Path $teamLog 'team-server.err.log') -PassThru
$teamProcess.Id | Set-Content -LiteralPath $teamPidFile
Write-Output ('Team server started with process ID ' + $teamProcess.Id + '. Check Status Team Server.ps1 for readiness.')
