# Extract-Banco-central

Pipeline Python para copiar Magento e Ativo (MySQL) para o PostgreSQL existente
**Atendimento**, schema **raw**. Implementação atual: **Fase 1 — infraestrutura**.

Esta entrega configura conexões e cria apenas `raw._etl_runs` e
`raw._etl_watermark`. A inicialização é transacional e pode ser repetida.
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
.venv\Scripts\python -m pytest -q
```

`check` apenas verifica conexões. `init` conecta diretamente ao Atendimento e
aplica os dois arquivos de `sql/postgres` em uma transação. Exceções provocam
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

## Próximas fases previstas

2. `sales_order`: FULL em chunks e incremental por `updated_at`, com margem de 5 minutos.
3. `sales_order_item`: FULL/incremental, preservando itens pai e filhos.
4. `sa_pedido`: FULL, incremental por PK e reconciliação por `dt_pedido`.
5. `sa_pedido_evento`: FULL, incremental por PK e reconciliação por pedidos recentes.
6. Demais entidades, após inspecionar colunas, PKs e índices reais.

Os comandos `full`, `incremental`, `reconcile` e `snapshot`, bem como `--batch-size`
e `--days`, pertencem às próximas fases e ainda não estão implementados.
`BATCH_SIZE=10000` e `RECONCILIATION_DAYS=30` já são validados na configuração.

FULL deverá extrair em lotes com paginação por chave. INCREMENTAL por PK buscará
IDs novos; RECONCILIATION relerá registros recentes para capturar alterações em
IDs antigos; SNAPSHOT sincronizará tabelas pequenas transacionalmente. O carregador
usará COPY e tabela temporária para UPSERT, preservando campos originais e
adicionando `_source`, `_extracted_at` em UTC e `_batch_id` UUID.

As tabelas de controle estão preparadas para uma execução por entidade (UUID),
contagens e status. A lógica de execução e avanço do watermark ainda será
implementada junto às cargas: dados, sucesso e watermark deverão ser confirmados
atomicamente; falhas serão registradas após rollback, sem avanço do watermark.

Os testes atuais cobrem configuração, segredos, proteção do database, conexão
MySQL somente leitura, parametrização e propagação de falhas na transação.
Integração e validação origem × destino dependerão das próximas fases. Após a
carga, comparar contagens e verificar os itens Magento 703415–703418 e o atributo
321 do produto 47522. Nenhuma regra de negócio, staging, core ou mart faz parte da RAW.
