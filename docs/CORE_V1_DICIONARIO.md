# Dicionário CORE V1 — proveniência e grão

| Objeto/campo | Grão/origem | Regra |
|---|---|---|
| `dim_evento` | `(seed_origem, seed_evento_id)` | Ativo `staging.ativo_evento`; Magento `staging.magento_evento`. Não unifica por SKU. |
| `evento_source_map` | `(origem, evento_id_origem)` | Mapa inicial para evento da própria origem; vínculo manual validado não é sobrescrito. |
| `dim_combo` | `(origem, combo_id_origem)` | `staging.ativo_combo`; quantidade prevista NULL e composição não validada. |
| `fato_pedido` | `(origem, pedido_id_origem)` | Ativo `staging.ativo_pedido`; Magento `staging.magento_pedido`. |
| `fato_inscricao` | `(origem, inscricao_id_origem)` | Ativo `staging.ativo_inscricao`; Magento bundle pai `staging.magento_inscricao`. |
| `protocolo` | Pedido | Ativo `pedido_id::text`; Magento `protocolo` (`increment_id`). |
| `comprador_id_origem` | Pedido | Magento `cliente_id`; Ativo NULL por falta de contrato. Nunca vira participante automaticamente. |
| `data_pedido` | Pedido | Ativo conversão defensiva de `data_pedido`; Magento `criado_em`. Não é data do pagamento. |
| `status_corporativo` | Pedido | Ativo códigos 1/2/5/6; Magento matriz fechada `state/status`. |
| `pedido_elegivel` | Pedido | Ativo 2 ou 1/Balcão 2; Magento confirmado/novo/pendente coerente. |
| `pagamento_confirmado` | Pedido/inscrição | Ativo pedido 2 e inscrição elegível; Magento estado/status coerentes de aprovação. |
| `pagamento_presumido` | Inscrição Magento | Pedido `new/pending`, evento passado relativo a `data_referencia_pagamento`, sem evidência de teste. |
| `valor_bruto_pedido` | Pedido | Magento `subtotal`; Ativo soma de inscrições não canceladas somente com cobertura completa. |
| `desconto_pedido_origem` | Pedido | Magento `discount_amount` com sinal; Ativo `staging.ativo_pedido.desconto` sem atribuição. |
| `valor_liquido_pedido` | Pedido | Magento subtotal + desconto; Ativo soma dos líquidos individuais apenas com cobertura/calculabilidade. |
| `valor_total_cobrado` | Pedido Magento | `grand_total`; residual não rotulado como taxa. |
| `desconto_itens_identificado`/`desconto_nao_atribuido` | Pedido Magento | Soma priorizada filhos/pai; diferença para módulo do desconto cabeçalho. |
| `valor_bruto_inscricao` | Inscrição | Ativo `preco`; Magento bundle pai `valor_bruto` original. |
| `desconto_individual_origem` | Inscrição Ativo | `try_numeric_20_4(desconto_individual)`; texto inválido vira NULL com alerta. |
| `valor_kit_ativo` | Inscrição Ativo | `staging.ativo_categoria.valor_kit` por categoria ID. |
| `taxa_servico_ativo` | Inscrição Ativo | `staging.ativo_inscricao.taxa`; não é kit nem receita própria. |
| `valor_liquido_inscricao` | Inscrição | Ativo `GREATEST(0,preço-desconto-kit)` válido; Magento somente quando cabeçalho/itens e quantidade conciliados. |
| `classificacao_comercial` | Inscrição | GRUPOS > CORTESIA > SITE; NULL para cupom Ativo com classificação de cabeçalho ausente. |
| `participante_id_origem` + `participante_namespace_origem` | Inscrição Ativo | Um único `usuario_id` ou `usuario_balcao_id`; ambos => NULL. Magento NULL. |
| `combo_key` | Inscrição Ativo | Combo do pedido se mapeado; não prova composição. |
| `conteudo_hash` | Pedido/inscrição | Alterações no conjunto básico de atributos selecionados. |
| `dependencias_hash_snapshot` | Inscrição | Hash de status, finanças, auxiliares, regra e data de referência; controle de rederivação. |
| `estado_derivacao` | Inscrição | `PENDENTE`/`VALIDADO`; publicação permanece vedada na view. |
| `core_alerta_qualidade` | Regra + PK numérica | Códigos/severidades apenas; nenhuma coluna de dado pessoal. |
| `core_etl_execucao` | Lote | Início/fim/status/IDs mínimo-máximo/linhas; falha transacional não marca sucesso. |

As colunas originais adicionais e seus tipos estão no DDL
`sql/core/proposed/001_core_ddl.sql` e na migração
`sql/core/v1/006_core_v1_extensions.sql`.
