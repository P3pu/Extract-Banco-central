# Extract-Banco-central

Pipeline Python para copiar Magento e Ativo (MySQL) para o PostgreSQL existente
**Atendimento**, schema **raw**. Implementação atual: **Fases 1 e 2 — infraestrutura e sales_order**.

Esta entrega configura conexões, `raw._etl_runs`, `raw._etl_watermark` e
`raw.magento_sales_order`. A inicialização é transacional e pode ser repetida.
Não cria databases. A configuração recusa qualquer destino diferente de
`Atendimento`. Tabelas existentes não são apagadas ou recriadas; `IF NOT EXISTS`
não migra estruturas preexistentes incompatíveis.

## Instalação

Python 3.11 ou superior, a partir da raiz do repositório:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
```

Preencha `.env` localmente. O arquivo é ignorado pelo Git. Variáveis de ambiente
têm prioridade. As senhas são interpretadas literalmente, sem expansão de `${...}`.
Use aspas simples em senhas com caracteres especiais. Nunca compartilhe `.env`.

## Comandos disponíveis

```powershell
.venv\Scripts\python -m src.main check
.venv\Scripts\python -m src.main check --source postgres
.venv\Scripts\python -m src.main init
.venv\Scripts\python -m src.main inspect --source magento --table sales_order
.venv\Scripts\python -m src.main inspect --source ativo --table sa_pedido
.venv\Scripts\python -m src.main full --source magento --entity sales_order --batch-size 10000
.venv\Scripts\python -m src.main incremental --source magento --entity sales_order
.venv\Scripts\python -m pytest -q
```

`check` apenas verifica conexões. `init` conecta diretamente ao Atendimento e
aplica os dois primeiros arquivos de `sql/postgres` em uma transação. Exceções provocam
rollback. `inspect` consulta colunas e índices reais no `information_schema`,
sem ler registros pessoais. Use-o antes de definir as tabelas RAW de negócio.
Também é possível passar `--env-file CAMINHO` antes do subcomando.

MySQL usa TLS com validação do certificado e uma transação `READ ONLY`, encerrada
com rollback. A API disponibilizada limita-se a consultas. Recomenda-se conceder
somente SELECT aos usuários das origens. No PostgreSQL, o padrão `require`
criptografa o tráfego, mas não verifica a identidade do servidor. Para verificação
de identidade configure `POSTGRES_SSLMODE=verify-full` e a CA confiável do libpq.
Para MySQL no Amazon RDS, configure `MYSQL_SSL_CA` com o caminho do bundle oficial
de certificados da AWS. O diretório local `certs/` é ignorado pelo Git.
Se o PostgreSQL não oferecer TLS, `require` bloqueia a conexão. O modo `prefer`
permite compatibilidade com esses servidores, usando conexão sem criptografia.

Erros retornam código 1 e apenas a classe da falha, sem mensagens brutas dos
drivers, senhas ou registros pessoais. Falhas de rede/TLS devem ser resolvidas
na conectividade, certificados ou permissões. O timeout de conexão é configurável.

## sales_order — implementado

Os 21 campos solicitados foram encontrados no schema real em 2026-09-28. A PK é
`entity_id`; existe índice iniciando em `updated_at`. O contrato é verificado a
cada execução, antes do DDL de negócio. `INT UNSIGNED` vira BIGINT e
`SMALLINT UNSIGNED` vira INTEGER para evitar overflow. Valores monetários são
NUMERIC(20,4); `total_qty_ordered` é NUMERIC(12,4). Nenhum cálculo é aplicado.

FULL percorre a PK com keyset e limite superior fixo, usando lotes em memória.
O incremental exige uma carga FULL prévia e consulta `updated_at >= watermark - 5
minutos`, limitado à visão da origem capturada no início. Ordena e pagina por
`(updated_at, entity_id)`, preservando empates. Ambas as cargas usam a mesma
transação MySQL READ ONLY em REPEATABLE READ; novas mudanças entram na próxima
execução. A origem retorna TIMESTAMP em `America/Buenos_Aires`: esses valores
são preservados como TIMESTAMP sem fuso; o contrato recusa mudanças de fuso.
Somente `_extracted_at` e os horários de controle usam UTC/TIMESTAMPTZ.

COPY escreve lotes em uma tabela temporária PostgreSQL; INSERT SELECT com
ON CONFLICT(entity_id) faz UPSERT. Repetir uma carga preserva uma linha por ID,
atualizando também os metadados `_source`, `_extracted_at` e `_batch_id`.
FULL não apaga registros de origem removidos: divergência de contagem provoca
rollback e exige investigação. Exclusões não são propagadas pelo incremental.

Uma carga inteira usa uma transação PostgreSQL: lotes, watermark e SUCCESS são
confirmados juntos. Assim, falhas não deixam carga parcial; a contrapartida é
uma transação longa na primeira carga. O watermark é o maior updated_at
processado, sem regressão. FULL valida contagens dentro das mesmas transações.
Uma origem vazia não produz watermark temporal; o incremental exigirá FULL
novamente quando houver registros.

Cada execução recebe UUID e logs JSON com contagens, duração e watermark,
sem valores das linhas. Um advisory lock impede duas cargas simultâneas da
entidade. Falhas desfazem dados/watermark e registram FAILED após rollback.
Se o processo for encerrado abruptamente ou perder a conexão de destino, pode
restar RUNNING; confira o estado no servidor antes de repetir a carga. O lock
é liberado ao fechar a sessão. Falhas de conexão na confirmação exigem consultar
`_etl_runs` para determinar se o commit foi efetivado.

Testes de integração são opcionais; usam consultas de metadados e tabelas TEMP,
sem persistir linhas de teste:

```powershell
$env:RUN_INTEGRATION = '1'
.venv\Scripts\python -m pytest tests/integration -q
Remove-Item Env:RUN_INTEGRATION
```

## Próximas fases previstas

Validação realizada em 2026-09-28: FULL com 1.654.948 linhas em origem e destino
na mesma visão de extração, concluído em 337,94 segundos. Dois incrementais
posteriores processaram 33 e 17 linhas (incluindo sobreposição), resultando em
1.654.962 IDs únicos na RAW. Amostra de 10 pedidos coincidiu nos 21 campos.
As três execuções terminaram em SUCCESS; watermark final dessa validação:
`2026-09-28T11:13:16` no fuso da origem. Suíte: 26 testes unitários e 2 testes de
integração aprovados. Esses números são um registro da validação, não contagens
atuais de uma origem que continua recebendo dados.

3. `sales_order_item`: FULL/incremental, preservando itens pai e filhos.
4. `sa_pedido`: FULL, incremental por PK e reconciliação por `dt_pedido`.
5. `sa_pedido_evento`: FULL, incremental por PK e reconciliação por pedidos recentes.
6. Demais entidades, após inspecionar colunas, PKs e índices reais.

`full`, `incremental` e `--batch-size` estão disponíveis para `magento/sales_order`.
Os comandos `reconcile`, `snapshot` e `--days` pertencem às próximas fases.
`BATCH_SIZE=10000` e `RECONCILIATION_DAYS=30` já são validados na configuração.

No Ativo, INCREMENTAL por PK buscará
IDs novos; RECONCILIATION relerá registros recentes para capturar alterações em
IDs antigos; SNAPSHOT sincronizará tabelas pequenas transacionalmente. O carregador
usará a mesma estratégia COPY e tabela temporária para UPSERT, preservando campos originais e
adicionando `_source`, `_extracted_at` em UTC e `_batch_id` UUID.

Os testes atuais cobrem configuração, segredos, proteção do database, conexão
MySQL somente leitura, parametrização, paginação, janela incremental, concorrência,
COPY/UPSERT e rollback sem avanço de watermark. Nas próximas fases, verificar
os itens Magento 703415–703418 e o atributo
321 do produto 47522. Nenhuma regra de negócio, staging, core ou mart faz parte da RAW.
