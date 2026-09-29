CREATE TABLE IF NOT EXISTS raw.ativo_cupom_desconto_item (
    id_cupom_desconto_item BIGINT PRIMARY KEY,
    nr_cupom VARCHAR(45) NOT NULL,
    fl_usado VARCHAR(1) NOT NULL,
    ds_ip VARCHAR(15),
    dt_sistema TEXT NOT NULL,
    dt_uso TEXT,
    id_cupom_desconto BIGINT NOT NULL,
    id_evento INTEGER,
    fl_reserva BIGINT,
    _source TEXT NOT NULL,
    _extracted_at TIMESTAMPTZ NOT NULL,
    _batch_id UUID NOT NULL
);
