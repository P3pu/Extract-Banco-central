CREATE TABLE IF NOT EXISTS raw.ativo_pedido_status (
    id_pedido_status INTEGER PRIMARY KEY,
    ds_status VARCHAR(50) NOT NULL,
    _source TEXT NOT NULL,
    _extracted_at TIMESTAMPTZ NOT NULL,
    _batch_id UUID NOT NULL
);
