CREATE TABLE IF NOT EXISTS raw.ativo_combo (
    id_combo BIGINT PRIMARY KEY,
    ds_titulo VARCHAR(60) NOT NULL,
    _source TEXT NOT NULL,
    _extracted_at TIMESTAMPTZ NOT NULL,
    _batch_id UUID NOT NULL
);
