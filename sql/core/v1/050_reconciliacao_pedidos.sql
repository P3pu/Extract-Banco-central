-- Pedidos impactados pelas inscrições do lote; agregação antes do UPDATE.
WITH pedidos AS (
    SELECT DISTINCT origem,pedido_id_origem
    FROM core.fato_inscricao
    WHERE inscricao_id_origem BETWEEN %(id_min)s AND %(id_max)s
      AND pedido_id_origem IS NOT NULL
), magento_itens AS (
    SELECT pai.pedido_id,
           SUM(CASE WHEN COALESCE(filhos.desconto,0)<>0
                THEN filhos.desconto ELSE COALESCE(pai.desconto,0) END)
                desconto_itens,
           SUM(CASE WHEN pai.valor_linha IS NOT NULL
                         AND pai.valor_linha<>0 THEN pai.valor_linha
                    ELSE filhos.bruto END) bruto_itens,
           COUNT(*) qtd_bundles
    FROM staging.magento_item_pedido pai
    LEFT JOIN LATERAL (
        SELECT SUM(c.desconto) desconto,SUM(c.valor_linha) bruto
        FROM staging.magento_bundle_componente c
        WHERE c.inscricao_item_id=pai.item_id
    ) filhos ON true
    WHERE pai.eh_bundle
      AND pai.pedido_id IN (SELECT pedido_id_origem FROM pedidos
                            WHERE origem='magento')
    GROUP BY pai.pedido_id
), eventos AS (
    SELECT origem,pedido_id_origem,
           BOOL_OR(flag_evento_teste IS TRUE) tem_teste,
           BOOL_OR(flag_evento_teste IS FALSE) tem_real,
           BOOL_OR(data_evento < %(as_of_date)s::date) tem_passado,
           BOOL_OR(data_evento >= %(as_of_date)s::date) tem_futuro
    FROM core.fato_inscricao
    WHERE EXISTS (SELECT 1 FROM pedidos p
                  WHERE p.origem=core.fato_inscricao.origem
                    AND p.pedido_id_origem=core.fato_inscricao.pedido_id_origem)
    GROUP BY origem,pedido_id_origem
), ativo_valores AS (
    SELECT f.pedido_id_origem,
           COUNT(*) qtd_core,
           COUNT(*) FILTER (WHERE f.valor_bruto_inscricao IS NOT NULL)
              qtd_bruto,
           COUNT(*) FILTER (WHERE f.valor_liquido_inscricao IS NOT NULL)
              qtd_liquido,
           COUNT(*) FILTER (WHERE f.taxa_servico_ativo IS NOT NULL)
              qtd_taxa,
           COUNT(*) FILTER (WHERE f.contabiliza_inscricao IS NOT NULL)
              qtd_status,
           SUM(f.valor_bruto_inscricao) FILTER
              (WHERE f.contabiliza_inscricao IS TRUE) bruto,
           SUM(f.valor_liquido_inscricao) FILTER
              (WHERE f.contabiliza_inscricao IS TRUE) liquido,
           SUM(f.taxa_servico_ativo) FILTER
              (WHERE f.contabiliza_inscricao IS TRUE) taxa
    FROM core.fato_inscricao f
    WHERE f.origem='ativo'
      AND f.pedido_id_origem IN (SELECT pedido_id_origem FROM pedidos
                                 WHERE origem='ativo')
    GROUP BY f.pedido_id_origem
), ativo_cobertura AS (
    SELECT i.pedido_id,COUNT(*) qtd_staging
    FROM staging.ativo_inscricao i
    WHERE i.pedido_id IN (SELECT pedido_id_origem FROM pedidos
                          WHERE origem='ativo')
    GROUP BY i.pedido_id
)
UPDATE core.fato_pedido f SET
    desconto_itens_identificado=CASE WHEN f.origem='magento'
                                     THEN m.desconto_itens END,
    desconto_nao_atribuido=CASE WHEN f.origem='magento'
       AND f.desconto_pedido_origem IS NOT NULL
       AND m.desconto_itens IS NOT NULL
       THEN ABS(f.desconto_pedido_origem)-m.desconto_itens END,
    flag_evento_teste=e.tem_teste,
    flag_pedido_misto_teste=e.tem_teste AND e.tem_real,
    flag_pedido_misto_temporal=CASE WHEN f.origem='magento'
       THEN e.tem_passado AND e.tem_futuro END,
    flag_excecao_financeira=CASE WHEN f.origem='magento' THEN
        f.desconto_pedido_origem IS NULL OR m.desconto_itens IS NULL
        OR ABS(ABS(f.desconto_pedido_origem)-m.desconto_itens)>0.0001
        OR f.valor_bruto_pedido IS NULL OR m.bruto_itens IS NULL
        OR ABS(f.valor_bruto_pedido-m.bruto_itens)>0.0001
        OR (e.tem_teste AND e.tem_real)
      ELSE a.qtd_core IS DISTINCT FROM ac.qtd_staging
        OR a.qtd_bruto IS DISTINCT FROM a.qtd_core
        OR a.qtd_liquido IS DISTINCT FROM a.qtd_core
        OR a.qtd_status IS DISTINCT FROM a.qtd_core END,
    -- Ativo só consolida quando TODAS as inscrições do pedido estão na CORE.
    -- Totais comerciais excluem canceladas, mas taxa segue segregada.
    valor_bruto_pedido=CASE WHEN f.origem='ativo'
        AND a.qtd_core=ac.qtd_staging AND a.qtd_bruto=a.qtd_core
        AND a.qtd_status=a.qtd_core
        THEN a.bruto ELSE NULL END,
    valor_liquido_pedido=CASE WHEN f.origem='ativo'
        AND a.qtd_core=ac.qtd_staging AND a.qtd_liquido=a.qtd_core
        AND a.qtd_status=a.qtd_core
        THEN a.liquido ELSE NULL END,
    taxa_servico_total_ativo=CASE WHEN f.origem='ativo'
        AND a.qtd_core=ac.qtd_staging AND a.qtd_taxa=a.qtd_core
        AND a.qtd_status=a.qtd_core
        THEN a.taxa ELSE NULL END,
    atualizado_core_em=clock_timestamp()
FROM pedidos p
LEFT JOIN magento_itens m ON p.origem='magento'
                         AND m.pedido_id=p.pedido_id_origem
LEFT JOIN eventos e ON e.origem=p.origem
                   AND e.pedido_id_origem=p.pedido_id_origem
LEFT JOIN ativo_valores a ON p.origem='ativo'
                          AND a.pedido_id_origem=p.pedido_id_origem
LEFT JOIN ativo_cobertura ac ON p.origem='ativo'
                             AND ac.pedido_id=p.pedido_id_origem
WHERE f.origem=p.origem AND f.pedido_id_origem=p.pedido_id_origem;
