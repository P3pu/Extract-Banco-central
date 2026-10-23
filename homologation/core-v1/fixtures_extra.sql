-- Somente IDs e valores inventados; complementar a fixture C1 no volume V1.
BEGIN;
INSERT INTO raw.ativo_pedido_status
  (id_pedido_status,ds_status,_source,_extracted_at,_batch_id)
VALUES (1,'Aguardando sintético','synthetic','2025-01-01T00:00:00Z',
        '00000000-0000-0000-0000-000000000001');
INSERT INTO raw.ativo_pedido
  (id_pedido,id_pedido_status,ds_cod,dt_pedido,fl_local_inscricao,
   nr_desconto,_source,_extracted_at,_batch_id)
VALUES (3001,2,'SYN-A-3001','2025-01-01 12:00:00',1,0,
        'synthetic','2025-01-01T00:00:00Z',
        '00000000-0000-0000-0000-000000000001'),
       (3003,1,'SYN-A-3003','2025-01-01 12:00:00',2,0,
        'synthetic','2025-01-01T00:00:00Z',
        '00000000-0000-0000-0000-000000000001'),
       (3004,2,'SYN-A-3004','2025-01-01 12:00:00',1,0,
        'synthetic','2025-01-01T00:00:00Z',
        '00000000-0000-0000-0000-000000000001');
UPDATE raw.ativo_pedido SET id_combo=2001 WHERE id_pedido=3004;
INSERT INTO raw.ativo_modalidade_categoria
  (id_categoria,ds_categoria,vl_kit,_source,_extracted_at,_batch_id)
VALUES (1103,'Cortesia sintética',0,'synthetic','2025-01-01T00:00:00Z',
        '00000000-0000-0000-0000-000000000001');
INSERT INTO raw.ativo_cupom_desconto_item
  (id_cupom_desconto_item,nr_cupom,fl_usado,dt_sistema,id_cupom_desconto,
   _source,_extracted_at,_batch_id)
VALUES (8102,'GR-SYNTHETIC','S','2025-01-01 12:00:00',8201,
        'synthetic','2025-01-01T00:00:00Z',
        '00000000-0000-0000-0000-000000000001');
INSERT INTO raw.ativo_pedido_evento
  (id_pedido_evento,id_pedido,id_evento,id_categoria,id_usuario,
   id_status_detalhado,id_cupom_individual,nr_preco,nr_taxa,
   nr_desconto_individual,fl_amigo,dt_cadastro,_source,_extracted_at,_batch_id)
VALUES (5005,3001,1001,1101,7005,0,NULL,100,7.25,'0','N',
        '2025-01-01 12:00:00','synthetic','2025-01-01T00:00:00Z',
        '00000000-0000-0000-0000-000000000001'),
       (5006,3001,1001,1101,7006,5,NULL,100,7.25,'0','N',
        '2025-01-01 12:00:00','synthetic','2025-01-01T00:00:00Z',
        '00000000-0000-0000-0000-000000000001'),
       (5007,3003,1001,1101,7007,0,NULL,100,1.50,'0','N',
        '2025-01-01 12:00:00','synthetic','2025-01-01T00:00:00Z',
        '00000000-0000-0000-0000-000000000001'),
       (5008,3001,1001,1101,7008,14,NULL,100,1.50,'0','N',
        '2025-01-01 12:00:00','synthetic','2025-01-01T00:00:00Z',
        '00000000-0000-0000-0000-000000000001'),
       (5009,3002,1001,1103,7009,0,8102,0,0,'0','N',
        '2025-01-01 12:00:00','synthetic','2025-01-01T00:00:00Z',
        '00000000-0000-0000-0000-000000000001'),
       (5010,3002,1001,1103,7010,0,NULL,0,0,'0','N',
        '2025-01-01 12:00:00','synthetic','2025-01-01T00:00:00Z',
        '00000000-0000-0000-0000-000000000001');
INSERT INTO raw.ativo_pedido_evento
  (id_pedido_evento,id_pedido,id_evento,id_categoria,id_usuario,
   id_status_detalhado,id_cupom_individual,nr_preco,nr_taxa,
   nr_desconto_individual,fl_amigo,dt_cadastro,_source,_extracted_at,_batch_id)
SELECT g,3004,1001,1101,7000+g,0,NULL,100,2,'0','N',
       '2025-01-01 12:00:00','synthetic','2025-01-01T00:00:00Z',
       '00000000-0000-0000-0000-000000000001'
FROM generate_series(5011,5015) AS s(g);
UPDATE raw.ativo_evento SET id_campanha_salesforce='SYN-EVENT'
WHERE id_evento=1001;
INSERT INTO raw.magento_product
  (entity_id,sku,type_id,attribute_set_id,created_at,updated_at,
   _source,_extracted_at,_batch_id)
VALUES (9005,'SYN-FUTURE-EVENT','virtual',1,'2025-01-01','2025-01-01',
        'synthetic','2025-01-01T00:00:00Z',
        '00000000-0000-0000-0000-000000000001'),
       (9006,'SYN-FUTURE-BUNDLE','bundle',1,'2025-01-01','2025-01-01',
        'synthetic','2025-01-01T00:00:00Z',
        '00000000-0000-0000-0000-000000000001');
INSERT INTO raw.magento_product_varchar
  (value_id,attribute_id,store_id,entity_id,value,
   _source,_extracted_at,_batch_id)
VALUES (2,321,0,9006,'9005','synthetic','2025-01-01T00:00:00Z',
        '00000000-0000-0000-0000-000000000001');
INSERT INTO raw.magento_product_datetime
  (value_id,attribute_id,store_id,entity_id,value,
   _source,_extracted_at,_batch_id)
VALUES (1,195,0,9001,'2025-01-10','synthetic','2025-01-01T00:00:00Z',
        '00000000-0000-0000-0000-000000000001'),
       (2,195,0,9005,'2027-01-10','synthetic','2025-01-01T00:00:00Z',
        '00000000-0000-0000-0000-000000000001');
INSERT INTO raw.magento_sales_order
  (entity_id,increment_id,state,status,subtotal,discount_amount,grand_total,
   total_item_count,total_qty_ordered,created_at,updated_at,
   _source,_extracted_at,_batch_id)
VALUES (3070,'SYN-M-3070','new','new',120,0,120,4,4,
        '2025-01-01 12:00:00','2025-01-01 12:00:00',
        'synthetic','2025-01-01T00:00:00Z',
        '00000000-0000-0000-0000-000000000001');
INSERT INTO raw.magento_sales_order_item
  (item_id,order_id,parent_item_id,product_id,sku,product_type,
   price,base_price,row_total,base_row_total,discount_amount,
   qty_ordered,qty_canceled,qty_refunded,created_at,updated_at,
   _source,_extracted_at,_batch_id)
VALUES (4701,3070,NULL,9002,'SYN-BUNDLE','bundle',60,60,60,60,0,
        1,0,0,'2025-01-01','2025-01-01','synthetic','2025-01-01T00:00:00Z',
        '00000000-0000-0000-0000-000000000001'),
       (4702,3070,4701,9003,'SYN-CHILD-A','simple',60,60,60,60,0,
        1,0,0,'2025-01-01','2025-01-01','synthetic','2025-01-01T00:00:00Z',
        '00000000-0000-0000-0000-000000000001'),
       (4703,3070,NULL,9006,'SYN-FUTURE-BUNDLE','bundle',60,60,60,60,0,
        1,0,0,'2025-01-01','2025-01-01','synthetic','2025-01-01T00:00:00Z',
        '00000000-0000-0000-0000-000000000001'),
       (4704,3070,4703,9003,'SYN-CHILD-A','simple',60,60,60,60,0,
        1,0,0,'2025-01-01','2025-01-01','synthetic','2025-01-01T00:00:00Z',
        '00000000-0000-0000-0000-000000000001');
-- Magento usa legitimamente item_id=0; o alerta CORE deve preservá-lo.
INSERT INTO raw.magento_sales_order
  (entity_id,increment_id,state,status,subtotal,discount_amount,grand_total,
   total_item_count,total_qty_ordered,created_at,updated_at,
   _source,_extracted_at,_batch_id)
VALUES (3090,'SYN-M-3090','processing','approved',10,-2,8,1,1,
        '2025-01-01 12:00:00','2025-01-01 12:00:00',
        'synthetic','2025-01-01T00:00:00Z',
        '00000000-0000-0000-0000-000000000001');
INSERT INTO raw.magento_sales_order_item
  (item_id,order_id,parent_item_id,product_id,sku,product_type,
   price,base_price,row_total,base_row_total,discount_amount,
   qty_ordered,qty_canceled,qty_refunded,created_at,updated_at,
   _source,_extracted_at,_batch_id)
VALUES (0,3090,NULL,9002,'SYN-ZERO-BUNDLE','bundle',10,10,10,10,0,
        1,0,0,'2025-01-01','2025-01-01','synthetic','2025-01-01T00:00:00Z',
        '00000000-0000-0000-0000-000000000001');
COMMIT;
