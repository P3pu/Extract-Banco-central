# Automação local RAW → STAGING → CORE

Esta implantação roda no computador Windows do responsável pelo projeto, não em
container nem no Naruto. O túnel SSH dedicado entrega a conexão PostgreSQL ao
loopback local; não se transmite a senha PostgreSQL em texto aberto pela rede.
MySQL Ativo e Magento são lidos diretamente pelo Python existente.

## Ciclo e escopo

- Uma tarefa horária executa `deploy/local/run_automation.ps1` somente quando o
  usuário Windows está conectado. O computador precisa estar ligado, com rede e
  sem suspensão. Durante a execução, o processo solicita ao Windows que evite
  suspensão por ociosidade; a tarefa também solicita despertar no horário.
  Suspensão manual, fechamento da tampa ou queda de energia ainda interrompem
  o ciclo. O executor recusa concorrência pelo advisory lock PostgreSQL e
  mantém sua sessão de controle ativa por heartbeat. Se perder o lock, para
  antes do próximo lote e preserva o diário. Só essa sessão de controle usa
  `idle_session_timeout=120000` (2 minutos), para liberar automaticamente um
  lock órfão após queda de conexão; a configuração não é persistente no banco.
- Cada ciclo processa `sales_order`, `sales_order_item`, `pedido` e
  `pedido_evento` em modo INCREMENTAL, com seus watermarks e UPSERTs existentes.
  Magento mantém a sobreposição de cinco minutos.
- A cada 15 dias desde a última reconciliação bem-sucedida de cada entidade
  Ativo, executa separadamente a janela de 30 dias. Mudanças em pedidos
  históricos fora dessa janela não são garantidamente detectadas.
- As views STAGING refletem a RAW sem etapa de carga. Após as transações RAW, o
  diário SQLite local fornece os IDs alterados à CORE. São atualizados apenas
  `core.fato_pedido` e `core.fato_inscricao`, por faixas limitadas e pelos IDs
  efetivamente afetados. Mudanças em pedidos também reprocessam inscrições
  relacionadas. Dimensões auxiliares de eventos/combos e regras externas não
  fazem parte deste agendamento; alterações nelas requerem rotina própria.
- A view `core.fato_inscricao_indicadores_validos` deve continuar fechada. A
  automação recusa rodar se o gate abrir e verifica que seu resultado é vazio.

Não existe rota FULL nem migração automática nesta tarefa. Uma falha mantém os
IDs no diário para reprocessamento; nunca se deve apagar o diário para
"resolver" um erro. O último resultado também aparece em
`%LOCALAPPDATA%\BancoCentralDados\automation-windows.log`, sem senhas nem
dados pessoais.

## Preparação e verificação

No diretório do repositório, com o `.venv` e o `.env` locais já provisionados:

```powershell
.venv\Scripts\python.exe -m src.automation.local_raw_core check
.venv\Scripts\python.exe -m src.automation.local_raw_core plan-core
.venv\Scripts\python.exe -m src.automation.local_raw_core audit-core
```

`check` testa os dois MySQL e o PostgreSQL via túnel. `plan-core` mostra apenas
contagens e número de faixas pendentes. `audit-core` lê os últimos lotes sem
expor registros. A chave `~\.ssh\bcd_automation_ed25519` pertence a um usuário
SSH sem shell, restrito ao encaminhamento de `127.0.0.1:59381` no Naruto. A
validação da chave do servidor permanece obrigatória.

Após uma atualização RAW feita fora deste executor, o bootstrap dos IDs pode
ser necessário uma única vez, com o marco temporal conferido com as auditorias:

```powershell
.venv\Scripts\python.exe -m src.automation.local_raw_core bootstrap --since 2026-10-23T12:00:00+00:00
```

O bootstrap é idempotente no diário, mas consulta quatro tabelas RAW grandes;
não deve ser repetido sem avaliar custo. Para concluir apenas a CORE pendente:

```powershell
$env:BCD_AUTOMATION_ENABLE = 'approved'
.venv\Scripts\python.exe -m src.automation.local_raw_core core-only
```

## Agendamento e suspensão

A tarefa Windows deve usar a conta interativa do proprietário, privilégios
limitados, repetição de uma hora e a ação:

```text
powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "<repositorio>\deploy\local\run_automation.ps1"
```

Não registrar senhas na ação, no XML da tarefa ou nos logs. O bloqueio por
advisory lock protege contra sobreposição mesmo se o Agendador disparar outra
instância. Verificar `LastTaskResult`, log local, `raw._etl_runs` e
`core.core_etl_execucao`. Em falha, desabilitar a tarefa e investigar antes de
retomar. Desabilitar a tarefa é o rollback operacional; preserva RAW, CORE,
watermarks, diário e logs. Não remover volumes ou tabelas.

## Critérios antes de considerar saudável

1. Conectividade às três fontes aprovada sem desabilitar TLS dos MySQL.
2. Um ciclo manual termina com `AUTOMATION_CYCLE_OK` e diário vazio.
3. Últimos lotes CORE estão `SUCCEEDED`; zero registros na view de indicadores.
4. Sem lacuna entre a última extração RAW e a atualização das duas fatos CORE.
5. Tarefa agendada habilitada, configurada para não paralelizar, com último
   resultado zero após uma execução real.

O agendamento local não garante funcionamento quando o computador estiver
desligado ou o usuário desconectado. Para disponibilidade contínua, será
necessário outro executor aprovado futuramente.
