-- PROPOSTA FASE B v1. NÃO EXECUTAR. UPSERT CONSERVADOR DE INSCRIÇÃO.
-- :id_min/:id_max delimitam pedido_id. Executar apenas depois de 001/002/003
-- e de validar EXPLAIN/uniqueness dos dois SELECTs; sem backfill autorizado.
-- Não promove métricas financeiras, status especiais, pessoa ou classificação
-- incompleta. Esses campos ficam NULL e são tratados em passo separado após
-- aprovação das dependências. Preserva órfãos com pedido_key NULL.

BEGIN;
WITH fonte AS MATERIALIZED (
    SELECT 'ativo'::TEXT AS origem, i.inscricao_id::BIGINT AS inscricao_id_origem,
           i.pedido_id::BIGINT AS pedido_id_origem, fp.pedido_key,
           i.evento_id::BIGINT AS evento_id_origem, em.evento_key,
           i.usuario_id::TEXT AS participante_id_origem,
           combo.combo_key, core.try_date(i.data_evento) AS data_evento,
           i.data_evento AS data_evento_original,
           i.campanha_salesforce_id AS sku_evento_origem,
           NULL::TEXT AS sku_inscricao_magento,
           i.modalidade_id::TEXT AS modalidade_id_origem,
           i.modalidade AS modalidade_origem,
           i.categoria_id::TEXT AS categoria_id_origem,
           i.categoria AS categoria_nome_origem,
           i.tamanho_camiseta_id::TEXT AS tamanho_id_origem,
           i.tamanho_camiseta AS tamanho_origem,
           i.status_pedido AS status_pedido_origem,
           i.status_detalhado_id AS status_individual_codigo,
           i.preco::NUMERIC(20,4) AS valor_bruto_inscricao,
           i.desconto_individual AS desconto_individual_original,
           i.taxa::NUMERIC(20,4) AS taxa_servico_ativo,
           de.flag_evento_teste,
           fp.pedido_key IS NULL AS flag_pedido_nao_encontrado,
           em.evento_key IS NULL AS flag_evento_nao_mapeado,
           i.batch_id AS batch_id_origem
    FROM staging.ativo_inscricao i
    LEFT JOIN core.fato_pedido fp
      ON fp.origem='ativo' AND fp.pedido_id_origem=i.pedido_id
    LEFT JOIN core.evento_source_map em
      ON em.origem='ativo' AND em.evento_id_origem=i.evento_id
    LEFT JOIN core.dim_evento de ON de.evento_key=em.evento_key
    LEFT JOIN staging.ativo_pedido ap ON ap.pedido_id=i.pedido_id
    LEFT JOIN core.dim_combo combo
      ON combo.origem='ativo' AND combo.combo_id_origem=ap.combo_id::TEXT
    WHERE i.pedido_id BETWEEN :id_min AND :id_max
    UNION ALL
    SELECT 'magento', i.inscricao_id::BIGINT,
           i.pedido_id::BIGINT, fp.pedido_key,
           i.evento_id::BIGINT, em.evento_key,
           NULL::TEXT, NULL::BIGINT, i.data_evento::DATE,
           i.data_evento::TEXT, i.evento_sku, i.sku_inscricao,
           NULL::TEXT, i.modalidade,
           i.categoria_origem::TEXT, NULL::TEXT,
           NULL::TEXT, i.tamanho,
           i.status_pedido, NULL::INTEGER,
           i.valor_bruto::NUMERIC(20,4), NULL::TEXT, NULL::NUMERIC(20,4),
           de.flag_evento_teste,
           fp.pedido_key IS NULL, em.evento_key IS NULL,
           i.batch_id
    FROM staging.magento_inscricao i
    LEFT JOIN core.fato_pedido fp
      ON fp.origem='magento' AND fp.pedido_id_origem=i.pedido_id
    LEFT JOIN core.evento_source_map em
      ON em.origem='magento' AND em.evento_id_origem=i.evento_id
    LEFT JOIN core.dim_evento de ON de.evento_key=em.evento_key
    WHERE i.pedido_id BETWEEN :id_min AND :id_max
), pronta AS (
    SELECT f.*,
           md5(ROW(f.origem,f.inscricao_id_origem,f.pedido_id_origem,
                   f.pedido_key,f.evento_id_origem,f.evento_key,
                   f.participante_id_origem,f.sku_evento_origem,
                   f.sku_inscricao_magento,
                   f.combo_key,f.data_evento,f.data_evento_original,
                   f.modalidade_id_origem,f.modalidade_origem,
                   f.categoria_id_origem,f.categoria_nome_origem,
                   f.tamanho_id_origem,f.tamanho_origem,
                   f.status_pedido_origem,f.status_individual_codigo,
                   f.valor_bruto_inscricao,f.desconto_individual_original,
                   f.taxa_servico_ativo,f.flag_evento_teste,
                   f.flag_pedido_nao_encontrado,
                   f.flag_evento_nao_mapeado)::TEXT) AS hash_novo
    FROM fonte f
)
INSERT INTO core.fato_inscricao
    (origem,inscricao_id_origem,pedido_id_origem,pedido_key,
     evento_id_origem,evento_key,participante_id_origem,combo_key,
     data_evento,data_evento_original,sku_evento_origem,
     sku_inscricao_magento,modalidade_id_origem,modalidade_origem,
     categoria_id_origem,categoria_nome_origem,tamanho_id_origem,
     tamanho_origem,status_pedido_origem,status_individual_codigo,
     valor_bruto_inscricao,desconto_individual_original,taxa_servico_ativo,
     flag_evento_teste,flag_pedido_nao_encontrado,
     flag_evento_nao_mapeado,flag_excecao_financeira,
     batch_id_origem,conteudo_hash)
SELECT origem,inscricao_id_origem,pedido_id_origem,pedido_key,
       evento_id_origem,evento_key,participante_id_origem,combo_key,
       data_evento,data_evento_original,sku_evento_origem,
       sku_inscricao_magento,modalidade_id_origem,modalidade_origem,
       categoria_id_origem,categoria_nome_origem,tamanho_id_origem,
       tamanho_origem,status_pedido_origem,status_individual_codigo,
       valor_bruto_inscricao,desconto_individual_original,taxa_servico_ativo,
       flag_evento_teste,flag_pedido_nao_encontrado,
       flag_evento_nao_mapeado,TRUE,batch_id_origem,hash_novo
FROM pronta
ON CONFLICT (origem,inscricao_id_origem) DO UPDATE SET
    pedido_id_origem=EXCLUDED.pedido_id_origem,
    pedido_key=EXCLUDED.pedido_key,
    evento_id_origem=EXCLUDED.evento_id_origem,
    evento_key=EXCLUDED.evento_key,
    participante_id_origem=EXCLUDED.participante_id_origem,
    combo_key=EXCLUDED.combo_key,
    data_evento=EXCLUDED.data_evento,
    data_evento_original=EXCLUDED.data_evento_original,
    sku_evento_origem=EXCLUDED.sku_evento_origem,
    sku_inscricao_magento=EXCLUDED.sku_inscricao_magento,
    modalidade_id_origem=EXCLUDED.modalidade_id_origem,
    modalidade_origem=EXCLUDED.modalidade_origem,
    categoria_id_origem=EXCLUDED.categoria_id_origem,
    categoria_nome_origem=EXCLUDED.categoria_nome_origem,
    tamanho_id_origem=EXCLUDED.tamanho_id_origem,
    tamanho_origem=EXCLUDED.tamanho_origem,
    status_pedido_origem=EXCLUDED.status_pedido_origem,
    status_individual_codigo=EXCLUDED.status_individual_codigo,
    valor_bruto_inscricao=EXCLUDED.valor_bruto_inscricao,
    desconto_individual_original=EXCLUDED.desconto_individual_original,
    taxa_servico_ativo=EXCLUDED.taxa_servico_ativo,
    flag_evento_teste=EXCLUDED.flag_evento_teste,
    flag_pedido_nao_encontrado=EXCLUDED.flag_pedido_nao_encontrado,
    flag_evento_nao_mapeado=EXCLUDED.flag_evento_nao_mapeado,
    flag_excecao_financeira=TRUE,
    flag_cancelado_inscricao=NULL,
    contabiliza_inscricao=NULL,
    contabiliza_bruto=NULL,
    pagamento_confirmado=NULL,
    pagamento_presumido=NULL,
    pago_considerado=NULL,
    classificacao_venda=NULL,
    motivo_classificacao=NULL,
    desconto_aplicado_inscricao=NULL,
    valor_liquido_itens=NULL,
    valor_liquido_inscricao=NULL,
    liquido_individual_conciliado=NULL,
    batch_id_origem=EXCLUDED.batch_id_origem,
    conteudo_hash=EXCLUDED.conteudo_hash,
    atualizado_core_em=clock_timestamp()
WHERE core.fato_inscricao.conteudo_hash IS DISTINCT FROM EXCLUDED.conteudo_hash;
COMMIT;

-- A etapa de métrica/alerta permanece retida conforme 004. Não usar a
-- inscrição conservadora para faturamento enquanto flags/valores são NULL.
