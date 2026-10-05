-- Grão: uma linha por cliente_id de company_user; company é PK id.
CREATE OR REPLACE VIEW staging.magento_cliente_empresa AS
SELECT u.customer_id AS cliente_id, u.company_id AS empresa_id,
       NULLIF(BTRIM(c.name), '') AS empresa_nome,
       NULLIF(BTRIM(c.legal_name), '') AS razao_social,
       c.status AS empresa_status, u.status AS vinculo_status,
       u.is_root, u.company_group_id, u.company_role_id,
       u._source AS origem, u._extracted_at AS extraido_em, u._batch_id AS batch_id
FROM raw.magento_company_user u
LEFT JOIN raw.magento_company c ON c.id = u.company_id;
