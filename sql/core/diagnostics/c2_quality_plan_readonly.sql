-- C2.1 / Naruto: apenas EXPLAIN, sem ANALYZE; consulta idêntica à de dados.
-- Não executar no Naruto antes de autorização. Revisar cada plano separadamente.
BEGIN READ ONLY;
SET LOCAL statement_timeout = '5s';
SET LOCAL lock_timeout = '500ms';
SET LOCAL c2.ativo_id_min = 'UNSET';
SET LOCAL c2.ativo_id_max = 'UNSET';
SELECT current_database() AS banco, current_setting('transaction_read_only') AS modo,
       1 / CASE WHEN current_database() = 'Atendimento'
                     AND current_setting('transaction_read_only') = 'on'
                     AND current_setting('c2.ativo_id_min') ~ '^[0-9]{1,18}$'
                     AND current_setting('c2.ativo_id_max') ~ '^[0-9]{1,18}$'
                THEN CASE WHEN current_setting('c2.ativo_id_min')::BIGINT > 0
                                AND current_setting('c2.ativo_id_max')::BIGINT
                                    >= current_setting('c2.ativo_id_min')::BIGINT
                                AND current_setting('c2.ativo_id_max')::BIGINT
                                    - current_setting('c2.ativo_id_min')::BIGINT < 1000
                          THEN 1 ELSE 0 END
                ELSE 0 END AS destino_e_intervalo_validados;

-- Plano 1: cardinalidade e mapeamento Magento.
EXPLAIN (FORMAT TEXT, COSTS TRUE)
WITH ids(pedido_id) AS (VALUES (166688::BIGINT),(1673612),(1673646),(1673884)),
base AS MATERIALIZED (
    SELECT inscricao_id, pedido_id, evento_nao_mapeado,
           cliente_ambiguo, modalidade_ambigua
    FROM staging.magento_inscricao
    WHERE pedido_id IN (166688,1673612,1673646,1673884)
)
SELECT ids.pedido_id, COUNT(b.inscricao_id) AS linhas_bundle,
       COUNT(DISTINCT b.inscricao_id) AS ids_bundle_distintos,
       COUNT(*) FILTER (WHERE b.evento_nao_mapeado) AS eventos_sem_mapa,
       COUNT(*) FILTER (WHERE b.cliente_ambiguo) AS clientes_ambiguos,
       COUNT(*) FILTER (WHERE b.modalidade_ambigua) AS modalidades_ambiguas,
       CASE WHEN COUNT(b.inscricao_id)=0 THEN 'NAO_COBERTO'
            WHEN COUNT(b.inscricao_id)<>COUNT(DISTINCT b.inscricao_id)
              THEN 'DIVERGENTE' ELSE 'APROVADO' END AS cardinalidade
FROM ids LEFT JOIN base b ON b.pedido_id=ids.pedido_id
GROUP BY ids.pedido_id ORDER BY ids.pedido_id;

-- Plano 2: sinais de classificação Magento e regras.
EXPLAIN (FORMAT TEXT, COSTS TRUE)
WITH ids(pedido_id) AS (VALUES (166688::BIGINT),(1673612),(1673646),(1673884)),
regras AS MATERIALIZED (
    SELECT pedido_id, regra_id, regra_id_valido, etiqueta
    FROM staging.magento_pedido_regra
    WHERE pedido_id IN (166688,1673612,1673646,1673884)
)
SELECT ids.pedido_id, p.pedido_id IS NOT NULL AS pedido_presente,
       p.cupom ~* '^GR' AS cupom_prefixo_grupos,
       COUNT(r.regra_id) AS regras_resolvidas,
       COUNT(*) FILTER (WHERE r.regra_id_valido IS FALSE)
         AS tokens_regra_invalidos,
       COUNT(*) FILTER (WHERE r.etiqueta ILIKE '%grupos%')
         AS etiquetas_grupos,
       COUNT(*) FILTER (WHERE r.etiqueta ~* '(cortesia|corttesia|corteisa)')
         AS etiquetas_cortesia,
       COUNT(*) FILTER (WHERE r.regra_id IS NOT NULL AND r.etiqueta IS NULL)
         AS regras_sem_etiqueta
FROM ids LEFT JOIN staging.magento_pedido p ON p.pedido_id=ids.pedido_id
LEFT JOIN regras r ON r.pedido_id=ids.pedido_id
GROUP BY ids.pedido_id,p.pedido_id,p.cupom ORDER BY ids.pedido_id;

-- Plano 3: sinais Ativo, cupons e status no intervalo.
EXPLAIN (FORMAT TEXT, COSTS TRUE)
WITH base AS MATERIALIZED (
    SELECT inscricao_id, pedido_id, pedido_mapeado, evento_mapeado,
           evento_id, categoria, cupom_individual_id, status_pedido_id,
           status_detalhado_id
    FROM staging.ativo_inscricao
    WHERE inscricao_id BETWEEN current_setting('c2.ativo_id_min')::BIGINT
                             AND current_setting('c2.ativo_id_max')::BIGINT
), sinais AS (
    SELECT b.*, c.cupom_id, c.cupom_desconto_id,
           c.codigo_cupom ~* '^GR' AS prefixo_grupos
    FROM base b LEFT JOIN staging.ativo_cupom c
      ON c.cupom_id=b.cupom_individual_id
)
SELECT COUNT(*) AS linhas_amostra,
       COUNT(DISTINCT inscricao_id) AS ids_distintos,
       COUNT(*) FILTER (WHERE NOT pedido_mapeado) AS orfas,
       COUNT(*) FILTER (WHERE NOT evento_mapeado) AS eventos_sem_mapa,
       COUNT(*) FILTER (WHERE evento_id=22054) AS evento_teste_22054,
       COUNT(*) FILTER (WHERE status_pedido_id=5
                           OR status_detalhado_id IN (5,6,7,8)) AS canceladas,
       COUNT(*) FILTER (WHERE status_detalhado_id=17) AS estorno_parcial,
       COUNT(*) FILTER (WHERE cupom_individual_id IS NOT NULL
                           AND cupom_id IS NULL) AS cupons_nao_encontrados,
       COUNT(*) FILTER (WHERE cupom_id IS NOT NULL
                           AND cupom_desconto_id IS NOT NULL)
         AS cupons_com_referencia_cabecalho_sem_classificacao,
       COUNT(*) FILTER (WHERE prefixo_grupos) AS prefixo_grupos,
       COUNT(*) FILTER (WHERE categoria ILIKE '%grupo%') AS categoria_grupos,
       COUNT(*) FILTER (WHERE categoria ILIKE '%cortesia%'
                           OR categoria ILIKE '%patrocinador%')
         AS categoria_cortesia
FROM sinais;

-- Plano 4: tentativas de pagamento Ativo por pedido da amostra.
EXPLAIN (FORMAT TEXT, COSTS TRUE)
WITH pedidos AS MATERIALIZED (
    SELECT DISTINCT pedido_id
    FROM staging.ativo_inscricao
    WHERE inscricao_id BETWEEN current_setting('c2.ativo_id_min')::BIGINT
                             AND current_setting('c2.ativo_id_max')::BIGINT
), pagamentos AS (
    SELECT p.pedido_id, p.pagamento_id, p.status_pagamento,
           NULLIF(BTRIM(p.data_pagamento), '') IS NOT NULL AS data_preenchida
    FROM staging.ativo_pagamento p
    JOIN pedidos i ON i.pedido_id=p.pedido_id
)
SELECT status_pagamento, COUNT(*) AS tentativas,
       COUNT(DISTINCT pedido_id) AS pedidos,
       COUNT(*) FILTER (WHERE data_preenchida) AS com_data,
       COUNT(*) - COUNT(DISTINCT pedido_id) AS tentativas_adicionais_no_status
FROM pagamentos GROUP BY status_pagamento ORDER BY status_pagamento;
COMMIT;
