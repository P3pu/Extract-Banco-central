CREATE TABLE IF NOT EXISTS raw.ativo_pais (
    id_pais INTEGER PRIMARY KEY,
    ds_pais VARCHAR(50) NOT NULL,
    ds_pais_en VARCHAR(100) NOT NULL,
    ds_pais_es VARCHAR(100) NOT NULL,
    ds_sigla VARCHAR(10),
    id_continente INTEGER,
    latitude VARCHAR(50),
    longitude VARCHAR(50),
    id_situacao_cadastro INTEGER,
    _source TEXT NOT NULL,
    _extracted_at TIMESTAMPTZ NOT NULL,
    _batch_id UUID NOT NULL
);
