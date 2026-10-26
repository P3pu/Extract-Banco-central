-- RAW R1: dimensionamento/monitoramento apenas leitura; NÃO aplica índice.
-- Rodar somente após autorização de diagnóstico no Atendimento.
BEGIN READ ONLY;
SET LOCAL statement_timeout = '5s';
SET LOCAL lock_timeout = '500ms';
SELECT current_database() AS banco,
       current_setting('transaction_read_only') AS modo,
       current_setting('server_version') AS versao,
       1 / CASE WHEN current_database()='Atendimento'
                     AND current_setting('transaction_read_only')='on'
                THEN 1 ELSE 0 END AS destino_validado;

SELECT t.reltuples::BIGINT AS linhas_estimadas_catalogo,
       pg_table_size(t.oid) AS bytes_tabela_incluindo_toast,
       pg_indexes_size(t.oid) AS bytes_indices_atuais,
       pg_total_relation_size(t.oid) AS bytes_totais_atuais,
       -- Faixa de planejamento, NÃO previsão física: deduplicação/densidade variam.
       (GREATEST(t.reltuples,0)*24)::BIGINT AS indice_heuristico_min_bytes,
       (GREATEST(t.reltuples,0)*64)::BIGINT AS indice_heuristico_max_bytes,
       pg_relation_size(to_regclass('raw.idx_magento_sales_order_item_order_id'))
         AS bytes_indice_r1_se_existir
FROM pg_class t
WHERE t.oid=to_regclass('raw.magento_sales_order_item');

SELECT s.n_live_tup AS linhas_vivas_estimadas,
       s.n_dead_tup AS linhas_mortas_estimadas,
       s.n_tup_ins AS insercoes_desde_reset_stats,
       s.n_tup_upd AS atualizacoes_desde_reset_stats,
       s.n_tup_del AS exclusoes_desde_reset_stats,
       s.last_autoanalyze
FROM pg_stat_user_tables s
WHERE s.relid=to_regclass('raw.magento_sales_order_item');

SELECT x.indexrelid::regclass AS indice, am.amname AS metodo,
       x.indisvalid, x.indisready, x.indislive,
       x.indnkeyatts, x.indnatts, x.indkey::TEXT AS colunas_fisicas,
       pg_get_indexdef(x.indexrelid) AS definicao,
       pg_relation_size(x.indexrelid) AS bytes_indice,
       COALESCE(st.idx_scan,0) AS scans_desde_reset_stats
FROM pg_index x
JOIN pg_class i ON i.oid=x.indexrelid
JOIN pg_am am ON am.oid=i.relam
LEFT JOIN pg_stat_user_indexes st ON st.indexrelid=i.oid
WHERE x.indrelid=to_regclass('raw.magento_sales_order_item')
ORDER BY i.relname;

SELECT p.pid, p.phase, p.blocks_total, p.blocks_done,
       p.tuples_total, p.tuples_done, p.lockers_total, p.lockers_done
FROM pg_stat_progress_create_index p
WHERE p.relid=to_regclass('raw.magento_sales_order_item');
COMMIT;
