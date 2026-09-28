CREATE TABLE IF NOT EXISTS raw.ativo_formas_pagamento (
    id_formas_pagamento INTEGER PRIMARY KEY,
    ds_descricao VARCHAR(255),
    _source TEXT NOT NULL,
    _extracted_at TIMESTAMPTZ NOT NULL,
    _batch_id UUID NOT NULL
);
