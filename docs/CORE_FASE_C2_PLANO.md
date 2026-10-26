# CORE — Fase C2.1: diagnóstico histórico read-only

**Estado em 2026-10-20:** preparação versionada; **nenhuma consulta desta fase
foi executada no Naruto**. A C1.5 local passou segundo o relato do usuário,
mas isso não comprova reconciliação histórica real. A CORE ainda não existe no
`Atendimento`; nenhum script abaixo depende dela. A view de indicadores da
proposta CORE continua fechada por `WHERE FALSE` e não será criada/publicada.

## Escopo e ordem futura (dependem de nova autorização)

Todos os arquivos em `sql/core/diagnostics/` iniciam `BEGIN READ ONLY`, usam
`SET LOCAL statement_timeout` e `lock_timeout`, e falham se o banco não for
`Atendimento` ou a transação não estiver read-only. `SET LOCAL` não persiste.
Não executar no Naruto antes de autorização específica, inclusive os EXPLAINs.
Executar **um arquivo por vez**; não enviar toda a pasta ao pgAdmin.

1. `c2_quality_catalog_readonly.sql`: contrato/índices e evento teste 22054
   por PK; sem leitura de cadastro pessoal.
2. `c2_magento_header_readonly.sql`: quatro cabeçalhos por PK, status e
   comparação com os líquidos/residuais documentados.
3. `c2_magento_items_plan_readonly.sql`: dois `EXPLAIN` distintos, da
   reconciliação completa por bundle (CTEs, joins, agregações e filtros) e da
   seleção detalhada dos quatro pedidos. Revisar **ambos** antes de autorizar
   `c2_magento_items_after_plan_readonly.sql`.
4. Para Ativo, escolher **um intervalo de até 1.000 IDs de inscrição** a partir
   de critério de amostragem aprovado. Substituir `UNSET` em
   `c2_ativo_range_plan_readonly.sql` e executar somente `EXPLAIN`. Se aprovado,
   usar exatamente o mesmo intervalo em `c2_ativo_range_after_plan_readonly.sql`.
   O intervalo é por `inscricao_id`, não por `pedido_id`; zero linhas é
   `NAO_COBERTO`, não sucesso.
5. `c2_quality_plan_readonly.sql`: quatro `EXPLAIN` das quatro consultas
   efetivas (cardinalidade Magento, regras Magento, sinais Ativo e tentativas
   de pagamento), com as mesmas CTEs, joins, agregações e filtros do arquivo
   de dados. Só depois de revisar **cada** plano e aprovar custo, executar
   `c2_quality_after_plan_readonly.sql`.

Em caso de erro ou timeout, **parar** e registrar o SQLSTATE/arquivo; não
aumentar timeout, expandir intervalo ou substituir view por scan RAW sem
revisão. `EXPLAIN` é sempre sem `ANALYZE`. Nenhum SQL faz DDL, DML, exportação,
mudança persistente de configuração ou acesso à CORE.

## Reconciliação e critério por cenário

Preencher `CORE_FASE_C2_MATRIZ.md` somente com resultados efetivamente
observados e evidência (arquivo, data, intervalo, plano aprovado). Valores
esperados da Fase B são **baseline de revisão**, não prova de que o histórico
atual permaneceu igual. Para valores numéricos com baseline, diferença =
observado − esperado; tolerância técnica de 0,0001 apenas para comparação,
sem arredondar ou coagir `NULL` a zero.

- `APROVADO`: fonte presente, cardinalidade válida, esperado e observado
  reconciliados, sem exceção relevante para a regra testada.
- `DIVERGENTE`: diferença acima da tolerância ou violação comprovada de grão,
  vínculo, quantidade, status ou classificação.
- `INDETERMINADO`: linha existe, mas falta operando, semântica, regra ou fonte
  para concluir; exemplo: desconto só no cabeçalho ou kit `NULL`.
- `NAO_COBERTO`: consulta não executada, ID/intervalo sem linha, ou caso sem
  fixture/amostra. **Zero linhas não é aprovação.**

Cabeçalho Magento é 1:1 por pedido. Seu líquido = `subtotal + desconto`;
residual = `grand_total − líquido`. Frete e imposto são exibidos à parte,
mas o residual **não é assumido como taxa de serviço**. Itens são filtrados por
quatro IDs e agregados por bundle antes de qualquer join com cabeçalho;
desconto só no header fica não atribuído, sem rateio. Pais/filhos não são
somados juntos como receita. Quantidades `!= 1`, cancelamentos e reembolsos
bloqueiam a promoção automática de líquido final individual.

No Ativo, o líquido candidato usa `preco − desconto_individual − valor_kit`
apenas quando todos estão válidos. `taxa` é campo separado. O texto do desconto
é validado antes do cast; `NULL` e texto inválido não viram zero. Pedido status
5 ou inscrição status 5–8 prevalece como cancelamento; código 17 permanece
indeterminado. `dt_pagamento` preenchida não confirma recebimento: a view de
pagamento é por tentativa e a amostra futura só contará status/data, sem
expor valor ou inferir caixa.

## Consultas que exigem aprovação adicional de custo

Os DDL RAW versionados não declaram índices por
`magento_sales_order_item.order_id` e `ativo_pedido_evento.id_pedido`. Logo,
mesmo quatro pedidos ou 1.000 IDs podem provocar leitura ampla. Não há custo
estimado real nesta preparação; é obrigatório revisar os planos no Naruto.

| Consulta de dados | EXPLAIN prévio | Risco a revisar |
| --- | --- | --- |
| Reconciliação por bundle Magento | `c2_magento_items_plan_readonly.sql`, plano 1 | Scan de itens por `pedido_id`, materialização, agrupamentos por pai/pedido e join ao cabeçalho. |
| Detalhe de itens Magento | `c2_magento_items_plan_readonly.sql`, plano 2 | Nova leitura dos itens e ordenação dos IDs pai/filho. |
| Inscrições Ativo por intervalo | `c2_ativo_range_plan_readonly.sql` | Pushdown da PK através de joins STAGING; categoria. |
| Cardinalidade `magento_inscricao` | `c2_quality_plan_readonly.sql`, plano 1 | Mapeamento produto/evento, CTEs EAV e agregação por pedido. |
| Regras e classificação Magento | `c2_quality_plan_readonly.sql`, plano 2 | Tokenização, escolha de etiqueta e agregação por pedido. |
| Sinais/cupom Ativo | `c2_quality_plan_readonly.sql`, plano 3 | Join para RAW historicamente seletiva e agregação da amostra. |
| Pagamentos Ativo | `c2_quality_plan_readonly.sql`, plano 4 | Relação por `pedido_id` sem índice declarado, CTE de pedidos e agregação por status. |

**Aprovação objetiva de cada plano:** registrar banco, versão, commit dos
scripts, intervalo Ativo (quando aplicável), número de nós/linhas estimadas,
custo total estimado e operações mais caras. Confirmar que o filtro por quatro
pedidos ou por até 1.000 IDs chega às relações-base antes de joins/agrupamentos;
verificar separadamente leituras repetidas, `Seq Scan` em tabelas grandes,
`Sort`/`Hash` volumosos, materialização e necessidade potencial de memória.
Comparar o SQL planejado ao SQL de dados do **mesmo commit**; o teste estático
`test_every_plan_matches_the_effective_data_query` exige igualdade textual da
consulta após retirar somente `EXPLAIN`, comentários e espaço externo. Plano
simplificado, intervalo diferente ou mudança posterior no SQL **invalida** a
aprovação. `statement_timeout` não substitui avaliação de custo.

Se não for possível justificar custo e cardinalidade de **todos os planos de um
arquivo de dados**, não executar esse arquivo: marcar o cenário `NAO_COBERTO`,
registrar o plano e propor alternativa em revisão separada. Em particular,
um `Seq Scan` grande, `Sort`/`Hash` de milhões de linhas ou custo
desproporcional exige nova decisão explícita. Não criar índice nesta fase.

## Dependências não resolvidas

1. `sa_cupom_desconto` e a classificação `Grupos` do cabeçalho não integram
   RAW/STAGING definitiva; prefixo `GR`/categoria/etiqueta são apenas sinais.
   `staging.ativo_cupom` é historicamente seletiva.
2. `sa_status_detalhado` (descrição/tipo) não integra o ambiente principal;
   código 17 e `tipo='pedido'` exigem validação funcional.
3. Comprador Ativo: `sa_pedido.id_usuario` não foi extraído para
   `staging.ativo_pedido`; participante da inscrição não substitui comprador.
4. Combo: faltam `nr_qntprovas` e composição evento/categoria, portanto uma
   amostra de inscrições não prova venda completa.
5. Eventos Magento sem mapa e papel de participante seguem incertos; não
   fazer correspondência automática entre origens ou por SKU.
6. `nr_valor_pago` Ativo não está na RAW; data de pagamento também ocorre em
   tentativas recusadas. Não calcular caixa a partir dessas consultas.
7. Reconciliador/hash de todas as dependências derivadas não existe. Nenhum
   diagnóstico read-only autoriza abrir `core.fato_inscricao_indicadores_validos`.

## Encerramento

A C2.1 de **preparação** termina com scripts revisados, testes estáticos
passando e branch publicada. A reconciliação histórica C2 só pode ser
considerada concluída após autorização, revisão dos planos, execução
controlada, preenchimento da matriz com observados, investigação de toda
divergência/indeterminação e revisão final do usuário. Não fazer merge na
`main`, criar CORE/MART no Naruto ou publicar indicadores nesta fase.
