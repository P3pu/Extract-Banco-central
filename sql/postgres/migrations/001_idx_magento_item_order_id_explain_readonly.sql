-- RAW R1: verificar plano APÓS índice válido; sem ANALYZE e sem ler itens.
BEGIN READ ONLY;
SET LOCAL statement_timeout = '5s';
SET LOCAL lock_timeout = '500ms';
SELECT current_database() AS banco,
       current_setting('transaction_read_only') AS modo,
       1 / CASE WHEN current_database()='Atendimento'
                     AND current_setting('transaction_read_only')='on'
                THEN 1 ELSE 0 END AS destino_validado;
EXPLAIN (FORMAT TEXT, COSTS TRUE)
SELECT item_id, order_id, parent_item_id, row_total, discount_amount,
       qty_ordered, qty_canceled, qty_refunded
FROM raw.magento_sales_order_item
WHERE order_id IN (166688,1673612,1673646,1673884);
COMMIT;
