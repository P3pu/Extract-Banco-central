-- C2.1 / Naruto: somente EXPLAIN, sem ANALYZE. Avaliar custo/índices antes
-- de aprovar c2_quality_after_plan_readonly.sql para o MESMO intervalo.
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

EXPLAIN (FORMAT TEXT, COSTS TRUE)
SELECT i.pedido_id, i.inscricao_id, i.evento_nao_mapeado,
       i.cliente_ambiguo, i.modalidade_ambigua
FROM staging.magento_inscricao i
WHERE i.pedido_id IN (166688,1673612,1673646,1673884);

EXPLAIN (FORMAT TEXT, COSTS TRUE)
SELECT r.pedido_id, r.regra_id, r.etiqueta
FROM staging.magento_pedido_regra r
WHERE r.pedido_id IN (166688,1673612,1673646,1673884);

EXPLAIN (FORMAT TEXT, COSTS TRUE)
SELECT i.inscricao_id, i.cupom_individual_id, c.cupom_id
FROM staging.ativo_inscricao i
LEFT JOIN staging.ativo_cupom c ON c.cupom_id=i.cupom_individual_id
WHERE i.inscricao_id BETWEEN current_setting('c2.ativo_id_min')::BIGINT
                         AND current_setting('c2.ativo_id_max')::BIGINT;

EXPLAIN (FORMAT TEXT, COSTS TRUE)
SELECT p.pedido_id, p.pagamento_id, p.status_pagamento,
       NULLIF(BTRIM(p.data_pagamento), '') IS NOT NULL AS data_preenchida
FROM staging.ativo_pagamento p
JOIN (
    SELECT DISTINCT pedido_id FROM staging.ativo_inscricao
    WHERE inscricao_id BETWEEN current_setting('c2.ativo_id_min')::BIGINT
                             AND current_setting('c2.ativo_id_max')::BIGINT
) pedidos ON pedidos.pedido_id=p.pedido_id;
COMMIT;
