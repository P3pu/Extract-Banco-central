# RAW R1 — laboratório local isolado (preparado, não executado)

Este laboratório comprova compatibilidade funcional do índice em PostgreSQL
16.13. Poucas linhas sintéticas **não** comprovam ganho real de desempenho nem
substituem o plano/monitoramento do servidor Naruto. Nenhuma etapa SQL deste
roteiro está autorizada nesta entrega.

`compose.yaml` fixa o projeto `banco-central-raw-r1` e o volume
`banco-central-raw-r1_raw_r1_pgdata`, distintos dos laboratórios C1/C1.5.
`network_mode: none`, ausência de `ports` e montagens `:ro` impedem acesso de
rede, publicação de porta e uso de volumes da produção. `trust` existe apenas
para este container sem rede; não reutilizar essa configuração fora dele.
O perfil `manual` exige selecionar explicitamente o serviço `db`.

O `run.sh` usa somente `psql` por socket Unix e verifica antes de cada arquivo:
banco `raw_r1_homolog`, usuário `raw_r1`, servidor 16.13 e ausência de endereço
TCP. `schema` exige que o esquema `raw` ainda não exista. Os arquivos
`schema.psql`, `seed.sql` e `tests.psql` aplicam apenas o contrato da tabela
RAW versionada e IDs/dados inventados. `index` executa preflight, depois uma
chamada `psql` separada em autocommit para `CREATE INDEX CONCURRENTLY`, depois
verificação do catálogo. `existing` repete essa sequência e exige o mesmo OID
para comprovar o comportamento de índice já existente. Não há limpeza
automática nem execução de `DROP INDEX`.

## Roteiro **somente após autorização específica para SQL local**

Na raiz do repositório, PowerShell. Primeiro revisar o resultado de `config`:
nenhuma porta, rede ou volume C1/C1.5. A guarda abaixo interrompe se o volume
já existir; não reutilizar nem apagar. Executar etapas uma a uma, verificando
o resultado de cada uma antes de avançar.

```powershell
$r1Compose = 'homologation/raw-index-r1/compose.yaml'
docker info --format '{{.ServerVersion}}'
if ($LASTEXITCODE -ne 0) { throw 'Docker indisponível' }
docker compose -f $r1Compose --profile manual config
if ($LASTEXITCODE -ne 0) { throw 'Compose inválido' }
docker compose -f $r1Compose --profile manual config --volumes
if ($LASTEXITCODE -ne 0) { throw 'Volumes inválidos' }
docker volume inspect banco-central-raw-r1_raw_r1_pgdata 2>$null | Out-Null
if ($LASTEXITCODE -eq 0) { throw 'Volume R1 já existe: parar e revisar' }
docker compose -f $r1Compose --profile manual up -d db
if ($LASTEXITCODE -ne 0) { throw 'Container não iniciado' }
docker compose -f $r1Compose --profile manual ps
docker compose -f $r1Compose --profile manual exec -T db sh -c "tr -d '\r' < /workspace/r1/run.sh | sh -s schema"
if ($LASTEXITCODE -ne 0) { throw 'schema falhou' }
docker compose -f $r1Compose --profile manual exec -T db sh -c "tr -d '\r' < /workspace/r1/run.sh | sh -s seed"
if ($LASTEXITCODE -ne 0) { throw 'seed falhou' }
docker compose -f $r1Compose --profile manual exec -T db sh -c "tr -d '\r' < /workspace/r1/run.sh | sh -s index"
if ($LASTEXITCODE -ne 0) { throw 'index falhou' }
docker compose -f $r1Compose --profile manual exec -T db sh -c "tr -d '\r' < /workspace/r1/run.sh | sh -s test"
if ($LASTEXITCODE -ne 0) { throw 'test falhou' }
docker compose -f $r1Compose --profile manual exec -T db sh -c "tr -d '\r' < /workspace/r1/run.sh | sh -s existing"
if ($LASTEXITCODE -ne 0) { throw 'existing falhou' }
```

Parar imediatamente se qualquer comando falhar. Os comandos acima executam
DDL/DML **somente no laboratório**, portanto não executá-los antes da próxima
autorização. O SQL de teste escreve depois da criação do índice e só deve ser
executado uma vez no volume novo. O teste `existing` não recria nem substitui
o índice válido; se houver definição inválida, o preflight falha e exige
análise manual. O `EXPLAIN` local pode continuar escolhendo Seq Scan por causa
do tamanho da fixture; isso não é falha funcional.

Para apenas **parar** o laboratório, preservando o volume para revisão:

```powershell
docker compose -f $r1Compose --profile manual down
```

Não executar `down --volumes`, `docker volume rm` ou equivalentes sem
autorização específica. O descarte posterior deve identificar e inspecionar
somente `banco-central-raw-r1_raw_r1_pgdata`; nunca atingir volumes C1/C1.5.
