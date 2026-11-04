-- Inscrição do Ativo apagada na origem (decisão 04/11/2026): a RAW guarda a linha
-- para auditoria, mas ela deixa de contar. Preenchida por
-- src/pipeline/ativo_eventos_abertos.py, sempre após confirmar pela PK na origem.
CREATE TABLE IF NOT EXISTS core.inscricao_removida_origem (
    origem TEXT NOT NULL CHECK (origem='ativo'),
    inscricao_id_origem BIGINT NOT NULL,
    detectada_em TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    batch_id UUID,
    PRIMARY KEY (origem, inscricao_id_origem)
);
