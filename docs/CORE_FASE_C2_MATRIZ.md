# Matriz de reconciliação CORE — C2.1

**Estado:** ainda não há observações da C2 no Naruto. `—` significa dado não
apurado, não zero. Todos os resultados abaixo são `NAO_COBERTO` até execução
autorizada e evidência registrada. Os esperados vêm de
`docs/CORE_VALIDACAO_TECNICA.md` / `sql/core/proposed/900_core_acceptance_readonly.sql`.

| Origem | Cenário | Valor esperado | Valor observado | Diferença | Resultado | Evidência |
| --- | --- | ---: | ---: | ---: | --- | --- |
| Magento 166688 | Líquido cabeçalho | 59,0000 | — | — | NAO_COBERTO | `c2_magento_header_readonly.sql`; pendente |
| Magento 166688 | Residual operacional | 14,2100 | — | — | NAO_COBERTO | `c2_magento_header_readonly.sql`; pendente |
| Magento 166688 | Bruto dos pais | 59,0000 | — | — | NAO_COBERTO | `c2_magento_items_after_plan_readonly.sql`; pendente |
| Magento 166688 | Desconto filhos / pais | 0 / 0 | — | — | NAO_COBERTO | plano de itens pendente |
| Magento 1673612 | Líquido cabeçalho | 159,8400 | — | — | NAO_COBERTO | cabeçalho pendente |
| Magento 1673612 | Residual operacional | 19,9800 | — | — | NAO_COBERTO | cabeçalho pendente |
| Magento 1673612 | Bundles | 2 | — | — | NAO_COBERTO | plano de itens pendente |
| Magento 1673612 | Desconto filhos / pais | 39,9600 / 0 | — | — | NAO_COBERTO | plano de itens pendente |
| Magento 1673646 | Líquido cabeçalho | 125,0128 | — | — | NAO_COBERTO | cabeçalho pendente |
| Magento 1673646 | Residual operacional | 26,0000 | — | — | NAO_COBERTO | cabeçalho pendente |
| Magento 1673646 | Desconto filhos / pais | 0 / 0 | — | — | NAO_COBERTO | plano de itens pendente |
| Magento 1673646 | Desconto apenas no cabeçalho | −134,9972; líquido individual indeterminado | — | — | NAO_COBERTO | cabeçalho + itens pendentes |
| Magento 1673884 | Líquido cabeçalho | 119,9200 | — | — | NAO_COBERTO | cabeçalho pendente |
| Magento 1673884 | Residual operacional | 14,9900 | — | — | NAO_COBERTO | cabeçalho pendente |
| Magento 1673884 | Desconto filhos / pais | 29,9800 / 0 | — | — | NAO_COBERTO | plano de itens pendente |
| Magento quatro pedidos | Subtotal, desconto cabeçalho e total cobrado | Fonte, sem baseline numérico completo | — | — | NAO_COBERTO | `c2_magento_header_readonly.sql` |
| Magento quatro pedidos | Diferença bruto pais × subtotal e filhos sem pai bundle | Comparar grãos; não presumir que todo filho seja bundle | — | — | NAO_COBERTO | `c2_magento_items_after_plan_readonly.sql` |
| Magento quatro pedidos | Quantidades, cancelamentos, reembolsos, status, IDs pai/filho | Preservar fonte; não promover exceções | — | — | NAO_COBERTO | `c2_magento_items_after_plan_readonly.sql` |
| Magento quatro pedidos | Cupons Grupos/Cortesia, eventos sem mapa, cardinalidade | Sinais e grão 1:1; sem classificação definitiva | — | — | NAO_COBERTO | `c2_quality_after_plan_readonly.sql` |
| Ativo intervalo aprovado | Bruto, desconto, kit, líquido candidato, taxa separada | Fórmula da Fase B; `NULL` preservado | — | — | NAO_COBERTO | `c2_ativo_range_after_plan_readonly.sql` |
| Ativo intervalo aprovado | Órfãos, status pedido/inscrição, dados inválidos | Preservar órfãos; não inferir caixa | — | — | NAO_COBERTO | scripts Ativo/qualidade |
| Ativo 22054 | Evento de teste | Presente e excluído dos indicadores comerciais futuros | — | — | NAO_COBERTO | `c2_quality_catalog_readonly.sql` |
| Ativo intervalo aprovado | Cupons Grupos/Cortesia e pagamento | Sinais apenas; data não confirma recebimento | — | — | NAO_COBERTO | `c2_quality_after_plan_readonly.sql` |
| Ambas | Fontes auxiliares e composição de combos | Contrato completo antes de derivar | — | — | NAO_COBERTO | catálogo e dependências pendentes |

Ao preencher: registrar data/hora, intervalo exato, plano revisado, contagem
de linhas, valor observado e diferença. Se a fonte não tiver linha, manter
`NAO_COBERTO`; se tiver linha com operando `NULL` ou regra não validada,
marcar `INDETERMINADO`. Não copiar dados pessoais para esta matriz.
