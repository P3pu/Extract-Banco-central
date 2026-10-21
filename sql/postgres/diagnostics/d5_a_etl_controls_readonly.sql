-- D5-A: executar somente após preflight e existência de raw._etl_watermark/_etl_runs.
-- Somente metadados técnicos. A parte EXPLAIN NÃO executa a consulta de runs.
BEGIN READ ONLY;
SET LOCAL statement_timeout = '5s';
SET LOCAL lock_timeout = '500ms';

SELECT current_database() AS database_conectado,
       current_database() = 'Atendimento' AS destino_ok,
       current_setting('transaction_read_only') = 'on' AS leitura_ok,
       clock_timestamp() AS diagnostico_em;

-- Usa a PK composta versionada em raw._etl_watermark; não varre tabelas de negócio.
WITH alvo(pipeline_name, source_system, source_table) AS (VALUES
    ('raw.magento_sales_order', 'magento', 'sales_order'),
    ('raw.magento_sales_order_item', 'magento', 'sales_order_item'),
    ('raw.ativo_pedido', 'ativo', 'sa_pedido'),
    ('raw.ativo_pedido_evento', 'ativo', 'sa_pedido_evento')
)
SELECT a.pipeline_name, a.source_system, a.source_table,
       w.pipeline_name IS NOT NULL AS watermark_existe,
       w.strategy, w.watermark_column, w.watermark_value,
       w.last_success_at,
       clock_timestamp() - w.last_success_at AS defasagem_ultimo_sucesso
FROM alvo a LEFT JOIN raw._etl_watermark w
  ON (w.pipeline_name, w.source_system, w.source_table)
   = (a.pipeline_name, a.source_system, a.source_table)
WHERE current_database() = 'Atendimento'
  AND current_setting('transaction_read_only') = 'on'
ORDER BY a.source_system, a.source_table;

-- Estatísticas estimadas, não COUNT(*); conferem custo potencial da consulta de runs.
SELECT s.relname, s.n_live_tup AS linhas_vivas_estimadas,
       s.n_dead_tup AS linhas_mortas_estimadas,
       s.last_analyze, s.last_autoanalyze,
       s.seq_scan, s.idx_scan
FROM pg_catalog.pg_stat_user_tables s
WHERE s.schemaname = 'raw' AND s.relname IN ('_etl_runs', '_etl_watermark')
  AND current_database() = 'Atendimento'
  AND current_setting('transaction_read_only') = 'on'
ORDER BY s.relname;

-- Plano da consulta candidata de últimas runs: SEM ANALYZE, SEM execução.
-- Não executar o SELECT correspondente sem revisar o plano e os índices.
EXPLAIN (FORMAT TEXT)
SELECT pipeline_name, source_system, source_table, mode, status,
       started_at, finished_at, rows_extracted, rows_loaded,
       finished_at - started_at AS duracao
FROM raw._etl_runs
WHERE (pipeline_name, source_system, source_table) IN (
    ('raw.magento_sales_order', 'magento', 'sales_order'),
    ('raw.magento_sales_order_item', 'magento', 'sales_order_item'),
    ('raw.ativo_pedido', 'ativo', 'sa_pedido'),
    ('raw.ativo_pedido_evento', 'ativo', 'sa_pedido_evento')
)
ORDER BY started_at DESC
LIMIT 20;

-- Plano de FAILED/RUNNING: também NÃO executa a consulta de dados.
EXPLAIN (FORMAT TEXT)
SELECT pipeline_name, source_system, source_table, mode, status,
       started_at, finished_at, rows_extracted, rows_loaded
FROM raw._etl_runs
WHERE status IN ('FAILED', 'RUNNING')
  AND (pipeline_name, source_system, source_table) IN (
    ('raw.magento_sales_order', 'magento', 'sales_order'),
    ('raw.magento_sales_order_item', 'magento', 'sales_order_item'),
    ('raw.ativo_pedido', 'ativo', 'sa_pedido'),
    ('raw.ativo_pedido_evento', 'ativo', 'sa_pedido_evento')
  )
ORDER BY started_at DESC
LIMIT 20;

COMMIT;

-- Os SELECTs de raw._etl_runs requerem revisão e autorização após EXPLAIN.
-- O contrato versionado oferece apenas PK(batch_id); um Seq Scan + Sort em
-- histórico grande não atende ao limite de custo desta D5-A. Não criar índice aqui.
