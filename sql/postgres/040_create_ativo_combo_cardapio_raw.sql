-- Cardápio dos combos Ativo (sa_combo_evento_categoria), conferido em 30/10/2026.
CREATE TABLE IF NOT EXISTS raw.ativo_combo_cardapio (
    id_combo_evento_categoria BIGINT PRIMARY KEY,
    ds_categoria VARCHAR(60) NOT NULL,
    id_evento INTEGER NOT NULL,
    id_combo INTEGER NOT NULL,
    fl_obrigatorio INTEGER,
    _source TEXT NOT NULL,
    _extracted_at TIMESTAMPTZ NOT NULL,
    _batch_id UUID NOT NULL
);
