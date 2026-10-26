-- RAW R1: catálogo somente leitura. Usar psql -X -v ON_ERROR_STOP=1.
-- Estado permitido: A_CRIAR ou JA_VALIDO. Qualquer outra condição falha.
BEGIN READ ONLY;
SET LOCAL statement_timeout = '5s';
SET LOCAL lock_timeout = '500ms';
WITH alvo AS (
    SELECT to_regclass('raw.magento_sales_order_item') AS tabela_oid,
           to_regclass('raw.idx_magento_sales_order_item_order_id') AS indice_oid
), verificacao AS (
    SELECT a.tabela_oid, a.indice_oid,
           t.relkind='r' AND t.relpersistence='p' AS tabela_regular,
           c.attnum IS NOT NULL AND c.atttypid='int8'::regtype
             AND c.attnotnull AS coluna_correta,
           EXISTS (
               SELECT 1 FROM pg_index x
               JOIN pg_class i ON i.oid=x.indexrelid
               JOIN pg_am am ON am.oid=i.relam
               JOIN pg_opclass op ON op.oid=x.indclass[0]
               WHERE x.indexrelid=a.indice_oid AND x.indrelid=a.tabela_oid
                 AND i.relnamespace=to_regnamespace('raw')
                 AND i.relkind='i' AND i.relpersistence='p'
                 AND am.amname='btree' AND op.opcname='int8_ops'
                 AND op.opcnamespace='pg_catalog'::regnamespace
                 AND x.indnkeyatts=1 AND x.indnatts=1
                 AND x.indkey[0]=c.attnum AND x.indoption[0]=0
                 AND x.indcollation[0]=0
                 AND x.indpred IS NULL AND x.indexprs IS NULL
                 AND NOT x.indisunique AND NOT x.indisprimary
                 AND x.indisvalid AND x.indisready AND x.indislive
           ) AS indice_exato_valido,
           EXISTS (
               SELECT 1 FROM pg_index x
               JOIN pg_class i ON i.oid=x.indexrelid
               JOIN pg_am am ON am.oid=i.relam
               WHERE x.indrelid=a.tabela_oid
                 AND x.indexrelid IS DISTINCT FROM a.indice_oid
                 AND x.indkey[0]=c.attnum AND am.amname='btree'
           ) AS outro_btree_iniciado_em_order_id
    FROM alvo a
    LEFT JOIN pg_class t ON t.oid=a.tabela_oid
    LEFT JOIN pg_attribute c ON c.attrelid=a.tabela_oid
      AND c.attname='order_id' AND NOT c.attisdropped
)
SELECT current_database() AS banco,
       current_setting('transaction_read_only') AS modo,
       CASE WHEN indice_oid IS NULL THEN 'A_CRIAR' ELSE 'JA_VALIDO' END AS estado,
       tabela_regular, coluna_correta, indice_exato_valido,
       outro_btree_iniciado_em_order_id,
       1 / CASE WHEN current_setting('transaction_read_only')='on'
                     AND COALESCE(tabela_regular,FALSE)
                     AND COALESCE(coluna_correta,FALSE)
                     AND NOT outro_btree_iniciado_em_order_id
                     AND (indice_oid IS NULL OR indice_exato_valido)
                THEN 1 ELSE 0 END AS preflight_aprovado
FROM verificacao;
COMMIT;
