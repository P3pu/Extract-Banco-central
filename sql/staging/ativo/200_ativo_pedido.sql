-- Grão: uma linha por pedido_id; LEFT JOIN preserva status órfãos.
CREATE OR REPLACE VIEW staging.ativo_pedido AS
SELECT p.id_pedido AS pedido_id, p.id_pedido_status AS status_id,
       NULLIF(BTRIM(s.ds_status), '') AS status,
       p.id_combo AS combo_id,
       p.id_cupom_desconto_item AS cupom_desconto_item_id,
       NULLIF(BTRIM(p.ds_cod), '') AS codigo,
       p.dt_pedido AS data_pedido, p.dt_alteracao AS data_alteracao,
       p.fl_local_inscricao AS local_inscricao_codigo,
       p.fl_delivery, p.fl_mobile, p.fl_assinante, p.fl_evento_da_casa,
       p.nr_taxa AS taxa, p.nr_delivery AS delivery,
       p.nr_desconto AS desconto, p.tp_entregakit AS tipo_entrega_kit,
       NULLIF(BTRIM(p.nm_camiseta), '') AS nome_camiseta,
       NULLIF(BTRIM(p.ds_campo_apolo), '') AS campo_apolo,
       NULLIF(BTRIM(p.ds_obs), '') AS observacao,
       p._source AS origem, p._extracted_at AS extraido_em, p._batch_id AS batch_id,
       -- No fim: CREATE OR REPLACE VIEW só aceita colunas novas ao final.
       p.id_usuario AS comprador_usuario_id
FROM raw.ativo_pedido p
LEFT JOIN raw.ativo_pedido_status s ON s.id_pedido_status = p.id_pedido_status;
