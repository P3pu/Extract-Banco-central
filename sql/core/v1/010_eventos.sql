WITH fonte AS (
    SELECT 'ativo'::text origem, evento_id::bigint evento_id_origem,
           evento_nome nome_evento, core.try_date(data_evento) data_evento,
           data_evento::text data_evento_original,
           campanha_salesforce_id sku_referencia,
           (evento_id = 22054) flag_evento_teste
    FROM staging.ativo_evento
    WHERE evento_id BETWEEN %(id_min)s AND %(id_max)s
    UNION ALL
    SELECT 'magento', evento_id::bigint, evento_nome, data_evento::date,
           data_evento::text, evento_sku, false
    FROM staging.magento_evento
    WHERE evento_id BETWEEN %(id_min)s AND %(id_max)s
)
INSERT INTO core.dim_evento
    (seed_origem, seed_evento_id, nome_evento, data_evento,
     data_evento_original, sku_referencia, flag_evento_teste,
     motivo_evento_teste)
SELECT origem, evento_id_origem, nome_evento, data_evento,
       data_evento_original, sku_referencia, flag_evento_teste,
       CASE WHEN flag_evento_teste THEN 'CURADORIA_ATIVO_22054' END
FROM fonte
ON CONFLICT (seed_origem, seed_evento_id) DO UPDATE SET
    nome_evento = EXCLUDED.nome_evento,
    data_evento = EXCLUDED.data_evento,
    data_evento_original = EXCLUDED.data_evento_original,
    sku_referencia = EXCLUDED.sku_referencia,
    flag_evento_teste = EXCLUDED.flag_evento_teste,
    motivo_evento_teste = EXCLUDED.motivo_evento_teste,
    data_atualizacao_core = clock_timestamp()
WHERE (core.dim_evento.nome_evento, core.dim_evento.data_evento,
       core.dim_evento.data_evento_original, core.dim_evento.sku_referencia,
       core.dim_evento.flag_evento_teste, core.dim_evento.motivo_evento_teste)
  IS DISTINCT FROM
      (EXCLUDED.nome_evento, EXCLUDED.data_evento,
       EXCLUDED.data_evento_original, EXCLUDED.sku_referencia,
       EXCLUDED.flag_evento_teste, EXCLUDED.motivo_evento_teste);
