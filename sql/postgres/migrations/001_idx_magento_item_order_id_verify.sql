-- RAW R1: verificação posterior somente leitura. Falhar se inválido/incompleto.
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
       indice_oid::regclass AS indice,
       tabela_regular, coluna_correta, indice_exato_valido,
       outro_btree_iniciado_em_order_id,
       pg_get_indexdef(indice_oid) AS definicao,
       1 / CASE WHEN current_setting('transaction_read_only')='on'
                     AND COALESCE(tabela_regular,FALSE)
                     AND COALESCE(coluna_correta,FALSE)
                     AND indice_exato_valido
                     AND NOT outro_btree_iniciado_em_order_id
                THEN 1 ELSE 0 END AS indice_verificado
FROM verificacao;
COMMIT;
