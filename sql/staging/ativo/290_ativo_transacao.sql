-- Grão: uma linha por transacao_id; todas as transações são mantidas.
CREATE OR REPLACE VIEW staging.ativo_transacao AS
SELECT id_transacao AS transacao_id,
       id_pedido_pagamento AS pagamento_id,
       NULLIF(BTRIM(nr_nsu), '') AS nsu,
       NULLIF(BTRIM(nr_tid), '') AS tid,
       NULLIF(BTRIM(nr_codigo_autorizacao), '') AS codigo_autorizacao,
       dt_cadastro AS data_cadastro,
       dt_cancelamento_transacao AS data_cancelamento,
       _source AS origem, _extracted_at AS extraido_em, _batch_id AS batch_id
FROM raw.ativo_transacao;
