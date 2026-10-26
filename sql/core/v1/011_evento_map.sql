INSERT INTO core.evento_source_map
    (origem, evento_id_origem, evento_key, sku_origem, criterio_vinculo)
SELECT d.seed_origem, d.seed_evento_id, d.evento_key,
       d.sku_referencia, 'ORIGEM'
FROM core.dim_evento d
WHERE d.seed_evento_id BETWEEN %(id_min)s AND %(id_max)s
ON CONFLICT (origem, evento_id_origem) DO UPDATE SET
    sku_origem = EXCLUDED.sku_origem
WHERE core.evento_source_map.criterio_vinculo = 'ORIGEM'
  AND core.evento_source_map.sku_origem IS DISTINCT FROM EXCLUDED.sku_origem;
