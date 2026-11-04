# Operação

Guia para conferir se o pipeline está saudável e agir quando algo falha. As etapas do
ciclo estão em [AUTOMACAO_LOCAL_RAW_CORE.md](AUTOMACAO_LOCAL_RAW_CORE.md), e os arquivos
do servidor, em [DEPLOY_SERVIDOR_SEM_DOCKER.md](DEPLOY_SERVIDOR_SEM_DOCKER.md).

Os comandos abaixo só leem, salvo onde está indicado. Nunca copie CPF, nome ou e-mail
para logs, planilhas ou conversas: confira documentos só por contagem ou hash.

## Conferência rápida

No servidor:

```bash
# Timer ativo e horário do próximo ciclo
systemctl is-active bcd-raw-core.timer
systemctl list-timers bcd-raw-core.timer --no-pager

# Versão instalada
readlink -f /opt/extract-banco-central/app

# Resultado dos últimos ciclos
journalctl -u bcd-raw-core --since "-6h" --no-pager -o short-iso \
  | grep -E "AUTOMATION_CYCLE|AUTOMATION_SOURCE_FAILED|Traceback"

# Túnel do Ativo: deve mostrar uma linha
ss -ltn | grep 13306
```

Está saudável quando o último ciclo terminou com `AUTOMATION_CYCLE_OK`, há menos de duas
horas. Com o notebook desligado, `failed=ativo` é esperado, e o Ativo retoma sozinho.

## Consultas no banco

O PostgreSQL roda em Docker. Envie o SQL pela entrada padrão, e use
`SET max_parallel_workers_per_gather=0` em consultas grandes, porque o `/dev/shm` tem só
64 MB:

```bash
C=$(docker ps -qf name=postgres_postgres | head -1)
docker exec -i "$C" psql -U postgres -d Atendimento -X -q < consulta.sql
```

Última carga bem-sucedida de cada tabela RAW:

```sql
SELECT source_system, source_table, mode, max(finished_at) AS ultima
FROM raw._etl_runs WHERE status='SUCCESS'
GROUP BY 1,2,3 ORDER BY ultima;
```

Últimas falhas da RAW e da CORE:

```sql
SELECT source_table, mode, finished_at, error_message
FROM raw._etl_runs WHERE status='FAILED' ORDER BY finished_at DESC LIMIT 10;

SELECT escopo, iniciada_em, encerrada_em, erro_codigo
FROM core.core_etl_execucao WHERE status='FAILED' ORDER BY iniciada_em DESC LIMIT 10;
```

Inscrições que contam, mas ficam fora dos KPIs de pessoas:

```sql
SELECT origem, motivo, count(*)
FROM core.inscricao_fora_kpi_pessoas
WHERE contabiliza_inscricao AND data_evento >= '2026-01-01' AND data_evento < '2027-01-01'
GROUP BY 1,2 ORDER BY 1,3 DESC;
```

Última releitura completa do Ativo:

```sql
SELECT status, finished_at, rows_extracted, rows_loaded
FROM raw._etl_runs WHERE source_table='sa_releitura_completa'
ORDER BY started_at DESC LIMIT 5;
```

## Sintomas e o que fazer

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| `AUTOMATION_CYCLE_PARTIAL failed=ativo` | Túnel fora do ar: notebook desligado ou suspenso | Ligar o notebook e conferir a tarefa `BancoCentral-Ativo-Tunnel`. O Ativo retoma pelo watermark, sem perda |
| `failed=ativo` com o túnel no ar | Falha na origem ou na releitura | Ver a linha `AUTOMATION_SOURCE_FAILED`, que indica a etapa |
| `failed=core_diario` | Falha em `event_sync` ou no religamento | Ver o log. Os outros passos seguem, e o passo tenta de novo na próxima carga de cadastros |
| `failed=core_releitura` | Falha ao levar a releitura à CORE | Repete sozinho a cada ciclo. Não apague `ativo_releitura.sqlite` |
| `Muitas faixas CORE` ou `Muitos lotes de inscrições` | Mudança grande demais para o ciclo | Investigar a origem do volume antes de agir. Não apague o diário |
| `Remoções acima do limite` | Mais de 5.000 inscrições novas sumiram da origem | Ver "Revisar remoções" abaixo |
| `Conflitos de identidade demais` | Mais de 100 conflitos em um lote: erro de leitura ou de chave | Não forçar. Conferir a chave HMAC e a origem |
| `Token de CPF existente divergente` ou `Chave HMAC diverge` | Chave HMAC errada | Parar e conferir `/var/lib/bcd/core-person-hmac.key`. Nunca gerar outra sem o procedimento de rotação |
| `CORE_PERSON_REVISAR_IDENTIDADE` | Documento do cadastro mudou | Sem ação imediata: o registro fica sem pessoa e os demais seguem |
| `EVENT_SYNC ... revisar=SKU` | SKU com datas diferentes no Ativo, possivelmente cidades diferentes | Ver "Curadoria de SKU" abaixo |
| `EVENT_SYNC_ADIADO` | Mais de 50.000 inscrições afetadas no dia | A execução foi desfeita. Investigar qual data ou evento mudou |
| `could not resize shared memory segment` | `/dev/shm` de 64 MB | Em consulta manual, desligar o paralelismo |
| `Já existe carga Ativo em execução` | Outra carga segura o lock | Conferir `pg_locks` e se há carga manual rodando |
| `canceling statement due to statement timeout` | Faixa pesada; `041_inscricao_magento` já passou do limite de 60 s | O diário é preservado e o ciclo tenta de novo. Se repetir, ver [a otimização](CORE_V1_OTIMIZACAO_INSCRICOES.md) |

Regra geral: uma falha mantém os IDs no diário para nova tentativa. **Nunca apague o
diário nem altere um watermark para "resolver" um erro.**

## Rotinas

### Instalar uma versão

Siga [o deploy](DEPLOY_SERVIDOR_SEM_DOCKER.md#instalar-ou-atualizar-uma-versão). Pare o
timer, espere o ciclo terminar, instale, aplique migrações se houver e religue o timer.

### Curadoria de SKU

Quando um SKU aparece em `revisar`, compare os eventos Ativo pelo nome e pela cidade. Só
una os que são a mesma prova: acrescente uma linha por evento (`sku`, `ativo_evento_id`)
em `sql/core/v1/data/evento_sku_curadoria_20261104.csv` e faça uma nova release. O evento
de outra cidade fica de fora da lista.

### Revisar remoções

A releitura mensal para quando as inscrições novas removidas passam de 5.000. O cursor em
`/var/lib/bcd/ativo_releitura.json` mantém a parada, e o ciclo fica parcial até a revisão.
As cargas normais seguem rodando.

1. Conte as novas em `core.inscricao_removida_origem`, por `detectada_em`.
2. Confira uma amostra por ID na origem. Elas já foram confirmadas pela PK, mas um volume
   alto pede explicação.
3. Se forem reais, apague só o arquivo `ativo_releitura.json`. A releitura recomeça, e as
   já marcadas não contam de novo. **Isso altera o estado no servidor.**
4. Se não forem, retire as marcas erradas de `core.inscricao_removida_origem` e leve esses
   IDs à CORE antes de continuar. Ao voltarem a ser lidas na origem, as inscrições também
   perdem a marca sozinhas.

### Cargas longas à mão

Rode fora da sessão SSH, com o timer parado, para que uma queda de conexão não interrompa:

```bash
systemd-run --unit=bcd-carga-exemplo --wait --collect -p TimeoutStartSec=4h /caminho/do/script.sh
journalctl -u bcd-carga-exemplo --no-pager
```

Scripts de cargas únicas ficam em `/var/lib/bcd/releitura/`, fora do repositório. Prefira
retomáveis, que gravem só o que mudou e parem se contagem ou valor mudarem além do esperado.

### Conferir uma planilha com a CORE

Compare com a planilha exportada do sistema, por prova, separando Ativo e Magento:
inscritos não cancelados, valor, tipo de venda e documentos. Compare documentos só por
hash, nunca em texto. Apague os arquivos derivados ao terminar. Diferença em linhas muito
recentes pode ser só horário: a planilha foi gerada depois do último ciclo.

### Atualizar o painel

O painel "Inscritos, Pessoas e Eventos" não atualiza sozinho. Os dados são extraídos da
CORE sob demanda, só em agregados, sem nome nem CPF, e depois publicados. A API para
automatizar isso segue sem decisão ([pendências](CORE_PENDENCIAS.md)).
