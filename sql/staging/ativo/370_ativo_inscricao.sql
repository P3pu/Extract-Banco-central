-- Grão: uma linha por id_pedido_evento. Todas as relações são N:1 pela PK.
-- Não juntar pagamentos, transações, produtos ou endereços (1:N).
CREATE OR REPLACE VIEW staging.ativo_inscricao AS
SELECT
    i.id_pedido_evento AS inscricao_id,
    i.id_pedido AS pedido_id, p.pedido_id IS NOT NULL AS pedido_mapeado,
    i.id_evento AS evento_id, e.evento_nome, e.data_evento,
    e.evento_id IS NOT NULL AS evento_mapeado,
    e.campanha_salesforce_id,
    i.id_modalidade AS modalidade_id, m.modalidade,
    m.modalidade_id IS NOT NULL AS modalidade_mapeada,
    i.id_categoria AS categoria_id, c.categoria,
    c.categoria_id IS NOT NULL AS categoria_mapeada,
    i.id_usuario AS usuario_id, i.id_usuario_balcao AS usuario_balcao_id,
    i.id_tamanho_camiseta AS tamanho_camiseta_id,
    t.tamanho_camiseta,
    t.tamanho_camiseta_id IS NOT NULL AS tamanho_camiseta_mapeado,
    i.id_status_detalhado AS status_detalhado_id,
    i.id_cupom_individual AS cupom_individual_id,
    i.nr_peito AS numero_peito,
    i.nr_preco AS preco, i.nr_taxa AS taxa,
    i.nr_desconto_individual AS desconto_individual,
    i.nr_protocolo_revezamento AS protocolo_revezamento,
    i.nr_ordem_revezamento AS ordem_revezamento,
    i.fl_capitao_revezamento AS capitao_revezamento,
    i.fl_assinante AS assinante, i.fl_amigo AS amigo,
    i.pos_id_evento AS pos_evento_id,
    i.pos_id_pedido AS pos_pedido_id,
    i.pos_id_pedido_evento AS pos_pedido_evento_id,
    NULLIF(BTRIM(i.ds_equipe), '') AS equipe,
    NULLIF(BTRIM(i.ds_nome_equipe_revezamento), '') AS nome_equipe_revezamento,
    NULLIF(BTRIM(i.ds_obs), '') AS observacao,
    NULLIF(BTRIM(i.nm_camiseta), '') AS nome_camiseta,
    i.nr_preco_nm_camiseta AS preco_nome_camiseta,
    i.nr_preco_foto_clube AS preco_foto_clube,
    i.nr_preco_personalizacao_medalha AS preco_personalizacao_medalha,
    i.dt_cadastro AS data_cadastro,
    p.status_id AS status_pedido_id, p.status AS status_pedido,
    p.data_pedido, p.local_inscricao_codigo,
    i._source AS origem, i._extracted_at AS extraido_em, i._batch_id AS batch_id
FROM raw.ativo_pedido_evento i
LEFT JOIN staging.ativo_pedido p ON p.pedido_id = i.id_pedido
LEFT JOIN staging.ativo_evento e ON e.evento_id = i.id_evento
LEFT JOIN staging.ativo_modalidade m ON m.modalidade_id = i.id_modalidade
LEFT JOIN staging.ativo_categoria c ON c.categoria_id = i.id_categoria
LEFT JOIN staging.ativo_tamanho_camiseta t
  ON t.tamanho_camiseta_id = i.id_tamanho_camiseta;
