-- Alertas de pedido sem texto livre; apenas regra e ID numérico.
WITH desejados AS (
    SELECT 'magento'::text origem,'pedido'::text entidade,
           p.pedido_id::bigint identificador_origem,
           core.magento_status_alerta(p.estado_pedido,p.status_pedido)
              codigo_regra,
           'WARNING'::text severidade
    FROM staging.magento_pedido p
    WHERE p.pedido_id BETWEEN %(id_min)s AND %(id_max)s
      AND core.magento_status_alerta(p.estado_pedido,p.status_pedido) IS NOT NULL
    UNION ALL
    SELECT 'ativo','pedido',p.pedido_id,'DATA_INVALIDA','WARNING'
    FROM staging.ativo_pedido p
    WHERE p.pedido_id BETWEEN %(id_min)s AND %(id_max)s
      AND p.data_pedido IS NOT NULL
      AND core.try_timestamp(p.data_pedido) IS NULL
), encerrados AS (
    UPDATE core.core_alerta_qualidade a SET ativo=false,
        resolvido_em=clock_timestamp()
    WHERE a.entidade='pedido' AND a.ativo
      AND a.codigo_regra IN ('STATUS_CONTRADITORIO','STATUS_ESPECIAL',
                             'DATA_INVALIDA')
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
