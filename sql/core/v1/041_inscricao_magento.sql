-- Derivação por bundle pai. Filhos e regras são pré-agregados; nunca geram
-- novas inscrições. O cabeçalho permanece a fonte financeira no grão pedido.
WITH filhos AS (
    SELECT c.inscricao_item_id,
           SUM(c.desconto) FILTER (WHERE c.desconto IS NOT NULL) desconto,
           COUNT(c.desconto) qtd_descontos,
           SUM(c.valor_linha) FILTER (WHERE c.valor_linha IS NOT NULL) bruto
    FROM staging.magento_bundle_componente c
    WHERE c.inscricao_item_id BETWEEN %(id_min)s AND %(id_max)s
    GROUP BY c.inscricao_item_id
), regras AS (
    SELECT r.pedido_id,
           BOOL_OR(COALESCE(r.etiqueta,'') ~* 'grupos?') grupos,
           BOOL_OR(COALESCE(r.etiqueta,'') ~* 'cortesia|corttesia|corteisa') cortesia
    FROM staging.magento_pedido_regra r
    WHERE r.pedido_id IN (
        SELECT DISTINCT pedido_id FROM staging.magento_inscricao
        WHERE inscricao_id BETWEEN %(id_min)s AND %(id_max)s
    )
    GROUP BY r.pedido_id
), base AS (
    SELECT f.inscricao_key, f.conteudo_hash, f.flag_evento_teste,
           f.flag_evento_nao_mapeado, f.flag_pedido_nao_encontrado,
           f.data_evento, i.pedido_id, i.inscricao_id,
           i.valor_bruto, i.desconto_item, i.cupom,
           i.estado_pedido, i.status_pedido,
           pai.quantidade_pedida, pai.quantidade_cancelada,
           pai.quantidade_reembolsada, pai.valor_linha,
           COALESCE(filhos.desconto,0) desconto_filhos,
           COALESCE(filhos.qtd_descontos,0) qtd_descontos_filhos,
           filhos.bruto bruto_filhos,
           COALESCE(regras.grupos,false) etiqueta_grupos,
           COALESCE(regras.cortesia,false) etiqueta_cortesia,
           p.desconto desconto_cabecalho,
           p.subtotal subtotal_cabecalho,
           p.valor_total total_cabecalho,
           core.magento_status_corporativo(i.estado_pedido,i.status_pedido)
             status_analitico
    FROM core.fato_inscricao f
    JOIN staging.magento_inscricao i ON i.inscricao_id=f.inscricao_id_origem
    JOIN staging.magento_item_pedido pai ON pai.item_id=i.inscricao_id
      AND pai.item_id BETWEEN %(id_min)s AND %(id_max)s
    LEFT JOIN filhos ON filhos.inscricao_item_id=i.inscricao_id
    LEFT JOIN regras ON regras.pedido_id=i.pedido_id
    LEFT JOIN staging.magento_pedido p ON p.pedido_id=i.pedido_id
    WHERE f.origem='magento'
      AND f.inscricao_id_origem BETWEEN %(id_min)s AND %(id_max)s
), calculo AS (
    SELECT b.*,
           CASE WHEN qtd_descontos_filhos>0 AND desconto_filhos<>0
                     THEN desconto_filhos
                WHEN desconto_item IS NOT NULL THEN desconto_item
                WHEN desconto_cabecalho=0 THEN 0::numeric END desconto_atribuivel,
           CASE WHEN valor_linha IS NOT NULL AND valor_linha<>0
                     THEN valor_linha
                WHEN bruto_filhos IS NOT NULL AND bruto_filhos<>0
                     THEN bruto_filhos END bruto_atribuivel,
           (quantidade_pedida=1 AND COALESCE(quantidade_cancelada,0)=0
             AND COALESCE(quantidade_reembolsada,0)=0) qtd_segura,
           (quantidade_pedida IS NULL OR quantidade_pedida<>1
             OR COALESCE(quantidade_cancelada,0)>0
             OR COALESCE(quantidade_reembolsada,0)>0) qtd_ambigua,
           (COALESCE(cupom,'') ~* '^GR' OR etiqueta_grupos) sinal_grupos,
           (etiqueta_cortesia OR valor_bruto=0) sinal_cortesia
    FROM base b
), conciliacao AS (
    -- Comparação considera todos os bundles do pedido, não só o lote atual.
    SELECT p.pedido_id,
           SUM(CASE WHEN cf.desconto IS NOT NULL AND cf.desconto<>0
                         THEN cf.desconto ELSE COALESCE(pai.desconto,0) END)
                         desconto_itens,
           SUM(CASE WHEN pai.valor_linha IS NOT NULL
                         AND pai.valor_linha<>0 THEN pai.valor_linha
                    ELSE cf.bruto END) bruto_itens,
           COUNT(*) qtd_bundles,
           BOOL_AND(pai.desconto IS NOT NULL OR cf.desconto IS NOT NULL)
                         componentes_presentes
    FROM staging.magento_pedido p
    JOIN staging.magento_item_pedido pai
      ON pai.pedido_id=p.pedido_id AND pai.eh_bundle
    LEFT JOIN LATERAL (
        SELECT SUM(c.desconto) desconto,SUM(c.valor_linha) bruto
        FROM staging.magento_bundle_componente c
        WHERE c.inscricao_item_id=pai.item_id
    ) cf ON true
    WHERE p.pedido_id IN (SELECT DISTINCT pedido_id FROM base)
    GROUP BY p.pedido_id
), final AS (
    SELECT c.*,
           (c.desconto_cabecalho IS NOT NULL AND co.componentes_presentes
             AND c.subtotal_cabecalho IS NOT NULL
             AND ABS(ABS(c.desconto_cabecalho)-co.desconto_itens)<=0.0001
             AND ABS(c.subtotal_cabecalho-co.bruto_itens)<=0.0001)
             desconto_conciliado,
           (c.status_analitico='PENDENTE' OR c.status_analitico='NOVO')
             AND c.data_evento < %(as_of_date)s::date
             AND c.flag_evento_teste IS FALSE presuncao,
           md5(ROW(c.conteudo_hash,c.valor_bruto,c.desconto_item,c.cupom,
                   c.estado_pedido,c.status_pedido,c.quantidade_pedida,
                   c.quantidade_cancelada,c.quantidade_reembolsada,
                   c.valor_linha,c.desconto_filhos,c.bruto_filhos,
                   c.etiqueta_grupos,c.etiqueta_cortesia,
                   c.desconto_cabecalho,c.subtotal_cabecalho,
                   c.total_cabecalho,co.desconto_itens,co.bruto_itens,
                   co.componentes_presentes,c.flag_evento_teste,
                   c.data_evento,%(as_of_date)s::date,
                   'CORE_V1_20261022')::text) dep_hash
    FROM calculo c
    LEFT JOIN conciliacao co ON co.pedido_id=c.pedido_id
)
UPDATE core.fato_inscricao f SET
    flag_cancelado_inscricao=CASE WHEN d.status_analitico='CANCELADO' THEN true
        WHEN d.quantidade_pedida>0
         AND d.quantidade_cancelada>=d.quantidade_pedida THEN true
        WHEN d.quantidade_cancelada IS NOT NULL THEN false END,
    contabiliza_inscricao=CASE WHEN d.status_analitico='CANCELADO'
        OR (d.quantidade_pedida>0
            AND d.quantidade_cancelada>=d.quantidade_pedida) THEN false
        WHEN d.qtd_ambigua OR d.flag_evento_nao_mapeado
          OR d.flag_pedido_nao_encontrado
          OR d.flag_evento_teste IS DISTINCT FROM false
          OR d.status_analitico='INDETERMINADO' THEN NULL
        ELSE true END,
    contabiliza_bruto=CASE WHEN d.status_analitico='CANCELADO' THEN false
        WHEN d.qtd_segura AND d.bruto_atribuivel IS NOT NULL
          AND d.flag_evento_teste IS FALSE THEN true END,
    pagamento_confirmado=CASE WHEN d.status_analitico='CONFIRMADO' THEN true
        WHEN d.status_analitico IN ('NOVO','PENDENTE','CANCELADO') THEN false END,
    pagamento_presumido=CASE WHEN d.presuncao THEN true
        WHEN d.status_analitico IN ('NOVO','PENDENTE','CONFIRMADO','CANCELADO')
          THEN false END,
    pago_considerado=CASE WHEN d.status_analitico='CONFIRMADO'
        OR d.presuncao THEN true
        WHEN d.status_analitico IN ('NOVO','PENDENTE','CANCELADO') THEN false END,
    motivo_elegibilidade=CASE WHEN d.status_analitico='CANCELADO'
        THEN 'PEDIDO_CANCELADO'
        WHEN d.qtd_ambigua THEN 'QUANTIDADE_OU_REEMBOLSO_AMBIGUO'
        WHEN d.presuncao THEN 'PAGO_PRESUMIDO_EVENTO_REALIZADO'
        ELSE d.status_analitico END,
    motivo_status_analitico=CASE WHEN d.presuncao
        THEN 'PAGO_PRESUMIDO_EVENTO_REALIZADO' ELSE d.status_analitico END,
    status_pendente_validacao=(d.status_analitico='INDETERMINADO'
                              OR d.qtd_ambigua),
    classificacao_comercial=CASE WHEN d.sinal_grupos THEN 'GRUPOS'
        WHEN d.sinal_cortesia THEN 'CORTESIA' ELSE 'SITE' END,
    classificacao_venda=CASE WHEN d.sinal_grupos THEN 'Grupos'
        WHEN d.sinal_cortesia THEN 'Cortesia' ELSE 'Site' END,
    classificacao_incompleta=false,
    motivo_classificacao=CASE WHEN d.sinal_grupos THEN 'CUPOM_OU_ETIQUETA_GRUPOS'
        WHEN d.etiqueta_cortesia THEN 'ETIQUETA_CORTESIA'
        WHEN d.sinal_cortesia THEN 'BRUTO_ZERO' ELSE 'SEM_SINAL_ESPECIAL' END,
    regras_classificacao=jsonb_build_object(
        'cupom_gr',COALESCE(d.cupom ~* '^GR',false),
        'etiqueta_grupos',d.etiqueta_grupos,
        'etiqueta_cortesia',d.etiqueta_cortesia,
        'categoria_textual_disponivel',false),
    cupom_codigo_origem=d.cupom,
    desconto_filhos_magento=d.desconto_filhos,
    desconto_pai_magento=d.desconto_item,
    desconto_aplicado_inscricao=d.desconto_atribuivel,
    quantidade_pedida=d.quantidade_pedida,
    quantidade_cancelada=d.quantidade_cancelada,
    quantidade_reembolsada=d.quantidade_reembolsada,
    valor_liquido_itens=CASE WHEN d.bruto_atribuivel IS NOT NULL
                               AND d.desconto_atribuivel IS NOT NULL
        THEN d.bruto_atribuivel-d.desconto_atribuivel END,
    valor_liquido_inscricao=CASE WHEN d.desconto_conciliado
        AND d.qtd_segura AND d.bruto_atribuivel IS NOT NULL
        AND d.desconto_atribuivel IS NOT NULL
        THEN d.bruto_atribuivel-d.desconto_atribuivel END,
    liquido_individual_conciliado=(d.desconto_conciliado AND d.qtd_segura
       AND d.bruto_atribuivel IS NOT NULL),
    flag_excecao_financeira=(d.desconto_conciliado IS DISTINCT FROM true
       OR d.qtd_ambigua OR d.bruto_atribuivel IS NULL),
    estado_derivacao=CASE WHEN d.status_analitico='INDETERMINADO'
        OR d.qtd_ambigua OR d.desconto_conciliado IS DISTINCT FROM true
        OR d.flag_evento_nao_mapeado OR d.flag_pedido_nao_encontrado
        THEN 'PENDENTE' ELSE 'VALIDADO' END,
    derivado_de_hash=f.conteudo_hash,
    dependencias_hash_snapshot=d.dep_hash,
    derivado_de_dependencias_hash=d.dep_hash,
    versao_regras_derivacao='CORE_V1_20261022',
    derivado_em=%(as_of_date)s::date,
    data_referencia_pagamento=%(as_of_date)s::date,
    atualizado_core_em=clock_timestamp()
FROM final d
WHERE f.inscricao_key=d.inscricao_key
  AND (f.dependencias_hash_snapshot IS DISTINCT FROM d.dep_hash
       OR f.derivado_de_hash IS DISTINCT FROM f.conteudo_hash
       OR f.versao_regras_derivacao IS DISTINCT FROM 'CORE_V1_20261022');
