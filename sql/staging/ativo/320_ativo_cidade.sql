-- Grão: uma linha por id físico, não por id_cidade. Sem JOIN geográfico.
CREATE OR REPLACE VIEW staging.ativo_cidade AS
SELECT id AS cidade_registro_id, id_cidade AS cidade_id,
       id_estado AS estado_id, id_pais AS pais_id,
       NULLIF(BTRIM(ds_cidade), '') AS cidade,
       NULLIF(BTRIM(ds_estado), '') AS estado_texto,
       ds_cidade_en AS cidade_en, ds_cidade_es AS cidade_es,
       nr_cep AS cep, latitude, longitude, nr_ibge AS ibge_codigo,
       id_situacao_cadastro AS situacao_cadastro_id,
       id_pais_origem AS pais_origem_id, atualizado, status, ativo,
       _source AS origem, _extracted_at AS extraido_em, _batch_id AS batch_id
FROM raw.ativo_cidade;
