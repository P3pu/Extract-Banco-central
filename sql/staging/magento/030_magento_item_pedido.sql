-- Grão: uma linha por item_id; inclui pais e filhos sem agregação.
CREATE OR REPLACE VIEW staging.magento_item_pedido AS
SELECT
    item_id, order_id AS pedido_id, parent_item_id AS item_pai_id,
    product_id AS produto_id,
    NULLIF(BTRIM(sku), '') AS sku,
    NULLIF(BTRIM(name), '') AS nome_item,
    NULLIF(BTRIM(product_type), '') AS tipo_produto,
    price AS preco, base_price AS preco_base,
    row_total AS valor_linha, base_row_total AS valor_linha_base,
    discount_amount AS desconto, base_discount_amount AS desconto_base,
    tax_amount AS imposto, base_tax_amount AS imposto_base,
    qty_ordered AS quantidade_pedida, qty_invoiced AS quantidade_faturada,
    qty_canceled AS quantidade_cancelada, qty_refunded AS quantidade_reembolsada,
    parent_item_id IS NOT NULL AS eh_item_filho,
    product_type = 'bundle' AS eh_bundle,
    additional_data, ext_order_item_id, ozone_customers,
    created_at AS criado_em, updated_at AS atualizado_em,
    _source AS origem, _extracted_at AS extraido_em, _batch_id AS batch_id
FROM raw.magento_sales_order_item;
