CREATE TABLE IF NOT EXISTS raw.ativo_pedido_pagamento (
    id_pedido_pagamento INTEGER PRIMARY KEY,
    id_pedido INTEGER NOT NULL,
    id_formas_pagamento INTEGER NOT NULL,
    fl_status VARCHAR(10) NOT NULL,
    dt_registro TIMESTAMP NOT NULL,
    dt_pagamento TEXT,
    _source TEXT NOT NULL,
    _extracted_at TIMESTAMPTZ NOT NULL,
    _batch_id UUID NOT NULL
);
