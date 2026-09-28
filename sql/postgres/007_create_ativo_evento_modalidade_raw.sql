-- data_update TEXT conserva os timestamps zero da origem.
CREATE TABLE IF NOT EXISTS raw.ativo_evento_modalidade (
    id_modalidade INTEGER PRIMARY KEY,
    nm_modalidade VARCHAR(100) NOT NULL,
    ds_horario VARCHAR(150),
    nr_ordem INTEGER,
    data_update TEXT,
    _source TEXT NOT NULL,
    _extracted_at TIMESTAMPTZ NOT NULL,
    _batch_id UUID NOT NULL
);
