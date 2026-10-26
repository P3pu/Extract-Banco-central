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

-- Plano 1: financeiro/status Ativo com parsing, categoria e faixa validada.
EXPLAIN (FORMAT TEXT, COSTS TRUE)
WITH base AS (
    SELECT i.inscricao_id, i.pedido_id, i.pedido_mapeado,
           i.evento_id, i.evento_mapeado, i.categoria_id,
           i.preco, i.taxa, i.status_pedido_id,
           i.status_detalhado_id, c.valor_kit,
           i.desconto_individual IS NOT NULL AS desconto_preenchido,
           CASE WHEN NULLIF(BTRIM(i.desconto_individual), '')
                          ~ '^[+-]?[0-9]{1,16}([,.][0-9]{1,4})?$'
                THEN REPLACE(BTRIM(i.desconto_individual), ',', '.')::NUMERIC(20,4)
           END AS desconto_numero
    FROM staging.ativo_inscricao i
    LEFT JOIN staging.ativo_categoria c ON c.categoria_id = i.categoria_id
    WHERE i.inscricao_id BETWEEN current_setting('c2.ativo_id_min')::BIGINT
                             AND current_setting('c2.ativo_id_max')::BIGINT
)
SELECT inscricao_id, pedido_id, evento_id, categoria_id,
       preco AS bruto_inscricao, desconto_numero AS desconto_individual,
       valor_kit, taxa AS taxa_servico_separada,
       CASE WHEN preco IS NOT NULL AND desconto_numero IS NOT NULL
                      AND valor_kit IS NOT NULL
            THEN GREATEST(0::NUMERIC, preco - desconto_numero - valor_kit)
       END AS liquido_candidato,
       status_pedido_id, status_detalhado_id,
       NOT pedido_mapeado AS pedido_orfao,
       NOT evento_mapeado AS evento_sem_mapa,
       evento_id = 22054 AS evento_teste,
       CASE WHEN desconto_preenchido AND desconto_numero IS NULL
                 THEN 'DESCONTO_INVALIDO'
            WHEN preco IS NULL OR valor_kit IS NULL OR desconto_numero IS NULL
                 THEN 'FINANCEIRO_INDETERMINADO'
            ELSE NULL END AS alerta_financeiro,
       CASE WHEN status_pedido_id = 5 OR status_detalhado_id IN (5,6,7,8)
                 THEN 'CANCELADO'
            WHEN status_detalhado_id = 17 THEN 'INDETERMINADO_ESTORNO_PARCIAL'
            WHEN status_detalhado_id = 0 AND status_pedido_id = 2
                 AND evento_mapeado AND evento_id <> 22054
                 THEN 'CANDIDATO_CONFIRMADO'
            ELSE 'INDETERMINADO' END AS avaliacao_status
FROM base ORDER BY inscricao_id;
COMMIT;
