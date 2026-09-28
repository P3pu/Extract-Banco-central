CREATE TABLE IF NOT EXISTS raw.ativo_modalidade_categoria (
    id_categoria INTEGER PRIMARY KEY,
    ds_categoria VARCHAR(100) NOT NULL,
    vl_kit NUMERIC(10,2),
    data_update TIMESTAMP,
    _source TEXT NOT NULL,
    _extracted_at TIMESTAMPTZ NOT NULL,
    _batch_id UUID NOT NULL
);
