-- C2.1 / Naruto: APENAS plano; não executar a consulta de itens antes de revisar.
-- O DDL RAW versionado não declara índice em sales_order_item.order_id.
BEGIN READ ONLY;
SET LOCAL statement_timeout = '5s';
SET LOCAL lock_timeout = '500ms';
SELECT current_database() AS banco, current_setting('transaction_read_only') AS modo,
       1 / CASE WHEN current_database() = 'Atendimento'
                     AND current_setting('transaction_read_only') = 'on'
                THEN 1 ELSE 0 END AS destino_validado;
EXPLAIN (FORMAT TEXT, COSTS TRUE)
SELECT i.pedido_id, i.item_id, i.item_pai_id, i.eh_bundle,
       i.valor_linha, i.desconto, i.quantidade_pedida,
       i.quantidade_cancelada, i.quantidade_reembolsada
FROM staging.magento_item_pedido i
WHERE i.pedido_id IN (166688,1673612,1673646,1673884);
COMMIT;
