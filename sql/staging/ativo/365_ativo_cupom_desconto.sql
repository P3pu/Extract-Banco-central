-- Grão: uma linha por cupom_desconto_id (cabeçalho do cupom).
CREATE OR REPLACE VIEW staging.ativo_cupom_desconto AS
SELECT id_cupom_desconto AS cupom_desconto_id,
       NULLIF(BTRIM(en_cupom_classificacao), '') AS classificacao,
       _source AS origem, _extracted_at AS extraido_em, _batch_id AS batch_id
FROM raw.ativo_cupom_desconto;
