-- IDs e valores inteiramente sinteticos; nenhum dado pessoal ou da producao.
INSERT INTO raw.magento_sales_order_item
    (item_id, order_id, price, base_price, row_total, base_row_total,
     discount_amount, qty_ordered, qty_canceled, qty_refunded,
     created_at, updated_at, _source, _extracted_at, _batch_id)
VALUES
    (900000001, 800000001, 100.0000, 100.0000, 100.0000, 100.0000,
     0.0000, 1.0000, 0.0000, 0.0000,
     TIMESTAMP '2020-01-01', TIMESTAMP '2020-01-01', 'synthetic-r1',
     TIMESTAMPTZ '2020-01-01 00:00:00+00', '11111111-1111-4111-8111-111111111111'),
    (900000002, 800000001, 40.0000, 40.0000, 80.0000, 80.0000,
     -10.0000, 2.0000, 0.0000, 0.0000,
     TIMESTAMP '2020-01-01', TIMESTAMP '2020-01-01', 'synthetic-r1',
     TIMESTAMPTZ '2020-01-01 00:00:00+00', '11111111-1111-4111-8111-111111111111'),
    (900000003, 800000002, 70.0000, 70.0000, 70.0000, 70.0000,
     0.0000, 1.0000, 0.0000, 0.0000,
     TIMESTAMP '2020-01-01', TIMESTAMP '2020-01-01', 'synthetic-r1',
     TIMESTAMPTZ '2020-01-01 00:00:00+00', '11111111-1111-4111-8111-111111111111');
