-- Métricas técnicas de cobertura, sem filtro de testes/cancelados e sem KPI.
SELECT COUNT(*) AS total_inscricoes,
       COUNT(*) FILTER (WHERE evento_nao_mapeado) AS sem_evento,
       COUNT(*) FILTER (WHERE modalidade_ambigua) AS modalidade_ambigua,
       COUNT(*) FILTER (WHERE cliente_ambiguo) AS cliente_ambiguo
FROM staging.magento_inscricao;

SELECT COUNT(*) AS total_inscricoes,
       COUNT(*) FILTER (WHERE NOT pedido_mapeado) AS sem_pedido,
       COUNT(*) FILTER (WHERE NOT evento_mapeado) AS sem_evento,
       COUNT(*) FILTER (WHERE NOT modalidade_mapeada) AS sem_modalidade,
       COUNT(*) FILTER (WHERE NOT categoria_mapeada) AS sem_categoria,
       COUNT(*) FILTER (WHERE NOT tamanho_camiseta_mapeado) AS sem_tamanho
FROM staging.ativo_inscricao;

-- Diferencia ID ausente de ID histórico sem referência atual.
SELECT COUNT(*) FILTER (WHERE modalidade_id IS NULL) AS modalidade_sem_id,
       COUNT(*) FILTER (WHERE modalidade_id IS NOT NULL AND NOT modalidade_mapeada) AS modalidade_orfa,
       COUNT(*) FILTER (WHERE categoria_id IS NULL) AS categoria_sem_id,
       COUNT(*) FILTER (WHERE categoria_id IS NOT NULL AND NOT categoria_mapeada) AS categoria_orfa,
       COUNT(*) FILTER (WHERE tamanho_camiseta_id IS NULL) AS tamanho_sem_id,
       COUNT(*) FILTER (WHERE tamanho_camiseta_id IS NOT NULL AND NOT tamanho_camiseta_mapeado) AS tamanho_orfao
FROM staging.ativo_inscricao;
