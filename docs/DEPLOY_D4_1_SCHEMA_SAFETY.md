# D4.1 — segurança do schema RAW nas cargas

Estado: **código e testes locais para revisão; nenhuma alteração no Naruto**. Base: D4, commit `3d73020`. A CORE, STAGING, dados RAW e serviços existentes não foram tocados.

## Separação de DDL e carga

Todos os pipelines acessíveis pela CLI RAW em `INCREMENTAL` ou `RECONCILIATION` agora validam a tabela existente em vez de executar scripts de criação ou migração. Isso inclui as quatro entidades do executor D1/D4, os demais incrementais Magento e as rotas Ativo de usuários, financeiro, complementos e cupom. Em `src/pipeline/sales_order.py` e `src/pipeline/ativo_pedido.py`, o ramo `FULL` preserva a execução legada dos scripts de criação; no caso de `pedido_evento`, a migração `005b_migrate_ativo_pedido_evento_fl_amigo.sql` permanece exclusivamente nesse ramo. As demais rotas `FULL` e `SNAPSHOT` também preservam seu comportamento anterior. O executor D1/D4 não expõe rota FULL nem SNAPSHOT. `src/pipeline/ativo_cupom.py` não tem modo FULL: a tabela de cupom precisa ser provisionada por operação separada antes da primeira reconciliação.

Nos modos incremental e de reconciliação, `src/loaders/postgres_loader.py::validate_target` é chamado antes de consultar páginas da origem e antes da tabela temporária. A CLI `init` e os modos FULL/SNAPSHOT continuam sendo operações distintas; esta mudança **não** torna essas rotas adequadas para execução automática em produção.

O verificador faz apenas `SELECT` no `pg_catalog` e exige tabela comum permanente (`relkind=r`, `relpersistence=p`), conjunto exato de colunas do contrato `FIELDS` da entidade mais `_source`, `_extracted_at` e `_batch_id`, tipos físicos com comprimento/precisão/escala, nullabilidade, ausência de coluna gerada/identidade e PK simples válida/pronta conforme o contrato. Divergência ou tabela ausente causa `ValueError`. Isso é deliberadamente conservador: até uma coluna extra requer revisão da versão do contrato. Índices secundários adicionais não são proibidos.

O registro técnico da tentativa pode passar de `RUNNING` a `FAILED`; a transação de negócio é revertida. Não há UPSERT nem avanço de watermark na falha. O UPSERT por PK, logs e transações permanecem. `etl_raw_batch` continua `CREATE TEMP TABLE ... ON COMMIT DROP`, usada só após validação dentro de carga autorizada; `COPY` e `TRUNCATE` referenciam `pg_temp`. Nenhuma estrutura permanente é criada nesse caminho. As regras de watermark Magento (`updated_at` com cinco minutos de sobreposição), Ativo (PK) e reconciliação D4 de 35 dias não mudaram.

Se a RAW real divergir, **não** contornar a validação nem alterar tabela durante a carga. Primeiro diagnosticar em leitura, preparar migração independente, revisar impacto/backup/janela, obter autorização específica e só então repetir a carga. Esta D4.1 não executa a migração `005b` nem outra DDL em produção.

## Reprodutibilidade do executor

- `deploy/d1/Dockerfile` fixa o manifesto `linux/amd64` de `python:3.12-slim-bookworm` por SHA-256, observado no Docker Hub em 21/10/2026. A tag continua descritiva; o digest é o identificador efetivo.
- `deploy/d1/requirements.lock` fixa cinco wheels, incluindo dependências transitivas `psycopg-binary` e `typing-extensions`, com SHA-256. O build usa `pip --require-hashes --only-binary=:all:`; wheel ou arquitetura diferente falha em vez de instalar artefato não revisado.
- Build local `linux/amd64` passou; imports de `psycopg`, `pymysql`, `dotenv` e `src.main` passaram offline; UID/GID foram `10001:10001`; `--help` não apresentou FULL.
- O arquivo de fonte, imagem final e manifesto do **commit D4.1 aprovado** ainda precisam ser produzidos e conferidos pelo procedimento D4. O build local de revisão não é o artefato a implantar. Digest e hashes não substituem verificação de vulnerabilidades nem aprovação de atualizações de segurança.
- Docker rootful no worker continua um risco administrativo: não colocar operadores no grupo `docker`; manter comandos systemd fixos/root-owned conforme D4 e exigir aprovação de segurança antes de instalar.

## Evidências locais

| Teste | Resultado |
| --- | --- |
| Suíte completa `pytest -q tests` com integração real opt-in desativada | **289 passaram, 72 pulados, 111 subtestes passaram**. Os pulados exigem fontes/bancos reais e não foram executados. |
| Testes D4.1 com mocks | Cobrem tabela ausente, coluna/tipo/nullabilidade/PK incompatíveis, DDL ausente nos dois modos e nas demais rotas da CLI RAW, falha sem watermark, UPSERT e temporária de sessão. |
| PostgreSQL 16 efêmero no Docker Desktop local, sem rede/portas/volume permanente | `D4_1_LOCAL_CATALOG_PASSED`: os quatro DDLs RAW versionados foram aceitos; tabela ausente e `fl_amigo` em `CHAR(1)` foram rejeitados. Container e dados sintéticos foram removidos automaticamente após o teste. |
| Build Linux amd64 com digest/hashes e smoke offline | Aprovado: imports, UID/GID `10001`, executor sem FULL. |
| `docker compose config --quiet` | Aprovado localmente; arquivo Compose inalterado. |

Os testes não certificam o schema real do Naruto. Antes de liberar qualquer gate, confirmar em modo de leitura que as quatro tabelas RAW permanentes e tabelas técnicas existem e correspondem aos contratos; conferir conectividade DNS/TCP/TLS conforme D4. A primeira execução autorizada deve ser por entidade, observando `FAILED`, watermark, recursos e logs.

## Pendências para deploy

1. Comparar catálogo RAW real e permissões do executor com o contrato, **sem** DDL nesta etapa. Qualquer divergência requer plano de migração separado. Em particular, confirmar `raw.ativo_pedido_evento.fl_amigo` como `VARCHAR(1)`.
2. Validar DNS, porta, CA e TLS das três conexões a partir do executor ocioso, mantendo gates `no`.
3. Produzir artefato do commit aprovado, verificar SHA-256 de fonte/imagem e revisão de vulnerabilidades; não usar a tag local de teste.
4. Aprovar segurança do Docker rootful e permissões dos segredos, orçamento da reconciliação e procedimento de rollback D4.
5. Nenhum incremental, reconciliação, timer, índice ou CORE deve ser ativado sem autorização posterior.
