# Homologação local CORE — Fase C1 (preparação)

**Estado:** arquivos preparados; nenhuma criação ou carga local foi executada.
Não executar os comandos abaixo antes de autorização explícita. O banco
de produção nunca é destino deste roteiro.

## Compatibilidade e isolamento

Uma consulta `SELECT current_setting(...)` no servidor existente, com
`transaction_read_only=on`, retornou PostgreSQL **16.13**
(`server_version_num=160013`). O Compose fixa a imagem oficial
[`postgres:16.13-trixie`](https://hub.docker.com/_/postgres/tags?name=16.13),
da mesma versão principal e patch.

O serviço usa `network_mode: none`, **não publica portas**, chama-se
`core_c1_homolog` e só aceita comandos pelo socket Unix interno. Os únicos
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
- `tests.psql`: asserts sintéticos e execução das consultas candidatas/aceite.

`schema` aplica os DDLs versionados de `sql/postgres/` em ordem numérica,
incluindo `003b` e `005b`, depois `sql/staging/001_create_staging_schema.sql`
e as 31 views Magento/Ativo em ordem. Por último, **somente no laboratório**,
aplica a proposta `sql/core/proposed/000_missing_sources.sql` para que os
lookups opcionais de cupom/status da consulta candidata compilem. Esse arquivo
não é uma migração aprovada para produção; a view de comprador Ativo continua
sem `comprador_usuario_id`, como no repositório atual.

`core` aplica apenas `001_core_ddl.sql` e `002_core_helpers.sql`, nessa ordem.
`test` usa os UPSERTs versionados `003` e `005` exclusivamente no banco
sintético, compila as consultas `004`, executa `900` e verifica constraints,
idempotência, órfão, comprador Ativo nulo, descontos de pai/filhos/cabeçalho,
status contraditório, classificação exata `Grupos`, limite inclusivo de lote,
preservação dos derivados e gate de publicação fechado.

## Roteiro após autorização

Executar na raiz deste repositório, em PowerShell, com Docker Desktop/Compose
disponíveis. **Na preparação, o comando `docker` não estava disponível neste
shell**; instalar/iniciar o Docker antes de solicitar a execução. Conferir o
diretório e o nome do projeto antes de cada comando.

```powershell
$c1Compose = 'homologation/core-c1/compose.yaml'
docker compose -f $c1Compose --profile manual up -d db
docker compose -f $c1Compose --profile manual ps
docker compose -f $c1Compose --profile manual exec -T db sh -c "tr -d '\r' < /workspace/c1/run.sh | sh -s schema"
docker compose -f $c1Compose --profile manual exec -T db sh -c "tr -d '\r' < /workspace/c1/run.sh | sh -s seed"
docker compose -f $c1Compose --profile manual exec -T db sh -c "tr -d '\r' < /workspace/c1/run.sh | sh -s core"
docker compose -f $c1Compose --profile manual exec -T db sh -c "tr -d '\r' < /workspace/c1/run.sh | sh -s test"
```

`tr` apenas normaliza CRLF de um checkout Windows no fluxo para `sh`; não
altera os arquivos do repositório nem o banco.

Critério mínimo: `run.sh test` termina com `C1_LOCAL_TESTS_PASSED`; as
consultas `B02`/`B03` do `900` retornam zero divergências; `B07` retorna
`indicadores_publicados=0`. O script falha na primeira violação. Usar volume
novo para uma repetição completa de `schema`/`seed`/`core`: os scripts de
estrutura e as fixtures não são concebidos para reaplicação no mesmo volume.

Para parar sem apagar os dados sintéticos:

```powershell
docker compose -f $c1Compose --profile manual down
```

Para **descartar irreversivelmente** o volume exclusivo deste laboratório
(`banco-central-core-c1_core_c1_pgdata`), após conferir que não há dados que
precisem ser preservados:

```powershell
docker compose -f $c1Compose --profile manual config --volumes
docker compose -f $c1Compose --profile manual down --volumes
```

O Compose declara somente `core_c1_pgdata`; `down --volumes` afeta esse volume
e o container da pilha `banco-central-core-c1`, sem remover órfãos de outros
projetos. Não usar `docker volume prune` ou comandos de remoção genéricos.

## Limites da homologação

Os dados sintéticos provam compilação e invariantes básicos, não cobertura de
casos históricos, performance ou reconciliação com produção. As fontes
`sa_cupom_desconto`, `sa_status_detalhado`, comprador Ativo e composição de
combo ainda dependem de integração separada. O cálculo/invalidação completo
dos indicadores derivados **não existe**; `core.fato_inscricao_indicadores_validos`
continua fechada por `WHERE FALSE`, inclusive neste laboratório. Nenhum teste
autoriza remover esse gate ou executar DDL/cargas em produção.
