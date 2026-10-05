-- Grão: uma linha por produto_id. ROW_NUMBER escolhe um valor por atributo,
-- preferindo store_id=0 e desempatando pelo menor store_id/maior value_id.
CREATE OR REPLACE VIEW staging.magento_produto AS
WITH varchar_ranked AS (
    SELECT entity_id, attribute_id, value,
           ROW_NUMBER() OVER (
               PARTITION BY entity_id, attribute_id
               ORDER BY CASE WHEN store_id = 0 THEN 0 ELSE 1 END,
                        store_id, value_id DESC
           ) AS rn
    FROM raw.magento_product_varchar
    WHERE attribute_id IN (73, 321)
), varchar_values AS (
    SELECT entity_id,
           MAX(value) FILTER (WHERE attribute_id = 73) AS nome_produto,
           MAX(value) FILTER (WHERE attribute_id = 321) AS evento_pai_id_bruto
    FROM varchar_ranked WHERE rn = 1 GROUP BY entity_id
), int_ranked AS (
    SELECT entity_id, attribute_id, value,
           ROW_NUMBER() OVER (
               PARTITION BY entity_id, attribute_id
               ORDER BY CASE WHEN store_id = 0 THEN 0 ELSE 1 END,
                        store_id, value_id DESC
           ) AS rn
    FROM raw.magento_product_int
    WHERE attribute_id IN (194, 206, 207)
), int_values AS (
    SELECT entity_id,
           MAX(value) FILTER (WHERE attribute_id = 194) AS event_combo_option_id,
           MAX(value) FILTER (WHERE attribute_id = 206) AS modalidade_option_id,
           MAX(value) FILTER (WHERE attribute_id = 207) AS tamanho_option_id
    FROM int_ranked WHERE rn = 1 GROUP BY entity_id
), datetime_ranked AS (
    SELECT entity_id, value,
           ROW_NUMBER() OVER (
               PARTITION BY entity_id
               ORDER BY CASE WHEN store_id = 0 THEN 0 ELSE 1 END,
                        store_id, value_id DESC
           ) AS rn
    FROM raw.magento_product_datetime
    WHERE attribute_id = 195
), datetime_values AS (
    SELECT entity_id, value AS data_evento FROM datetime_ranked WHERE rn = 1
)
SELECT
    p.entity_id AS produto_id, NULLIF(BTRIM(p.sku), '') AS sku,
    p.type_id AS tipo_produto, p.attribute_set_id AS conjunto_atributos_id,
    NULLIF(BTRIM(v.nome_produto), '') AS nome_produto,
    v.evento_pai_id_bruto,
    CASE WHEN BTRIM(v.evento_pai_id_bruto) ~ '^[0-9]+$'
         THEN CASE WHEN BTRIM(v.evento_pai_id_bruto)::NUMERIC <= 9223372036854775807
                   THEN BTRIM(v.evento_pai_id_bruto)::BIGINT END
    END AS evento_pai_id,
    d.data_evento, i.event_combo_option_id,
    i.modalidade_option_id, NULLIF(BTRIM(mod.label), '') AS modalidade,
    i.modalidade_option_id IS NULL OR mod.option_id IS NOT NULL AS modalidade_mapeada,
    i.tamanho_option_id, NULLIF(BTRIM(tam.label), '') AS tamanho,
    i.tamanho_option_id IS NULL OR tam.option_id IS NOT NULL AS tamanho_mapeado,
    p.created_at AS criado_em, p.updated_at AS atualizado_em,
    p._source AS origem, p._extracted_at AS extraido_em, p._batch_id AS batch_id
FROM raw.magento_product p
LEFT JOIN varchar_values v ON v.entity_id = p.entity_id
LEFT JOIN int_values i ON i.entity_id = p.entity_id
LEFT JOIN datetime_values d ON d.entity_id = p.entity_id
LEFT JOIN LATERAL (
    SELECT option_id, label FROM staging.magento_option_label
    WHERE option_id = i.modalidade_option_id
    ORDER BY value_id DESC LIMIT 1
) mod ON TRUE
LEFT JOIN LATERAL (
    SELECT option_id, label FROM staging.magento_option_label
    WHERE option_id = i.tamanho_option_id
    ORDER BY value_id DESC LIMIT 1
) tam ON TRUE;
