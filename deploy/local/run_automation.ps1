# Executa o ciclo já autorizado no perfil Windows do proprietário do projeto.
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
$log = Join-Path $logDirectory 'automation-windows.log'
Set-Location -LiteralPath $projectRoot
$env:BCD_AUTOMATION_ENABLE = 'approved'

Add-Content -LiteralPath $log -Encoding Unicode `
    -Value ("AUTOMATION_START {0:o}" -f (Get-Date))
& $python -m src.automation.local_raw_core run-once *>> $log
$exitCode = $LASTEXITCODE
Add-Content -LiteralPath $log -Encoding Unicode `
    -Value ("AUTOMATION_EXIT {0:o} code={1}" -f (Get-Date), $exitCode)
exit $exitCode
