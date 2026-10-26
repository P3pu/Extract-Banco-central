-- CORE V1: aplicar somente depois de proposed/001 e proposed/002.
-- A migração é preparada para homologação; nunca é chamada pelo executor RAW.
BEGIN;

ALTER TABLE core.fato_pedido
    ADD COLUMN IF NOT EXISTS pedido_elegivel BOOLEAN,
    ADD COLUMN IF NOT EXISTS pagamento_considerado BOOLEAN,
    ADD COLUMN IF NOT EXISTS motivo_status_analitico TEXT,
    ADD COLUMN IF NOT EXISTS flag_pedido_misto_temporal BOOLEAN,
    ADD COLUMN IF NOT EXISTS flag_evento_teste BOOLEAN;

ALTER TABLE core.fato_inscricao
    ADD COLUMN IF NOT EXISTS status_pendente_validacao BOOLEAN,
    ADD COLUMN IF NOT EXISTS motivo_status_analitico TEXT,
    ADD COLUMN IF NOT EXISTS participante_namespace_origem TEXT
        CHECK (participante_namespace_origem IN ('Usuario','UsuarioBalcao')),
    ADD COLUMN IF NOT EXISTS classificacao_comercial TEXT
        CHECK (classificacao_comercial IN ('GRUPOS','CORTESIA','SITE')),
    ADD COLUMN IF NOT EXISTS classificacao_incompleta BOOLEAN,
    ADD COLUMN IF NOT EXISTS valor_bruto_mais_taxa_derivado NUMERIC(20,4),
    ADD COLUMN IF NOT EXISTS data_referencia_pagamento DATE;

ALTER TABLE core.core_etl_execucao
    ADD COLUMN IF NOT EXISTS linhas_processadas BIGINT NOT NULL DEFAULT 0
        CHECK (linhas_processadas >= 0),
    ADD COLUMN IF NOT EXISTS limite_inferior BIGINT,
    ADD COLUMN IF NOT EXISTS limite_superior BIGINT;

CREATE TABLE IF NOT EXISTS core.schema_migration (
    migration_id TEXT PRIMARY KEY,
    sha256 TEXT NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    aplicada_em TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

-- Atribuição explícita por instância vendida de combo. Nenhum transformador
-- automático preenche esta tabela: requer composição e revisão humana.
CREATE TABLE IF NOT EXISTS core.combo_inscricao_atribuicao (
    inscricao_key BIGINT PRIMARY KEY REFERENCES core.fato_inscricao(inscricao_key),
    combo_key BIGINT NOT NULL REFERENCES core.dim_combo(combo_key),
    grupo_comercial_id TEXT NOT NULL CHECK (BTRIM(grupo_comercial_id)<>''),
    validado_por TEXT NOT NULL CHECK (BTRIM(validado_por)<>''),
    validado_em TIMESTAMPTZ NOT NULL,
    UNIQUE (combo_key,grupo_comercial_id,inscricao_key)
);

-- O gate de publicação continua fechado até revisão da primeira carga real,
-- invalidadores de dependências e política de acesso aos indicadores.
CREATE OR REPLACE VIEW core.fato_inscricao_indicadores_validos AS
SELECT * FROM core.fato_inscricao WHERE FALSE;

COMMIT;
