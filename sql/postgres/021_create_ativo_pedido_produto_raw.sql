CREATE TABLE IF NOT EXISTS raw.ativo_pedido_produto (
    id_pedido_produto INTEGER PRIMARY KEY,
    id_pedido INTEGER NOT NULL,
    id_produto INTEGER NOT NULL,
    nr_preco NUMERIC(10,2) NOT NULL,
    nr_quantidade INTEGER NOT NULL,
    _source TEXT NOT NULL,
    _extracted_at TIMESTAMPTZ NOT NULL,
    _batch_id UUID NOT NULL
);
