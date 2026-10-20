-- C2.1 / Naruto: somente cabeçalhos por PK. Não requer CORE.
-- Executar apenas após autorização; não exportar resultados com PII.
BEGIN READ ONLY;
SET LOCAL statement_timeout = '5s';
SET LOCAL lock_timeout = '500ms';
SELECT current_database() AS banco, current_setting('transaction_read_only') AS modo,
       1 / CASE WHEN current_database() = 'Atendimento'
                     AND current_setting('transaction_read_only') = 'on'
                THEN 1 ELSE 0 END AS destino_validado;

WITH esperado(pedido_id, liquido, residual) AS (VALUES
    (166688::BIGINT, 59.0000::NUMERIC, 14.2100::NUMERIC),
    (1673612, 159.8400, 19.9800),
    (1673646, 125.0128, 26.0000),
    (1673884, 119.9200, 14.9900)
), observado AS (
    SELECT e.pedido_id, e.liquido AS liquido_esperado,
           e.residual AS residual_esperado,
           p.pedido_id IS NOT NULL AS encontrado,
           p.subtotal AS bruto_pedido, p.desconto AS desconto_cabecalho,
           CASE WHEN p.subtotal IS NOT NULL AND p.desconto IS NOT NULL
                THEN p.subtotal + p.desconto END AS liquido_observado,
           p.valor_total AS total_cobrado, p.frete, p.imposto,
           CASE WHEN p.valor_total IS NOT NULL AND p.subtotal IS NOT NULL
                     AND p.desconto IS NOT NULL
                THEN p.valor_total - (p.subtotal + p.desconto) END AS residual_observado,
           p.estado_pedido AS state_origem, p.status_pedido AS status_origem,
           LOWER(BTRIM(p.estado_pedido)) AS state_normalizado,
           LOWER(BTRIM(p.status_pedido)) AS status_normalizado
    FROM esperado e
    LEFT JOIN staging.magento_pedido p ON p.pedido_id = e.pedido_id
)
SELECT pedido_id, encontrado, bruto_pedido, desconto_cabecalho,
       liquido_esperado, liquido_observado,
       liquido_observado - liquido_esperado AS diferenca_liquido,
       total_cobrado, frete, imposto,
       residual_esperado, residual_observado,
       residual_observado - residual_esperado AS diferenca_residual,
       state_origem, status_origem,
       CASE
         WHEN state_normalizado = 'canceled' OR status_normalizado = 'canceled'
           THEN 'CANCELADO'
         WHEN state_normalizado IN ('processing','approved','complete')
          AND status_normalizado IN ('processing','approved','complete')
           THEN 'CONFIRMADO'
         WHEN state_normalizado = 'new' AND status_normalizado = 'new'
           THEN 'NOVO'
         WHEN state_normalizado IN ('new','pending')
          AND status_normalizado IN ('new','pending')
           THEN 'PENDENTE'
         ELSE 'INDETERMINADO'
       END AS status_candidato,
       CASE WHEN NOT encontrado THEN 'NAO_COBERTO'
            WHEN liquido_observado IS NULL OR residual_observado IS NULL
              THEN 'INDETERMINADO'
            WHEN ABS(liquido_observado - liquido_esperado) > 0.0001
              OR ABS(residual_observado - residual_esperado) > 0.0001
              THEN 'DIVERGENTE'
            ELSE 'APROVADO' END AS resultado_financeiro
FROM observado ORDER BY pedido_id;
-- residual_observado NÃO é sinônimo de taxa de serviço.
COMMIT;
