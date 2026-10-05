-- Grão: uma linha por forma_pagamento_id.
CREATE OR REPLACE VIEW staging.ativo_forma_pagamento AS
SELECT id_formas_pagamento AS forma_pagamento_id,
       NULLIF(BTRIM(ds_descricao), '') AS forma_pagamento,
       _source AS origem, _extracted_at AS extraido_em, _batch_id AS batch_id
FROM raw.ativo_formas_pagamento;
