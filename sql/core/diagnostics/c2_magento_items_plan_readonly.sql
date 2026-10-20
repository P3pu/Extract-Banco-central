-- C2.1 / Naruto: apenas EXPLAIN, sem ANALYZE; consulta idêntica à de dados.
-- Não executar no Naruto antes de autorização. Revisar cada plano separadamente.
BEGIN READ ONLY;
SET LOCAL statement_timeout = '5s';
SET LOCAL lock_timeout = '500ms';
SELECT current_database() AS banco, current_setting('transaction_read_only') AS modo,
       1 / CASE WHEN current_database() = 'Atendimento'
                     AND current_setting('transaction_read_only') = 'on'
                THEN 1 ELSE 0 END AS destino_validado;

-- Plano 1: reconciliação por bundle (CTEs, joins, agregações e quatro IDs).
EXPLAIN (FORMAT TEXT, COSTS TRUE)
WITH esperado(pedido_id, bundles, bruto_pais, desconto_filhos, desconto_pais) AS (VALUES
    (166688::BIGINT, 1::BIGINT, 59.0000::NUMERIC, 0::NUMERIC, 0::NUMERIC),
    (1673612, 2, NULL::NUMERIC, 39.9600, 0),
    (1673646, NULL::BIGINT, NULL::NUMERIC, 0, 0),
    (1673884, NULL::BIGINT, NULL::NUMERIC, 29.9800, 0)
), itens AS MATERIALIZED (
    SELECT pedido_id, item_id, item_pai_id, eh_bundle, valor_linha,
           desconto, quantidade_pedida, quantidade_cancelada,
           quantidade_reembolsada
    FROM staging.magento_item_pedido
    WHERE pedido_id IN (166688,1673612,1673646,1673884)
), pais AS (
    SELECT * FROM itens WHERE eh_bundle
), por_bundle AS (
    SELECT p.pedido_id, p.item_id AS bundle_item_id,
           p.valor_linha AS bruto_pai, p.desconto AS desconto_pai,
           p.quantidade_pedida, p.quantidade_cancelada,
           p.quantidade_reembolsada,
           COUNT(f.item_id) AS quantidade_filhos,
           COUNT(f.desconto) AS filhos_com_desconto_informado,
           SUM(f.desconto) AS desconto_filhos,
           COUNT(*) FILTER (WHERE f.item_id IS NOT NULL
                              AND (f.quantidade_cancelada > 0
                                   OR f.quantidade_reembolsada > 0)) AS filhos_com_estorno,
           CASE WHEN SUM(f.desconto) > 0 THEN SUM(f.desconto)
                WHEN p.desconto IS NOT NULL THEN p.desconto
                WHEN COUNT(f.item_id) > 0 AND COUNT(f.desconto) = COUNT(f.item_id)
                     THEN 0::NUMERIC END AS desconto_identificado
    FROM pais p LEFT JOIN itens f
      ON f.item_pai_id = p.item_id AND f.pedido_id = p.pedido_id
    GROUP BY p.pedido_id, p.item_id, p.valor_linha, p.desconto,
             p.quantidade_pedida, p.quantidade_cancelada,
             p.quantidade_reembolsada
), agregado AS (
    SELECT pedido_id, COUNT(*) AS bundles, SUM(bruto_pai) AS bruto_pais,
           SUM(desconto_filhos) AS desconto_filhos,
           SUM(desconto_pai) AS desconto_pais,
           SUM(desconto_identificado) AS desconto_itens_identificado,
           COUNT(*) FILTER (WHERE desconto_identificado IS NULL)
             AS bundles_desconto_indeterminado,
           COUNT(*) FILTER (WHERE quantidade_pedida IS DISTINCT FROM 1)
             AS bundles_quantidade_diferente_de_um,
           COUNT(*) FILTER (WHERE quantidade_cancelada > 0)
             AS bundles_cancelados,
           COUNT(*) FILTER (WHERE quantidade_reembolsada > 0)
             AS bundles_reembolsados,
           SUM(filhos_com_estorno) AS filhos_com_estorno
    FROM por_bundle GROUP BY pedido_id
), filhos_sem_pai AS (
    SELECT f.pedido_id, COUNT(*) AS quantidade
    FROM itens f LEFT JOIN pais p
      ON p.item_id=f.item_pai_id AND p.pedido_id=f.pedido_id
    WHERE f.item_pai_id IS NOT NULL AND p.item_id IS NULL
    GROUP BY f.pedido_id
)
SELECT e.pedido_id, e.bundles AS bundles_esperados, a.bundles,
       a.bundles - e.bundles AS diferenca_bundles,
       e.bruto_pais AS bruto_pais_esperado,
       a.bruto_pais, a.bruto_pais - e.bruto_pais AS diferenca_bruto_pais,
       p.subtotal AS bruto_cabecalho,
       a.bruto_pais - p.subtotal AS diferenca_bruto_pais_cabecalho,
       e.desconto_filhos AS desconto_filhos_esperado,
       a.desconto_filhos, a.desconto_filhos - e.desconto_filhos
         AS diferenca_desconto_filhos,
       e.desconto_pais AS desconto_pais_esperado,
       a.desconto_pais, a.desconto_pais - e.desconto_pais
         AS diferenca_desconto_pais,
       a.desconto_itens_identificado, a.bundles_desconto_indeterminado,
       CASE WHEN p.desconto IS NOT NULL
                 AND a.bundles_desconto_indeterminado = 0
            THEN ABS(p.desconto) - a.desconto_itens_identificado END
         AS desconto_nao_atribuido,
       COALESCE(f.quantidade,0) AS filhos_sem_pai_bundle,
       a.bundles_quantidade_diferente_de_um, a.bundles_cancelados,
       a.bundles_reembolsados, a.filhos_com_estorno,
       CASE WHEN a.pedido_id IS NULL THEN 'NAO_COBERTO'
            WHEN a.bundles_desconto_indeterminado > 0
              OR a.desconto_filhos IS NULL OR a.desconto_pais IS NULL
              THEN 'INDETERMINADO'
            WHEN COALESCE(f.quantidade,0) > 0 THEN 'INDETERMINADO'
            WHEN ABS(a.desconto_filhos - e.desconto_filhos) > 0.0001
              OR ABS(a.desconto_pais - e.desconto_pais) > 0.0001
              OR (e.bundles IS NOT NULL AND a.bundles <> e.bundles)
              OR (e.bruto_pais IS NOT NULL
                  AND ABS(a.bruto_pais - e.bruto_pais) > 0.0001)
              THEN 'DIVERGENTE'
            ELSE 'APROVADO' END AS resultado_itens
FROM esperado e
LEFT JOIN agregado a ON a.pedido_id = e.pedido_id
LEFT JOIN staging.magento_pedido p ON p.pedido_id = e.pedido_id
LEFT JOIN filhos_sem_pai f ON f.pedido_id=e.pedido_id
ORDER BY e.pedido_id;

-- Plano 2: seleção detalhada de itens dos mesmos quatro pedidos.
EXPLAIN (FORMAT TEXT, COSTS TRUE)
SELECT pedido_id, item_id, item_pai_id, eh_bundle, valor_linha,
       desconto, quantidade_pedida, quantidade_cancelada, quantidade_reembolsada
FROM staging.magento_item_pedido
WHERE pedido_id IN (166688,1673612,1673646,1673884)
ORDER BY pedido_id, item_pai_id NULLS FIRST, item_id;
COMMIT;
