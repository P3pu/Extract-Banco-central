-- Grão: uma linha por bundle pai (inscricao_id = item_id).
-- Componentes são agregados ANTES do join, evitando multiplicação.
CREATE OR REPLACE VIEW staging.magento_inscricao AS
WITH componentes AS (
    SELECT inscricao_item_id,
           COUNT(*) AS qtd_componentes,
           COUNT(DISTINCT modalidade_option_id) AS qtd_modalidades_distintas,
           CASE WHEN COUNT(DISTINCT modalidade_option_id) = 1
                THEN MIN(modalidade) END AS modalidade,
           COUNT(DISTINCT tamanho_option_id) AS qtd_tamanhos_distintos,
           CASE WHEN COUNT(DISTINCT tamanho_option_id) = 1
                THEN MIN(tamanho) END AS tamanho
    FROM staging.magento_bundle_componente
    GROUP BY inscricao_item_id
)
SELECT pai.item_id AS inscricao_id, pai.pedido_id, ic.cliente_id,
       m.evento_id, e.evento_sku, e.evento_nome, e.data_evento,
       pai.produto_id, pai.sku AS sku_inscricao,
       produto.conjunto_atributos_id AS categoria_origem,
       c.modalidade, c.tamanho,
       pai.valor_linha AS valor_bruto, pai.desconto AS desconto_item,
       pedido.estado_pedido, pedido.status_pedido,
       pedido.cupom, pedido.criado_em AS data_pedido,
       ce.empresa_id, ce.empresa_nome,
       COALESCE(c.qtd_componentes, 0) AS qtd_componentes,
       COALESCE(c.qtd_modalidades_distintas, 0) AS qtd_modalidades_distintas,
       COALESCE(c.qtd_modalidades_distintas, 0) > 1 AS modalidade_ambigua,
       COALESCE(c.qtd_tamanhos_distintos, 0) AS qtd_tamanhos_distintos,
       COALESCE(ic.qtd_clientes_associados, 0) AS qtd_clientes_associados,
       COALESCE(ic.cliente_ambiguo, FALSE) AS cliente_ambiguo,
       COALESCE(m.metodo_mapeamento, 'nao_mapeado') AS metodo_mapeamento_evento,
       e.evento_id IS NULL AS evento_nao_mapeado,
       pai.origem, pai.extraido_em, pai.batch_id
FROM staging.magento_item_pedido pai
LEFT JOIN staging.magento_pedido pedido ON pedido.pedido_id = pai.pedido_id
LEFT JOIN staging.magento_item_cliente ic ON ic.item_id = pai.item_id
LEFT JOIN staging.magento_cliente_empresa ce ON ce.cliente_id = ic.cliente_id
LEFT JOIN staging.magento_produto produto ON produto.produto_id = pai.produto_id
LEFT JOIN staging.magento_produto_evento_mapeamento m ON m.produto_id = pai.produto_id
LEFT JOIN staging.magento_evento e ON e.evento_id = m.evento_id
LEFT JOIN componentes c ON c.inscricao_item_id = pai.item_id
WHERE pai.eh_bundle;
