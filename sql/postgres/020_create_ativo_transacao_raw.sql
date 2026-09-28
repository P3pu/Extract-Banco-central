CREATE TABLE IF NOT EXISTS raw.ativo_transacao (
    id_transacao INTEGER PRIMARY KEY,
    id_pedido_pagamento INTEGER NOT NULL,
    nr_nsu VARCHAR(255),
    nr_tid VARCHAR(255),
    nr_codigo_autorizacao VARCHAR(255),
    dt_cadastro TIMESTAMP NOT NULL,
    dt_cancelamento_transacao TIMESTAMP,
    _source TEXT NOT NULL,
    _extracted_at TIMESTAMPTZ NOT NULL,
    _batch_id UUID NOT NULL
);
