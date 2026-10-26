INSERT INTO core.dim_combo (origem, combo_id_origem, nome_combo)
SELECT 'ativo', combo_id::text, combo_nome
FROM staging.ativo_combo
WHERE combo_id BETWEEN %(id_min)s AND %(id_max)s
ON CONFLICT (origem, combo_id_origem) DO UPDATE SET
    nome_combo = EXCLUDED.nome_combo,
    atualizado_core_em = clock_timestamp()
WHERE core.dim_combo.nome_combo IS DISTINCT FROM EXCLUDED.nome_combo;
