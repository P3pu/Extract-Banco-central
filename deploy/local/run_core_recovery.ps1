# Rederivação única das inscrições invalidadas pelo antigo 022.
# Segredos permanecem no .env local e no túnel SSH; não entram na tarefa agendada.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw 'Ambiente Python local não encontrado'
}

$logDirectory = Join-Path $env:LOCALAPPDATA 'BancoCentralDados'
New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
$log = Join-Path $logDirectory 'core-recovery.log'
Set-Location -LiteralPath $projectRoot
$env:BCD_AUTOMATION_ENABLE = 'approved'

Add-Content -LiteralPath $log -Encoding Unicode `
    -Value ("RECOVERY_START {0:o}" -f (Get-Date))
& $python -u -m src.automation.core_recovery *>> $log
$exitCode = $LASTEXITCODE
Add-Content -LiteralPath $log -Encoding Unicode `
    -Value ("RECOVERY_EXIT {0:o} code={1}" -f (Get-Date), $exitCode)
exit $exitCode
