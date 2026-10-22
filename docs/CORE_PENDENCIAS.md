# CORE V1 — pendências reais

1. `sa_cupom_desconto.en_cupom_classificacao` não está na STAGING. Sem esse
   atributo, cupons Ativo não-GR podem permanecer com classificação NULL;
   não inferir Grupos de outras classificações.
2. Descrição de `id_status_detalhado` não integrada à STAGING. Códigos
   especiais ficam pendentes, sem rótulo inventado.
3. Comprador Ativo ausente da view de pedidos. Papéis comprador/participante,
   política CPF/HMAC e vinculação entre origens aguardam aprovação; não
   popular `dim_pessoa`/`pessoa_source_map` automaticamente.
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
   indicadores não poderá abrir antes do reconciliador completo.
8. Homologação PostgreSQL Docker local e os 20 cenários mínimos ainda devem
   ser executados/expandidos. Docker Desktop não iniciou no ambiente desta
   execução; não substituir esse teste por produção.
9. Antes de produção: revisão de DDL/índices, cardinalidade e planos no
   `Atendimento` em leitura, estimativa de recursos, papel mínimo, backup,
   janela, aprovação explícita e carga inicial supervisionada. Nenhuma dessas
   atividades foi autorizada nesta tarefa.
