-- Grão: uma linha por pedido_id + token de regra distinto. Tokens inválidos
-- permanecem em regra_id_bruto com regra_id NULL para auditoria.
CREATE OR REPLACE VIEW staging.magento_pedido_regra AS
WITH tokens AS (
    SELECT p.pedido_id, BTRIM(t.token) AS regra_id_bruto
    FROM staging.magento_pedido p
    CROSS JOIN LATERAL regexp_split_to_table(p.regras_aplicadas_ids, ',') AS t(token)
    WHERE p.regras_aplicadas_ids IS NOT NULL
      AND NULLIF(BTRIM(t.token), '') IS NOT NULL
), ids AS (
    SELECT pedido_id, regra_id_bruto,
           CASE WHEN regra_id_bruto ~ '^[0-9]+$'
                THEN CASE WHEN regra_id_bruto::NUMERIC <= 9223372036854775807
                          THEN regra_id_bruto::BIGINT END END AS regra_id
    FROM tokens
), canon AS (
    SELECT DISTINCT ON (
        pedido_id, COALESCE(regra_id::TEXT, 'invalid:' || regra_id_bruto)
    ) pedido_id, regra_id_bruto, regra_id
    FROM ids
    ORDER BY pedido_id,
             COALESCE(regra_id::TEXT, 'invalid:' || regra_id_bruto),
             regra_id_bruto
), labels AS (
    SELECT DISTINCT ON (rule_id) rule_id, label, store_id
    FROM raw.magento_salesrule_label
    ORDER BY rule_id, CASE WHEN store_id = 0 THEN 0 ELSE 1 END,
             store_id, label_id DESC
)
SELECT i.pedido_id, i.regra_id, i.regra_id_bruto,
       i.regra_id IS NOT NULL AS regra_id_valido,
       NULLIF(BTRIM(r.name), '') AS regra_nome,
       NULLIF(BTRIM(r.description), '') AS regra_descricao,
       r.from_date AS valido_de, r.to_date AS valido_ate,
       r.is_active = 1 AS ativo,
       NULLIF(BTRIM(lbl.label), '') AS etiqueta,
       lbl.store_id AS etiqueta_store_id
FROM canon i
LEFT JOIN raw.magento_salesrule r ON r.rule_id = i.regra_id
LEFT JOIN labels lbl ON lbl.rule_id = i.regra_id;
