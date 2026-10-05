-- Grão: uma linha por pagamento_id; nunca selecionar só o último pagamento.
CREATE OR REPLACE VIEW staging.ativo_pagamento AS
SELECT p.id_pedido_pagamento AS pagamento_id,
       p.id_pedido AS pedido_id,
       p.id_formas_pagamento AS forma_pagamento_id,
       f.forma_pagamento,
       NULLIF(BTRIM(p.fl_status), '') AS status_pagamento,
       p.dt_registro AS data_registro,
       p.dt_pagamento AS data_pagamento,
       p._source AS origem, p._extracted_at AS extraido_em, p._batch_id AS batch_id
FROM raw.ativo_pedido_pagamento p
LEFT JOIN staging.ativo_forma_pagamento f
  ON f.forma_pagamento_id = p.id_formas_pagamento;
