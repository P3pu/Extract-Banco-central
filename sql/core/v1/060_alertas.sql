-- Sem texto livre, nomes, CPF, e-mail ou documento. Reprocessar apenas faixa.
WITH desejados AS (
    SELECT origem,'inscricao'::text entidade,
           inscricao_id_origem identificador_origem,
           'ORFAO_PEDIDO'::text codigo_regra,'WARNING'::text severidade
    FROM core.fato_inscricao
    WHERE inscricao_id_origem BETWEEN %(id_min)s AND %(id_max)s
      AND flag_pedido_nao_encontrado
    UNION ALL
    SELECT origem,'inscricao',inscricao_id_origem,'EVENTO_SEM_MAPA','WARNING'
    FROM core.fato_inscricao
    WHERE inscricao_id_origem BETWEEN %(id_min)s AND %(id_max)s
      AND flag_evento_nao_mapeado
    UNION ALL
    SELECT origem,'inscricao',inscricao_id_origem,'STATUS_ESPECIAL','WARNING'
    FROM core.fato_inscricao
    WHERE inscricao_id_origem BETWEEN %(id_min)s AND %(id_max)s
      AND status_pendente_validacao IS TRUE
    UNION ALL
    SELECT origem,'inscricao',inscricao_id_origem,'DATA_INVALIDA','WARNING'
    FROM core.fato_inscricao
    WHERE inscricao_id_origem BETWEEN %(id_min)s AND %(id_max)s
      AND data_evento_original IS NOT NULL AND data_evento IS NULL
    UNION ALL
    SELECT origem,'inscricao',inscricao_id_origem,'DESCONTO_INVALIDO','WARNING'
    FROM core.fato_inscricao
    WHERE origem='ativo'
      AND inscricao_id_origem BETWEEN %(id_min)s AND %(id_max)s
      AND desconto_individual_original IS NOT NULL
      AND desconto_individual_origem IS NULL
    UNION ALL
    SELECT origem,'inscricao',inscricao_id_origem,'DESCONTO_CABECALHO','WARNING'
    FROM core.fato_inscricao
    WHERE origem='magento'
      AND inscricao_id_origem BETWEEN %(id_min)s AND %(id_max)s
      AND flag_excecao_financeira IS TRUE
      AND liquido_individual_conciliado IS DISTINCT FROM true
    UNION ALL
    SELECT origem,'inscricao',inscricao_id_origem,'QTD_BUNDLE','WARNING'
    FROM core.fato_inscricao
    WHERE origem='magento'
      AND inscricao_id_origem BETWEEN %(id_min)s AND %(id_max)s
      AND quantidade_pedida IS DISTINCT FROM 1
    UNION ALL
    SELECT origem,'inscricao',inscricao_id_origem,'REEMBOLSO','WARNING'
    FROM core.fato_inscricao
    WHERE origem='magento'
      AND inscricao_id_origem BETWEEN %(id_min)s AND %(id_max)s
      AND quantidade_reembolsada>0
    UNION ALL
    SELECT origem,'inscricao',inscricao_id_origem,'CANCELAMENTO_PARCIAL','WARNING'
    FROM core.fato_inscricao
    WHERE origem='magento'
      AND inscricao_id_origem BETWEEN %(id_min)s AND %(id_max)s
      AND quantidade_cancelada>0
      AND quantidade_cancelada<quantidade_pedida
    UNION ALL
    SELECT origem,'inscricao',inscricao_id_origem,'CUPOM_HEADER_AUSENTE','WARNING'
    FROM core.fato_inscricao
    WHERE origem='ativo'
      AND inscricao_id_origem BETWEEN %(id_min)s AND %(id_max)s
      AND classificacao_incompleta IS TRUE
    UNION ALL
    SELECT origem,'inscricao',inscricao_id_origem,'COMBO_COMPOSICAO','INFO'
    FROM core.fato_inscricao
    WHERE origem='ativo'
      AND inscricao_id_origem BETWEEN %(id_min)s AND %(id_max)s
      AND combo_key IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM core.dim_combo c
                      WHERE c.combo_key=core.fato_inscricao.combo_key
                        AND c.flag_composicao_validada)
), encerrados AS (
    UPDATE core.core_alerta_qualidade a SET ativo=false,
        resolvido_em=clock_timestamp()
    WHERE a.entidade='inscricao' AND a.ativo
      AND a.codigo_regra IN ('ORFAO_PEDIDO','EVENTO_SEM_MAPA',
           'STATUS_ESPECIAL','DATA_INVALIDA','DESCONTO_INVALIDO',
           'DESCONTO_CABECALHO',
           'QTD_BUNDLE','REEMBOLSO','CANCELAMENTO_PARCIAL',
           'CUPOM_HEADER_AUSENTE','COMBO_COMPOSICAO')
      AND a.identificador_origem BETWEEN %(id_min)s AND %(id_max)s
      AND NOT EXISTS (SELECT 1 FROM desejados d
          WHERE d.origem=a.origem AND d.entidade=a.entidade
            AND d.identificador_origem=a.identificador_origem
            AND d.codigo_regra=a.codigo_regra)
    RETURNING a.alerta_key
)
INSERT INTO core.core_alerta_qualidade
    (origem,entidade,identificador_origem,codigo_regra,severidade)
SELECT origem,entidade,identificador_origem,codigo_regra,severidade
FROM desejados
WHERE NOT EXISTS (
    SELECT 1 FROM core.core_alerta_qualidade a
    WHERE a.ativo AND a.origem=desejados.origem
      AND a.entidade=desejados.entidade
      AND a.identificador_origem=desejados.identificador_origem
      AND a.codigo_regra=desejados.codigo_regra
);
