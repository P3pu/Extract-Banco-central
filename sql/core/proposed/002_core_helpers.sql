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

-- Apenas token já validado fora do banco pode entrar em dim_pessoa.
-- Não criar função de hash simples para CPF: CPF tem domínio pequeno;
-- a política futura deve usar HMAC e segredo externo/serviço aprovado.
COMMIT;
