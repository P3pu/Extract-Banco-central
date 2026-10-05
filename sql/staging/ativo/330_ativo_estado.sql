-- Grão: uma linha por id físico, não por id_estado. Sem JOIN geográfico.
CREATE OR REPLACE VIEW staging.ativo_estado AS
SELECT id AS estado_registro_id, id_estado AS estado_id, id_pais AS pais_id,
       NULLIF(BTRIM(ds_estado), '') AS estado,
       ds_estado_en AS estado_en, ds_sigla AS sigla,
       id_situacao_cadastro AS situacao_cadastro_id,
       _source AS origem, _extracted_at AS extraido_em, _batch_id AS batch_id
FROM raw.ativo_estado;
