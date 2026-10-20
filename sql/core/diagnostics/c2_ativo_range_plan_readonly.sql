-- C2.1 / Naruto: plano de um intervalo de no máximo 1.000 IDs de inscrição.
-- Substituir UNSET por limites aprovados antes de executar; não usar ID de pedido.
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
SELECT i.inscricao_id, i.pedido_id, i.evento_id, i.categoria_id,
       i.preco, i.desconto_individual, i.taxa,
       i.status_pedido_id, i.status_detalhado_id, c.valor_kit
FROM staging.ativo_inscricao i
LEFT JOIN staging.ativo_categoria c ON c.categoria_id = i.categoria_id
WHERE i.inscricao_id BETWEEN current_setting('c2.ativo_id_min')::BIGINT
                         AND current_setting('c2.ativo_id_max')::BIGINT;
COMMIT;
