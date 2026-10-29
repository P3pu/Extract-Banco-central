# Registra a ponte temporária do MySQL Ativo para o servidor e já a inicia.
# Remover com: Unregister-ScheduledTask BancoCentral-Ativo-Tunnel -Confirm:$false
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$taskName = 'BancoCentral-Ativo-Tunnel'
$script = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot 'run_ativo_tunnel.ps1')).Path
$user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    throw 'Tarefa existente: remova antes de registrar de novo'
}
$action = New-ScheduledTaskAction -Execute 'powershell.exe' `
    -Argument ('-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + $script + '"')
$atLogon = New-ScheduledTaskTrigger -AtLogOn -User $user
$every5 = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes 5) -RepetitionDuration (New-TimeSpan -Days 3650)
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -StartWhenAvailable -RunOnlyIfNetworkAvailable
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger @($atLogon, $every5) `
    -Principal $principal -Settings $settings `
    -Description 'Ponte temporaria do MySQL Ativo para o servidor (ate liberar o IP no RDS).' | Out-Null
Start-ScheduledTask -TaskName $taskName
Write-Output "REGISTERED $taskName"
