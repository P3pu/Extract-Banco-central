-- Grão: uma linha por evento_id existente e resolvido no mapeamento.
CREATE OR REPLACE VIEW staging.magento_evento AS
SELECT p.produto_id AS evento_id, p.sku AS evento_sku,
       p.nome_produto AS evento_nome, p.data_evento, p.tipo_produto,
       p.criado_em, p.atualizado_em,
       p.origem, p.extraido_em, p.batch_id
FROM staging.magento_produto p
JOIN (
    SELECT DISTINCT evento_id
    FROM staging.magento_produto_evento_mapeamento
    WHERE evento_id IS NOT NULL
) m ON m.evento_id = p.produto_id;
