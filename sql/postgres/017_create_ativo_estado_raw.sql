CREATE TABLE IF NOT EXISTS raw.ativo_estado (
    id INTEGER PRIMARY KEY,
    id_pais INTEGER NOT NULL,
    id_estado INTEGER NOT NULL,
    ds_estado VARCHAR(100) NOT NULL,
    ds_estado_en VARCHAR(100) NOT NULL,
    ds_sigla VARCHAR(5) NOT NULL,
    id_situacao_cadastro INTEGER,
    _source TEXT NOT NULL,
    _extracted_at TIMESTAMPTZ NOT NULL,
    _batch_id UUID NOT NULL
);
