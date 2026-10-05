-- Grão: uma linha por endereco_id; não escolhe endereço principal.
CREATE OR REPLACE VIEW staging.ativo_endereco_pedido AS
SELECT id_pedido_endereco AS endereco_id,
       id_pedido AS pedido_id, id_pedido_evento AS pedido_evento_id,
       id_cidade AS cidade_id,
       NULLIF(BTRIM(ds_endereco), '') AS endereco,
       NULLIF(BTRIM(ds_num), '') AS numero,
       NULLIF(BTRIM(ds_complemento), '') AS complemento,
       NULLIF(BTRIM(ds_bairro), '') AS bairro,
       NULLIF(BTRIM(nr_cep), '') AS cep,
       dt_cadastro AS data_cadastro,
       _source AS origem, _extracted_at AS extraido_em, _batch_id AS batch_id
FROM raw.ativo_pedido_endereco;
