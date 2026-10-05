-- Grão: uma linha por modalidade_id.
CREATE OR REPLACE VIEW staging.ativo_modalidade AS
SELECT id_modalidade AS modalidade_id,
       NULLIF(BTRIM(nm_modalidade), '') AS modalidade,
       NULLIF(BTRIM(ds_horario), '') AS horario,
       nr_ordem AS ordem, data_update,
       _source AS origem, _extracted_at AS extraido_em, _batch_id AS batch_id
FROM raw.ativo_evento_modalidade;
