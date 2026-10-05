-- Grão: uma linha por componente_item_id cujo pai é bundle.
CREATE OR REPLACE VIEW staging.magento_bundle_componente AS
SELECT filho.item_id AS componente_item_id,
       pai.item_id AS inscricao_item_id,
       filho.pedido_id, filho.produto_id, filho.sku, filho.nome_item,
       filho.preco, filho.valor_linha, filho.desconto,
       produto.modalidade_option_id, produto.modalidade,
       produto.tamanho_option_id, produto.tamanho,
       produto.evento_pai_id, produto.event_combo_option_id,
       filho.origem, filho.extraido_em, filho.batch_id
FROM staging.magento_item_pedido filho
JOIN staging.magento_item_pedido pai
  ON pai.item_id = filho.item_pai_id AND pai.eh_bundle
LEFT JOIN staging.magento_produto produto ON produto.produto_id = filho.produto_id;
