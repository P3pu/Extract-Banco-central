-- Grão: uma linha por endereco_id; não escolhe endereço principal.
CREATE OR REPLACE VIEW staging.magento_endereco_cliente AS
SELECT entity_id AS endereco_id, parent_id AS cliente_id,
       NULLIF(BTRIM(telephone), '') AS telefone,
       NULLIF(BTRIM(city), '') AS cidade,
       NULLIF(BTRIM(region), '') AS estado,
       region_id AS estado_id,
       NULLIF(BTRIM(street), '') AS endereco,
       NULLIF(BTRIM(postcode), '') AS cep,
       NULLIF(BTRIM(country_id), '') AS pais_codigo,
       created_at AS criado_em, updated_at AS atualizado_em,
       _source AS origem, _extracted_at AS extraido_em, _batch_id AS batch_id
FROM raw.magento_customer_address;
