-- Somente laboratório/curadoria; não é indicador publicado.
-- Grupos comerciais precisam de atribuições aprovadas uma a uma.
BEGIN READ ONLY;
SET LOCAL statement_timeout='20s';
SET LOCAL lock_timeout='2s';
SELECT current_database(),current_setting('transaction_read_only');
WITH por_grupo AS (
    SELECT a.combo_key,a.grupo_comercial_id,c.qtd_inscricoes_previstas,
           COUNT(*) qtd_atribuida,
           BOOL_AND(f.combo_key=a.combo_key AND f.origem='ativo'
              AND f.contabiliza_inscricao IS TRUE
              AND f.valor_liquido_inscricao IS NOT NULL
              AND f.estado_derivacao='VALIDADO') integridade,
           SUM(f.valor_liquido_inscricao) soma_liquida
    FROM core.combo_inscricao_atribuicao a
    JOIN core.dim_combo c ON c.combo_key=a.combo_key
    JOIN core.fato_inscricao f ON f.inscricao_key=a.inscricao_key
    WHERE c.flag_composicao_validada IS TRUE
    GROUP BY a.combo_key,a.grupo_comercial_id,c.qtd_inscricoes_previstas
)
SELECT combo_key,grupo_comercial_id,qtd_atribuida,qtd_inscricoes_previstas,
       (qtd_atribuida=qtd_inscricoes_previstas AND integridade) completo,
       CASE WHEN qtd_atribuida=qtd_inscricoes_previstas AND integridade
            THEN soma_liquida END liquido_candidato
FROM por_grupo
ORDER BY combo_key,grupo_comercial_id LIMIT 1000;
ROLLBACK;
