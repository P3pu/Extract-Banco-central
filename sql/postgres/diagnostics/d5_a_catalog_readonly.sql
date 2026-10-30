-- D5-A: executar no pgAdmin somente após conferir a conexão autorizada.
-- Copiar primeiro APENAS o bloco de preflight; prosseguir se destino_ok e leitura_ok forem true.
-- Metadados apenas: nenhuma linha de pedidos, inscrições ou clientes é consultada.

BEGIN READ ONLY;
SET LOCAL statement_timeout = '5s';
SET LOCAL lock_timeout = '500ms';
SELECT current_database() AS database_conectado,
       current_database() = 'Atendimento' AS destino_ok,
       current_setting('transaction_read_only') = 'on' AS leitura_ok,
       current_setting('server_version') AS versao_postgresql,
       clock_timestamp() AS diagnostico_em;
COMMIT;

-- Executar o restante somente se o preflight tiver aprovado.
BEGIN READ ONLY;
SET LOCAL statement_timeout = '5s';
SET LOCAL lock_timeout = '500ms';

-- Existência, permanência e estimativa do catálogo (reltuples não é COUNT real).
WITH alvo(table_name) AS (VALUES
    ('magento_sales_order'), ('magento_sales_order_item'),
    ('ativo_pedido'), ('ativo_pedido_evento'),
    ('_etl_watermark'), ('_etl_runs')
)
SELECT a.table_name, c.oid IS NOT NULL AS existe, c.relkind,
       c.relpersistence, c.reltuples::bigint AS linhas_estimadas,
       pg_catalog.pg_size_pretty(pg_catalog.pg_relation_size(c.oid)) AS tamanho_relacao
FROM alvo a
LEFT JOIN pg_catalog.pg_namespace n ON n.nspname = 'raw'
LEFT JOIN pg_catalog.pg_class c ON c.relnamespace = n.oid AND c.relname = a.table_name
WHERE current_database() = 'Atendimento'
  AND current_setting('transaction_read_only') = 'on'
ORDER BY a.table_name;

-- Manifesto físico derivado dos quatro contratos FIELDS do commit b34a3e4.
-- typmod: VARCHAR(n)/CHAR(n) = n+4; NUMERIC(p,s) = ((p<<16)|s)+4.
-- A saída mostra somente divergências. Zero linhas NÃO dispensa conferir existência, PK e índices.
WITH contratos(table_name, pk_column, fields) AS (VALUES
    ('magento_sales_order', 'entity_id',
     'entity_id|int8|-1|true,increment_id|varchar|36|false,customer_id|int8|-1|false,state|varchar|36|false,status|varchar|36|false,coupon_code|varchar|259|false,applied_rule_ids|varchar|132|false,subtotal|numeric|1310728|false,base_subtotal|numeric|1310728|false,discount_amount|numeric|1310728|false,base_discount_amount|numeric|1310728|false,shipping_amount|numeric|1310728|false,base_shipping_amount|numeric|1310728|false,tax_amount|numeric|1310728|false,base_tax_amount|numeric|1310728|false,grand_total|numeric|1310728|false,base_grand_total|numeric|1310728|false,total_item_count|int4|-1|true,total_qty_ordered|numeric|786440|false,created_at|timestamp|-1|true,updated_at|timestamp|-1|true'),
    ('magento_sales_order_item', 'item_id',
     'item_id|int8|-1|true,order_id|int8|-1|true,parent_item_id|int8|-1|false,product_id|int8|-1|false,sku|varchar|259|false,name|varchar|259|false,product_type|varchar|259|false,additional_data|text|-1|false,ext_order_item_id|varchar|259|false,ozone_customers|text|-1|false,price|numeric|786440|true,base_price|numeric|786440|true,row_total|numeric|1310728|true,base_row_total|numeric|1310728|true,discount_amount|numeric|1310728|false,base_discount_amount|numeric|1310728|false,tax_amount|numeric|1310728|false,base_tax_amount|numeric|1310728|false,qty_ordered|numeric|786440|false,qty_invoiced|numeric|786440|false,qty_canceled|numeric|786440|false,qty_refunded|numeric|786440|false,created_at|timestamp|-1|true,updated_at|timestamp|-1|true'),
    ('ativo_pedido', 'id_pedido',
     'id_pedido|int4|-1|true,id_pedido_status|int4|-1|true,id_usuario|int4|-1|true,id_combo|int8|-1|false,id_cupom_desconto_item|int4|-1|false,ds_cod|varchar|29|false,dt_pedido|text|-1|true,dt_alteracao|text|-1|false,fl_local_inscricao|int4|-1|false,fl_delivery|bpchar|5|false,fl_mobile|int4|-1|false,fl_assinante|int4|-1|false,fl_evento_da_casa|int4|-1|false,nr_taxa|numeric|655366|false,nr_delivery|numeric|655366|false,nr_desconto|numeric|655366|true,tp_entregakit|int4|-1|false,nm_camiseta|varchar|154|false,ds_campo_apolo|varchar|104|false,ds_obs|varchar|154|false'),
    ('ativo_pedido_evento', 'id_pedido_evento',
     'id_pedido_evento|int4|-1|true,id_pedido|int4|-1|true,id_evento|int4|-1|true,id_modalidade|int4|-1|false,id_categoria|int4|-1|false,id_usuario|int4|-1|true,id_usuario_balcao|int8|-1|false,id_tamanho_camiseta|int4|-1|false,id_status_detalhado|int4|-1|false,id_cupom_individual|int4|-1|false,nr_peito|int4|-1|false,nr_preco|numeric|655366|true,nr_taxa|numeric|655368|false,nr_desconto_individual|varchar|154|false,nr_protocolo_revezamento|int4|-1|false,nr_ordem_revezamento|int4|-1|false,fl_capitao_revezamento|int4|-1|false,fl_assinante|int4|-1|false,fl_amigo|varchar|5|true,pos_id_evento|int4|-1|false,pos_id_pedido|int4|-1|false,pos_id_pedido_evento|int4|-1|false,ds_equipe|varchar|54|false,ds_nome_equipe_revezamento|varchar|104|false,ds_obs|varchar|204|false,nm_camiseta|varchar|154|false,nr_preco_nm_camiseta|varchar|154|false,nr_preco_foto_clube|varchar|154|false,nr_preco_personalizacao_medalha|varchar|154|false,dt_cadastro|timestamp|-1|true')
), esperado AS (
    SELECT c.table_name, split_part(f.spec, '|', 1) AS column_name,
           split_part(f.spec, '|', 2) AS typname,
           split_part(f.spec, '|', 3)::integer AS typmod,
           split_part(f.spec, '|', 4)::boolean AS not_null
    FROM contratos c CROSS JOIN LATERAL unnest(string_to_array(c.fields, ',')) AS f(spec)
    UNION ALL
    SELECT c.table_name, m.column_name, m.typname, m.typmod, m.not_null
    FROM contratos c CROSS JOIN (VALUES
        ('_source', 'text', -1, true),
        ('_extracted_at', 'timestamptz', -1, true),
        ('_batch_id', 'uuid', -1, true)
    ) AS m(column_name, typname, typmod, not_null)
), observado AS (
    SELECT c.relname AS table_name, a.attname AS column_name,
           t.typname, a.atttypmod AS typmod, a.attnotnull AS not_null,
           a.attgenerated, a.attidentity
    FROM pg_catalog.pg_class c
    JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
    JOIN pg_catalog.pg_attribute a ON a.attrelid = c.oid
    JOIN pg_catalog.pg_type t ON t.oid = a.atttypid
    WHERE n.nspname = 'raw'
      AND c.relname IN (SELECT table_name FROM contratos)
      AND a.attnum > 0 AND NOT a.attisdropped
), comparacao AS (
    SELECT coalesce(e.table_name, o.table_name) AS table_name,
           coalesce(e.column_name, o.column_name) AS column_name,
           e.typname AS tipo_esperado, e.typmod AS typmod_esperado,
           e.not_null AS not_null_esperado,
           o.typname AS tipo_observado, o.typmod AS typmod_observado,
           o.not_null AS not_null_observado,
           CASE WHEN e.column_name IS NULL THEN 'EXTRA'
                WHEN o.column_name IS NULL THEN 'AUSENTE'
                WHEN (e.typname, e.typmod, e.not_null)
                     IS DISTINCT FROM (o.typname, o.typmod, o.not_null)
                  OR o.attgenerated <> '' OR o.attidentity <> '' THEN 'DIVERGENTE'
                ELSE 'OK' END AS resultado
    FROM esperado e FULL JOIN observado o
      ON o.table_name = e.table_name AND o.column_name = e.column_name
)
SELECT * FROM comparacao
WHERE resultado <> 'OK' AND current_database() = 'Atendimento'
  AND current_setting('transaction_read_only') = 'on'
ORDER BY table_name, column_name;

-- Chave primária simples, incluindo os estados de validade/prontidão.
WITH esperado(table_name, pk_column) AS (VALUES
    ('magento_sales_order', 'entity_id'),
    ('magento_sales_order_item', 'item_id'),
    ('ativo_pedido', 'id_pedido'),
    ('ativo_pedido_evento', 'id_pedido_evento')
), observado AS (
    SELECT c.relname AS table_name,
           array_agg(a.attname ORDER BY keys.ordinality) AS pk_columns,
           i.indisvalid, i.indisready
    FROM pg_catalog.pg_index i
    JOIN pg_catalog.pg_class c ON c.oid = i.indrelid
    JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
    CROSS JOIN LATERAL unnest(i.indkey) WITH ORDINALITY AS keys(attnum, ordinality)
    JOIN pg_catalog.pg_attribute a ON a.attrelid = c.oid AND a.attnum = keys.attnum
    WHERE n.nspname = 'raw' AND i.indisprimary
      AND c.relname IN (SELECT table_name FROM esperado)
    GROUP BY c.relname, i.indisvalid, i.indisready
)
SELECT e.table_name, e.pk_column AS pk_esperada, o.pk_columns AS pk_observada,
       o.indisvalid, o.indisready,
       coalesce(o.pk_columns::text[] = ARRAY[e.pk_column] AND o.indisvalid AND o.indisready, false)
         AS pk_compativel
FROM esperado e LEFT JOIN observado o USING (table_name)
WHERE current_database() = 'Atendimento'
  AND current_setting('transaction_read_only') = 'on'
ORDER BY e.table_name;

-- Índices existentes: somente definição/catalogo, sem EXPLAIN ANALYZE.
SELECT c.relname AS table_name, ic.relname AS index_name, am.amname AS metodo,
       i.indisprimary, i.indisunique, i.indisvalid, i.indisready,
       pg_catalog.pg_get_indexdef(i.indexrelid) AS definicao
FROM pg_catalog.pg_index i
JOIN pg_catalog.pg_class c ON c.oid = i.indrelid
JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
JOIN pg_catalog.pg_class ic ON ic.oid = i.indexrelid
JOIN pg_catalog.pg_am am ON am.oid = ic.relam
WHERE n.nspname = 'raw'
  AND c.relname IN ('magento_sales_order', 'magento_sales_order_item',
                    'ativo_pedido', 'ativo_pedido_evento', '_etl_runs')
  AND current_database() = 'Atendimento'
  AND current_setting('transaction_read_only') = 'on'
ORDER BY c.relname, ic.relname;

COMMIT;
