CREATE TABLE IF NOT EXISTS raw.ativo_pedido_endereco (
    id_pedido_endereco INTEGER PRIMARY KEY,
    id_pedido INTEGER NOT NULL,
    id_pedido_evento INTEGER,
    id_cidade INTEGER NOT NULL,
    ds_endereco VARCHAR(255) NOT NULL,
    ds_num VARCHAR(20) NOT NULL,
    ds_complemento VARCHAR(20) NOT NULL,
    ds_bairro VARCHAR(100) NOT NULL,
    nr_cep VARCHAR(10) NOT NULL,
    dt_cadastro TIMESTAMP NOT NULL,
    _source TEXT NOT NULL,
    _extracted_at TIMESTAMPTZ NOT NULL,
    _batch_id UUID NOT NULL
);
