# Extract-Banco-central

Pipeline Python para copiar Magento e Ativo (MySQL) para o PostgreSQL existente
**Atendimento**, schema **raw**. Implementação atual: **Fases 1 a 5 e parte da
Fase 6 — infraestrutura, pedidos, produtos e clientes Magento, pedidos e inscrições Ativo, usuários, pagamentos,
transações, produtos de pedido, endereços, cupons individuais e onze referenciais Ativo**.

Esta entrega configura conexões, `raw._etl_runs`, `raw._etl_watermark` e
`raw.magento_sales_order`, `raw.magento_sales_order_item`, `raw.magento_product`,
`raw.magento_product_varchar`, `raw.magento_product_int`,
`raw.magento_product_datetime`, `raw.magento_eav_attribute`,
`raw.magento_option_value`, `raw.magento_customer`, `raw.magento_customer_address`,
`raw.magento_customer_order_item`, `raw.magento_product_link`,
`raw.magento_company_user`,
`raw.ativo_pedido` e
`raw.ativo_pedido_evento`, `raw.ativo_evento`, `raw.ativo_evento_modalidade`,
`raw.ativo_modalidade_categoria`, `raw.ativo_pedido_status`,
`raw.ativo_usuario`, `raw.ativo_usuario_balcao`, `raw.ativo_tamanho_camiseta`,
`raw.ativo_formas_pagamento`, `raw.ativo_produto`, `raw.ativo_combo`,
`raw.ativo_cidade`, `raw.ativo_estado`, `raw.ativo_pais`,
`raw.ativo_pedido_pagamento`, `raw.ativo_transacao`,
`raw.ativo_pedido_produto`, `raw.ativo_pedido_endereco` e
`raw.ativo_cupom_desconto_item`.
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
.venv\Scripts\python -m src.main full --source magento --entity product --batch-size 10000
.venv\Scripts\python -m src.main incremental --source magento --entity product
.venv\Scripts\python -m src.main full --source magento --entity customer --batch-size 10000
.venv\Scripts\python -m src.main incremental --source magento --entity customer
.venv\Scripts\python -m src.main full --source magento --entity customer_address --batch-size 10000
.venv\Scripts\python -m src.main incremental --source magento --entity customer_address
.venv\Scripts\python -m src.main full --source magento --entity customer_order_item --batch-size 50000
.venv\Scripts\python -m src.main incremental --source magento --entity customer_order_item
.venv\Scripts\python -m src.main snapshot --source magento --entity customer_order_item --batch-size 50000
.venv\Scripts\python -m src.main full --source magento --entity product_link
.venv\Scripts\python -m src.main incremental --source magento --entity product_link
.venv\Scripts\python -m src.main snapshot --source magento --entity product_link
.venv\Scripts\python -m src.main full --source magento --entity company_user
.venv\Scripts\python -m src.main incremental --source magento --entity company_user
.venv\Scripts\python -m src.main snapshot --source magento --entity company_user
.venv\Scripts\python -m src.main full --source magento --entity product_varchar --batch-size 10000
.venv\Scripts\python -m src.main incremental --source magento --entity product_varchar
.venv\Scripts\python -m src.main snapshot --source magento --entity product_varchar
.venv\Scripts\python -m src.main full --source magento --entity product_int --batch-size 10000
.venv\Scripts\python -m src.main incremental --source magento --entity product_int
.venv\Scripts\python -m src.main snapshot --source magento --entity product_int
.venv\Scripts\python -m src.main full --source magento --entity product_datetime --batch-size 10000
.venv\Scripts\python -m src.main incremental --source magento --entity product_datetime
.venv\Scripts\python -m src.main snapshot --source magento --entity product_datetime
.venv\Scripts\python -m src.main snapshot --source magento --entity eav_attribute
.venv\Scripts\python -m src.main snapshot --source magento --entity option_value
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
.venv\Scripts\python -m src.main full --source ativo --entity pedido_pagamento --batch-size 20000
.venv\Scripts\python -m src.main incremental --source ativo --entity pedido_pagamento
.venv\Scripts\python -m src.main reconcile --source ativo --entity pedido_pagamento --days 30
.venv\Scripts\python -m src.main full --source ativo --entity transacao --batch-size 20000
.venv\Scripts\python -m src.main incremental --source ativo --entity transacao
.venv\Scripts\python -m src.main reconcile --source ativo --entity transacao --days 30
.venv\Scripts\python -m src.main full --source ativo --entity pedido_produto --batch-size 10000
.venv\Scripts\python -m src.main incremental --source ativo --entity pedido_produto
.venv\Scripts\python -m src.main snapshot --source ativo --entity pedido_produto
.venv\Scripts\python -m src.main full --source ativo --entity pedido_endereco --batch-size 20000
.venv\Scripts\python -m src.main incremental --source ativo --entity pedido_endereco
.venv\Scripts\python -m src.main reconcile --source ativo --entity pedido_endereco --days 30
.venv\Scripts\python -m src.main reconcile --source ativo --entity cupom_desconto_item --batch-size 10000
.venv\Scripts\python -m src.main incremental --source ativo --entity cupom_desconto_item
.venv\Scripts\python -m src.main snapshot --source ativo --entity evento --batch-size 10000
.venv\Scripts\python -m src.main snapshot --source ativo --entity evento_modalidade
.venv\Scripts\python -m src.main snapshot --source ativo --entity modalidade_categoria
.venv\Scripts\python -m src.main snapshot --source ativo --entity pedido_status
.venv\Scripts\python -m src.main snapshot --source ativo --entity tamanho_camiseta
.venv\Scripts\python -m src.main snapshot --source ativo --entity formas_pagamento
.venv\Scripts\python -m src.main snapshot --source ativo --entity produto
.venv\Scripts\python -m src.main snapshot --source ativo --entity combo
.venv\Scripts\python -m src.main snapshot --source ativo --entity cidade
.venv\Scripts\python -m src.main snapshot --source ativo --entity estado
.venv\Scripts\python -m src.main snapshot --source ativo --entity pais
.venv\Scripts\python -m src.main snapshot
.venv\Scripts\python -m pytest -q
```

`check` apenas verifica conexões. `init` conecta diretamente ao Atendimento e
aplica os dois primeiros arquivos de `sql/postgres` em uma transação. Exceções provocam
rollback. `inspect` consulta colunas e índices reais no `information_schema`,
sem ler registros pessoais. Use-o antes de definir as tabelas RAW de negócio.
Também é possível passar `--env-file CAMINHO` antes do subcomando.
Sem `--source`, FULL executa onze objetos Magento e as oito
entidades Ativo com carga por PK (`sa_pedido`, `sa_pedido_evento`, `sa_usuario`,
`sa_usuario_balcao`, `sa_pedido_pagamento`, `sa_transacao`,
`sa_pedido_produto` e `sa_pedido_endereco`) em sequência.
O incremental padrão inclui também `sa_cupom_desconto_item` após essas entidades;
antes de executá-lo, faça a carga seletiva explícita de cupons com `reconcile`.
`reconcile` sem `--entity` percorre `sa_pedido`, `sa_pedido_evento`,
`sa_usuario`, `sa_usuario_balcao`, `sa_pedido_pagamento` e
`sa_pedido_endereco`; `sa_transacao` só é reconciliada quando solicitada
explicitamente, porque a origem não tem índice nas colunas de data.
`snapshot` sem `--source` percorre os onze referenciais Ativo e `sa_pedido_produto`;
com `--source magento`, sincroniza os EAV varchar, int e datetime de produtos,
os seis metadados em `eav_attribute`, todos os valores de opções, links de produto
e vínculos empresa-cliente.
Com `--source magento` em FULL/incremental sem `--entity`, executam-se as onze
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

## catalog_product_entity — implementado

`raw.magento_product` preserva os seis campos pedidos: `entity_id`, `sku`,
`type_id`, `attribute_set_id`, `created_at` e `updated_at`, além dos três
metadados RAW. A PK real é `entity_id`; `sku` aceita NULL. `INT UNSIGNED` usa
BIGINT, `SMALLINT UNSIGNED` usa INTEGER, e os TIMESTAMP são guardados sem fuso,
tal como recebidos da sessão Magento em `America/Buenos_Aires`. O schema real
tem ainda `has_options` e `required_options`, fora dos seis campos solicitados.

FULL e incremental usam lotes e paginação por PK. Como `updated_at` não tem
índice na origem, o incremental percorre a PK com `FORCE INDEX (PRIMARY)` e
filtra `updated_at >= watermark - 5 minutos`; assim também encontra mudanças
em IDs antigos. A tabela tinha 49.953 linhas e cerca de 3,7 MB de dados na
inspeção; essa varredura deve ser reavaliada se ela crescer muito. O incremental
exige FULL prévio. O FULL confere contagens e todo o processo usa COPY, UPSERT,
transações, lock, logs sem payload e watermark confirmados juntos. Exclusões
na origem não são propagadas automaticamente.

Em 2026-09-29, o FULL carregou 49.953 linhas, com contagens iguais em ambas
as bases. O incremental seguinte relê uma linha da janela de segurança, sem
alterar o watermark `2026-09-29T09:12:39`. Uma amostra de 21 produtos,
incluindo `entity_id=47522`, coincidiu nos seis campos. Um primeiro ensaio
incremental sofreu timeout transitório; a transação foi revertida, a execução
foi registrada como FAILED e a repetição terminou em SUCCESS. Totais podem
mudar na origem.

## catalog_product_entity_varchar — atributos 73 e 321

`raw.magento_product_varchar` copia somente `attribute_id IN (73, 321)` com
`value_id`, `attribute_id`, `store_id`, `entity_id` e `value`, além dos três
metadados RAW. A PK real é `value_id`; `value` aceita NULL. O atributo 73 é
`name` e o 321 é `event_rel_pai`, mas os valores são mantidos literalmente:
não há conversão de `entity_id` nem criação de relações nesta etapa.
`INT UNSIGNED` usa BIGINT e `SMALLINT UNSIGNED` usa INTEGER.

FULL inicial e incremental paginam por `value_id`, sem OFFSET. O incremental
busca apenas IDs maiores que o watermark; como não existe coluna de atualização,
ele **não detecta mudanças ou exclusões em IDs antigos**. O snapshot explícito
relê os dois atributos e sincroniza a RAW, removendo apenas linhas que não
existem mais nessa seleção após a extração completa e a conferência de contagem.
Cada modo usa transação PostgreSQL, COPY/UPSERT, lock, logs sem payload e
watermark confirmado somente após sucesso. A origem permanece somente leitura.

Na validação de 2026-09-29, FULL e snapshot encontraram 56.510 linhas:
50.327 do atributo 73 e 6.183 do atributo 321, incluindo um `value` NULL.
As contagens da RAW coincidiram com a origem; o snapshot removeu zero linhas.
O incremental não encontrou IDs novos e manteve o watermark `1895392`.
Uma amostra de 21 linhas coincidiu nos cinco campos, inclusive o exemplo
`entity_id=47522`, `attribute_id=321`, `value=48158`. Totais podem mudar.

## catalog_product_entity_int — atributos 194, 206 e 207

`raw.magento_product_int` copia apenas `attribute_id IN (194, 206, 207)` com
`value_id`, `attribute_id`, `store_id`, `entity_id` e `value`, além dos metadados
RAW. A PK real é `value_id`; `value` é INTEGER nullable. Os atributos conhecidos
são `event_combo`, `kit_modality` e `size`, respectivamente, mas os números de
`value` permanecem literais, sem converter opções ou aplicar regras de negócio.

FULL inicial e incremental paginam pela PK em lotes. O incremental lê somente
IDs acima do watermark e não encontra alterações ou exclusões de IDs antigos,
pois não há coluna de atualização nessa tabela. O snapshot explícito relê os
três atributos, faz UPSERT e remove linhas ausentes somente depois de uma
extração completa e contagens iguais, tudo na mesma transação PostgreSQL.
Logs não incluem valores de linhas; a origem MySQL permanece somente leitura.

Em 2026-09-29, FULL e snapshot carregaram 35.249 linhas: 1.895 do atributo
194, 8.338 do 206 e 25.016 do 207. A RAW preservou 84 valores NULL e 1.521
zeros, iguais aos da origem. O snapshot removeu zero linhas e o incremental
não encontrou IDs novos; o watermark permaneceu em `567586091`. Uma amostra
de 21 linhas coincidiu nos cinco campos. Totais podem mudar na origem.

## catalog_product_entity_datetime — atributo 195

`raw.magento_product_datetime` copia somente `attribute_id=195` (`event_date`)
com `value_id`, `attribute_id`, `store_id`, `entity_id` e `value`, além dos
metadados RAW. A PK real é `value_id` e `value` é DATETIME nullable na origem.
Nenhuma data zero ou com partes zeradas foi encontrada na inspeção, por isso
`value` usa TIMESTAMP sem fuso no PostgreSQL: o horário é preservado como
recebido, sem conversão. Se uma data zero aparecer futuramente, a carga falhará
e será revertida até que o mapeamento seja reavaliado; não há substituição
silenciosa.

FULL inicial e incremental paginam por PK. O incremental só vê IDs novos; o
snapshot explícito relê o atributo para refletir mudanças e exclusões antigas.
O snapshot remove linhas ausentes apenas após extração completa e validação
das contagens, na mesma transação de COPY/UPSERT, watermark e SUCCESS.

Em 2026-09-29, FULL e snapshot carregaram 1.342 linhas, com contagens iguais
entre origem e RAW. O snapshot não removeu linhas e o incremental não encontrou
IDs novos; o watermark ficou em `18292`. Uma amostra de 21 linhas coincidiu
nos cinco campos. Totais podem mudar na origem.

## eav_attribute — seis metadados de produto

`raw.magento_eav_attribute` sincroniza somente os IDs 73, 194, 195, 206, 207
e 321, com `attribute_id`, `attribute_code`, `backend_type` e
`frontend_input`, além dos metadados RAW. A PK real é `attribute_id`;
`frontend_input` aceita NULL. Os seis códigos reais foram confirmados:
`name`, `event_combo`, `event_date`, `kit_modality`, `size` e `event_rel_pai`.
Esses campos são copiados literalmente, sem traduzir opções ou relacioná-los
a produtos nesta camada.

O modo é SNAPSHOT explícito. Ele extrai os seis IDs em uma transação MySQL
somente leitura, faz COPY/UPSERT em lotes e compara contagens. Apenas depois
disso remove da RAW os IDs dessa seleção que deixaram de existir na origem.
Dados, exclusões, watermark e SUCCESS são confirmados juntos no PostgreSQL.

Em 2026-09-29, o snapshot carregou seis linhas, todas iguais à origem nos
quatro campos. Uma segunda execução manteve seis linhas e removeu zero,
confirmando a idempotência. Totais podem mudar na origem.

## eav_attribute_option_value — valores de opções

`raw.magento_option_value` copia a tabela inteira, sem filtrar atributos:
`value_id`, `option_id`, `store_id` e `value`, além dos metadados RAW.
`value_id` é a PK real; IDs INT UNSIGNED usam BIGINT e `value` aceita NULL.
Nenhum `option_id` é convertido em modalidade, tamanho ou outro conceito.

O modo é SNAPSHOT. A extração usa paginação por PK, transação MySQL somente
leitura e COPY/UPSERT em lotes. A RAW só remove linhas ausentes após a
extração completa e a validação das contagens, na mesma transação PostgreSQL
que confirma dados, watermark e SUCCESS. Caracteres NUL futuros em texto
são substituídos por `�`, sem emitir valores nos logs.

Em 2026-09-29, foram carregadas 2.370 linhas, abrangendo 2.350 opções e
dois `store_id`. Uma amostra de 21 linhas coincidiu nos quatro campos.
O segundo snapshot manteve 2.370 linhas e removeu zero. Totais podem mudar.

## customer_entity — implementado

`raw.magento_customer` copia somente os dez campos pedidos, sem idade, nome
completo, status de assinante ou ajuste de gênero. Dados pessoais não são
emitidos em logs nem em testes. `entity_id` é a PK; `dob` e `created_at` são
texto para preservar datas com ano zero existentes na origem MySQL.
NUL em texto, caso apareça, é substituído por `�`, conforme decisão do usuário.

FULL e INCREMENTAL paginam pela PK em transação MySQL somente leitura. A
origem não tem índice em `updated_at`, então o incremental percorre a PK e
seleciona registros atualizados desde o watermark com sobreposição de cinco
minutos. Isso detecta alterações em IDs antigos, mas exclusões físicas não
são detectadas. Contagens FULL e destino são validados antes do commit.
Em 2026-09-29, a inspeção agregada encontrou cerca de 1,2 milhão de linhas,
11.845 `created_at` zero, ao menos um `dob` com ano zero e nenhum NUL nos
campos textuais selecionados. Uma primeira tentativa FULL foi revertida ao
encontrar a data inválida; a definição textual corrige essa incompatibilidade.
O FULL confirmado carregou 1.197.016 linhas com contagens iguais. O incremental
seguinte releu 84 registros na janela de sobreposição e concluiu com sucesso;
a RAW tinha 1.197.021 linhas após novos cadastros. Uma amostra de 22 linhas,
incluindo datas com ano zero, coincidiu em todos os dez campos. Totais mudam
enquanto a origem está em operação.

## customer_address_entity — implementado

`raw.magento_customer_address` copia todos os endereços e somente os onze campos
solicitados. A PK é `entity_id`; `parent_id`, `region`, `region_id` e `postcode`
aceitam NULL conforme a origem. Nomes e outros campos não solicitados não são
extraídos. Telefones e endereços não são exibidos em logs ou testes. NUL em
texto, caso apareça, é substituído por `�`.

FULL e INCREMENTAL paginam pela PK. A origem não tem índice em `updated_at`,
então o incremental percorre a PK e seleciona linhas atualizadas desde o
watermark com sobreposição de cinco minutos; exclusões físicas não são
detectadas. O FULL só confirma após contagens iguais na origem e no destino.
Em 2026-09-29, o FULL carregou 845.966 endereços; o incremental seguinte
releu 68 registros e a RAW passou a 845.967 linhas após novos cadastros.
Uma amostra de 20 linhas coincidiu nos onze campos. A consulta à origem não
encontrou `parent_id` nulo. Totais podem mudar na origem.

## customer_has_related_order_items — implementado

`raw.magento_customer_order_item` preserva os dois campos solicitados,
`sales_order_item_item_id` e `customer_id`, mais `id`, a PK física necessária
para manter cada relação individualmente. As duas referências aceitam NULL na
origem; nenhuma associação ou regra de negócio é inferida. Outros campos não
são copiados.

FULL percorre toda a PK em lotes e valida as contagens antes de confirmar a
transação. INCREMENTAL copia IDs novos. A tabela não possui `updated_at`,
portanto o incremental não detecta alterações ou exclusões em IDs antigos.
O SNAPSHOT explícito relê a origem inteira, atualiza relações antigas e remove
da RAW as ausentes somente após validar a extração, na mesma transação. Por
ter cerca de 6,89 milhões de linhas, ele não entra no snapshot Magento padrão.

Em 2026-10-01, o FULL confirmou 6.893.379 relações com contagens iguais;
o incremental seguinte trouxe 18 IDs e a RAW passou a 6.893.397 linhas.
Uma amostra de 22 linhas, incluindo referências nulas, coincidiu nos três
campos. O SNAPSHOT está implementado e testado, mas não foi executado na
tabela inteira. Totais podem mudar na origem.

## catalog_product_link — implementado

`raw.magento_product_link` copia `link_id`, `product_id`, `linked_product_id`
e `link_type_id`, sem interpretar os tipos de link e sem copiar `store_id`,
que não foi solicitado. A PK física é `link_id`; IDs INT UNSIGNED usam BIGINT.

FULL e INCREMENTAL percorrem a PK em lotes. Como a fonte não tem timestamp de
atualização, o incremental vê apenas IDs novos. O SNAPSHOT sincroniza mudanças
e exclusões antigas, removendo linhas ausentes somente após extração completa
e contagens validadas na mesma transação; a tabela é pequena e entra no
snapshot Magento padrão.

Em 2026-10-01, FULL e SNAPSHOT confirmaram 6.393 links, sem remoções; o
incremental não encontrou IDs novos. Uma amostra de 24 links, incluindo os
cinco tipos presentes na origem, coincidiu nos quatro campos. Totais podem mudar.

## aw_ca_company_user — implementado

`raw.magento_company_user` copia os seis campos solicitados, com PK real
`customer_id`. `is_root` e `status` permanecem numéricos, sem interpretação;
`job_title` e `telephone` não são extraídos. Como a fonte não possui timestamp
de atualização, o incremental por PK detecta apenas IDs novos. O snapshot
relê a tabela inteira e sincroniza alterações e exclusões de forma transacional.

Em 2026-10-01, FULL e SNAPSHOT confirmaram 143 vínculos com contagens iguais;
o incremental não encontrou IDs novos e o snapshot removeu zero. Uma
comparação de todos os 143 registros coincidiu nos seis campos. Totais podem
mudar na origem.

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
Sem `--entity`, `snapshot` executa os onze referenciais disponíveis em
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

## Cidade, estado e país — snapshots implementados

Os contratos preservam todos os 17, 7 e 9 campos originais, respectivamente.
Em `sa_cidade` e `sa_estado`, a PK física é `id`; `id_cidade` e `id_estado`
são apenas campos de origem e não foram usados como chave de UPSERT.
Nenhuma regra geográfica é aplicada nesta camada RAW.

Em 2026-09-28, as cargas continham 47.378 cidades, 34.465 estados e 246
países, com contagens iguais na origem e no destino. Amostras de 15 cidades,
15 estados e 10 países coincidiram em todos os campos, incluindo cinco linhas
com NUL em cada uma das duas primeiras tabelas. Seguindo a escolha de
substituição por `�`, foram trocados somente 46 caracteres NUL em cidades e
48 em estados. A contagem das substituições consta nos logs, sem valores de
origem.

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

## sa_pedido_pagamento e sa_transacao — implementados

Os seis campos mínimos de pagamento e os sete de transação foram conferidos
contra os tipos, nullabilidade, PKs e índices reais do MySQL. `fl_status`
permanece seu valor literal do ENUM; não há cálculo de valor pago ou qualquer
outra regra financeira. Em `sa_pedido_pagamento`, `dt_pagamento` é TEXT na RAW
para preservar 60 datas zero encontradas na origem. As demais datas
selecionadas permanecem TIMESTAMP, sem datas zero observadas na inspeção.

FULL e INCREMENTAL percorrem PK crescente em lotes. A reconciliação de
pagamentos relê as janelas de `dt_registro` e `dt_pagamento` pelos índices
reais `idx_dt_registro` e `dt_pagamento`. Uma linha que pertence às duas
janelas pode ser contada duas vezes na extração e recebe UPSERT, sem duplicata
na RAW; o watermark da PK não avança. A reconciliação de transações considera
`dt_cadastro` ou `dt_cancelamento_transacao` na janela, mas a origem não tem
índice de data: a consulta precisa varrer a PK e só é executada mediante
`--entity transacao` explícito. Alterações antigas sem atualização dessas
datas não são detectadas pelas reconciliações e exigem uma nova carga FULL.

Em 2026-09-28, o FULL de pagamentos carregou 5.930.991 linhas com contagens
iguais e watermark `1112998441`. Dois incrementais carregaram 5 e 6 novos
IDs, chegando a `1112998452`. A reconciliação de 30 dias releu 33.487
ocorrências nas duas janelas sem avançar o watermark. Uma amostra de 20
registros, inclusive dez com data zero, coincidiu em todos os seis campos.
O FULL de transações carregou 2.080.550 linhas com contagens iguais e
watermark `2080587`; um incremental trouxe 2 novos IDs, e a reconciliação
explícita releu 4.908 linhas sem avançar o watermark. Amostras do início e
do fim da PK e dez transações com cancelamento coincidiram nos sete campos.
Os totais mudam enquanto a origem está em operação.

## sa_pedido_produto e sa_pedido_endereco — implementados

Os cinco e dez campos mínimos, respectivamente, foram validados contra a
origem. `sa_pedido_produto` tem PK física `id_pedido_produto` e preço
NUMERIC(10,2), sem agregação ou cálculo. `sa_pedido_endereco` tem PK
`id_pedido_endereco` e índice em `id_pedido`. Seus campos textuais selecionados
e `dt_cadastro` não apresentaram NUL nem datas zero na inspeção; nomes e
endereços nunca são emitidos nos logs.

FULL e INCREMENTAL usam paginação por PK. O snapshot de produto sincroniza
linhas ausentes da origem somente após extração completa e contagem igual,
na mesma transação PostgreSQL; preserva o watermark numérico para o próximo
incremental. Endereços são reconciliados via pedidos com `dt_pedido` na
janela e join pelos índices de `id_pedido`, sem varredura frequente da data
de cadastro. Alterações em endereços de pedidos mais antigos que a janela
não são detectadas por essa reconciliação.

Em 2026-09-28, FULL e snapshot de produto carregaram 60.809 linhas cada,
com contagens iguais, nenhuma remoção no snapshot e watermark `8055794`.
Os incrementais antes e depois do snapshot não encontraram novos IDs;
20 registros coincidiram nos cinco campos. O FULL de endereços carregou
1.196.100 linhas com contagens iguais e watermark `8026373`. O incremental
não encontrou novos IDs. Na janela padrão de 30 dias havia 18.797 pedidos,
mas nenhum com endereço nessa tabela; uma reconciliação histórica de 1.825
dias releu 66 endereços sem avançar o watermark. Trinta registros, incluindo
dez dessa janela, coincidiram nos dez campos. Totais podem mudar na origem.

## Cupons individuais Ativo — carga seletiva

`sa_cupom_desconto_item` tem cerca de 29,3 milhões de linhas e não é carregada
integralmente nesta etapa. O primeiro `reconcile --source ativo --entity
cupom_desconto_item` reúne e deduplica os IDs referenciados por
`raw.ativo_pedido.id_cupom_desconto_item` e
`raw.ativo_pedido_evento.id_cupom_individual`, consulta esses IDs pela PK no
MySQL e faz UPSERT na RAW. A operação é idempotente e pode ser repetida para
capturar referências novas ou atualizações de cupons já referenciados. Não
aceita `--days` e fica fora do `reconcile` padrão para evitar releituras
custosas. `full` não está disponível para cupons.

Após a carga seletiva, `incremental --source ativo --entity
cupom_desconto_item` lê todos os IDs de origem acima do watermark da PK,
inclusive os que ainda não aparecem em pedidos. O incremental não detecta
alterações em IDs antigos; rode a reconciliação explícita conforme a necessidade.
O watermark inicial só avança após a carga seletiva confirmar; reconciliações
posteriores não o avançam. Ambas usam lotes, transação e controle de execução.
As datas MySQL são preservadas como texto para comportar `0000-00-00` sem perda.

Na carga de 2026-09-29, havia 784.754 IDs distintos referenciados: 781.853
cupons localizados e carregados na RAW; 2.901 IDs não existiam na visão da
origem e não foram fabricados. O watermark ficou em `94036505` e o incremental
seguinte não encontrou IDs novos. Uma amostra de 20 linhas coincidiu nos nove
campos. Portanto, a RAW de cupons **não representa o histórico completo** da
origem; uma decisão de ampliar a cobertura exige avaliar tempo e armazenamento.
Essas contagens podem mudar.

## Próximas fases previstas

6. Continuar gradualmente com as demais entidades após inspecionar colunas,
   PKs e índices reais; os dois cadastros de usuário, pagamentos, transações,
   produtos de pedido, endereços, cupons individuais, produto e EAV
   varchar/int/datetime, metadados e valores de opções EAV Magento, clientes
   e endereços de clientes, relações cliente-item, links de produto e vínculos
   empresa-cliente Magento, além de onze referenciais, já estão implementados.
   A próxima tabela Magento prevista é `aw_ca_company`.

`full`, `incremental` e `--batch-size` estão disponíveis para pedidos, itens,
produtos, clientes, endereços de clientes, relações cliente-item, links de
produto, vínculos empresa-cliente e EAV
varchar/int/datetime Magento,
e para `sa_pedido`, `sa_pedido_evento`,
`sa_usuario`, `sa_usuario_balcao`,
`sa_pedido_pagamento`, `sa_transacao`, `sa_pedido_produto` e
`sa_pedido_endereco`. O incremental também aceita `sa_cupom_desconto_item` após
sua carga seletiva. `reconcile` e `--days` estão disponíveis para
`sa_pedido`, `sa_pedido_evento`, `sa_usuario`, `sa_usuario_balcao`,
`sa_pedido_pagamento`, `sa_transacao` e `sa_pedido_endereco`, com transações
somente de forma explícita.
Para cupons individuais, `reconcile` é explícito e não aceita `--days`.
O snapshot Magento sincroniza `catalog_product_entity_varchar`,
`catalog_product_entity_int`, `catalog_product_entity_datetime` e
`eav_attribute`, além de toda a `eav_attribute_option_value` e
`catalog_product_link` e `aw_ca_company_user`.
`customer_has_related_order_items` tem snapshot explícito, fora do padrão.
`snapshot` está disponível para `sa_evento`, `sa_evento_modalidade`,
`sa_modalidade_categoria`, `sa_pedido_status`, `sa_tamanho_camiseta`,
`sa_formas_pagamento`, `sa_produto`, `sa_combo`, `sa_cidade`, `sa_estado` e
`sa_pais` e `sa_pedido_produto`; outras entidades serão
adicionadas gradualmente.
`BATCH_SIZE=10000` e `RECONCILIATION_DAYS=30` já são validados na configuração.

SNAPSHOT sincroniza tabelas pequenas transacionalmente usando COPY e tabela
temporária para UPSERT, preservando campos originais e adicionando `_source`,
`_extracted_at` em UTC e `_batch_id` UUID.

Os testes atuais cobrem configuração, segredos, proteção do database, conexão
MySQL somente leitura, parametrização, paginação, janela incremental, concorrência,
COPY/UPSERT e rollback sem avanço de watermark. A validação dos itens usa os IDs
Magento 703415–703418; a validação EAV conferiu o atributo 321 do produto
47522. Nenhuma regra de negócio, staging, core ou mart faz parte da RAW.
