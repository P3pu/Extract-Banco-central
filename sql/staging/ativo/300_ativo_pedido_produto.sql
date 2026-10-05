-- Grão: uma linha por pedido_produto_id; quantidade não expande linhas.
CREATE OR REPLACE VIEW staging.ativo_pedido_produto AS
SELECT p.id_pedido_produto AS pedido_produto_id,
       p.id_pedido AS pedido_id, p.id_produto AS produto_id,
       NULLIF(BTRIM(prod.ds_titulo), '') AS produto_nome,
       p.nr_preco AS preco, p.nr_quantidade AS quantidade,
       p._source AS origem, p._extracted_at AS extraido_em, p._batch_id AS batch_id
FROM raw.ativo_pedido_produto p
LEFT JOIN raw.ativo_produto prod ON prod.id_produto = p.id_produto;
