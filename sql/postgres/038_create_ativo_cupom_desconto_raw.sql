-- Cabeçalho de cupom Ativo (sa_cupom_desconto), conferido em 30/10/2026.
-- ENUM de classificação preservado como texto, inclusive valor vazio.
CREATE TABLE IF NOT EXISTS raw.ativo_cupom_desconto (
    id_cupom_desconto BIGINT PRIMARY KEY,
    en_cupom_classificacao TEXT,
    _source TEXT NOT NULL,
    _extracted_at TIMESTAMPTZ NOT NULL,
    _batch_id UUID NOT NULL
);
