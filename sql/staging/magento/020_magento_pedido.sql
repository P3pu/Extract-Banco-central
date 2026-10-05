-- Grão: uma linha por pedido_id (= raw.magento_sales_order.entity_id).
CREATE OR REPLACE VIEW staging.magento_pedido AS
SELECT
    entity_id AS pedido_id,
    NULLIF(BTRIM(increment_id), '') AS protocolo,
    customer_id AS cliente_id,
    NULLIF(BTRIM(state), '') AS estado_pedido,
    NULLIF(BTRIM(status), '') AS status_pedido,
    NULLIF(BTRIM(coupon_code), '') AS cupom,
    NULLIF(BTRIM(applied_rule_ids), '') AS regras_aplicadas_ids,
    subtotal, base_subtotal AS subtotal_base,
    discount_amount AS desconto, base_discount_amount AS desconto_base,
    shipping_amount AS frete, base_shipping_amount AS frete_base,
    tax_amount AS imposto, base_tax_amount AS imposto_base,
    grand_total AS valor_total, base_grand_total AS valor_total_base,
    total_item_count AS quantidade_itens,
    total_qty_ordered AS quantidade_total,
    created_at AS criado_em, updated_at AS atualizado_em,
    _source AS origem, _extracted_at AS extraido_em, _batch_id AS batch_id
FROM raw.magento_sales_order;
