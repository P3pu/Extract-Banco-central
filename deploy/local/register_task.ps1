param([switch]$Activate)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$taskName = 'BancoCentral-RAW-CORE-Hourly'
$runScript = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot 'run_automation.ps1')).Path
$currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$now = Get-Date
$nextHour = $now.Date.AddHours($now.Hour + 1)

if (-not $Activate) {
    Write-Output "PREVIEW task=$taskName user=$currentUser next=$($nextHour.ToString('o'))"
    Write-Output 'Sem -Activate, nenhuma tarefa foi registrada.'
    exit 0
}
if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    throw 'Tarefa existente: revisar antes de alterar'
}

$argument = '-NoProfile -NonInteractive -File "' + $runScript + '"'
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $argument
$trigger = New-ScheduledTaskTrigger -Once -At $nextHour `
    -RepetitionInterval (New-TimeSpan -Hours 1) `
    -RepetitionDuration (New-TimeSpan -Days 3650)
$principal = New-ScheduledTaskPrincipal -UserId $currentUser `
    -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 4) `
    -StartWhenAvailable -RunOnlyIfNetworkAvailable -WakeToRun

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
    -Principal $principal -Settings $settings `
    -Description 'MySQL RAW e CORE; execução horária no usuário interativo.' | Out-Null
$info = Get-ScheduledTaskInfo -TaskName $taskName
Write-Output "REGISTERED task=$taskName next=$($info.NextRunTime.ToString('o'))"
