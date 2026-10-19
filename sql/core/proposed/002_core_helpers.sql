-- PROPOSTA FASE B v1. NÃO EXECUTAR sem aprovação explícita.
-- Executar somente depois de 001_core_ddl.sql.

BEGIN;

CREATE OR REPLACE FUNCTION core.try_numeric_20_4(valor TEXT)
RETURNS NUMERIC(20,4) LANGUAGE plpgsql IMMUTABLE PARALLEL SAFE AS $$
DECLARE
    limpo TEXT;
BEGIN
    limpo := NULLIF(BTRIM(valor), '');
    IF limpo IS NULL THEN RETURN NULL; END IF;
    -- Um separador decimal, sem separadores de milhar ambíguos.
    IF limpo !~ '^[+-]?[0-9]{1,16}([,.][0-9]{1,4})?$' THEN RETURN NULL; END IF;
    RETURN REPLACE(limpo, ',', '.')::NUMERIC(20,4);
EXCEPTION WHEN numeric_value_out_of_range THEN
    RETURN NULL;
END $$;

CREATE OR REPLACE FUNCTION core.try_timestamp(valor TEXT)
RETURNS TIMESTAMP LANGUAGE plpgsql IMMUTABLE PARALLEL SAFE AS $$
DECLARE
    limpo TEXT;
BEGIN
    limpo := NULLIF(BTRIM(valor), '');
    IF limpo IS NULL THEN RETURN NULL; END IF;
    IF limpo !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}([ T][0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]{1,6})?)?$'
    THEN RETURN NULL; END IF;
    RETURN make_timestamp(
        SUBSTRING(limpo FROM 1 FOR 4)::INTEGER,
        SUBSTRING(limpo FROM 6 FOR 2)::INTEGER,
        SUBSTRING(limpo FROM 9 FOR 2)::INTEGER,
        COALESCE(NULLIF(SUBSTRING(limpo FROM 12 FOR 2), ''), '0')::INTEGER,
        COALESCE(NULLIF(SUBSTRING(limpo FROM 15 FOR 2), ''), '0')::INTEGER,
        COALESCE(NULLIF(SUBSTRING(limpo FROM 18), ''), '0')::DOUBLE PRECISION
    );
EXCEPTION WHEN datetime_field_overflow OR invalid_datetime_format OR numeric_value_out_of_range THEN
    RETURN NULL;
END $$;

CREATE OR REPLACE FUNCTION core.try_date(valor TEXT)
RETURNS DATE LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
    SELECT core.try_timestamp(valor)::DATE
$$;

-- Matriz fechada: ambos os lados precisam concordar numa família conhecida.
-- Um lado aprovado e o outro new/pending/closed/desconhecido não confirma.
-- Cancelamento explícito prevalece, mas o conflito deve gerar alerta separado.
CREATE OR REPLACE FUNCTION core.magento_status_corporativo(
    estado TEXT, status TEXT)
RETURNS TEXT LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
    WITH par AS (
        SELECT LOWER(NULLIF(BTRIM(estado), '')) AS e,
               LOWER(NULLIF(BTRIM(status), '')) AS s
    )
    SELECT CASE
        WHEN e = 'canceled' OR s = 'canceled' THEN 'CANCELADO'
        WHEN e IN ('processing','approved','complete')
         AND s IN ('processing','approved','complete') THEN 'CONFIRMADO'
        WHEN e = 'new' AND s = 'new' THEN 'NOVO'
        WHEN e IN ('new','pending') AND s IN ('new','pending') THEN 'PENDENTE'
        ELSE 'INDETERMINADO'
    END FROM par
$$;

CREATE OR REPLACE FUNCTION core.magento_pagamento_confirmado(
    estado TEXT, status TEXT)
RETURNS BOOLEAN LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
    SELECT CASE core.magento_status_corporativo(estado,status)
        WHEN 'CONFIRMADO' THEN TRUE
        WHEN 'CANCELADO' THEN FALSE
        WHEN 'PENDENTE' THEN FALSE
        WHEN 'NOVO' THEN FALSE
        ELSE NULL END
$$;

CREATE OR REPLACE FUNCTION core.magento_status_alerta(
    estado TEXT, status TEXT)
RETURNS TEXT LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
    WITH par AS (
        SELECT LOWER(NULLIF(BTRIM(estado), '')) AS e,
               LOWER(NULLIF(BTRIM(status), '')) AS s
    )
    SELECT CASE
        WHEN (e = 'canceled' AND s IS NOT NULL AND s <> 'canceled')
          OR (s = 'canceled' AND e IS NOT NULL AND e <> 'canceled')
          OR (e IN ('new','pending') AND s IN ('processing','approved','complete'))
          OR (s IN ('new','pending') AND e IN ('processing','approved','complete'))
            THEN 'STATUS_CONTRADITORIO'
        WHEN core.magento_status_corporativo(estado,status) = 'INDETERMINADO'
            THEN 'STATUS_ESPECIAL'
        ELSE NULL
    END FROM par
$$;

-- pgAdmin e futuro executor usam o mesmo contrato de parâmetros de sessão.
-- Falha fechada se um limite faltar, não for inteiro ou exceder 100 mil IDs.
CREATE OR REPLACE FUNCTION core.batch_min()
RETURNS BIGINT LANGUAGE plpgsql STABLE AS $$
DECLARE
    texto_min TEXT := current_setting('core.id_min', TRUE);
    texto_max TEXT := current_setting('core.id_max', TRUE);
    minimo BIGINT;
    maximo BIGINT;
BEGIN
    IF texto_min IS NULL OR texto_max IS NULL
       OR texto_min !~ '^[0-9]+$' OR texto_max !~ '^[0-9]+$' THEN
        RAISE EXCEPTION 'Intervalo CORE ausente ou inválido';
    END IF;
    minimo := texto_min::BIGINT;
    maximo := texto_max::BIGINT;
    IF minimo > maximo OR maximo - minimo > 100000 THEN
        RAISE EXCEPTION 'Intervalo CORE invertido ou maior que 100000 IDs';
    END IF;
    RETURN minimo;
EXCEPTION WHEN numeric_value_out_of_range THEN
    RAISE EXCEPTION 'Intervalo CORE fora do BIGINT';
END $$;

CREATE OR REPLACE FUNCTION core.batch_max()
RETURNS BIGINT LANGUAGE plpgsql STABLE AS $$
BEGIN
    PERFORM core.batch_min();
    RETURN current_setting('core.id_max')::BIGINT;
END $$;

CREATE OR REPLACE FUNCTION core.classificacao_ativo(
    classificacao_cupom TEXT, categoria TEXT, codigo_cupom TEXT,
    preco NUMERIC, tem_referencia_cupom BOOLEAN, tem_cabecalho_cupom BOOLEAN)
RETURNS TEXT LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
    SELECT CASE
        WHEN classificacao_cupom ILIKE '%grupos%'
          OR categoria ILIKE '%grupo%'
          OR categoria ILIKE '%saúde corporativa%'
          OR categoria ILIKE '%saude corporativa%'
          OR codigo_cupom ~* '^GR' THEN 'Grupos'
        WHEN tem_referencia_cupom IS TRUE AND tem_cabecalho_cupom IS NOT TRUE
            THEN NULL
        WHEN categoria ILIKE '%cortesia%'
          OR categoria ILIKE '%patrocinador%'
          OR preco = 0 THEN 'Cortesia'
        ELSE 'Site'
    END
$$;

CREATE OR REPLACE FUNCTION core.classificacao_magento(
    etiqueta_grupos BOOLEAN, etiqueta_cortesia BOOLEAN,
    codigo_cupom TEXT, valor_bruto NUMERIC)
RETURNS TEXT LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
    SELECT CASE
        WHEN etiqueta_grupos IS TRUE OR codigo_cupom ~* '^GR' THEN 'Grupos'
        WHEN etiqueta_cortesia IS TRUE OR valor_bruto = 0 THEN 'Cortesia'
        ELSE 'Site'
    END
$$;

-- Apenas token já validado fora do banco pode entrar em dim_pessoa.
-- Não criar função de hash simples para CPF: CPF tem domínio pequeno;
-- a política futura deve usar HMAC e segredo externo/serviço aprovado.
COMMIT;
