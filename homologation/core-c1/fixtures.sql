-- Dados integralmente inventados. Não usar dumps, CSVs ou IDs de produção.
-- Executar uma vez em volume vazio, depois de run.sh schema.
BEGIN;

INSERT INTO raw.ativo_pedido_status
  (id_pedido_status, ds_status, _source, _extracted_at, _batch_id)
VALUES
  (2, 'Confirmado sintético', 'synthetic', '2025-01-01T00:00:00Z',
   '00000000-0000-0000-0000-000000000001');

INSERT INTO raw.ativo_evento
  (id_evento, ds_evento, dt_evento, _source, _extracted_at, _batch_id)
VALUES
  (1001, 'Evento sintético A', '2025-01-10', 'synthetic',
   '2025-01-01T00:00:00Z', '00000000-0000-0000-0000-000000000001');

INSERT INTO raw.ativo_modalidade_categoria
  (id_categoria, ds_categoria, vl_kit, _source, _extracted_at, _batch_id)
VALUES
  (1101, 'Categoria sintética', 5.00, 'synthetic',
   '2025-01-01T00:00:00Z', '00000000-0000-0000-0000-000000000001');

INSERT INTO raw.ativo_combo
  (id_combo, ds_titulo, _source, _extracted_at, _batch_id)
VALUES
  (2001, 'Combo sintético', 'synthetic', '2025-01-01T00:00:00Z',
   '00000000-0000-0000-0000-000000000001');

INSERT INTO raw.ativo_pedido
  (id_pedido, id_pedido_status, id_combo, ds_cod, dt_pedido,
   nr_desconto, _source, _extracted_at, _batch_id)
VALUES
  (3002, 2, 2001, 'SYN-A-3002', '2025-01-01 12:00:00',
   0, 'synthetic', '2025-01-01T00:00:00Z',
   '00000000-0000-0000-0000-000000000001');

INSERT INTO raw.ativo_cupom_desconto
  (id_cupom_desconto, en_cupom_classificacao, _source, _extracted_at, _batch_id)
VALUES
  (8201, ' GrUpOs  ', 'synthetic', '2025-01-01T00:00:00Z',
   '00000000-0000-0000-0000-000000000001');

INSERT INTO raw.ativo_cupom_desconto_item
  (id_cupom_desconto_item, nr_cupom, fl_usado, dt_sistema,
   id_cupom_desconto, _source, _extracted_at, _batch_id)
VALUES
  (8101, 'SYN-CUPOM-1', 'S', '2025-01-01 12:00:00',
   8201, 'synthetic', '2025-01-01T00:00:00Z',
   '00000000-0000-0000-0000-000000000001');

INSERT INTO raw.ativo_status_detalhado
  (id_status_detalhado, id_pedido_status, status, tipo, ativo,
   _source, _extracted_at, _batch_id)
VALUES
  (0, 2, 'Regular sintético', 'inscricao', 'S',
   'synthetic', '2025-01-01T00:00:00Z',
   '00000000-0000-0000-0000-000000000001');

INSERT INTO raw.ativo_pedido_evento
  (id_pedido_evento, id_pedido, id_evento, id_categoria, id_usuario,
   id_status_detalhado, id_cupom_individual, nr_preco, nr_taxa,
   nr_desconto_individual, fl_amigo, dt_cadastro,
   _source, _extracted_at, _batch_id)
VALUES
  (5001, 3002, 1001, 1101, 7001, 0, 8101, 100.00, 2.00,
   '10.00', 'N', '2025-01-01 12:00:00',
   'synthetic', '2025-01-01T00:00:00Z',
   '00000000-0000-0000-0000-000000000001'),
  -- Pedido 3999 não existe: órfão deliberado, sem dados de pessoa.
  (5002, 3999, 1001, 1101, 7002, 0, NULL, 50.00, 0.00,
   '0', 'N', '2025-01-01 12:00:00',
   'synthetic', '2025-01-01T00:00:00Z',
   '00000000-0000-0000-0000-000000000001');

INSERT INTO raw.magento_product
  (entity_id, sku, type_id, attribute_set_id, created_at, updated_at,
   _source, _extracted_at, _batch_id)
VALUES
  (9001, 'SYN-EVENT', 'virtual', 1, '2025-01-01', '2025-01-01',
   'synthetic', '2025-01-01T00:00:00Z',
   '00000000-0000-0000-0000-000000000001'),
  (9002, 'SYN-BUNDLE', 'bundle', 1, '2025-01-01', '2025-01-01',
   'synthetic', '2025-01-01T00:00:00Z',
   '00000000-0000-0000-0000-000000000001'),
  (9003, 'SYN-CHILD-A', 'simple', 1, '2025-01-01', '2025-01-01',
   'synthetic', '2025-01-01T00:00:00Z',
   '00000000-0000-0000-0000-000000000001'),
  (9004, 'SYN-CHILD-B', 'simple', 1, '2025-01-01', '2025-01-01',
   'synthetic', '2025-01-01T00:00:00Z',
   '00000000-0000-0000-0000-000000000001');

INSERT INTO raw.magento_product_varchar
  (value_id, attribute_id, store_id, entity_id, value,
   _source, _extracted_at, _batch_id)
VALUES
  (1, 321, 0, 9002, '9001', 'synthetic', '2025-01-01T00:00:00Z',
   '00000000-0000-0000-0000-000000000001');

INSERT INTO raw.magento_sales_order
  (entity_id, increment_id, state, status, subtotal, discount_amount,
   grand_total, total_item_count, total_qty_ordered, created_at, updated_at,
   _source, _extracted_at, _batch_id)
VALUES
  (3001, 'SYN-M-3001', 'processing', 'approved', 100.00, -15.00,
   85.00, 3, 3.00, '2025-01-01 12:00:00', '2025-01-01 12:00:00',
   'synthetic', '2025-01-01T00:00:00Z',
   '00000000-0000-0000-0000-000000000001');

INSERT INTO raw.magento_sales_order_item
  (item_id, order_id, parent_item_id, product_id, sku, product_type,
   price, base_price, row_total, base_row_total, discount_amount,
   qty_ordered, qty_canceled, qty_refunded, created_at, updated_at,
   _source, _extracted_at, _batch_id)
VALUES
  (4001, 3001, NULL, 9002, 'SYN-BUNDLE', 'bundle',
   100.00, 100.00, 100.00, 100.00, 0.00,
   1, 0, 0, '2025-01-01', '2025-01-01',
   'synthetic', '2025-01-01T00:00:00Z',
   '00000000-0000-0000-0000-000000000001'),
  (4002, 3001, 4001, 9003, 'SYN-CHILD-A', 'simple',
   60.00, 60.00, 60.00, 60.00, 10.00,
   1, 0, 0, '2025-01-01', '2025-01-01',
   'synthetic', '2025-01-01T00:00:00Z',
   '00000000-0000-0000-0000-000000000001'),
  (4003, 3001, 4001, 9004, 'SYN-CHILD-B', 'simple',
   40.00, 40.00, 40.00, 40.00, 5.00,
   1, 0, 0, '2025-01-01', '2025-01-01',
   'synthetic', '2025-01-01T00:00:00Z',
   '00000000-0000-0000-0000-000000000001');

COMMIT;
