-- Tipos observados em sa_pedido no Ativo em 2026-09-28.
-- Datas zero não cabem em TIMESTAMP PostgreSQL; preservar em TEXT.
CREATE TABLE IF NOT EXISTS raw.ativo_pedido (
    id_pedido INTEGER PRIMARY KEY,
    id_pedido_status INTEGER NOT NULL,
    id_combo BIGINT,
    id_cupom_desconto_item INTEGER,
    ds_cod VARCHAR(25),
    dt_pedido TEXT NOT NULL,
    dt_alteracao TEXT,
    fl_local_inscricao INTEGER,
    fl_delivery CHAR(1),
    fl_mobile INTEGER,
    fl_assinante INTEGER,
    fl_evento_da_casa INTEGER,
    nr_taxa NUMERIC(10,2),
    nr_delivery NUMERIC(10,2),
    nr_desconto NUMERIC(10,2) NOT NULL,
    tp_entregakit INTEGER,
    nm_camiseta VARCHAR(150),
    ds_campo_apolo VARCHAR(100),
    ds_obs VARCHAR(150),
    _source TEXT NOT NULL,
    _extracted_at TIMESTAMPTZ NOT NULL,
    _batch_id UUID NOT NULL
);
