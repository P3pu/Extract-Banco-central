-- RAW R1. Executar UMA instrução, em autocommit, somente após preflight aprovado.
-- Nunca incluir em BEGIN/COMMIT ou em executores que envolvam o arquivo em transação.
-- IF NOT EXISTS não valida definição/estado: executar verificação posterior.
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_magento_sales_order_item_order_id
    ON raw.magento_sales_order_item USING btree (order_id);
