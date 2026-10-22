-- Faixa por ID da inscrição, não por pedido: inclui pedido_id NULL e órfãos.
-- Os JOINs são N:1; o executor verifica unicidade da STAGING antes do UPSERT.
WITH fonte AS (
    SELECT 'ativo'::text origem, i.inscricao_id::bigint inscricao_id_origem,
           i.pedido_id::bigint pedido_id_origem, fp.pedido_key,
           i.evento_id::bigint evento_id_origem, em.evento_key,
           CASE WHEN i.usuario_id IS NOT NULL AND i.usuario_balcao_id IS NOT NULL
                THEN NULL::bigint
                ELSE COALESCE(i.usuario_id,i.usuario_balcao_id)::bigint END
                participante_id_origem,
           CASE WHEN i.usuario_id IS NOT NULL AND i.usuario_balcao_id IS NOT NULL
                THEN NULL::text
                WHEN i.usuario_id IS NOT NULL THEN 'Usuario'
                WHEN i.usuario_balcao_id IS NOT NULL THEN 'UsuarioBalcao' END
                participante_namespace_origem,
           combo.combo_key,
           core.try_date(i.data_evento) data_evento,
           i.data_evento::text data_evento_original,
           i.campanha_salesforce_id::text sku_evento_origem,
           NULL::text sku_inscricao_magento,
           i.modalidade_id::text modalidade_id_origem,
           i.modalidade::text modalidade_origem,
           i.categoria_id::text categoria_id_origem,
           i.categoria::text categoria_nome_origem,
           i.tamanho_camiseta_id::text tamanho_id_origem,
           i.tamanho_camiseta::text tamanho_origem,
           i.status_pedido::text status_pedido_origem,
           i.status_detalhado_id::integer status_individual_codigo,
           i.preco::numeric(20,4) valor_bruto_inscricao,
           i.desconto_individual::text desconto_individual_original,
           i.taxa::numeric(20,4) taxa_servico_ativo,
           de.flag_evento_teste,
           (fp.pedido_key IS NULL) flag_pedido_nao_encontrado,
           (em.evento_key IS NULL) flag_evento_nao_mapeado,
           i.batch_id batch_id_origem
    FROM staging.ativo_inscricao i
    LEFT JOIN core.fato_pedido fp
      ON fp.origem='ativo' AND fp.pedido_id_origem=i.pedido_id
    LEFT JOIN core.evento_source_map em
      ON em.origem='ativo' AND em.evento_id_origem=i.evento_id
    LEFT JOIN core.dim_evento de ON de.evento_key=em.evento_key
    LEFT JOIN staging.ativo_pedido p ON p.pedido_id=i.pedido_id
    LEFT JOIN core.dim_combo combo
      ON combo.origem='ativo' AND combo.combo_id_origem=p.combo_id::text
    WHERE i.inscricao_id BETWEEN %(id_min)s AND %(id_max)s
    UNION ALL
    SELECT 'magento',i.inscricao_id::bigint,i.pedido_id::bigint,fp.pedido_key,
           i.evento_id::bigint,em.evento_key,NULL::bigint,NULL::text,
           NULL::bigint,i.data_evento::date,i.data_evento::text,
           i.evento_sku::text,i.sku_inscricao::text,
           NULL::text,i.modalidade::text,i.categoria_origem::text,NULL::text,
           NULL::text,i.tamanho::text,i.status_pedido::text,NULL::integer,
           i.valor_bruto::numeric(20,4),NULL::text,NULL::numeric(20,4),
           de.flag_evento_teste,
           (fp.pedido_key IS NULL),(em.evento_key IS NULL),i.batch_id
    FROM staging.magento_inscricao i
    LEFT JOIN core.fato_pedido fp
      ON fp.origem='magento' AND fp.pedido_id_origem=i.pedido_id
    LEFT JOIN core.evento_source_map em
      ON em.origem='magento' AND em.evento_id_origem=i.evento_id
    LEFT JOIN core.dim_evento de ON de.evento_key=em.evento_key
    WHERE i.inscricao_id BETWEEN %(id_min)s AND %(id_max)s
), pronta AS (
    SELECT f.*,
           md5(ROW(f.origem,f.inscricao_id_origem,f.pedido_id_origem,
                   f.pedido_key,f.evento_id_origem,f.evento_key,
                   f.participante_id_origem,f.participante_namespace_origem,
                   f.combo_key,f.data_evento,f.data_evento_original,
                   f.sku_evento_origem,f.sku_inscricao_magento,
                   f.modalidade_id_origem,f.modalidade_origem,
                   f.categoria_id_origem,f.categoria_nome_origem,
                   f.tamanho_id_origem,f.tamanho_origem,
                   f.status_pedido_origem,f.status_individual_codigo,
                   f.valor_bruto_inscricao,f.desconto_individual_original,
                   f.taxa_servico_ativo,f.flag_evento_teste,
                   f.flag_pedido_nao_encontrado,
                   f.flag_evento_nao_mapeado)::text) hash_novo
    FROM fonte f
)
INSERT INTO core.fato_inscricao
    (origem,inscricao_id_origem,pedido_id_origem,pedido_key,
     evento_id_origem,evento_key,participante_id_origem,
     participante_namespace_origem,combo_key,data_evento,
     data_evento_original,sku_evento_origem,sku_inscricao_magento,
     modalidade_id_origem,modalidade_origem,categoria_id_origem,
     categoria_nome_origem,tamanho_id_origem,tamanho_origem,
     status_pedido_origem,status_individual_codigo,valor_bruto_inscricao,
     desconto_individual_original,taxa_servico_ativo,flag_evento_teste,
     flag_pedido_nao_encontrado,flag_evento_nao_mapeado,
     batch_id_origem,conteudo_hash)
SELECT origem,inscricao_id_origem,pedido_id_origem,pedido_key,
       evento_id_origem,evento_key,participante_id_origem,
       participante_namespace_origem,combo_key,data_evento,
       data_evento_original,sku_evento_origem,sku_inscricao_magento,
       modalidade_id_origem,modalidade_origem,categoria_id_origem,
       categoria_nome_origem,tamanho_id_origem,tamanho_origem,
       status_pedido_origem,status_individual_codigo,valor_bruto_inscricao,
       desconto_individual_original,taxa_servico_ativo,flag_evento_teste,
       flag_pedido_nao_encontrado,flag_evento_nao_mapeado,
       batch_id_origem,hash_novo
FROM pronta
ON CONFLICT (origem,inscricao_id_origem) DO UPDATE SET
    pedido_id_origem=EXCLUDED.pedido_id_origem,
    pedido_key=EXCLUDED.pedido_key,
    evento_id_origem=EXCLUDED.evento_id_origem,
    evento_key=EXCLUDED.evento_key,
    participante_id_origem=EXCLUDED.participante_id_origem,
    participante_namespace_origem=EXCLUDED.participante_namespace_origem,
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
    estado_derivacao='PENDENTE',
    batch_id_origem=EXCLUDED.batch_id_origem,
    conteudo_hash=EXCLUDED.conteudo_hash,
    atualizado_core_em=clock_timestamp()
WHERE core.fato_inscricao.conteudo_hash IS DISTINCT FROM EXCLUDED.conteudo_hash;
