-- Grão: uma linha por evento_id. Datas textuais preservam datas zero.
CREATE OR REPLACE VIEW staging.ativo_evento AS
SELECT id_evento AS evento_id,
       NULLIF(BTRIM(id_campanha_salesforce), '') AS campanha_salesforce_id,
       NULLIF(BTRIM(ds_evento), '') AS evento_nome,
       dt_evento AS data_evento,
       NULLIF(BTRIM(hr_evento), '') AS hora_evento,
       id_pais_origem AS pais_origem_id,
       data_update, dt_modificacao AS data_modificacao,
       _source AS origem, _extracted_at AS extraido_em, _batch_id AS batch_id
FROM raw.ativo_evento;
