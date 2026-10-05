# Camada STAGING — Magento e Ativo

Esta camada contém somente views normais em `staging`, no database existente
`Atendimento`. A RAW permanece fonte somente leitura. Não há CORE, MART,
KPI, seleção de vendas válidas, exclusão de testes/cancelados nem união entre
Magento e Ativo.

## Implantação e validação

Com o `.env` local já configurado, aplique uma fase por vez:

```powershell
.venv\Scripts\python -m src.staging_deploy --phase 1
.venv\Scripts\python -m src.staging_deploy --phase 2
# Validar a fase antes de seguir para 3, e assim sucessivamente até 7.
```

O manifesto está em `src/staging_deploy.py`. Cada fase é transacional e usa
`CREATE OR REPLACE VIEW`; reexecutá-la não modifica a RAW. Os arquivos de
validação para pgAdmin/psql são `sql/staging/validation/900_validate_magento.sql`,
`910_validate_ativo.sql` e `920_data_quality.sql`. Cada consulta de duplicidade
com `GROUP BY ... HAVING COUNT(*) > 1` deve retornar zero linhas. Nas views
sem filtro, compare também `COUNT(*)` da RAW e da STAGING. Em consultas grandes,
é possível usar `SET max_parallel_workers_per_gather = 0` apenas na sessão se
o servidor limitar memória compartilhada; isso não altera a configuração
persistente.

Para executar automaticamente só as checagens de duplicidade (sem imprimir
linhas ou PII):

```powershell
.venv\Scripts\python -m src.staging_validate --system magento
.venv\Scripts\python -m src.staging_validate --system ativo
```

As views preservam, quando têm uma linha-fonte direta, `_source`,
`_extracted_at`, `_batch_id` como `origem`, `extraido_em`, `batch_id`. Views
agregadas/auxiliares (`magento_item_cliente`, `magento_pedido_regra`,
`magento_option_label`, `magento_produto_evento_mapeamento`) não têm um único
batch de origem e não inventam esse metadado. Esses campos nunca são chaves
de negócio. Textos vazios viram `NULL` nos campos semânticos indicados; campos
brutos de data em `TEXT` continuam textuais porque a RAW preserva datas zero.

## Views Magento

| View | Fonte principal e joins | Grão / chave lógica | Transformações, flags e riscos |
| --- | --- | --- | --- |
| `magento_option_label` | `raw.magento_option_value` | Uma opção global (`option_id`) | Filtra `store_id=0`. A unicidade deve ser validada; não deduplica silenciosamente. |
| `magento_pedido` | `raw.magento_sales_order` | Um pedido (`pedido_id`) | Nomes semânticos, textos vazios→`NULL`, valores `base_*` preservados; sem flag financeira. |
| `magento_item_pedido` | `raw.magento_sales_order_item` | Um item (`item_id`) | Pais e filhos preservados; `eh_item_filho` e `eh_bundle`; sem filtro nem agregação. |
| `magento_produto` | `raw.magento_product` + EAV varchar/int/datetime + label global | Um produto (`produto_id`) | Um valor por atributo via `ROW_NUMBER`: loja 0 primeiro, depois menor loja e maior `value_id`. `evento_pai_id_bruto` é mantido; conversão BIGINT apenas para inteiro não negativo dentro do limite. Flags `modalidade_mapeada` e `tamanho_mapeado`. Label é escolhida deterministicamente se aparecer duplicidade futura. |
| `magento_produto_evento_mapeamento` | `magento_produto` + `raw.magento_product_link` + produto de destino | Um produto (`produto_id`) | Prioriza `event_rel_pai` existente. Via link, considera o `evento_pai_id` válido de produtos vizinhos em ambas as direções e aceita só um candidato distinto. Métodos: `event_rel_pai`, `product_link`, `ambiguo`, `nao_mapeado`. ID direto órfão fica visível, mas não vira evento resolvido. |
| `magento_evento` | Produtos apontados pela view de mapeamento | Um evento resolvido (`evento_id`) | Subconjunto de produtos, sem cruzamento com Ativo. `DISTINCT` só deduplica os IDs de evento apontados por vários produtos. |
| `magento_cliente` | `raw.magento_customer` | Um cliente (`cliente_id`) | Email minúsculo, nomes semânticos; gênero fica no código original, sem idade/sexo inferido. `data_nascimento` e `criado_em` são texto da RAW. |
| `magento_endereco_cliente` | `raw.magento_customer_address` | Um endereço (`endereco_id`) | Não escolhe endereço principal, cobrança ou entrega. |
| `magento_item_cliente` | `raw.magento_customer_order_item` | Um item associado não nulo (`item_id`) | Agrupa associações: `cliente_id` somente com um cliente distinto; `qtd_clientes_associados` e `cliente_ambiguo`. Associações sem item não entram porque não têm chave de item. |
| `magento_cliente_empresa` | `raw.magento_company_user` LEFT JOIN `raw.magento_company` | Um vínculo por cliente (`cliente_id`) | Empresa ausente não elimina vínculo. Não classifica empresa como “Balcão”. |
| `magento_pedido_regra` | `magento_pedido` + `raw.magento_salesrule` + labels | Um pedido + ID de regra válido; para token inválido, pedido + token bruto | Quebra lista de IDs, colapsa repetições do mesmo ID e escolhe uma etiqueta por regra (loja 0 primeiro). Preserva token inválido em `regra_id_bruto` com `regra_id_valido=false`. Datas da regra permanecem texto. |
| `magento_bundle_componente` | `magento_item_pedido` filho + pai bundle + `magento_produto` do filho | Um item filho (`componente_item_id`) | Só entra se `item_pai_id` aponta para item `bundle`; não agrega componentes. Produto ausente mantém componente com atributos nulos. |
| `magento_inscricao` | Item bundle pai + pedido, item-cliente, empresa, produto, mapeamento, evento e componentes previamente agregados | Um bundle pai (`inscricao_id`) | Sem duplicação pelos filhos. Conta componentes, modalidades/tamanhos distintos, ambiguidade de modalidade/cliente e evento não mapeado. `categoria_origem` é o ID do conjunto de atributos do produto, sem interpretação comercial. `valor_bruto` e `desconto_item` permanecem separados; sem valor líquido. |

As views `magento_evento`, `magento_bundle_componente`, `magento_inscricao` e
`magento_pedido_regra` são subconjuntos/expansões estruturais; não se espera
que suas contagens sejam iguais às tabelas principais de pedido ou item.
`magento_produto` usa apenas os atributos EAV carregados na RAW (73, 194, 195,
206, 207, 321). A resolução de evento via link é uma inferência técnica
conservadora e deve ser reavaliada se a semântica dos links mudar.

## Views Ativo

| View | Fonte principal e joins | Grão / chave lógica | Transformações, flags e riscos |
| --- | --- | --- | --- |
| `ativo_pedido` | `raw.ativo_pedido` LEFT JOIN `raw.ativo_pedido_status` | Um pedido (`pedido_id`) | Status textual quando disponível; ID sempre preservado. Datas de pedido/alteração continuam texto; sem decisão de pagamento/venda. |
| `ativo_evento` | `raw.ativo_evento` | Um evento (`evento_id`) | ID Salesforce é chamado campanha, não SKU; datas textuais preservadas. |
| `ativo_modalidade` | `raw.ativo_evento_modalidade` | Uma modalidade (`modalidade_id`) | Nome, horário e ordem; `data_update` textual preservado. |
| `ativo_categoria` | `raw.ativo_modalidade_categoria` | Uma categoria (`categoria_id`) | Preserva `valor_kit`; não o subtrai do preço. |
| `ativo_tamanho_camiseta` | `raw.ativo_tamanho_camiseta` | Um tamanho (`tamanho_camiseta_id`) | Campos reais de peso, valor, situação e disponibilidade. |
| `ativo_usuario` | `raw.ativo_usuario` | Um usuário (`usuario_id`) | Email minúsculo, telefones/endereço preservados; datas zero continuam texto. Contém PII: não registrar payload em logs. |
| `ativo_usuario_balcao` | `raw.ativo_usuario_balcao` | Um usuário de balcão (`usuario_balcao_id`) | Entidade separada de `ativo_usuario`; sem UNION ou coalescência entre pessoas. Contém PII. |
| `ativo_forma_pagamento` | `raw.ativo_formas_pagamento` | Uma forma (`forma_pagamento_id`) | Descrição semântica simples. |
| `ativo_pagamento` | `raw.ativo_pedido_pagamento` LEFT JOIN forma | Um pagamento (`pagamento_id`) | Todos os pagamentos mantidos; data de pagamento textual pode conter zero. Não escolhe confirmado/último. |
| `ativo_transacao` | `raw.ativo_transacao` | Uma transação (`transacao_id`) | Todas as transações mantidas; sem `MAX(id)`. |
| `ativo_pedido_produto` | `raw.ativo_pedido_produto` LEFT JOIN `raw.ativo_produto` | Uma linha de produto (`pedido_produto_id`) | Quantidade permanece na linha; produto órfão mantém ID e nome nulo. Sem agregação/valor final. |
| `ativo_endereco_pedido` | `raw.ativo_pedido_endereco` | Um endereço registrado (`endereco_id`) | Preserva `pedido_evento_id`; não escolhe endereço principal nem enriquece geografia. |
| `ativo_cidade` | `raw.ativo_cidade` | Um registro físico (`cidade_registro_id`) | `cidade_id` é atributo distinto da PK física. Sem JOIN geográfico. |
| `ativo_estado` | `raw.ativo_estado` | Um registro físico (`estado_registro_id`) | `estado_id` é atributo distinto da PK física. Sem JOIN geográfico. |
| `ativo_pais` | `raw.ativo_pais` | Um país (`pais_id`) | Sem JOIN geográfico. |
| `ativo_combo` | `raw.ativo_combo` | Um combo (`combo_id`) | Nome semântico simples. |
| `ativo_cupom` | `raw.ativo_cupom_desconto_item` | Um cupom individual (`cupom_id`) | Só colunas existentes; herda cobertura inicial seletiva da RAW, sem histórico completo. |
| `ativo_inscricao` | `raw.ativo_pedido_evento` LEFT JOIN pedido, evento, modalidade, categoria, tamanho | Uma inscrição (`inscricao_id`) | IDs originais e descrições separados. Flags `pedido_mapeado`, `evento_mapeado`, `modalidade_mapeada`, `categoria_mapeada`, `tamanho_camiseta_mapeado` só são verdadeiras quando a referência existe; ID nulo conta como não mapeado. Órfãos, TESTE DEV e cancelados permanecem. Sem join 1:N a pagamentos, transações, produtos ou endereços; sem cálculo de valor líquido. |

`ativo_inscricao` pode conter referências históricas órfãs. Isso é informação de
qualidade, não motivo para excluir a linha. Os valores `nr_desconto_individual`
e preços acessórios são texto na RAW e permanecem texto na STAGING, sem
interpretação monetária prematura.

## Verificação realizada em 2026-10-05

- Magento: pedidos `1.654.992 = 1.654.992`, itens `7.021.966 = 7.021.966`,
  produtos `49.953 = 49.953`, clientes `1.197.021 = 1.197.021` e endereços
  `845.967 = 845.967` (RAW = STAGING). `magento_option_label` não apresentou
  option_id duplicado. Bundle `703415` é uma inscrição com componentes
  `703416`, `703417`, `703418`. Produto `47522` resolveu o evento `48158` por
  `event_rel_pai`. Os `2.044.545` itens bundle são `2.044.545` inscrições;
  as consultas de duplicidade para inscrição e produto retornaram zero.
- Ativo: pedidos `5.738.537 = 5.738.537`, inscrições
  `12.506.395 = 12.506.395`, pagamentos `5.931.002 = 5.931.002`, transações
  `2.080.552 = 2.080.552`, produtos de pedido `60.809 = 60.809` e endereços
  `1.196.100 = 1.196.100` (RAW = STAGING). A consulta de duplicidade da
  inscrição retornou zero. O evento `22054` (`TESTE DEV`) permanece consultável.
  No relatório técnico de inscrições: `96.214` sem pedido atual, `15` sem
  evento, `26.741` sem modalidade, `41.943` sem categoria e `2.380.303` sem
  tamanho; esses totais incluem IDs nulos e referências órfãs.

As 14 consultas automatizadas de duplicidade Magento e as 18 Ativo retornaram
zero chaves duplicadas.

As contagens refletem o estado observado na data acima e podem mudar com novas
cargas RAW. Não foram criados índices na RAW. Uma consulta paralela de
qualidade excedeu a memória compartilhada disponível no servidor; executada
sem paralelismo na sessão, concluiu normalmente. Performance de consumo das
views deve ser analisada depois com `EXPLAIN`/`EXPLAIN ANALYZE` antes de
qualquer proposta de índice.
