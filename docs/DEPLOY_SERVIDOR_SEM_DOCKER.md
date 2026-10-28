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

- Release `b2b553b` instalada; timer instalado e **desabilitado**.
- PostgreSQL e Magento conectam a partir do servidor; `audit-core` e
  `lock-status` funcionam em modo direto.
- **Bloqueio:** o MySQL do Ativo (RDS na AWS, endpoint público) não aceita
  conexões do IP `178.156.169.207` — falta a regra de entrada TCP 3306 no
  Security Group do RDS.
- A chave HMAC de CPF não foi encontrada no notebook. O gate
  `CORE_PII_ENABLE_SYNC` continua fechado; antes de abri-lo, localizar a chave
  usada no backfill de 27/10 ou definir rotação, para não gerar tokens
  diferentes para o mesmo CPF.
