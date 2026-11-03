-- Grão: uma linha por item do cardápio (evento/categoria permitidos no combo).
CREATE OR REPLACE VIEW staging.ativo_combo_cardapio AS
SELECT id_combo_evento_categoria AS cardapio_id, id_combo AS combo_id,
       id_evento AS evento_id, NULLIF(BTRIM(ds_categoria), '') AS categoria,
       fl_obrigatorio AS obrigatorio_codigo,
       _source AS origem, _extracted_at AS extraido_em, _batch_id AS batch_id
FROM raw.ativo_combo_cardapio;
