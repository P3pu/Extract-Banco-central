# Executor RAW → CORE no servidor, sem Docker

Substitui a tarefa horária do Windows (`docs/AUTOMACAO_LOCAL_RAW_CORE.md`)
pelo mesmo código Python rodando no servidor do PostgreSQL `Atendimento`.

## Layout

| Caminho | Conteúdo | Dono / modo |
|---|---|---|
| `/opt/extract-banco-central/releases/<commit>` | Código baixado do GitHub | root, 0755 |
| `/opt/extract-banco-central/app` | Link para a release ativa | root |
| `/opt/extract-banco-central/venv` | Ambiente Python (`requirements.txt`) | root |
| `/etc/bcd/app.env` | Credenciais MySQL/PostgreSQL; `POSTGRES_HOST=127.0.0.1` | root:bcd, 0640 |
| `/etc/bcd/global-bundle.pem` | CA pública da AWS para os MySQL | root, 0644 |
| `/var/lib/bcd/pending.sqlite` | Diário de IDs alterados | bcd, 0700 |
| `/var/lib/bcd/core-person-hmac.key` | Chave HMAC de CPF (quando provisionada) | bcd, 0600 |

O serviço roda como o usuário de sistema `bcd`, sem shell, com
`ProtectSystem=strict` e escrita só em `/var/lib/bcd`. Os logs vão para o
journald (`journalctl -u bcd-raw-core`).

`BCD_DIRECT_POSTGRES=1` dispensa o túnel SSH e conecta no loopback do
servidor, na porta publicada do PostgreSQL. `BCD_STATE_DIR` substitui o
`LOCALAPPDATA` do Windows para o diário e a chave HMAC.

## Instalar ou atualizar uma versão

```bash
curl -fsSL https://raw.githubusercontent.com/P3pu/Extract-Banco-central/<commit>/deploy/server/install.sh -o /tmp/bcd-install.sh
bash /tmp/bcd-install.sh <commit>
```

O instalador cria o usuário `bcd` e os diretórios, baixa a release, instala as
dependências, troca o link `app` e instala as unidades systemd. Não grava
segredos nem ativa o timer. Voltar de versão = rodar de novo com o commit
anterior.

## Verificação (somente leitura)

```bash
cd /opt/extract-banco-central/app
runuser -u bcd -- /opt/extract-banco-central/venv/bin/python -m src.main check --source postgres
runuser -u bcd -- /opt/extract-banco-central/venv/bin/python -m src.main check --source magento
runuser -u bcd -- /opt/extract-banco-central/venv/bin/python -m src.main check --source ativo
runuser -u bcd -- env BCD_DIRECT_POSTGRES=1 BCD_STATE_DIR=/var/lib/bcd \
  /opt/extract-banco-central/venv/bin/python -m src.automation.local_raw_core audit-core
```

## Virada do Windows para o servidor

1. As três verificações de conexão passam.
2. Desabilitar a tarefa `BancoCentral-RAW-CORE-Hourly` no Windows e rodar lá
   um `core-only` final, até o diário local ficar vazio. Os dois executores
   usam o mesmo advisory lock, mas cada um tem o seu diário: não alterná-los.
3. No servidor: `systemctl start bcd-raw-core.service` e conferir
   `AUTOMATION_CYCLE_OK` em `journalctl -u bcd-raw-core`.
4. `systemctl enable --now bcd-raw-core.timer` e acompanhar três ciclos.

Rollback: `systemctl disable --now bcd-raw-core.timer` e reabilitar a tarefa
Windows. Nada de RAW, CORE, watermarks ou diário é apagado.

## Situação em 28/10/2026

- Release `b2b553b` instalada. Virada concluída às 11:55: tarefa Windows
  `BancoCentral-RAW-CORE-Hourly` desabilitada, primeiro ciclo manual no
  servidor com `AUTOMATION_CYCLE_OK` e `bcd-raw-core.timer` habilitado.
- O MySQL do Ativo (RDS na AWS) não aceita conexões do IP `178.156.169.207`.
  Até a regra de entrada TCP 3306 sair no Security Group, o Ativo chega por
  uma ponte temporária: a tarefa Windows `BancoCentral-Ativo-Tunnel`
  (`deploy/local/run_ativo_tunnel.ps1`) publica o RDS em `127.0.0.1:13306`
  do servidor; o servidor resolve o hostname do RDS para `127.0.0.1` em
  `/etc/hosts`, mantendo a verificação TLS, e usa `ATIVO_MYSQL_PORT=13306`.
  A chave `bcd_tunnel` só pode escutar em `127.0.0.1:13306`. Com o notebook
  desligado, os ciclos falham na etapa Ativo e retomam pelos watermarks.
- Quando a regra da AWS sair: `ATIVO_MYSQL_PORT=3306` em `/etc/bcd/app.env`,
  remover a linha do RDS em `/etc/hosts`, remover `permitlisten` da chave
  `bcd_tunnel` e apagar a tarefa `BancoCentral-Ativo-Tunnel`.
- 29/10/2026: a ponte do Ativo ficou fora de 28/10 13:57 a 29/10 08:55
  (horário de Brasília) porque o notebook suspende após 5 minutos ocioso na
  tomada; os ciclos terminaram `AUTOMATION_CYCLE_PARTIAL failed=ativo` e o
  Ativo retomou pelo watermark sem perda. Release `fc510f8` instalada
  (retomada da recuperação CORE).
- A chave HMAC de CPF não foi encontrada no notebook. O gate
  `CORE_PII_ENABLE_SYNC` continua fechado; antes de abri-lo, localizar a chave
  usada no backfill de 27/10 ou definir rotação, para não gerar tokens
  diferentes para o mesmo CPF.
