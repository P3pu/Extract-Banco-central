CREATE TABLE IF NOT EXISTS raw.ativo_tamanho_camiseta (
    id_tamanho_camiseta INTEGER PRIMARY KEY,
    ds_tamanho VARCHAR(50) NOT NULL,
    nr_peso NUMERIC(10,2),
    vl_valor NUMERIC(10,2),
    id_situacao_cadastro INTEGER NOT NULL,
    disponivel_atleta INTEGER NOT NULL,
    id_pais_origem INTEGER,
    _source TEXT NOT NULL,
    _extracted_at TIMESTAMPTZ NOT NULL,
    _batch_id UUID NOT NULL
);
