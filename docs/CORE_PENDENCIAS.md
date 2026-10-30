# CORE V1 — pendências reais

1. Resolvido em 30/10/2026: `sa_cupom_desconto.en_cupom_classificacao` entra
   na STAGING (`staging.ativo_cupom_desconto`, snapshot diário); `Grupos`
   define GRUPOS, as demais são informativas; cupom sem classificação não
   deixa a inscrição pendente.
2. Descrição de `id_status_detalhado` não integrada à STAGING. Códigos
   especiais ficam pendentes, sem rótulo inventado.
3. Comprador Ativo: `sa_pedido.id_usuario` entra na RAW (migração 039 e
   `src.pipeline.ativo_pedido_usuario` para o histórico) e em
   `staging.ativo_pedido.comprador_usuario_id`. A política CPF/HMAC e a vinculação entre origens
   foram implementadas na migração 008 (`docs/CORE_DIM_PESSOA_CONTATO.md`),
   mas o preenchimento segue atrás do gate `CORE_PII_ENABLE_SYNC` e o backfill
   histórico desde 01/01/2026 aguarda aprovação de volume.
4. Composição e atribuição dos combos não comprovadas. `dim_combo` é parcial;
   combos vendidos e ticket médio de combo não são publicados.
5. Categoria Magento disponível na inscrição é ID numérico. A descrição
   textual requer fonte/contrato validado.
6. Descontos exclusivamente no cabeçalho Magento e pedidos mistos não têm
   rateio individual seguro. `valor_liquido_inscricao` permanece NULL.
7. É preciso reconciliar atualização antiga de RAW: rerodar ranges de
   inscrições impactadas por mudanças de categoria/cupom/regras/itens,
   cancelamentos e passagem da data do evento. O código invalida eventos,
   combos e pedidos, mas não há CDC de todas as views auxiliares. O gate de
   indicadores não poderá abrir antes do reconciliador completo. Em
   28/10/2026, ~1,55 milhão de inscrições rebaixadas pelo antigo `022`
   (hash de dependências NULL) foram agendadas para nova derivação
   (`src/automation/core_recovery.py`), e os cadastros RAW passaram a ser
   atualizados diariamente. A rederivação concluiu em 29/10/2026 às 13:58
   com `RECOVERY_STUCK_AFTER 0` e auditorias de contagem sem divergência.
8. A homologação sintética PostgreSQL 16.13 passou com 20 testes de integração,
   mas não substitui a reconciliação histórica real. As RAW versionadas
   declaram `pedido_id` NOT NULL; inscrição com pedido NULL está suportada na
   CORE mas não há fixture de origem contratualmente válida para esse caso.
9. Antes de produção: revisão de DDL/índices, cardinalidade e planos no
   `Atendimento` em leitura, estimativa de recursos, papel mínimo, backup,
   janela, aprovação explícita e carga inicial supervisionada. Nenhuma dessas
   atividades foi autorizada nesta tarefa.
