# Granularidade e chave primária das tabelas RAW

A granularidade indica o que **uma linha** representa. A PK é a chave física
utilizada pela RAW para identificar e atualizar essa linha; não significa que
outras combinações de colunas sejam únicas. `_source`, `_extracted_at` e
`_batch_id` são metadados de linhagem, não fazem parte da granularidade. Não há
agregação de registros nesta camada.

## Magento (16 tabelas)

| Tabela RAW | Granularidade: uma linha por... | PK |
| --- | --- | --- |
| `raw.magento_sales_order` | Pedido | `entity_id` |
| `raw.magento_sales_order_item` | Item/linha de pedido | `item_id` |
| `raw.magento_product` | Produto | `entity_id` |
| `raw.magento_product_varchar` | Registro de valor textual de atributo de produto, com produto, atributo e loja | `value_id` |
| `raw.magento_product_int` | Registro de valor inteiro de atributo de produto, com produto, atributo e loja | `value_id` |
| `raw.magento_product_datetime` | Registro de valor de data de atributo de produto, com produto, atributo e loja | `value_id` |
| `raw.magento_eav_attribute` | Definição de atributo | `attribute_id` |
| `raw.magento_option_value` | Registro de valor/rótulo de opção em uma loja | `value_id` |
| `raw.magento_customer` | Cliente | `entity_id` |
| `raw.magento_customer_address` | Endereço de cliente | `entity_id` |
| `raw.magento_customer_order_item` | Registro de associação entre cliente e item de pedido | `id` |
| `raw.magento_product_link` | Vínculo entre dois produtos | `link_id` |
| `raw.magento_company_user` | Vínculo de cliente com empresa | `customer_id` |
| `raw.magento_company` | Empresa | `id` |
| `raw.magento_salesrule` | Regra de venda/desconto | `rule_id` |
| `raw.magento_salesrule_label` | Rótulo de regra para uma loja | `label_id` |

As tabelas de valores EAV têm grão físico por `value_id`, **não** por produto.
`magento_product_varchar` carrega somente os atributos 73 e 321;
`magento_product_int`, 194, 206 e 207; `magento_product_datetime`, 195;
e `magento_eav_attribute`, esses seis atributos. A granularidade não implica
cobertura de todos os atributos existentes no Magento.

## Ativo (20 tabelas)

| Tabela RAW | Granularidade: uma linha por... | PK |
| --- | --- | --- |
| `raw.ativo_pedido` | Pedido | `id_pedido` |
| `raw.ativo_pedido_evento` | Inscrição/linha de evento associada a um pedido | `id_pedido_evento` |
| `raw.ativo_evento` | Evento | `id_evento` |
| `raw.ativo_evento_modalidade` | Modalidade cadastrada | `id_modalidade` |
| `raw.ativo_modalidade_categoria` | Categoria cadastrada | `id_categoria` |
| `raw.ativo_pedido_status` | Definição de status de pedido | `id_pedido_status` |
| `raw.ativo_usuario` | Usuário | `id_usuario` |
| `raw.ativo_usuario_balcao` | Usuário de balcão | `id_usuario` |
| `raw.ativo_tamanho_camiseta` | Tamanho de camiseta cadastrado | `id_tamanho_camiseta` |
| `raw.ativo_formas_pagamento` | Forma de pagamento cadastrada | `id_formas_pagamento` |
| `raw.ativo_produto` | Produto cadastrado | `id_produto` |
| `raw.ativo_combo` | Combo cadastrado | `id_combo` |
| `raw.ativo_cidade` | Registro físico de cidade | `id` |
| `raw.ativo_estado` | Registro físico de estado | `id` |
| `raw.ativo_pais` | País | `id_pais` |
| `raw.ativo_pedido_pagamento` | Registro de pagamento de pedido | `id_pedido_pagamento` |
| `raw.ativo_transacao` | Transação vinculada a um pagamento | `id_transacao` |
| `raw.ativo_pedido_produto` | Linha de produto de pedido, com sua quantidade | `id_pedido_produto` |
| `raw.ativo_pedido_endereco` | Endereço registrado para pedido | `id_pedido_endereco` |
| `raw.ativo_cupom_desconto_item` | Cupom individual | `id_cupom_desconto_item` |

Em `ativo_cidade` e `ativo_estado`, a PK física é `id`, não `id_cidade` ou
`id_estado`. `ativo_usuario` e `ativo_usuario_balcao` são entidades distintas,
embora ambas usem uma coluna chamada `id_usuario`. `ativo_cupom_desconto_item`
mantém uma linha por cupom, mas sua **carga inicial é seletiva** para IDs
referenciados por pedidos/inscrições; não representa todo o histórico da origem.
O incremental posterior pode acrescentar IDs mais novos, sem tornar a carga
inicial historicamente completa.

## Controle da pipeline (2 tabelas)

| Tabela RAW | Granularidade: uma linha por... | PK |
| --- | --- | --- |
| `raw._etl_runs` | Tentativa de execução de carga | `batch_id` |
| `raw._etl_watermark` | Checkpoint atual de uma combinação pipeline–origem–tabela | (`pipeline_name`, `source_system`, `source_table`) |
