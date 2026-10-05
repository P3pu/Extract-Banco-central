-- Grão: uma linha por cupom_id. A RAW inicial é historicamente seletiva.
CREATE OR REPLACE VIEW staging.ativo_cupom AS
SELECT id_cupom_desconto_item AS cupom_id,
       NULLIF(BTRIM(nr_cupom), '') AS codigo_cupom,
       fl_usado AS usado_codigo, ds_ip AS ip,
       dt_sistema AS data_sistema, dt_uso AS data_uso,
       id_cupom_desconto AS cupom_desconto_id,
       id_evento AS evento_id, fl_reserva AS reserva_codigo,
       _source AS origem, _extracted_at AS extraido_em, _batch_id AS batch_id
FROM raw.ativo_cupom_desconto_item;
