-- Grão: uma linha por cliente_id. Datas textuais preservam valores zero da RAW.
CREATE OR REPLACE VIEW staging.magento_cliente AS
SELECT entity_id AS cliente_id, group_id AS grupo_cliente_id,
       NULLIF(BTRIM(firstname), '') AS primeiro_nome,
       NULLIF(BTRIM(lastname), '') AS sobrenome,
       NULLIF(LOWER(BTRIM(email)), '') AS email,
       dob AS data_nascimento,
       NULLIF(BTRIM(taxvat), '') AS documento,
       gender AS genero_codigo,
       created_at AS criado_em, updated_at AS atualizado_em,
       _source AS origem, _extracted_at AS extraido_em, _batch_id AS batch_id
FROM raw.magento_customer;
