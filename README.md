# Extract-Banco-central

Pipeline Python para copiar Magento e Ativo (MySQL) para o PostgreSQL existente
**Atendimento**, schema **raw**. Implementação atual: **Fases 1 a 5 e parte da
Fase 6 — infraestrutura, Magento, pedidos, inscrições, usuários e oito referenciais Ativo**.

Esta entrega configura conexões, `raw._etl_runs`, `raw._etl_watermark` e
`raw.magento_sales_order`, `raw.magento_sales_order_item`, `raw.ativo_pedido` e
`raw.ativo_pedido_evento`, `raw.ativo_evento`, `raw.ativo_evento_modalidade`,
`raw.ativo_modalidade_categoria`, `raw.ativo_pedido_status`,
`raw.ativo_usuario`, `raw.ativo_usuario_balcao`, `raw.ativo_tamanho_camiseta`,
`raw.ativo_formas_pagamento`, `raw.ativo_produto` e `raw.ativo_combo`.
A inicialização é transacional e pode ser repetida.
Não cria databases. A configuração recusa qualquer destino diferente de
`Atendimento`. Tabelas existentes não são apagadas ou recriadas. A única
migração implementada ajusta `fl_amigo` na RAW de inscrições para preservar
strings vazias; outras estruturas preexistentes incompatíveis exigem avaliação.

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
.venv\Scripts\python -m src.main full --source magento --entity sales_order_item --batch-size 10000
.venv\Scripts\python -m src.main incremental --source magento --entity sales_order_item
.venv\Scripts\python -m src.main full --source ativo --entity pedido --batch-size 10000
.venv\Scripts\python -m src.main incremental --source ativo --entity pedido
.venv\Scripts\python -m src.main reconcile --source ativo --entity pedido --days 30
.venv\Scripts\python -m src.main full --source ativo --entity pedido_evento --batch-size 10000
.venv\Scripts\python -m src.main incremental --source ativo --entity pedido_evento
.venv\Scripts\python -m src.main reconcile --source ativo --entity pedido_evento --days 30
.venv\Scripts\python -m src.main full --source ativo --entity usuario --batch-size 20000
.venv\Scripts\python -m src.main incremental --source ativo --entity usuario
.venv\Scripts\python -m src.main reconcile --source ativo --entity usuario --days 30
.venv\Scripts\python -m src.main full --source ativo --entity usuario_balcao --batch-size 20000
.venv\Scripts\python -m src.main incremental --source ativo --entity usuario_balcao
.venv\Scripts\python -m src.main reconcile --source ativo --entity usuario_balcao --days 30
.venv\Scripts\python -m src.main snapshot --source ativo --entity evento --batch-size 10000
.venv\Scripts\python -m src.main snapshot --source ativo --entity evento_modalidade
.venv\Scripts\python -m src.main snapshot --source ativo --entity modalidade_categoria
.venv\Scripts\python -m src.main snapshot --source ativo --entity pedido_status
.venv\Scripts\python -m src.main snapshot --source ativo --entity tamanho_camiseta
.venv\Scripts\python -m src.main snapshot --source ativo --entity formas_pagamento
.venv\Scripts\python -m src.main snapshot --source ativo --entity produto
.venv\Scripts\python -m src.main snapshot --source ativo --entity combo
.venv\Scripts\python -m src.main snapshot
.venv\Scripts\python -m pytest -q
```

`check` apenas verifica conexões. `init` conecta diretamente ao Atendimento e
aplica os dois primeiros arquivos de `sql/postgres` em uma transação. Exceções provocam
rollback. `inspect` consulta colunas e índices reais no `information_schema`,
sem ler registros pessoais. Use-o antes de definir as tabelas RAW de negócio.
Também é possível passar `--env-file CAMINHO` antes do subcomando.
Sem `--source`, FULL/incremental executam os dois objetos Magento e as quatro
entidades Ativo com carga por PK (`sa_pedido`, `sa_pedido_evento`, `sa_usuario`
e `sa_usuario_balcao`) em sequência. `reconcile` sem `--entity` percorre essas
quatro entidades Ativo. Com `--source magento` sem `--entity`, executam as duas
entidades Magento. Cada uma tem seu próprio UUID, lock, transação e watermark. Uma falha interrompe
a sequência; uma entidade já confirmada não é revertida pela falha da seguinte.

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

## Validação da Fase 2

Validação realizada em 2026-09-28: FULL com 1.654.948 linhas em origem e destino
na mesma visão de extração, concluído em 337,94 segundos. Dois incrementais
posteriores processaram 33 e 17 linhas (incluindo sobreposição), resultando em
1.654.962 IDs únicos na RAW. Amostra de 10 pedidos coincidiu nos 21 campos.
As três execuções terminaram em SUCCESS; watermark final dessa validação:
`2026-09-28T11:13:16` no fuso da origem. Suíte: 26 testes unitários e 2 testes de
integração aprovados. Esses números são um registro da validação, não contagens
atuais de uma origem que continua recebendo dados.

## sales_order_item — implementado

Os 24 campos solicitados existem na origem, incluindo `ozone_customers` como TEXT.
`item_id` é a PK e inclui o valor zero, que também deve ser carregado.
Os índices e tipos foram inspecionados em 2026-09-28: IDs INT UNSIGNED usam BIGINT;
preços e quantidades usam NUMERIC(12,4), totais/descontos/impostos usam NUMERIC(20,4).
O carregador compartilhado com pedidos recebe explicitamente as colunas, a PK e
o destino de cada entidade. Nenhum GROUP BY, DISTINCT, filtro por tipo de produto
ou junção agrega/remove itens; pai e filhos são linhas independentes.

**Limitação de performance da origem:** não há índice em `updated_at` dos itens.
O incremental filtra `updated_at >= watermark - 5 minutos`, mas pagina por
`item_id`, percorrendo a PK com `FORCE INDEX (PRIMARY)`. Isso captura alterações
em IDs antigos sem depender de o pedido pai ter sido atualizado. O watermark é
o maior timestamp encontrado, mesmo que não pertença à última PK processada.
Limite superior da PK e REPEATABLE READ mantêm uma visão consistente da carga.
Não há segunda varredura para MAX(updated_at), nem ordenação global por data.
Ainda assim, o incremental precisa percorrer a tabela: planeje sua frequência
considerando esse custo. Nenhum índice/configuração é alterado na origem.

Os mesmos controles de atomicidade, logs sem payload, UPSERT, isolamento,
contagem FULL e tratamento de falhas dos pedidos se aplicam aos itens.
Os testes de integração usam texto sintético com caracteres especiais e
validam pai/filhos, preços, idempotência e rollback em tabelas temporárias.

Validação realizada em 2026-09-28: FULL de 7.021.703 itens, contagens iguais
na origem e na RAW na mesma visão, concluído em 1.160,11 segundos. Incremental
posterior processou 722 itens novos ou atualizados. A RAW ficou com 7.021.966
linhas únicas por PK, incluindo `item_id=0`. Os quatro itens 703415–703418
coincidiram nos 24 campos da origem; cada um permanece como linha independente.
As duas execuções terminaram em SUCCESS, com watermark `2026-09-28T11:42:08`
no fuso da origem. Foram aprovados 36 testes unitários e 4 de integração.
Os totais registram essa validação; a origem segue recebendo pedidos e itens.

## sa_pedido — implementado

Os 19 campos solicitados, a PK física `id_pedido` e o índice em `dt_pedido`
foram verificados no Ativo MySQL 5.7 em 2026-09-28. FULL percorre a PK em lotes;
INCREMENTAL lê apenas IDs maiores que o watermark; RECONCILIATION relê por
padrão os últimos 30 dias usando o índice `dt_pedido`, ordenado por
`(dt_pedido, id_pedido)` para tratar datas iguais. `--days` e `--batch-size`
ajustam a janela e o lote. Reconciliação usa UPSERT e mantém inalterado o
watermark da PK, para não deixar de buscar IDs novos em uma execução futura.

Foi encontrada 1 data zero em `dt_pedido` e 303 em `dt_alteracao`. PostgreSQL
TIMESTAMP não aceita `0000-00-00 00:00:00`; por isso, essas duas colunas são
TEXT na RAW para preservar o valor original. Datas válidas permanecem no formato
textual original da origem, sem cálculo ou ajuste de fuso. A sessão MySQL do
Ativo usa UTC. A seleção da reconciliação acontece no TIMESTAMP indexado do
MySQL; a RAW não usa a coluna textual para filtragem de carga. `dt_alteracao`
não é usada como filtro, evitando varreduras frequentes. A janela de 30 dias
continha 18.717 pedidos durante a inspeção.

Falhas reverterão dados e watermark da execução. O mesmo controle de UUID,
logs sem payload, isolamento de leitura, COPY em tabela temporária e UPSERT por
PK se aplica. Não há regras de negócio sobre taxas, descontos ou status.

Validação realizada em 2026-09-28: FULL de 5.738.531 pedidos, com contagens
iguais na visão da origem e na RAW, concluído em 394,18 segundos. Um incremental
carregou 4 IDs novos; a reconciliação de 30 dias releu 18.718 linhas e manteve
o watermark em `121642681`. Outro incremental carregou 2 IDs e avançou o
watermark para `121642683`. A RAW terminou a validação com 5.738.537 IDs.
Uma amostra de 10 pedidos coincidiu nos 19 campos da origem. A RAW manteve 1
`dt_pedido` zero e 303 `dt_alteracao` zero. As quatro execuções terminaram em
SUCCESS. Foram aprovados 44 testes unitários e 6 de integração. Os totais
registram a validação; a origem continua recebendo pedidos.

## sa_pedido_evento — implementado

Esta tabela representa inscrições individuais. Os 30 campos solicitados e a
PK `id_pedido_evento` foram validados na origem em 2026-09-28. Havia
12.506.369 inscrições na inspeção. `id_pedido` tem índice, permitindo relacionar
as inscrições aos pedidos recentes durante a reconciliação. FULL e INCREMENTAL
percorrem a PK com keyset; o incremental busca apenas IDs novos.

A reconciliação padrão usa os últimos 30 dias de `sa_pedido.dt_pedido`, filtrando
primeiro os pedidos pelo índice de data e então ligando cada inscrição por
`sa_pedido_evento.id_pedido`. Usa UPSERT e não avança o watermark da PK.
O plano do MySQL foi verificado antes da carga. A consulta não usa GROUP BY,
DISTINCT, filtros de tipo ou regras de negócio; preserva cada inscrição.

`nr_desconto_individual`, `nr_preco_nm_camiseta`, `nr_preco_foto_clube` e
`nr_preco_personalizacao_medalha` são VARCHAR na origem e permanecem VARCHAR na
RAW, apesar dos prefixos `nr_`. `nr_taxa` é DECIMAL(10,4), e `dt_cadastro` não
possui datas zero entre os registros observados, permitindo TIMESTAMP.
`fl_amigo` é CHAR(1) no MySQL, mas VARCHAR(1) na RAW para preservar a string
vazia sem preenchimento por espaço. A migração da primeira versão é
transacional, repetível e não recria a tabela. Os testes de integração
verificam texto literal, decimais, string vazia, UPSERT e rollback sem
persistir dados sintéticos.

Em 2026-09-28, o FULL carregou 12.506.375 inscrições em 806,36 s e validou
contagens iguais na origem e na RAW; watermark inicial `19570274`. O primeiro
incremental carregou 15 novos IDs. A reconciliação de 30 dias releu 61.568
inscrições sem avançar o watermark. Um segundo incremental carregou 5 IDs.
Após a migração de `fl_amigo`, a RAW tinha 12.506.395 IDs, com watermark
`19570294` na coluna correta `id_pedido_evento`; uma amostra de 10 inscrições
coincidiu nos 30 campos. Foram aprovados 50 testes unitários e 8 de integração.
Os totais são do momento da validação; a origem continua recebendo inscrições.

## sa_evento — snapshot implementado

Os oito campos mínimos, a PK `id_evento` e os tipos reais foram confirmados no
MySQL em 2026-09-28. `dt_evento` contém 107 datas zero e `dt_modificacao` contém
3; ambos ficam como texto literal na RAW. `id_campanha_salesforce` conserva seu
nome e valor, sem conversão em SKU.

`snapshot` extrai a visão completa em lotes por PK, faz COPY/UPSERT e só remove
linhas ausentes da origem depois que a extração termina com a contagem esperada.
Todas as alterações ficam na mesma transação PostgreSQL: falha provoca rollback
e preserva o snapshot anterior. O UUID do lote identifica a versão atual na
RAW, enquanto a tabela de controle registra execução e último snapshot bem-sucedido.

O primeiro snapshot e a repetição carregaram 22.702 linhas cada, com contagens
iguais na origem e no destino e nenhuma duplicata. Uma amostra de 10 registros
coincidiu nos oito campos, e as 107/3 datas zero foram preservadas. Os testes
incluem extração incompleta sem exclusão, UPSERT em tabela temporária e rollback.

## Outros referenciais Ativo — snapshots implementados

Em 2026-09-28, os campos mínimos, tipos e PKs reais de `sa_evento_modalidade`,
`sa_modalidade_categoria` e `sa_pedido_status` foram confirmados na origem.
O mesmo mecanismo transacional de `sa_evento` foi aplicado às três. Em
`sa_evento_modalidade`, `data_update` é TEXT na RAW para preservar cinco
timestamps zero; em `sa_modalidade_categoria`, sem datas zero observadas,
permanece TIMESTAMP. `vl_kit` fica NUMERIC(10,2), sem cálculo.

Os snapshots carregaram respectivamente 40.838, 161.374 e 6 linhas, com
contagens iguais às origens. As amostras coincidiram em todos os campos
selecionados (10/10, 10/10 e 6/6). As três execuções terminaram em SUCCESS.
Sem `--entity`, `snapshot` executa os oito referenciais disponíveis em
sequência; cada um tem UUID, lock, transação e registro de execução próprios.

## Tamanho, formas de pagamento, produto e combo — snapshots implementados

Os tipos, a nullabilidade e as PKs das quatro tabelas foram verificados na
origem antes de criar as estruturas RAW. `sa_tamanho_camiseta` tem seus sete
campos originais preservados; `id_produto` e `id_combo` são INT UNSIGNED na
origem e BIGINT na RAW. `data_update` de `sa_produto` permanece TIMESTAMP.

Em 2026-09-28, os snapshots de `sa_tamanho_camiseta`,
`sa_formas_pagamento`, `sa_produto` e `sa_combo` carregaram respectivamente
1.174, 81, 931 e 1.305 linhas. Origem e RAW tiveram contagens iguais, e
amostras de 10 registros coincidiram em todos os campos selecionados nas
quatro tabelas. Os totais são do momento da validação.

## sa_usuario e sa_usuario_balcao — implementados

Os 21 e 10 campos mínimos, respectivamente, foram conferidos no MySQL em
2026-09-28. As duas PKs são `id_usuario`; a de balcão é INT UNSIGNED e fica
BIGINT na RAW. `id_pais` em `sa_usuario` é VARCHAR(11), não um inteiro.
O ENUM `ds_categoria_balcao` permanece texto literal, sem categorização.
Os campos de data com valores zero são armazenados como TEXT; `data_update`
de `sa_usuario`, sem datas zero observadas, permanece TIMESTAMP.

FULL e INCREMENTAL percorrem a PK em lotes. A reconciliação pagina inscrições
de pedidos recentes pelo ID da inscrição, busca os usuários referenciados por
PK em lotes e faz UPSERT; não varre `data_update`, não agrega inscrições e não
avança o watermark de usuário. O plano de join usa índices de `dt_pedido` e
`id_pedido`. Nenhum nome, documento, contato ou endereço aparece nos logs.

O PostgreSQL não admite NUL em texto. Por escolha explícita do usuário,
caracteres NUL encontrados em campos textuais de `sa_usuario` são substituídos
por `�` na RAW, sem alterar outros caracteres. O número de substituições é
registrado, nunca o valor pessoal. A inspeção da origem não encontrou NUL em
`sa_usuario_balcao`.

Em 2026-09-28, o FULL de `sa_usuario` carregou 3.756.938 linhas com contagens
iguais, watermark `22573910` e 42 caracteres NUL substituídos. O primeiro
incremental carregou 5 novos IDs; a reconciliação de 30 dias releu 16.424
usuários sem avançar o watermark. Outro incremental carregou 4 IDs, chegando
ao watermark `22573919`. A RAW preservou 12.166 datas zero em
`dt_nascimento` e 1.192.697 em `data_create` na validação. Uma amostra de 10
usuários coincidiu nos 21 campos; uma amostra que continha NUL confirmou a
substituição pontual autorizada. Uma tentativa inicial interrompida pelo NUL
foi revertida integralmente: nem tabela parcial nem watermark foram mantidos;
apenas a execução FAILED ficou registrada no controle.

O FULL de `sa_usuario_balcao` carregou 1.517.953 linhas com contagens iguais
e watermark `1684513`. O incremental seguinte não encontrou novos IDs. A
reconciliação releu 26.168 usuários sem avançar o watermark; foram detectados
dois IDs de usuário de balcão referenciados em quatro inscrições recentes,
mas ausentes do próprio cadastro de origem. A pipeline não inventa linhas para
essas referências. A amostra de 10 registros coincidiu nos 10 campos; a RAW
preservou 280.118 datas zero em `dt_nascimento` e 20 em `dt_cadastro` no
momento da validação. Os totais podem mudar enquanto as origens operam.

## Próximas fases previstas

6. Continuar gradualmente com as demais entidades após inspecionar colunas,
   PKs e índices reais; os dois cadastros de usuário e oito referenciais já
   estão implementados.

`full`, `incremental` e `--batch-size` estão disponíveis para pedidos e itens Magento
e para `sa_pedido`, `sa_pedido_evento`, `sa_usuario` e `sa_usuario_balcao`;
`reconcile` e `--days` estão disponíveis para essas quatro entidades Ativo.
`snapshot` está disponível para `sa_evento`, `sa_evento_modalidade`,
`sa_modalidade_categoria`, `sa_pedido_status`, `sa_tamanho_camiseta`,
`sa_formas_pagamento`, `sa_produto` e `sa_combo`; outras entidades serão
adicionadas gradualmente.
`BATCH_SIZE=10000` e `RECONCILIATION_DAYS=30` já são validados na configuração.

SNAPSHOT sincroniza tabelas pequenas transacionalmente usando COPY e tabela
temporária para UPSERT, preservando campos originais e adicionando `_source`,
`_extracted_at` em UTC e `_batch_id` UUID.

Os testes atuais cobrem configuração, segredos, proteção do database, conexão
MySQL somente leitura, parametrização, paginação, janela incremental, concorrência,
COPY/UPSERT e rollback sem avanço de watermark. A validação dos itens usa os IDs
Magento 703415–703418. Nas próximas fases, verificar também o atributo 321 do
produto 47522. Nenhuma regra de negócio, staging, core ou mart faz parte da RAW.
