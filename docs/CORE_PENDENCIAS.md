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
   e o backfill desde 01/01/2026 foi aprovado em 30/10/2026; o gate
   `CORE_PII_ENABLE_SYNC` fica aberto na automação do servidor.
4. Resolvido em 03/11/2026: combos vendidos estão publicados, com as regras em
   `docs/CORE_REGRAS_DE_NEGOCIO.md`. `dim_combo` segue sem composição validada.
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
   Em 04/11/2026, a parte de status defasados do Ativo foi tratada: releitura
   completa manual, releitura diária de eventos abertos e releitura mensal.
8. A homologação sintética PostgreSQL 16.13 passou com 20 testes de integração,
   mas não substitui a reconciliação histórica real. As RAW versionadas
   declaram `pedido_id` NOT NULL; inscrição com pedido NULL está suportada na
   CORE mas não há fixture de origem contratualmente válida para esse caso.
9. A CORE roda em produção no `Atendimento`, pelo ciclo horário, desde 28/10/2026.
   A view de indicadores continua fechada. Papel mínimo e backup seguem sem registro
   de conclusão.

## Em aberto em 04/11/2026

10. Primeira rodada diária de `event_sync` e `relink_missing` a conferir, inclusive
    se `SEM_CLIENTE` de 2026 cai (1.526 em 04/11; 572 com ID acima do último item
    ligado a um cliente).
11. Primeira releitura mensal do Ativo a conferir, em 12/2026.
12. Três inscrições Magento em conflito de identidade, de dois clientes (ver
    `CORE_PERSON_REVISAR_IDENTIDADE` no log). Ficam sem pessoa, sem ação prevista.
13. Datas do Magento que parecem erradas e agora prevalecem no evento unificado:
    João Pessoa 2025 (17/08, Ativo 14 a 17/09), Girl Power Osasco 2026 (26/04, Ativo
    10/05), Estações Outono Rio 2025 (16/03, Ativo 18/04) e Estações Primavera Campo
    Grande 2026 (11/10, Ativo 26/09). A correção é no Magento; a CORE acompanha em
    um dia.
14. Túnel do Ativo: segue no notebook por decisão de 04/11/2026. A saída definitiva é
    a regra da AWS (`docs/DEPLOY_SERVIDOR_SEM_DOCKER.md`).
15. Cópia da chave HMAC em cofre, ainda não guardada.
16. `/dev/shm` do PostgreSQL com 64 MB: consultas manuais grandes precisam de
    `SET max_parallel_workers_per_gather=0`.
17. API somente leitura para o painel, sem decisão. O painel é atualizado a pedido.
18. KPIs de Sales Growth: metas e definições a fechar ([KPIS_SALES_GROWTH.md](KPIS_SALES_GROWTH.md)).

## Decidido em 04/11/2026

- Nenhuma investigação ou limpeza de CPF inválido: fica só sinalizado.
- 16 exceções de classificação do Magento na Night Run Fortaleza 2026 ficam como estão.
- `Cancelado - estorno` não conta. Inscrição que sumiu da origem é marcada, não apagada.
- Kit Patrocinador conta como Cortesia, mesmo quando pago.
