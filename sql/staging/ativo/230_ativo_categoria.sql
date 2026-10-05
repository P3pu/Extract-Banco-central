-- Grão: uma linha por categoria_id; valor_kit não é desconto.
CREATE OR REPLACE VIEW staging.ativo_categoria AS
SELECT id_categoria AS categoria_id,
       NULLIF(BTRIM(ds_categoria), '') AS categoria,
       vl_kit AS valor_kit, data_update,
       _source AS origem, _extracted_at AS extraido_em, _batch_id AS batch_id
FROM raw.ativo_modalidade_categoria;
