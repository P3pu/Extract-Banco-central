# Homologação local CORE — Fase C1.5 (cobertura para revisão)

**Estado:** o usuário informou que a C1 anterior terminou com
`C1_LOCAL_TESTS_PASSED` em PostgreSQL 16.13 local; esta revisão C1.5 **não foi
executada**. Não executar os comandos abaixo antes de autorização específica
para a nova carga local. O banco de produção nunca é destino deste roteiro.

## Compatibilidade e isolamento

Uma consulta `SELECT current_setting(...)` no servidor existente, com
`transaction_read_only=on`, retornou PostgreSQL **16.13**
(`server_version_num=160013`). O Compose fixa a imagem oficial
[`postgres:16.13-trixie`](https://hub.docker.com/_/postgres/tags?name=16.13),
da mesma versão principal e patch.

O serviço usa `network_mode: none`, **não publica portas**, usa o banco
`core_c1_homolog` e só aceita comandos pelo socket Unix interno. O nome do
projeto Compose agora é `banco-central-core-c15`: seu volume
`banco-central-core-c15_core_c1_pgdata` é distinto do volume C1 anterior
`banco-central-core-c1_core_c1_pgdata`, que não deve ser reutilizado nem
apagado. Os únicos
bind mounts são `sql/` e esta pasta, ambos somente leitura; `.env`, dumps e
credenciais de produção não entram no container. A autenticação `trust` é
admissível **somente** neste container descartável sem rede. Não reutilizar
esta configuração em servidor ou com portas publicadas. O perfil `manual`
impede `docker compose up` sem seleção explícita.

Não usar `src/staging_deploy.py` nem os comandos normais do projeto aqui:
eles foram projetados para produção. O `run.sh` verifica banco, usuário,
versão 16 e conexão por socket **antes de cada arquivo SQL**.

## Arquivos

- `compose.yaml`: PostgreSQL local isolado, volume próprio.
- `run.sh`: execução controlada por etapas `schema`, `seed`, `core`, `test`.
- `fixtures.sql`: apenas IDs, códigos e rótulos inventados; sem CPF, nome de
  pessoa, e-mail, IP real ou exportação de produção.
- `capture_candidates.sh`: extrai os dois SELECTs de `004` para tabelas
  temporárias de teste; não modifica o SQL candidato versionado.
- `tests.psql`: asserts sintéticos e execução das consultas candidatas/aceite.

`schema` aplica os DDLs versionados de `sql/postgres/` em ordem numérica,
incluindo `003b` e `005b`, depois `sql/staging/001_create_staging_schema.sql`
e as 31 views Magento/Ativo em ordem. Por último, **somente no laboratório**,
aplica a proposta `sql/core/proposed/000_missing_sources.sql` para que os
lookups opcionais de cupom/status da consulta candidata compilem. Esse arquivo
não é uma migração aprovada para produção; a view de comprador Ativo continua
sem `comprador_usuario_id`, como no repositório atual.

`core` aplica apenas `001_core_ddl.sql` e `002_core_helpers.sql`, nessa ordem.
`schema` também falha se o banco já contém os esquemas RAW/STAGING/CORE, para
evitar uma execução completa sobre volume modificado.
`test` usa os UPSERTs versionados `003` e `005` exclusivamente no banco
sintético, compila as consultas `004`, executa `900` e verifica constraints,
idempotência, órfão, comprador Ativo nulo, descontos de pai/filhos/cabeçalho,
status contraditório, classificação exata `Grupos`, limite inclusivo de lote,
preservação dos derivados e gate de publicação fechado. A C1.5 acrescenta
comparação automática, com `IS DISTINCT FROM`, dos resultados de `004` com
valores esperados, incluindo `NULL`; as consultas históricas sem fixtures são
marcadas `NAO_COBERTO`, não aprovadas por retornarem zero linhas.

## Roteiro após autorização

**Somente após nova autorização**, executar na raiz deste repositório, em
PowerShell, com Docker Desktop/Compose disponíveis. Conferir primeiro que o
projeto `banco-central-core-c15` e seu volume ainda não existem. Se já
existirem, parar e revisar; não fazer `down --volumes` nem reutilizar o volume.
Conferir o diretório e o nome do projeto antes de cada comando.

```powershell
$c1Compose = 'homologation/core-c1/compose.yaml'
docker compose -f $c1Compose --profile manual config
docker compose -f $c1Compose --profile manual config --volumes
docker volume inspect banco-central-core-c15_core_c1_pgdata
# A inspeção deve informar "No such volume"; se existir, PARAR.
docker compose -f $c1Compose --profile manual up -d db
docker compose -f $c1Compose --profile manual ps
docker compose -f $c1Compose --profile manual exec -T db sh -c "tr -d '\r' < /workspace/c1/run.sh | sh -s schema"
docker compose -f $c1Compose --profile manual exec -T db sh -c "tr -d '\r' < /workspace/c1/run.sh | sh -s seed"
docker compose -f $c1Compose --profile manual exec -T db sh -c "tr -d '\r' < /workspace/c1/run.sh | sh -s core"
docker compose -f $c1Compose --profile manual exec -T db sh -c "tr -d '\r' < /workspace/c1/run.sh | sh -s test"
```

`tr` apenas normaliza CRLF de um checkout Windows no fluxo para `sh`; não
altera os arquivos do repositório nem o banco.

Critério mínimo **sintético**: `run.sh test` termina com
`C1_HISTORICAL_ACCEPTANCE_NOT_COVERED` e `C1_LOCAL_TESTS_PASSED`; as
consultas `B02`/`B03` do `900` retornam zero divergências; `B07` retorna
`indicadores_publicados=0`. O script falha na primeira violação. Usar volume
novo para uma repetição completa de `schema`/`seed`/`core`: os scripts de
estrutura e as fixtures não são concebidos para reaplicação no mesmo volume.

Para parar sem apagar os dados sintéticos:

```powershell
docker compose -f $c1Compose --profile manual down
```

O descarte do volume **não está autorizado nesta fase**. Somente com
autorização específica e após conferir que não há dados que precisem ser
preservados, o volume exclusivo C1.5 seria
`banco-central-core-c15_core_c1_pgdata`. Não executar `down --volumes` agora.

```powershell
docker compose -f $c1Compose --profile manual config --volumes
# Com autorização separada: docker compose -f $c1Compose --profile manual down --volumes
```

O Compose declara somente `core_c1_pgdata`; `down --volumes` afetaria esse volume
e o container da pilha `banco-central-core-c15`, sem remover órfãos de outros
projetos. Não usar `docker volume prune` ou comandos de remoção genéricos.

## Resultados esperados da C1.5

- Magento 4001: desconto dos filhos 15, residual do cabeçalho 0, líquido
  individual candidato 85.
- Magento 4101: desconto apenas no cabeçalho 20, componentes com desconto 0,
  residual 20 e líquido individual `NULL` (sem rateio inventado).
- Magento 4201/4301/4401/4501: cancelamento parcial, reembolso, cancelamento
  total e quantidade 3; nenhum gera líquido individual candidato ou pagamento
  confirmado individualmente. O cancelamento individual é indeterminado no
  parcial e em quantidade 3, e verdadeiro no total.
- Magento 4601: desconto dos itens desconhecido (`NULL`), residual e líquidos
  candidatos `NULL`; não substituir ausência por zero.
- Ativo 5001: preço 100, desconto 10, kit 5, líquido candidato 85 e taxa de
  serviço 2 em campo separado. 5002 preserva o pedido órfão; 5003 tem desconto
  desconhecido e 5004 kit desconhecido, portanto ambos têm líquido `NULL`.
- Aceite histórico T04/T05/T06/T07/T18 e evento 22054: `NAO_COBERTO`, pois os
  IDs históricos não aparecem nas fixtures sintéticas. Resultado vazio não é
  aprovação desses critérios.

O contrato RAW versionado exige `raw.ativo_pedido_evento.id_pedido` e
`raw.magento_sales_order_item.order_id` não nulos. Assim, a C1.5 **não injeta**
inscrições com pedido nulo. O teste verifica essas duas restrições; se uma
fonte passar a admitir `NULL`, atualizar contrato, estratégia de lote (`BETWEEN`
hoje exclui `NULL`) e teste antes de afirmar cobertura.

Encerrar a C1 somente após: execução nova em volume sintético C1.5 vazio;
`schema`, `seed`, `core`, `test` sem erro; 31 views compiladas; asserts de
idempotência, órfãos, finanças, quantidades e status aprovados; definição da
view com gate `WHERE FALSE` e contagem zero; revisão explícita das lacunas de
aceite histórico e das dependências de derivação. Nenhum desses resultados
autoriza publicar indicadores ou migrar para o Naruto.

## Limites da homologação

Os dados sintéticos provam compilação e invariantes básicos, não cobertura de
casos históricos, performance ou reconciliação com produção. As fontes
`sa_cupom_desconto`, `sa_status_detalhado`, comprador Ativo e composição de
combo ainda dependem de integração separada. O cálculo/invalidação completo
dos indicadores derivados **não existe**; `core.fato_inscricao_indicadores_validos`
continua fechada por `WHERE FALSE`, inclusive neste laboratório. Nenhum teste
autoriza remover esse gate ou executar DDL/cargas em produção.
