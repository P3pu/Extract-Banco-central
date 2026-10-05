-- Grão: uma linha por pais_id.
CREATE OR REPLACE VIEW staging.ativo_pais AS
SELECT id_pais AS pais_id,
       NULLIF(BTRIM(ds_pais), '') AS pais,
       ds_pais_en AS pais_en, ds_pais_es AS pais_es,
       ds_sigla AS sigla, id_continente AS continente_id,
       latitude, longitude,
       id_situacao_cadastro AS situacao_cadastro_id,
       _source AS origem, _extracted_at AS extraido_em, _batch_id AS batch_id
FROM raw.ativo_pais;
