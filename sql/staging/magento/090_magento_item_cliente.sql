-- Grão: uma linha por item_id não nulo presente na associação RAW.
CREATE OR REPLACE VIEW staging.magento_item_cliente AS
SELECT sales_order_item_item_id::BIGINT AS item_id,
       CASE WHEN COUNT(DISTINCT customer_id) = 1 THEN MIN(customer_id)::BIGINT END AS cliente_id,
       COUNT(DISTINCT customer_id) AS qtd_clientes_associados,
       COUNT(DISTINCT customer_id) > 1 AS cliente_ambiguo
FROM raw.magento_customer_order_item
WHERE sales_order_item_item_id IS NOT NULL
GROUP BY sales_order_item_item_id;
