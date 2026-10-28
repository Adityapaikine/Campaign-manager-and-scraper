$ErrorActionPreference = 'Stop'
$teamPidFile = Join-Path $PSScriptRoot 'Logs\team-server.pid'
if (-not (Test-Path -LiteralPath $teamPidFile)) { Write-Output 'No recorded Team server process.'; exit 0 }
$teamId = [int](Get-Content -LiteralPath $teamPidFile)
$teamProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $teamId" -ErrorAction SilentlyContinue
if ($teamProcess -and $teamProcess.CommandLine -like ('*' + (Join-Path $PSScriptRoot 'team_server.py') + '*')) {
    # A Windows virtual environment may launch a second Python process. Stop
    # only descendants running this installation's server before its launcher.
    function Stop-TeamServerTree([int]$ServerProcessId) {
        $teamChildren = Get-CimInstance Win32_Process -Filter "ParentProcessId = $ServerProcessId" -ErrorAction SilentlyContinue
        foreach ($teamChild in $teamChildren) {
            if ($teamChild.CommandLine -like ('*' + (Join-Path $PSScriptRoot 'team_server.py') + '*')) {
                Stop-TeamServerTree -ServerProcessId $teamChild.ProcessId
            }
        }
        Stop-Process -Id $ServerProcessId -ErrorAction SilentlyContinue
    }
    Stop-TeamServerTree -ServerProcessId $teamId
    Write-Output 'Team server stopped. In-flight transactions roll back if not committed.'
} else { Write-Output 'The recorded process is no longer this Team server. No process was stopped.' }
Remove-Item -LiteralPath $teamPidFile
