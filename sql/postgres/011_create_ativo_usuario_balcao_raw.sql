-- CHAR da origem usa VARCHAR para preservar strings vazias sem padding.
-- dt_nascimento/dt_cadastro têm datas zero e permanecem texto literal.
CREATE TABLE IF NOT EXISTS raw.ativo_usuario_balcao (
    id_usuario BIGINT PRIMARY KEY,
    ds_nome VARCHAR(100) NOT NULL,
    fl_sexo VARCHAR(1) NOT NULL,
    nr_documento VARCHAR(45) NOT NULL,
    dt_nascimento TEXT NOT NULL,
    ds_email VARCHAR(150) NOT NULL,
    ds_telefone VARCHAR(20) NOT NULL,
    ds_celular VARCHAR(20) NOT NULL,
    pelotao VARCHAR(45) NOT NULL,
    dt_cadastro TEXT,
    _source TEXT NOT NULL,
    _extracted_at TIMESTAMPTZ NOT NULL,
    _batch_id UUID NOT NULL
);
