-- Grão: uma linha por produto_id. Candidato via link é o evento_pai_id
-- válido do produto vizinho; não se infere que qualquer produto ligado seja evento.
CREATE OR REPLACE VIEW staging.magento_produto_evento_mapeamento AS
WITH vizinhos AS (
    SELECT product_id AS produto_id, linked_product_id AS vizinho_id
    FROM raw.magento_product_link
    UNION ALL
    SELECT linked_product_id AS produto_id, product_id AS vizinho_id
    FROM raw.magento_product_link
), candidatos AS (
    SELECT v.produto_id, n.evento_pai_id AS candidato_id
    FROM vizinhos v
    JOIN staging.magento_produto n ON n.produto_id = v.vizinho_id
    JOIN raw.magento_product e ON e.entity_id = n.evento_pai_id
), links AS (
    SELECT produto_id, COUNT(DISTINCT candidato_id) AS qtd_eventos_via_link,
           MIN(candidato_id) AS candidato_unico_id
    FROM candidatos GROUP BY produto_id
)
SELECT p.produto_id, p.evento_pai_id AS evento_direto_id,
       CASE WHEN COALESCE(l.qtd_eventos_via_link, 0) = 1
            THEN l.candidato_unico_id END AS evento_via_link_id,
       COALESCE(l.qtd_eventos_via_link, 0) AS qtd_eventos_via_link,
       CASE WHEN direto.entity_id IS NOT NULL THEN p.evento_pai_id
            WHEN l.qtd_eventos_via_link = 1 THEN l.candidato_unico_id END AS evento_id,
       CASE WHEN direto.entity_id IS NOT NULL THEN 'event_rel_pai'
            WHEN l.qtd_eventos_via_link = 1 THEN 'product_link'
            WHEN l.qtd_eventos_via_link > 1 THEN 'ambiguo'
            ELSE 'nao_mapeado' END AS metodo_mapeamento
FROM staging.magento_produto p
LEFT JOIN raw.magento_product direto ON direto.entity_id = p.evento_pai_id
LEFT JOIN links l ON l.produto_id = p.produto_id;
