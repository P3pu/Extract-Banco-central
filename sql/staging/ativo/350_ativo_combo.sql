-- Grão: uma linha por combo_id.
CREATE OR REPLACE VIEW staging.ativo_combo AS
SELECT id_combo AS combo_id,
       NULLIF(BTRIM(ds_titulo), '') AS combo_nome,
       _source AS origem, _extracted_at AS extraido_em, _batch_id AS batch_id
FROM raw.ativo_combo;
