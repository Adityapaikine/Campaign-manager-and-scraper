param([string]$ServerUrl = 'http://127.0.0.1:8765')
$ErrorActionPreference = 'Stop'
try {
    $teamResult = Invoke-RestMethod -Uri ($ServerUrl.TrimEnd('/') + '/health') -TimeoutSec 5
    if ($teamResult.service -ne 'Lead Workspace' -or $teamResult.status -ne 'ok') { throw 'Unexpected service response.' }
    Write-Output ('Lead Workspace is responding; schema ' + $teamResult.schema + '. Authentication is still required for all records.')
} catch { Write-Output ('Not ready at ' + $ServerUrl + '. Check Logs\team-server.err.log and the server certificate.'); exit 1 }
