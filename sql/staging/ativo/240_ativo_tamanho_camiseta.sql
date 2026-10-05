-- Grão: uma linha por tamanho_camiseta_id. Campos conferidos na RAW.
CREATE OR REPLACE VIEW staging.ativo_tamanho_camiseta AS
SELECT id_tamanho_camiseta AS tamanho_camiseta_id,
       NULLIF(BTRIM(ds_tamanho), '') AS tamanho_camiseta,
       nr_peso AS peso, vl_valor AS valor,
       id_situacao_cadastro AS situacao_cadastro_id,
       disponivel_atleta, id_pais_origem AS pais_origem_id,
       _source AS origem, _extracted_at AS extraido_em, _batch_id AS batch_id
FROM raw.ativo_tamanho_camiseta;
