# D5-A — diagnóstico RAW do Naruto

**Estado em 21/10/2026: NÃO APTO para avançar à preparação do executor ocioso.** O diagnóstico real não foi executado: nesta sessão não havia conexão PostgreSQL autorizada e autenticada nem conta somente leitura disponível. Não reutilizei senhas compartilhadas em conversas, não li segredos de containers/arquivos protegidos e não acessei o Naruto. Portanto, os resultados abaixo são **expectativas do código**, não observações do banco. Nenhuma carga, DDL, implantação ou consulta a dados de negócio foi realizada.

Base examinada: branch `codex/deploy-d4-1-schema-safety`, commit `b34a3e47d22b9ed65578154344a135d392918c73`. O roteiro manual está em `sql/postgres/diagnostics/d5_a_catalog_readonly.sql` e `sql/postgres/diagnostics/d5_a_etl_controls_readonly.sql`. Ambos delimitam transações `READ ONLY`, `statement_timeout = 5s` e `lock_timeout = 500ms` e só consultam catálogo, estatísticas e controles técnicos. No pgAdmin, executar **primeiro apenas o bloco de preflight** do catálogo; prosseguir somente se `database_conectado = Atendimento`, `destino_ok = true` e `leitura_ok = true`. Parar em qualquer erro ou timeout.

## Contratos a conferir

| Origem | Tabela RAW | Contrato versionado | PK esperada | Resultado real |
| --- | --- | --- | --- | --- |
| Magento | `raw.magento_sales_order` | `src/sources/magento/sales_order.py` | `entity_id` | Não verificado |
| Magento | `raw.magento_sales_order_item` | `src/sources/magento/sales_order_item.py` | `item_id` | Não verificado |
| Ativo | `raw.ativo_pedido` | `src/sources/ativo/pedido.py` | `id_pedido` | Não verificado |
| Ativo | `raw.ativo_pedido_evento` | `src/sources/ativo/pedido_evento.py` | `id_pedido_evento` | Não verificado |

O teste D4.1 `src/loaders/postgres_loader.py::validate_target` exige tabela comum permanente (`relkind = r`, `relpersistence = p`), exatamente as colunas `FIELDS` mais `_source`, `_extracted_at` e `_batch_id`, tipo físico/typmod, nullabilidade, ausência de colunas geradas/identidade e PK simples válida/pronta. O SQL D5-A espelha essas verificações sem ler linhas RAW. Em particular, `raw.ativo_pedido_evento.fl_amigo` deve ser `VARCHAR(1)` (`typname = varchar`, `atttypmod = 5`, `NOT NULL`). **Tipo observado: desconhecido**; se for `CHAR(1)` ou qualquer outro, registrar divergência e planejar migração separada, sem corrigi-la nesta etapa. Também não foi possível confirmar os índices existentes.

## Controles ETL e backlog

`raw._etl_watermark` tem PK versionada em `(pipeline_name, source_system, source_table)`. Os registros esperados para as quatro entidades são consultados por essa chave no roteiro; estratégia prevista pelo código: `updated_at` para Magento e `pk+reconciliation` para Ativo. **Watermarks, valores, datas de sucesso e defasagens reais: não verificados.** A referência histórica de 28/09/2026 não deve ser tratada como estado atual. Se nenhum sucesso ocorreu desde então, a defasagem em 21/10/2026 seria de aproximadamente 23 dias; esta é somente uma hipótese, não uma medição.

O roteiro consulta apenas estatísticas estimadas de `raw._etl_runs` e prepara `EXPLAIN` **sem ANALYZE** para duas consultas candidatas: últimas 20 execuções das quatro entidades e últimas 20 com `FAILED`/`RUNNING`. Não executa as consultas de runs. O DDL versionado fornece apenas índice/PK em `batch_id`; sem outro índice observado e plano aprovado, `ORDER BY started_at DESC LIMIT 20` pode exigir varredura e ordenação do histórico. Assim, últimos status, horários, contagens e duração permanecem **indeterminados**, em vez de serem obtidos com uma consulta potencialmente custosa. Nenhum registro antigo `RUNNING` deve ser alterado nesta fase.

O número exato de alterações acumuladas nas origens **não pode ser inferido** de watermarks nem de estimativas PostgreSQL. A primeira sincronização deve ser autorizada por entidade e monitorada separadamente. `sales_order_item` é o maior risco de custo: o contrato de extração força o índice primário e pagina por `item_id`, aplicando `updated_at >= watermark - 5 minutos`, porque a origem não tem índice em `updated_at` segundo o código versionado. Isso evita perder atualizações de IDs antigos, mas pode percorrer grande parte da tabela na primeira execução após uma defasagem longa. Não consultar MySQL nem iniciar carga para estimar esse volume nesta etapa.

## Pendências bloqueantes e decisão

1. Obter uma sessão PostgreSQL autorizada, preferencialmente com usuário somente leitura, e confirmar `Atendimento` e `READ ONLY` pelo preflight.
2. Executar o catálogo D5-A e registrar existência/permanência, divergências de colunas/tipos, PK, `fl_amigo` e índices das quatro tabelas. Resultado sem linhas na consulta de divergências só vale junto às verificações de existência e PK.
3. Confirmar os quatro watermarks reais, estratégia, coluna de controle e defasagem. Watermark ausente/nulo impede o incremental conforme o código.
4. Revisar os planos e índices de `_etl_runs` antes de autorizar as consultas de histórico, `FAILED` e `RUNNING`. Sem isso, não há confirmação dos últimos resultados ETL.
5. Dimensionar e aprovar separadamente a primeira carga, sobretudo o custo de leitura MySQL de `sales_order_item`; nenhuma carga FULL deve ser repetida automaticamente.

**Decisão: NÃO APTO** para declarar a estrutura RAW compatível ou avançar com a preparação operacional do executor ocioso. Esta classificação decorre de evidência real ausente, não de divergência comprovada. Após receber os resultados de leitura, atualizar este relatório com observado × esperado e reavaliar a decisão. Os gates de carga permanecem fechados.
