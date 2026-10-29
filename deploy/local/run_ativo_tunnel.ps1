# Ponte temporária: publica o MySQL do Ativo em 127.0.0.1:13306 do servidor,
# passando pela rede deste computador (liberada no Security Group do RDS).
# Remover quando o IP do servidor for liberado no RDS.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
$line = Get-Content -LiteralPath (Join-Path $projectRoot '.env') |
    Where-Object { $_ -match '^ATIVO_MYSQL_HOST=' } | Select-Object -First 1
if (-not $line) { throw 'ATIVO_MYSQL_HOST ausente no .env' }
$ativoHost = ($line -split '=', 2)[1].Trim().Trim("'").Trim('"')
$key = Join-Path $env:USERPROFILE '.ssh\bcd_automation_ed25519'
$server = if ($env:BCD_SSH_HOST) { $env:BCD_SSH_HOST } else { '178.156.169.207' }

$logDirectory = Join-Path $env:LOCALAPPDATA 'BancoCentralDados'
New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
$log = Join-Path $logDirectory 'ativo-tunnel.log'
Add-Content -LiteralPath $log -Encoding Unicode -Value ("TUNNEL_START {0:o}" -f (Get-Date))
# Bloqueia enquanto o túnel estiver de pé; a tarefa reinicia em até 5 minutos.
& ssh.exe -N -i $key -o BatchMode=yes -o IdentitiesOnly=yes `
    -o StrictHostKeyChecking=yes -o ExitOnForwardFailure=yes `
    -o ServerAliveInterval=15 -o ServerAliveCountMax=3 `
    -R "127.0.0.1:13306:${ativoHost}:3306" "bcd_tunnel@$server"
Add-Content -LiteralPath $log -Encoding Unicode `
    -Value ("TUNNEL_EXIT {0:o} code={1}" -f (Get-Date), $LASTEXITCODE)
