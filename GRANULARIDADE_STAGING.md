# Granularidade e chaves das views STAGING

O schema `staging` contém **views**, não tabelas físicas. Portanto, nenhuma
view possui uma **PRIMARY KEY (PK) declarada ou imposta pelo PostgreSQL**. A
coluna “chave lógica” abaixo identifica o grão esperado e deve ser única nos
dados retornados. A coluna “PK da RAW principal” mostra de onde vem esse
identificador quando há uma fonte principal direta; ela não vira uma restrição
de PK na view. Campos técnicos como `origem`, `extraido_em` e `batch_id` não
fazem parte dessas chaves.

## Magento — 13 views

| View | Uma linha representa | Chave lógica na STAGING | PK da RAW principal |
| --- | --- | --- | --- |
| `staging.magento_option_label` | Um rótulo global de opção (`store_id = 0`) | `option_id` | `raw.magento_option_value.value_id` |
| `staging.magento_pedido` | Um pedido Magento | `pedido_id` | `raw.magento_sales_order.entity_id` |
| `staging.magento_item_pedido` | Um item de pedido, pai ou filho | `item_id` | `raw.magento_sales_order_item.item_id` |
| `staging.magento_produto` | Um produto com atributos EAV resolvidos sem multiplicação | `produto_id` | `raw.magento_product.entity_id` |
| `staging.magento_produto_evento_mapeamento` | O resultado do mapeamento de evento de um produto | `produto_id` | `raw.magento_product.entity_id` |
| `staging.magento_evento` | Um evento Magento existente e resolvido pelo mapeamento | `evento_id` | `raw.magento_product.entity_id` |
| `staging.magento_cliente` | Um cliente | `cliente_id` | `raw.magento_customer.entity_id` |
| `staging.magento_endereco_cliente` | Um endereço de cliente | `endereco_id` | `raw.magento_customer_address.entity_id` |
| `staging.magento_item_cliente` | O resumo das associações de um item a clientes | `item_id` | `raw.magento_customer_order_item.id` (agregado por item) |
| `staging.magento_cliente_empresa` | Um vínculo de cliente com empresa | `cliente_id` | `raw.magento_company_user.customer_id` |
| `staging.magento_pedido_regra` | Uma regra aplicada a um pedido, ou um token de regra inválido preservado | (`pedido_id`, `regra_id`) quando válido; (`pedido_id`, `regra_id_bruto`) quando inválido | Derivada de `raw.magento_sales_order.entity_id` e da lista `applied_rule_ids` |
| `staging.magento_bundle_componente` | Um item filho cujo pai é bundle | `componente_item_id` | `raw.magento_sales_order_item.item_id` |
| `staging.magento_inscricao` | Um item bundle pai interpretado como inscrição | `inscricao_id` | `raw.magento_sales_order_item.item_id` |

`magento_option_label` usa `option_id` como chave lógica porque filtra a loja
global; `value_id` continua sendo a PK física da RAW. Sua unicidade foi
validada nos dados atuais, mas não é uma restrição da view.
`magento_pedido_regra` é a única view Magento com chave lógica composta; tokens
inválidos ficam com `regra_id = NULL` e são distinguidos por `regra_id_bruto`.
`magento_evento`, `magento_bundle_componente` e `magento_inscricao` são
subconjuntos estruturais, não cópias integrais das respectivas fontes RAW.

## Ativo — 18 views

| View | Uma linha representa | Chave lógica na STAGING | PK da RAW principal |
| --- | --- | --- | --- |
| `staging.ativo_pedido` | Um pedido | `pedido_id` | `raw.ativo_pedido.id_pedido` |
| `staging.ativo_evento` | Um evento | `evento_id` | `raw.ativo_evento.id_evento` |
| `staging.ativo_modalidade` | Uma modalidade | `modalidade_id` | `raw.ativo_evento_modalidade.id_modalidade` |
| `staging.ativo_categoria` | Uma categoria | `categoria_id` | `raw.ativo_modalidade_categoria.id_categoria` |
| `staging.ativo_tamanho_camiseta` | Um tamanho de camiseta | `tamanho_camiseta_id` | `raw.ativo_tamanho_camiseta.id_tamanho_camiseta` |
| `staging.ativo_usuario` | Um usuário | `usuario_id` | `raw.ativo_usuario.id_usuario` |
| `staging.ativo_usuario_balcao` | Um usuário de balcão | `usuario_balcao_id` | `raw.ativo_usuario_balcao.id_usuario` |
| `staging.ativo_forma_pagamento` | Uma forma de pagamento | `forma_pagamento_id` | `raw.ativo_formas_pagamento.id_formas_pagamento` |
| `staging.ativo_pagamento` | Um pagamento de pedido | `pagamento_id` | `raw.ativo_pedido_pagamento.id_pedido_pagamento` |
| `staging.ativo_transacao` | Uma transação de pagamento | `transacao_id` | `raw.ativo_transacao.id_transacao` |
| `staging.ativo_pedido_produto` | Uma linha de produto de pedido, com quantidade | `pedido_produto_id` | `raw.ativo_pedido_produto.id_pedido_produto` |
| `staging.ativo_endereco_pedido` | Um endereço registrado para pedido | `endereco_id` | `raw.ativo_pedido_endereco.id_pedido_endereco` |
| `staging.ativo_cidade` | Um registro físico de cidade | `cidade_registro_id` | `raw.ativo_cidade.id` |
| `staging.ativo_estado` | Um registro físico de estado | `estado_registro_id` | `raw.ativo_estado.id` |
| `staging.ativo_pais` | Um país | `pais_id` | `raw.ativo_pais.id_pais` |
| `staging.ativo_combo` | Um combo | `combo_id` | `raw.ativo_combo.id_combo` |
| `staging.ativo_cupom` | Um cupom individual | `cupom_id` | `raw.ativo_cupom_desconto_item.id_cupom_desconto_item` |
| `staging.ativo_inscricao` | Uma inscrição (`pedido_evento`) | `inscricao_id` | `raw.ativo_pedido_evento.id_pedido_evento` |

Em `ativo_cidade` e `ativo_estado`, `cidade_id` e `estado_id` **não** são as
chaves físicas: o grão segue o campo `id` da RAW. `ativo_usuario` e
`ativo_usuario_balcao` são entidades diferentes, mesmo que suas tabelas de
origem usem o nome `id_usuario`. A view `ativo_cupom` herda a cobertura inicial
seletiva da RAW; sua chave não implica histórico completo. A inscrição não
junta pagamentos, transações, produtos ou endereços, pois essas relações 1:N
mudariam seu grão.

## Como verificar a unicidade

As consultas `GROUP BY ... HAVING COUNT(*) > 1` de todas as 31 views estão em
`sql/staging/validation/900_validate_magento.sql` e
`sql/staging/validation/910_validate_ativo.sql`. É possível executá-las sem
imprimir dados pessoais:

```powershell
.venv\Scripts\python -m src.staging_validate --system magento
.venv\Scripts\python -m src.staging_validate --system ativo
```

Na validação de 2026-10-05, as 32 checagens de duplicidade (14 Magento e 18
Ativo) retornaram zero. A diferença entre 32 checagens e 31 views ocorre
porque `magento_pedido_regra` verifica separadamente regras válidas e tokens
inválidos. As views são dinâmicas: a checagem deve ser repetida após novas
cargas RAW.
