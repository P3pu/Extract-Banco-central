CREATE TABLE IF NOT EXISTS raw.ativo_produto (
    id_produto BIGINT PRIMARY KEY,
    ds_titulo VARCHAR(250) NOT NULL,
    data_update TIMESTAMP,
    _source TEXT NOT NULL,
    _extracted_at TIMESTAMPTZ NOT NULL,
    _batch_id UUID NOT NULL
);
